"""POST /telephony/plivo/answer - the real Answer URL webhook: PLIVOXML
generation, the real activation gate (WOW must never activate itself),
and real X-Plivo-Signature-V3 validation. A real (temp file-backed)
SQLite database backs the User lookup - not mocked; see
test_telephony_plivo.py's docstring for why file-backed, not `:memory:`.
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.api.routes import telephony_plivo
from app.config import get_settings
from app.db.base import Base
from app.models.user import User
from app.providers.telephony.plivo_signature import compute_v3_signature

DEMO_USER_ID = get_settings().demo_user_id


@pytest.fixture(autouse=True)
def _local_unsigned_webhooks(monkeypatch):
    """Most tests here exercise XML/activation behavior, not signatures -
    they run in the explicit local-only unsigned mode (the webhook now FAILS
    CLOSED without it). Signature behavior is covered below and in
    test_plivo_security.py."""
    monkeypatch.setenv("PLIVO_ALLOW_UNSIGNED_WEBHOOKS", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _make_client(tmp_path, *, call_assistant_enabled: bool = True, active_until=None):
    db_path = tmp_path / "test_plivo_answer.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            User(
                id=uuid.UUID(DEMO_USER_ID),
                display_name="Aniket",
                phone_number="+910000000000",
                call_assistant_enabled=call_assistant_enabled,
                active_until=active_until,
            )
        )
        await session.commit()

    async def _get_db():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(telephony_plivo.router)
    app.dependency_overrides[get_db] = _get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), engine


async def test_answer_webhook_returns_plivo_xml_with_a_bidirectional_stream(tmp_path):
    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
    async with client:
        resp = await client.post(
            "/telephony/plivo/answer",
            data={"CallUUID": "abc-123", "From": "+919876543210", "To": "+911234567890"},
        )
    await engine.dispose()

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/xml")
    body = resp.text
    assert "<Stream" in body
    assert 'bidirectional="true"' in body
    assert 'contentType="audio/x-mulaw;rate=8000"' in body
    assert "/telephony/plivo/stream" in body


async def test_answer_webhook_hangs_up_when_wow_is_not_activated(tmp_path):
    """WOW must never activate itself - see the module's own docstring and
    the product spec this implements."""
    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=False)
    async with client:
        resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "abc-123"})
    await engine.dispose()

    assert resp.status_code == 200
    assert "<Hangup" in resp.text
    assert "<Stream" not in resp.text


# Note: the "activation window has actually expired" path (apply_activation_expiry's
# own datetime.now(timezone.utc) >= active_until comparison) is deliberately
# NOT re-tested here against SQLite - SQLite has no native timezone-aware
# datetime type and always round-trips one as naive, which breaks that
# comparison regardless of what's stored, for reasons unrelated to the
# real logic. That exact comparison is already proven against a real
# Postgres instance (the actual production database) in
# test_profile_verification.py's test_expired_activation_auto_deactivates_on_next_real_read
# (TEST_DATABASE_URL-gated, same as every other real-Postgres test in this
# suite). What IS tested here, safely, is this route's own new behavior:
# an unactivated (or nonexistent) user hangs up rather than answering.


async def test_answer_webhook_hangs_up_when_the_demo_user_does_not_exist(tmp_path):
    """No onboarded user at all is the same "not activated" outcome, not a crash."""
    get_settings.cache_clear()
    db_path = tmp_path / "test_plivo_answer_no_user.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _get_db():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(telephony_plivo.router)
    app.dependency_overrides[get_db] = _get_db
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async with client:
        resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "abc-123"})
    await engine.dispose()

    assert resp.status_code == 200
    assert "<Hangup" in resp.text


async def test_answer_webhook_uses_wss_when_public_base_url_is_https(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.trycloudflare.com")
    monkeypatch.setenv("PLIVO_AUTH_TOKEN", "real-secret-token")
    get_settings.cache_clear()
    try:
        client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
        params = {"CallUUID": "abc-123"}
        # Plivo signs the PUBLIC url it called, not uvicorn's internal one.
        signature = compute_v3_signature(
            "https://example.trycloudflare.com/telephony/plivo/answer", params, "n1", "real-secret-token"
        )
        async with client:
            resp = await client.post(
                "/telephony/plivo/answer",
                data=params,
                headers={"X-Plivo-Signature-V3": signature, "X-Plivo-Signature-V3-Nonce": "n1"},
            )
        await engine.dispose()
        assert resp.status_code == 200
        assert "wss://example.trycloudflare.com/telephony/plivo/stream?token=" in resp.text
    finally:
        monkeypatch.setenv("PUBLIC_BASE_URL", "")
        get_settings.cache_clear()


async def test_answer_webhook_derives_ws_scheme_from_the_request_when_no_public_base_url_set(tmp_path):
    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
    async with client:
        resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "abc-123"})
    await engine.dispose()
    # httpx's ASGITransport test requests are plain http - the fallback
    # path must reflect that honestly (ws://) rather than assuming https.
    assert "ws://test/telephony/plivo/stream" in resp.text


async def test_answer_webhook_hangs_up_without_a_call_uuid(tmp_path):
    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
    async with client:
        resp = await client.post("/telephony/plivo/answer", data={})
    await engine.dispose()

    assert resp.status_code == 200
    assert "<Hangup" in resp.text
    assert "<Stream" not in resp.text


# --- Signature validation ---


async def test_answer_webhook_rejects_an_invalid_signature_when_auth_token_is_configured(
    tmp_path, monkeypatch
):
    get_settings.cache_clear()
    monkeypatch.setenv("PLIVO_AUTH_TOKEN", "real-secret-token")
    get_settings.cache_clear()
    try:
        client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
        async with client:
            resp = await client.post(
                "/telephony/plivo/answer",
                data={"CallUUID": "abc-123"},
                headers={
                    "X-Plivo-Signature-V3": "not-the-real-signature",
                    "X-Plivo-Signature-V3-Nonce": "some-nonce",
                },
            )
        await engine.dispose()
        assert resp.status_code == 403
    finally:
        monkeypatch.setenv("PLIVO_AUTH_TOKEN", "")
        get_settings.cache_clear()


async def test_answer_webhook_rejects_missing_signature_headers_when_auth_token_is_configured(
    tmp_path, monkeypatch
):
    get_settings.cache_clear()
    monkeypatch.setenv("PLIVO_AUTH_TOKEN", "real-secret-token")
    get_settings.cache_clear()
    try:
        client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
        async with client:
            resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "abc-123"})
        await engine.dispose()
        assert resp.status_code == 403
    finally:
        monkeypatch.setenv("PLIVO_AUTH_TOKEN", "")
        get_settings.cache_clear()


async def test_answer_webhook_accepts_a_real_valid_signature(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("PLIVO_AUTH_TOKEN", "real-secret-token")
    get_settings.cache_clear()
    try:
        client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
        params = {"CallUUID": "abc-123"}
        url = "http://test/telephony/plivo/answer"
        nonce = "test-nonce"
        signature = compute_v3_signature(url, params, nonce, "real-secret-token")

        async with client:
            resp = await client.post(
                "/telephony/plivo/answer",
                data=params,
                headers={"X-Plivo-Signature-V3": signature, "X-Plivo-Signature-V3-Nonce": nonce},
            )
        await engine.dispose()
        assert resp.status_code == 200
        assert "<Stream" in resp.text
    finally:
        monkeypatch.setenv("PLIVO_AUTH_TOKEN", "")
        get_settings.cache_clear()


async def test_answer_webhook_unsigned_local_mode_warns_loudly(tmp_path, caplog):
    """PLIVO_ALLOW_UNSIGNED_WEBHOOKS (local-only, no PUBLIC_BASE_URL) lets a
    request through without a token - but never silently."""
    import logging

    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
    with caplog.at_level(logging.WARNING, logger="app.api.routes.telephony_plivo"):
        async with client:
            resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "abc-123"})
    await engine.dispose()

    assert resp.status_code == 200
    assert any("UNSIGNED webhook" in r.getMessage() for r in caplog.records)


async def test_answer_webhook_fails_closed_without_an_auth_token_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("PLIVO_ALLOW_UNSIGNED_WEBHOOKS", raising=False)
    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
    async with client:
        resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "abc-123"})
    await engine.dispose()
    assert resp.status_code == 503
    assert "<Stream" not in resp.text


# --- Phase 1: session/call correlation, XML validity, secrets ---


def _token_from(xml_text: str) -> str:
    import re
    from xml.etree import ElementTree

    root = ElementTree.fromstring(xml_text)  # also proves the XML is well-formed
    stream = root.find("Stream")
    assert stream is not None
    match = re.search(r"[?&]token=([A-Za-z0-9_\-]+)$", stream.text)
    assert match, stream.text
    return match.group(1)


async def test_answer_mints_a_stream_token_bound_to_this_calls_uuid(tmp_path):
    from app.providers.telephony.stream_tokens import get_stream_token_store

    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
    async with client:
        resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "uuid-777"})
    await engine.dispose()

    token = _token_from(resp.text)
    assert get_stream_token_store().consume(token) == "uuid-777"


async def test_each_call_gets_a_distinct_token(tmp_path):
    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
    async with client:
        a = await client.post("/telephony/plivo/answer", data={"CallUUID": "u1"})
        b = await client.post("/telephony/plivo/answer", data={"CallUUID": "u2"})
    await engine.dispose()
    assert _token_from(a.text) != _token_from(b.text)


async def test_no_token_is_minted_when_wow_is_off(tmp_path):
    from app.providers.telephony.stream_tokens import get_stream_token_store

    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=False)
    async with client:
        resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "u1"})
    await engine.dispose()
    assert "<Hangup" in resp.text
    assert get_stream_token_store().pending_count() == 0


async def test_no_token_is_minted_for_a_bad_signature(tmp_path, monkeypatch):
    from app.providers.telephony.stream_tokens import get_stream_token_store

    monkeypatch.setenv("PLIVO_AUTH_TOKEN", "real-secret-token")
    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
    async with client:
        resp = await client.post(
            "/telephony/plivo/answer",
            data={"CallUUID": "u1"},
            headers={"X-Plivo-Signature-V3": "bad", "X-Plivo-Signature-V3-Nonce": "n"},
        )
    await engine.dispose()
    assert resp.status_code == 403
    assert get_stream_token_store().pending_count() == 0


async def test_signature_covers_the_post_params_so_a_tampered_call_uuid_is_rejected(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PLIVO_AUTH_TOKEN", "real-secret-token")
    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
    sig = compute_v3_signature(
        "http://test/telephony/plivo/answer", {"CallUUID": "original"}, "n", "real-secret-token"
    )
    async with client:
        resp = await client.post(
            "/telephony/plivo/answer",
            data={"CallUUID": "attacker-chosen"},
            headers={"X-Plivo-Signature-V3": sig, "X-Plivo-Signature-V3-Nonce": "n"},
        )
    await engine.dispose()
    assert resp.status_code == 403


async def test_response_and_logs_never_contain_the_plivo_auth_token(tmp_path, monkeypatch, caplog):
    import logging

    secret = "super-secret-auth-token-value"
    monkeypatch.setenv("PLIVO_AUTH_TOKEN", secret)
    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
    sig = compute_v3_signature("http://test/telephony/plivo/answer", {"CallUUID": "u"}, "n", secret)
    with caplog.at_level(logging.DEBUG):
        async with client:
            ok = await client.post(
                "/telephony/plivo/answer",
                data={"CallUUID": "u"},
                headers={"X-Plivo-Signature-V3": sig, "X-Plivo-Signature-V3-Nonce": "n"},
            )
            bad = await client.post(
                "/telephony/plivo/answer",
                data={"CallUUID": "u"},
                headers={"X-Plivo-Signature-V3": "x", "X-Plivo-Signature-V3-Nonce": "n"},
            )
    await engine.dispose()
    assert secret not in ok.text and secret not in bad.text and secret not in caplog.text
    # the one-time stream token is likewise never logged
    assert _token_from(ok.text) not in caplog.text


async def test_answer_hangs_up_instead_of_500_when_the_user_lookup_fails(tmp_path):
    from app.providers.telephony.stream_tokens import get_stream_token_store

    get_settings.cache_clear()

    class _BrokenSession:
        async def execute(self, *_a, **_k):
            raise RuntimeError("db down")

    async def _broken_db():
        yield _BrokenSession()

    app = FastAPI()
    app.include_router(telephony_plivo.router)
    app.dependency_overrides[get_db] = _broken_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "u"})
    assert resp.status_code == 200
    assert "<Hangup" in resp.text and "<Stream" not in resp.text
    assert get_stream_token_store().pending_count() == 0


async def test_answer_hangs_up_when_the_concurrent_stream_cap_is_reached(tmp_path, monkeypatch):
    monkeypatch.setenv("PLIVO_MAX_CONCURRENT_STREAMS", "0")
    get_settings.cache_clear()
    client, engine = await _make_client(tmp_path, call_assistant_enabled=True)
    async with client:
        resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "u"})
    await engine.dispose()
    assert "<Hangup" in resp.text and "<Stream" not in resp.text


async def test_answer_hangs_up_once_the_activation_window_has_expired(tmp_path):
    from datetime import datetime, timedelta, timezone

    from app.providers.telephony.stream_tokens import get_stream_token_store

    get_settings.cache_clear()
    client, engine = await _make_client(
        tmp_path,
        call_assistant_enabled=True,
        active_until=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    async with client:
        resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "u"})
    await engine.dispose()
    assert "<Hangup" in resp.text and "<Stream" not in resp.text
    assert get_stream_token_store().pending_count() == 0


async def test_answer_still_answers_inside_an_unexpired_window(tmp_path):
    from datetime import datetime, timedelta, timezone

    get_settings.cache_clear()
    client, engine = await _make_client(
        tmp_path,
        call_assistant_enabled=True,
        active_until=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    async with client:
        resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "u"})
    await engine.dispose()
    assert "<Stream" in resp.text
