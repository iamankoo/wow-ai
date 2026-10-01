"""WS /telephony/plivo/stream - Phase 1 authentication + call lifecycle.

Everything here runs with lightweight fakes for the pipeline/recorder (no
Whisper/Piper/DB needed), so it runs unconditionally. It proves the *bridge
logic* (auth gate, call correlation, cleanup, caps). It does NOT prove a
real Plivo call works - only a real external call can; see
docs/PLIVO_TESTING.md.
"""

import asyncio
import base64
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_call_recorder, get_media_pipeline
from app.api.routes import telephony_plivo
from app.config import get_settings
from app.providers.telephony.stream_tokens import StreamTokenStore, get_stream_token_store
from tests.conftest import authorized_stream_path

_PCM = b"\x00\x00" * 160  # 10ms of silence at 16kHz


@pytest.fixture(autouse=True)
def _settings_reset(monkeypatch):
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    assert telephony_plivo._active_streams == 0, "a stream leaked its concurrency slot"


class FakeRecorder:
    def __init__(self, fail_end: bool = False):
        self.fail_end = fail_end
        self.started: list[str | None] = []
        self.turns: list[dict] = []
        self.ended: list[str | None] = []
        self.rolled_back = False

    async def start_call(self, *, user_id, caller_number, direction):
        self.started.append(caller_number)
        return SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())

    async def record_turn(self, **kwargs):
        self.turns.append(kwargs)

    async def end_call(self, *, call, conversation, summary_text=None):
        if self.fail_end:
            raise RuntimeError("db exploded")
        self.ended.append(summary_text)

    async def rollback(self):
        self.rolled_back = True


class FakePipeline:
    """mode: idle (drain audio until the call ends) | raise (STT-style
    failure on first audio) | hang (never yields, never ends) | turn
    (yields one finished turn, then drains) | greet_fail (TTS fails)."""

    def __init__(self, mode: str = "idle"):
        self.mode = mode

    async def synthesize_reply(self, *, user_id, text):
        if self.mode == "greet_fail":
            raise RuntimeError("tts boom")
        return _PCM, 16000

    async def stream_call_audio(self, *, user_id, audio_chunks, conversation_id, caller_number):
        if self.mode == "hang":
            await asyncio.sleep(3600)
        if self.mode == "raise":
            async for _ in audio_chunks:
                raise RuntimeError("stt boom")
        if self.mode == "turn":
            yield SimpleNamespace(
                transcript="hello there",
                agent_action=SimpleNamespace(payload={"reply": "hi, how can I help?"}),
                reply_audio=_PCM,
                reply_sample_rate=16000,
                language="en",
                stage_durations_ms={"stt": 1.0},
            )
        async for _ in audio_chunks:
            pass


def _client(pipeline=None, recorder=None):
    pipeline = pipeline or FakePipeline()
    recorder = recorder or FakeRecorder()
    built = {"pipeline": 0, "recorder": 0}

    def _get_pipeline():
        built["pipeline"] += 1
        return pipeline

    def _get_recorder():
        built["recorder"] += 1
        return recorder

    app = FastAPI()
    app.include_router(telephony_plivo.router)
    app.dependency_overrides[get_media_pipeline] = _get_pipeline
    app.dependency_overrides[get_call_recorder] = _get_recorder
    return TestClient(app), recorder, built


def _start_event(call_id: str | None, caller: str = "+919876543210") -> str:
    start = {"streamId": "s1", "from": caller}
    if call_id is not None:
        start["callId"] = call_id
    return json.dumps({"event": "start", "start": start})


def _media_event() -> str:
    return json.dumps(
        {"event": "media", "media": {"payload": base64.b64encode(b"\xff" * 160).decode()}}
    )


def _assert_rejected(client, path):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path):
            pass


# --- authentication ---------------------------------------------------------


def test_valid_token_connects_greets_records_and_cleans_up():
    client, recorder, _ = _client()
    with client.websocket_connect(authorized_stream_path("call-A")) as ws:
        ws.send_text(_start_event("call-A"))
        greeting = json.loads(ws.receive_text())
        assert greeting["event"] == "playAudio"
        ws.send_text(_media_event())
    assert recorder.started == ["+919876543210"]
    assert len(recorder.ended) == 1
    assert [t["speaker"].value for t in recorder.turns] == ["assistant"]  # the greeting


def test_missing_token_is_rejected_before_anything_runs():
    client, recorder, built = _client()
    _assert_rejected(client, "/telephony/plivo/stream")
    assert built == {"pipeline": 0, "recorder": 0}
    assert recorder.started == []


def test_invalid_token_is_rejected_before_anything_runs():
    client, recorder, built = _client()
    _assert_rejected(client, "/telephony/plivo/stream?token=not-a-real-token")
    assert built == {"pipeline": 0, "recorder": 0}
    assert recorder.started == []


def test_expired_token_is_rejected():
    store = StreamTokenStore(ttl_seconds=-1)  # already expired when issued
    token = store.issue("call-A")
    get_stream_token_store.cache_clear()
    get_stream_token_store()._entries.update(store._entries)
    client, recorder, built = _client()
    _assert_rejected(client, f"/telephony/plivo/stream?token={token}")
    assert built == {"pipeline": 0, "recorder": 0}
    assert recorder.started == []


def test_token_cannot_be_replayed():
    client, recorder, _ = _client()
    path = authorized_stream_path("call-A")
    with client.websocket_connect(path) as ws:
        ws.send_text(_start_event("call-A"))
        ws.receive_text()
    assert len(recorder.started) == 1
    _assert_rejected(client, path)  # same token again
    assert len(recorder.started) == 1  # no second, fake call record


def test_start_event_for_a_different_call_is_dropped_and_never_recorded():
    client, recorder, _ = _client()
    with client.websocket_connect(authorized_stream_path("call-A")) as ws:
        ws.send_text(_start_event("call-SOMEONE-ELSE"))
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()
    assert recorder.started == []  # never recorded
    assert recorder.ended == []


def test_start_event_without_a_call_id_is_tolerated_because_the_token_already_authenticated():
    client, recorder, _ = _client()
    with client.websocket_connect(authorized_stream_path("call-A")) as ws:
        ws.send_text(_start_event(None))
        ws.receive_text()
    assert len(recorder.started) == 1


def test_token_for_one_call_does_not_authorize_another_token_less_connection():
    client, recorder, _ = _client()
    authorized_stream_path("call-A")  # minted, never used
    _assert_rejected(client, "/telephony/plivo/stream")
    assert recorder.started == []


def test_rejections_do_not_leak_concurrency_slots_or_tokens():
    client, _, _ = _client()
    for _i in range(5):
        _assert_rejected(client, "/telephony/plivo/stream?token=bogus")
    assert telephony_plivo._active_streams == 0  # also asserted by the autouse fixture


# --- caps ---------------------------------------------------------------------


def test_stream_refused_when_concurrent_stream_cap_reached(monkeypatch):
    monkeypatch.setenv("PLIVO_MAX_CONCURRENT_STREAMS", "0")
    get_settings.cache_clear()
    client, recorder, _ = _client()
    _assert_rejected(client, authorized_stream_path("call-A"))
    assert recorder.started == []


def test_call_is_ended_at_the_max_duration(monkeypatch):
    monkeypatch.setenv("PLIVO_MAX_CALL_SECONDS", "1")
    get_settings.cache_clear()
    client, recorder, _ = _client(pipeline=FakePipeline("hang"))
    with client.websocket_connect(authorized_stream_path("call-A")) as ws:
        ws.send_text(_start_event("call-A"))
        ws.receive_text()  # greeting
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()  # server closes after ~1s
    assert len(recorder.ended) == 1


# --- lifecycle / cleanup --------------------------------------------------------


def test_normal_turn_is_recorded_and_replied_to():
    client, recorder, _ = _client(pipeline=FakePipeline("turn"))
    with client.websocket_connect(authorized_stream_path("call-A")) as ws:
        ws.send_text(_start_event("call-A"))
        assert json.loads(ws.receive_text())["event"] == "playAudio"  # greeting
        assert json.loads(ws.receive_text())["event"] == "playAudio"  # reply
    speakers = [t["speaker"].value for t in recorder.turns]
    assert speakers == ["assistant", "caller", "assistant"]
    assert "1 conversational turn" in recorder.ended[0]


def test_caller_disconnect_mid_call_still_finalizes():
    client, recorder, _ = _client()
    with client.websocket_connect(authorized_stream_path("call-A")) as ws:
        ws.send_text(_start_event("call-A"))
        ws.receive_text()
        ws.send_text(_media_event())
        # leave the block abruptly: client disconnect
    assert len(recorder.ended) == 1


def test_pipeline_error_mid_call_still_finalizes_and_closes():
    client, recorder, _ = _client(pipeline=FakePipeline("raise"))
    with client.websocket_connect(authorized_stream_path("call-A")) as ws:
        ws.send_text(_start_event("call-A"))
        ws.receive_text()
        ws.send_text(_media_event())
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()
    assert len(recorder.ended) == 1


def test_greeting_tts_failure_still_cleans_up():
    client, recorder, _ = _client(pipeline=FakePipeline("greet_fail"))
    with client.websocket_connect(authorized_stream_path("call-A")) as ws:
        ws.send_text(_start_event("call-A"))
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()
    assert len(recorder.ended) == 1


def test_history_failure_does_not_skip_socket_cleanup():
    recorder = FakeRecorder(fail_end=True)
    client, _, _ = _client(recorder=recorder)
    with client.websocket_connect(authorized_stream_path("call-A")) as ws:
        ws.send_text(_start_event("call-A"))
        ws.receive_text()
    assert recorder.rolled_back is True  # poisoned transaction discarded


def test_malformed_frames_do_not_kill_the_call():
    client, recorder, _ = _client()
    with client.websocket_connect(authorized_stream_path("call-A")) as ws:
        ws.send_text(_start_event("call-A"))
        ws.receive_text()
        for junk in ["not json", "[1,2,3]", "null", '{"event":"media"}',
                     '{"event":"media","media":{"payload":"!!!not-base64!!!"}}',
                     '{"event":"unknown"}']:
            ws.send_text(junk)
        ws.send_text(_media_event())
    assert len(recorder.ended) == 1


def test_repeated_calls_each_get_their_own_record_and_clean_up():
    client, recorder, _ = _client()
    for i in range(3):
        with client.websocket_connect(authorized_stream_path(f"call-{i}")) as ws:
            ws.send_text(_start_event(f"call-{i}"))
            ws.receive_text()
    assert len(recorder.started) == 3
    assert len(recorder.ended) == 3
    assert telephony_plivo._active_streams == 0
