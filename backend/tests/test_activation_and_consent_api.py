"""WOW activation (OFF by default; exactly 15m / 1h / 5h / until_stop / off),
lazy expiry, and the training-data-consent field - against the real routes
with a real (SQLite) User table. The Postgres-only tz-aware expiry round
trip is covered by test_profile_verification.py (TEST_DATABASE_URL-gated)."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.api.routes.users import apply_activation_expiry
from app.config import get_settings
from app.db.base import Base
from app.main import app
from app.models.user import User


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("API_ACCESS_KEY", "")
    get_settings.cache_clear()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'a.db'}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.factory = factory  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    await engine.dispose()


async def _new_user(client) -> str:
    uid = uuid.uuid4()
    async with client.factory() as s:
        s.add(User(id=uid, display_name="T", phone_number="+910000000000"))
        await s.commit()
    return str(uid)


def _minutes_from_now(iso: str) -> float:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - datetime.now(timezone.utc)).total_seconds() / 60


async def test_wow_is_off_by_default_for_a_new_user(client):
    uid = await _new_user(client)
    body = (await client.get(f"/users/{uid}")).json()
    assert body["call_assistant_enabled"] is False
    assert body["active_until"] is None
    assert body["training_data_consent"] is False  # consent also defaults to OFF


@pytest.mark.parametrize("duration,minutes", [("15m", 15), ("1h", 60), ("5h", 300)])
async def test_timed_activation_sets_the_exact_expiry(client, duration, minutes):
    uid = await _new_user(client)
    body = (await client.post(f"/users/{uid}/activation", json={"duration": duration})).json()
    assert body["call_assistant_enabled"] is True
    assert abs(_minutes_from_now(body["active_until"]) - minutes) < 0.5


async def test_until_stop_has_no_expiry_and_off_clears_everything(client):
    uid = await _new_user(client)
    on = (await client.post(f"/users/{uid}/activation", json={"duration": "until_stop"})).json()
    assert on["call_assistant_enabled"] is True and on["active_until"] is None
    off = (await client.post(f"/users/{uid}/activation", json={"duration": "off"})).json()
    assert off["call_assistant_enabled"] is False and off["active_until"] is None


@pytest.mark.parametrize("bad", ["2h", "30m", "forever", "", "15M"])
async def test_only_the_four_documented_durations_are_accepted(client, bad):
    uid = await _new_user(client)
    resp = await client.post(f"/users/{uid}/activation", json={"duration": bad})
    assert resp.status_code == 422
    assert (await client.get(f"/users/{uid}")).json()["call_assistant_enabled"] is False


async def test_activation_of_an_unknown_user_is_404_not_a_create(client):
    resp = await client.post(f"/users/{uuid.uuid4()}/activation", json={"duration": "1h"})
    assert resp.status_code == 404


async def test_activation_cannot_be_smuggled_in_through_profile_patch(client):
    uid = await _new_user(client)
    await client.patch(f"/users/{uid}", json={"call_assistant_enabled": True, "active_until": None})
    assert (await client.get(f"/users/{uid}")).json()["call_assistant_enabled"] is False


async def test_training_data_consent_round_trips_via_profile_update(client):
    uid = await _new_user(client)
    resp = await client.patch(f"/users/{uid}", json={"training_data_consent": True})
    assert resp.status_code == 200 and resp.json()["training_data_consent"] is True
    resp = await client.patch(f"/users/{uid}", json={"training_data_consent": False})
    assert resp.json()["training_data_consent"] is False


class _FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1

    async def refresh(self, _):
        pass


async def test_lazy_expiry_turns_wow_off_once_the_window_has_passed():
    user = SimpleNamespace(
        call_assistant_enabled=True, active_until=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    session = _FakeSession()
    await apply_activation_expiry(user, session)
    assert user.call_assistant_enabled is False
    assert user.active_until is None
    assert session.commits == 1


async def test_lazy_expiry_leaves_an_unexpired_or_open_ended_activation_alone():
    for until in (datetime.now(timezone.utc) + timedelta(minutes=5), None):
        user = SimpleNamespace(call_assistant_enabled=True, active_until=until)
        session = _FakeSession()
        await apply_activation_expiry(user, session)
        assert user.call_assistant_enabled is True
        assert session.commits == 0
