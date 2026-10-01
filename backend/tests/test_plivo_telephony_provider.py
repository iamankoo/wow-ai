"""app.providers.telephony.plivo.PlivoTelephonyProvider - real mu-law/PCM16
conversion (already independently verified in test_audio_codec.py) wired
into the real TelephonyProvider contract, and the inbound message
parsing/routing logic. Uses a fake WebSocket (the same kind of test double
this codebase already uses everywhere else - agent_fakes.py's
FakeLLMProvider, etc. - real logic under test, a controllable stand-in
only at the one real I/O boundary a unit test can't otherwise reach)."""

import base64
import json
import struct

from starlette.websockets import WebSocketState

from app.media.audio_codec import mulaw_to_pcm16, pcm16_to_mulaw
from app.providers.telephony.plivo import PlivoTelephonyProvider, queue_to_async_iterator


class _FakeWebSocket:
    def __init__(self):
        self.sent: list[str] = []
        self.closed = False
        self.client_state = WebSocketState.CONNECTED

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True
        self.client_state = WebSocketState.DISCONNECTED


def _pcm16(*samples: int) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


async def test_send_audio_converts_pcm16_to_mulaw_and_sends_a_real_play_audio_message():
    ws = _FakeWebSocket()
    provider = PlivoTelephonyProvider("call-1", ws)

    audio = _pcm16(1000, -1000, 2000, -2000) * 100  # a real-shaped, non-trivial chunk
    await provider.send_audio("call-1", audio, sample_rate=16000)

    assert len(ws.sent) == 1
    message = json.loads(ws.sent[0])
    assert message["event"] == "playAudio"
    assert message["media"]["contentType"] == "audio/x-mulaw"
    assert message["media"]["sampleRate"] == 8000

    sent_mulaw = base64.b64decode(message["media"]["payload"])
    assert len(sent_mulaw) > 0
    # Real, decodable mu-law - not opaque/fake bytes.
    decoded = mulaw_to_pcm16(sent_mulaw)
    assert len(decoded) > 0


async def test_send_audio_with_empty_chunk_sends_nothing():
    ws = _FakeWebSocket()
    provider = PlivoTelephonyProvider("call-1", ws)

    await provider.send_audio("call-1", b"", sample_rate=16000)

    assert ws.sent == []


async def test_end_call_closes_the_websocket_when_still_connected():
    ws = _FakeWebSocket()
    provider = PlivoTelephonyProvider("call-1", ws)

    await provider.end_call("call-1")

    assert ws.closed is True


async def test_end_call_is_safe_to_call_when_already_disconnected():
    ws = _FakeWebSocket()
    ws.client_state = WebSocketState.DISCONNECTED

    provider = PlivoTelephonyProvider("call-1", ws)
    await provider.end_call("call-1")  # must not raise

    assert ws.closed is False  # never double-closes an already-closed socket


async def test_answer_call_is_a_real_documented_no_op():
    """Not a missing feature - Plivo's model has no separate "answer" step;
    see the class docstring. Just must not raise."""
    ws = _FakeWebSocket()
    provider = PlivoTelephonyProvider("call-1", ws)
    await provider.answer_call("call-1")  # must not raise


async def test_on_audio_received_handler_is_invoked_with_real_converted_pcm16():
    ws = _FakeWebSocket()
    provider = PlivoTelephonyProvider("call-1", ws)

    received: list[bytes] = []

    async def handler(chunk: bytes) -> None:
        received.append(chunk)

    await provider.on_audio_received("call-1", handler)

    original_pcm = _pcm16(500, -500, 1500, -1500) * 20
    wire_mulaw = pcm16_to_mulaw(original_pcm)
    message = json.dumps(
        {"event": "media", "media": {"payload": base64.b64encode(wire_mulaw).decode("ascii")}}
    )

    keep_going = await provider.feed_inbound_message(message)

    assert keep_going is True
    assert len(received) == 1
    # 8kHz mu-law upsampled back to this project's internal 16kHz - real
    # conversion, roughly double the sample count.
    assert len(received[0]) > len(wire_mulaw)


async def test_feed_inbound_message_stop_event_signals_end_of_stream():
    ws = _FakeWebSocket()
    provider = PlivoTelephonyProvider("call-1", ws)

    keep_going = await provider.feed_inbound_message(json.dumps({"event": "stop"}))

    assert keep_going is False


async def test_feed_inbound_message_start_event_is_ignored_not_an_error():
    ws = _FakeWebSocket()
    provider = PlivoTelephonyProvider("call-1", ws)

    keep_going = await provider.feed_inbound_message(
        json.dumps({"event": "start", "start": {"from": "+919876543210"}})
    )

    assert keep_going is True


async def test_feed_inbound_message_non_json_is_ignored_not_a_crash():
    ws = _FakeWebSocket()
    provider = PlivoTelephonyProvider("call-1", ws)

    keep_going = await provider.feed_inbound_message("not json at all")

    assert keep_going is True


async def test_feed_inbound_message_media_event_with_no_payload_is_ignored_not_a_crash():
    ws = _FakeWebSocket()
    provider = PlivoTelephonyProvider("call-1", ws)

    keep_going = await provider.feed_inbound_message(json.dumps({"event": "media", "media": {}}))

    assert keep_going is True


async def test_feed_inbound_message_accepts_a_flat_top_level_payload_too():
    """Real defensiveness for the one detail Plivo's docs didn't quote the
    full nested shape of - see _extract_media_payload's docstring."""
    ws = _FakeWebSocket()
    provider = PlivoTelephonyProvider("call-1", ws)
    received: list[bytes] = []

    async def handler(chunk: bytes) -> None:
        received.append(chunk)

    await provider.on_audio_received("call-1", handler)
    wire_mulaw = pcm16_to_mulaw(_pcm16(100, 200, 300))
    message = json.dumps({"event": "media", "payload": base64.b64encode(wire_mulaw).decode("ascii")})

    keep_going = await provider.feed_inbound_message(message)

    assert keep_going is True
    assert len(received) == 1


async def test_queue_to_async_iterator_yields_until_the_none_sentinel():
    import asyncio

    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(b"one")
    await queue.put(b"two")
    await queue.put(None)

    chunks = [chunk async for chunk in queue_to_async_iterator(queue)]

    assert chunks == [b"one", b"two"]
