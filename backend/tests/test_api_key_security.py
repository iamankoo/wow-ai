"""Phase 1 API security boundary: X-WOW-API-Key (app/security.py), startup
fail-closed config, storage-time redaction, and pipeline per-turn
resilience. Single-tenant gate - NOT per-user auth (see docs/SECURITY.md)."""

import logging
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.config import Settings, get_settings
from app.db.base import Base
from app.main import app
from app.models.user import User
from app.security import API_KEY_HEADER, validate_security_config

KEY = "test-access-key-123"
SOME_ID = "00000000-0000-0000-0000-0000000000aa"

# (method, path) of routes that read or modify user/call state or burn
# compute - every one must be unreachable without the key.
PROTECTED = [
    ("GET", f"/users/{SOME_ID}"),
    ("POST", f"/users/{SOME_ID}/activation"),
    ("PATCH", f"/users/{SOME_ID}"),
    ("POST", "/users"),
    ("GET", f"/users/{SOME_ID}/calls"),
    ("GET", f"/users/{SOME_ID}/calls/today-summary"),
    ("GET", f"/calls/{SOME_ID}"),
    ("POST", "/brain/command"),
    ("POST", "/brain/voice-command"),
    ("GET", "/contacts"),
    ("POST", "/contacts"),
    ("GET", "/memories"),
    ("POST", "/memories"),
    ("POST", "/feedback"),
    ("GET", "/feedback/export"),
    ("PUT", "/feedback/consent"),
    ("DELETE", "/feedback"),
    ("POST", f"/users/{SOME_ID}/verify/mobile/request"),
]


@pytest.fixture
async def client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'k.db'}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    monkeypatch.setenv("API_ACCESS_KEY", KEY)
    get_settings.cache_clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    await engine.dispose()


@pytest.mark.parametrize("method,path", PROTECTED)
async def test_every_state_or_data_route_rejects_a_missing_key(client, method, path):
    resp = await client.request(method, path, json={})
    assert resp.status_code == 401


@pytest.mark.parametrize("method,path", PROTECTED)
async def test_every_state_or_data_route_rejects_a_wrong_key(client, method, path):
    resp = await client.request(method, path, json={}, headers={API_KEY_HEADER: "wrong"})
    assert resp.status_code == 401


async def test_another_users_wow_cannot_be_activated_without_the_key(client):
    resp = await client.post(f"/users/{SOME_ID}/activation", json={"duration": "5h"})
    assert resp.status_code == 401


async def test_correct_key_gets_past_the_gate(client):
    resp = await client.get(f"/users/{uuid.uuid4()}", headers={API_KEY_HEADER: KEY})
    assert resp.status_code == 404  # authenticated; user simply doesn't exist


async def test_health_stays_open(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


async def test_plivo_answer_is_not_behind_the_api_key_it_uses_plivo_signatures(client):
    resp = await client.post("/telephony/plivo/answer", data={"CallUUID": "x"})
    assert resp.status_code in (403, 503)  # rejected by *Plivo* auth, not 401


async def test_key_is_not_enforced_when_unset_for_backward_compatibility(client, monkeypatch):
    monkeypatch.delenv("API_ACCESS_KEY", raising=False)
    get_settings.cache_clear()
    resp = await client.get(f"/users/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_error_body_does_not_echo_the_expected_key(client):
    resp = await client.get(f"/users/{SOME_ID}", headers={API_KEY_HEADER: "wrong"})
    assert KEY not in resp.text


# --- startup fail-closed -----------------------------------------------------------


def _s(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_public_url_without_api_key_refuses_to_start():
    with pytest.raises(RuntimeError, match="API_ACCESS_KEY"):
        validate_security_config(
            _s(public_base_url="https://x.example.com", plivo_auth_token="t")
        )


def test_public_url_without_plivo_token_refuses_to_start():
    with pytest.raises(RuntimeError, match="PLIVO_AUTH_TOKEN"):
        validate_security_config(_s(public_base_url="https://x.example.com", api_access_key="k"))


def test_public_url_with_both_secrets_starts_and_never_logs_them(caplog):
    with caplog.at_level(logging.DEBUG):
        validate_security_config(
            _s(public_base_url="https://x.example.com", api_access_key="k-secret", plivo_auth_token="t-secret")
        )
    assert "k-secret" not in caplog.text and "t-secret" not in caplog.text


def test_error_message_never_contains_secret_values():
    with pytest.raises(RuntimeError) as exc:
        validate_security_config(
            _s(public_base_url="https://x.example.com", plivo_auth_token="t-secret")
        )
    assert "t-secret" not in str(exc.value)


def test_local_dev_without_secrets_still_starts():
    validate_security_config(_s())


def test_production_without_key_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="app.security"):
        validate_security_config(_s(app_env="production"))
    assert "API_ACCESS_KEY is not set" in caplog.text


# --- storage-time redaction ----------------------------------------------------------


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


async def test_stored_transcripts_never_contain_otp_pin_or_card_numbers():
    from app.agent.call_recorder import CallRecorder
    from app.models.transcript import Speaker

    session = _FakeSession()
    recorder = CallRecorder(session)
    conv = str(uuid.uuid4())
    await recorder.record_turn(
        conversation_id=conv, speaker=Speaker.CALLER, text="my otp is 482913 and card 4111 1111 1111 1111"
    )
    stored = session.added[0].text
    assert "482913" not in stored
    assert "4111" not in stored
    assert "[REDACTED_" in stored


async def test_callback_numbers_and_emails_are_kept_for_the_owner():
    """Deliberate Phase 1 boundary (docs/SECURITY.md): a message-taking
    assistant must keep callback details; full PII handling is Phase 3."""
    from app.agent.call_recorder import CallRecorder
    from app.models.transcript import Speaker

    session = _FakeSession()
    await CallRecorder(session).record_turn(
        conversation_id=str(uuid.uuid4()),
        speaker=Speaker.CALLER,
        text="call me back on 98765 43210 or mail ravi@example.com",
    )
    assert "98765 43210" in session.added[0].text
    assert "ravi@example.com" in session.added[0].text


# --- pipeline per-turn resilience ------------------------------------------------------


async def test_one_failed_turn_does_not_end_the_live_call_but_three_in_a_row_do():
    from app.providers.stt.simulated import SimulatedSTTProvider
    from tests.test_media_pipeline_streaming import _build_pipeline

    class FlakySTT(SimulatedSTTProvider):
        def __init__(self, fail_calls):
            super().__init__()
            self.calls = 0
            self.fail_calls = fail_calls

        async def transcribe(self, audio, *, sample_rate=16000):
            self.calls += 1
            if self.calls in self.fail_calls:
                raise RuntimeError("stt exploded")
            return await super().transcribe(audio, sample_rate=sample_rate)

    async def chunks(n):
        for _ in range(n):
            yield b"hello world please"  # SimulatedSTT decodes text from bytes

    # one failure in the middle: the call survives and the other turns come through
    pipeline = _build_pipeline()
    pipeline._stt = FlakySTT({2})
    turns = [t async for t in pipeline.stream_call_audio(user_id=str(uuid.uuid4()), audio_chunks=chunks(3))]
    assert len(turns) == 2

    # three consecutive failures: treated as systemic and surfaced
    pipeline = _build_pipeline()
    pipeline._stt = FlakySTT({1, 2, 3})
    with pytest.raises(RuntimeError):
        [t async for t in pipeline.stream_call_audio(user_id=str(uuid.uuid4()), audio_chunks=chunks(5))]
