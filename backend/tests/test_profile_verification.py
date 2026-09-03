"""Phase 6 Part C - real profile edit (18+ enforcement, verification-flag
reset) and real mobile/email verification (VerificationService + the
/users/{id}/verify/{channel}/... routes), against a real Postgres + pgvector
instance. Requires TEST_DATABASE_URL - skipped automatically otherwise.
"""

import os
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_db, get_verification_service
from app.api.routes import users, verification
from app.config import get_settings
from app.db.base import Base
from app.models.user import User
from app.models.verification_code import VerificationChannel
from app.providers.otp.logging_provider import LoggingOtpDeliveryProvider
from app.services.verification_service import (
    IncorrectCodeError,
    TooManyAttemptsError,
    VerificationService,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set; skipping DB integration"
)


@pytest.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _verification_service(session) -> VerificationService:
    settings = get_settings()
    return VerificationService(
        session,
        LoggingOtpDeliveryProvider(),
        code_ttl_seconds=settings.otp_code_ttl_seconds,
        max_attempts=settings.otp_max_attempts,
        expose_dev_code=True,
    )


async def test_profile_incomplete_until_verified_then_complete(session):
    user = User(display_name="Aniket", phone_number="+10000000010", email="a@example.com")
    session.add(user)
    await session.flush()
    await session.commit()

    assert user.profile_complete is False  # no DOB, not verified yet

    user.date_of_birth = date.today().replace(year=date.today().year - 25)
    await session.commit()
    assert user.profile_complete is False  # still not verified

    service = _verification_service(session)
    await service.confirm_code(
        user_id=str(user.id),
        channel=VerificationChannel.MOBILE,
        code=await service.request_code(user_id=str(user.id), channel=VerificationChannel.MOBILE),
    )
    await service.confirm_code(
        user_id=str(user.id),
        channel=VerificationChannel.EMAIL,
        code=await service.request_code(user_id=str(user.id), channel=VerificationChannel.EMAIL),
    )
    await session.commit()
    await session.refresh(user)

    assert user.mobile_verified is True
    assert user.email_verified is True
    assert user.profile_complete is True


async def test_under_18_is_rejected(session):
    user = User(display_name="Minor", phone_number="+10000000011")
    session.add(user)
    await session.flush()
    await session.commit()

    user.date_of_birth = date.today().replace(year=date.today().year - 16)
    assert user.is_adult is False
    assert user.profile_complete is False


async def test_wrong_code_does_not_verify_and_is_attempt_limited(session):
    user = User(display_name="Aniket", phone_number="+10000000012")
    session.add(user)
    await session.flush()
    await session.commit()

    settings = get_settings()
    service = VerificationService(
        session,
        LoggingOtpDeliveryProvider(),
        code_ttl_seconds=settings.otp_code_ttl_seconds,
        max_attempts=2,
        expose_dev_code=True,
    )
    real_code = await service.request_code(user_id=str(user.id), channel=VerificationChannel.MOBILE)
    wrong_code = "000000" if real_code != "000000" else "111111"

    with pytest.raises(IncorrectCodeError):
        await service.confirm_code(
            user_id=str(user.id), channel=VerificationChannel.MOBILE, code=wrong_code
        )
    with pytest.raises(IncorrectCodeError):
        await service.confirm_code(
            user_id=str(user.id), channel=VerificationChannel.MOBILE, code=wrong_code
        )
    # Third attempt (2 wrong already made, max_attempts=2) is attempt-limited,
    # even though the code itself is still technically unexpired.
    with pytest.raises(TooManyAttemptsError):
        await service.confirm_code(
            user_id=str(user.id), channel=VerificationChannel.MOBILE, code=real_code
        )
    await session.commit()
    await session.refresh(user)
    assert user.mobile_verified is False


async def test_expired_code_is_rejected(session):
    user = User(display_name="Aniket", phone_number="+10000000013")
    session.add(user)
    await session.flush()
    await session.commit()

    settings = get_settings()
    service = VerificationService(
        session,
        LoggingOtpDeliveryProvider(),
        code_ttl_seconds=-1,  # expires immediately
        max_attempts=settings.otp_max_attempts,
        expose_dev_code=True,
    )
    code = await service.request_code(user_id=str(user.id), channel=VerificationChannel.MOBILE)
    from app.services.verification_service import CodeExpiredOrMissingError

    with pytest.raises(CodeExpiredOrMissingError):
        await service.confirm_code(
            user_id=str(user.id), channel=VerificationChannel.MOBILE, code=code
        )


async def test_editing_phone_number_resets_mobile_verified_via_real_route(session):
    user = User(display_name="Aniket", phone_number="+10000000014", email="a2@example.com")
    session.add(user)
    await session.flush()
    await session.commit()

    service = _verification_service(session)
    code = await service.request_code(user_id=str(user.id), channel=VerificationChannel.MOBILE)
    await service.confirm_code(user_id=str(user.id), channel=VerificationChannel.MOBILE, code=code)
    await session.commit()
    await session.refresh(user)
    assert user.mobile_verified is True

    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[get_db] = lambda: session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/users/{user.id}", json={"phone_number": "+19999999999"}
        )

    assert response.status_code == 200
    assert response.json()["mobile_verified"] is False


async def test_under_18_rejected_via_real_route(session):
    user = User(display_name="Aniket", phone_number="+10000000015")
    session.add(user)
    await session.flush()
    await session.commit()

    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[get_db] = lambda: session

    minor_dob = date.today().replace(year=date.today().year - 17).isoformat()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/users/{user.id}", json={"date_of_birth": minor_dob}
        )

    assert response.status_code == 400
    assert "18" in response.json()["detail"]


async def test_verification_routes_full_round_trip(session):
    user = User(display_name="Aniket", phone_number="+10000000016", email="a3@example.com")
    session.add(user)
    await session.flush()
    await session.commit()

    app = FastAPI()
    app.include_router(verification.router)

    async def _get_verification_service():
        settings = get_settings()
        yield VerificationService(
            session,
            LoggingOtpDeliveryProvider(),
            code_ttl_seconds=settings.otp_code_ttl_seconds,
            max_attempts=settings.otp_max_attempts,
            expose_dev_code=True,
        )
        await session.commit()

    app.dependency_overrides[get_verification_service] = _get_verification_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        request_resp = await client.post(f"/users/{user.id}/verify/email/request")
        assert request_resp.status_code == 200
        dev_code = request_resp.json()["dev_code"]
        assert dev_code is not None

        confirm_resp = await client.post(
            f"/users/{user.id}/verify/email/confirm", json={"code": dev_code}
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["verified"] is True

    await session.refresh(user)
    assert user.email_verified is True


async def test_activation_endpoint_sets_real_expiry_and_off_clears_it(session):
    user = User(display_name="Aniket", phone_number="+10000000017")
    session.add(user)
    await session.flush()
    await session.commit()

    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[get_db] = lambda: session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/users/{user.id}/activation", json={"duration": "15m"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["call_assistant_enabled"] is True
        assert body["active_until"] is not None
        assert 0 < body["active_seconds_remaining"] <= 15 * 60

        resp = await client.post(f"/users/{user.id}/activation", json={"duration": "until_stop"})
        body = resp.json()
        assert body["call_assistant_enabled"] is True
        assert body["active_until"] is None
        assert body["active_seconds_remaining"] is None

        resp = await client.post(f"/users/{user.id}/activation", json={"duration": "off"})
        body = resp.json()
        assert body["call_assistant_enabled"] is False
        assert body["active_until"] is None


async def test_expired_activation_auto_deactivates_on_next_real_read(session):
    user = User(display_name="Aniket", phone_number="+10000000018")
    session.add(user)
    await session.flush()
    user.call_assistant_enabled = True
    user.active_until = datetime.now(timezone.utc) - timedelta(seconds=5)  # already expired
    await session.commit()

    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[get_db] = lambda: session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/users/{user.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["call_assistant_enabled"] is False
    assert body["active_until"] is None

    await session.refresh(user)
    assert user.call_assistant_enabled is False  # persisted, not just reported
