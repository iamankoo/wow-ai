"""Plivo Stream inbound-message parsing (start/media/stop).

Honest scope: Plivo's public docs name the fields (start carries streamId,
callId, from, to, mediaFormat; media carries a base64 payload; playAudio is
{"event":"playAudio","media":{contentType,sampleRate,payload}}) but publish
no verbatim JSON sample for the INBOUND events. These tests pin the shapes
the parser accepts (nested per the SDK access pattern, plus fallbacks) and
that nothing malformed can crash the call. They cannot prove Plivo's real
nesting - the first real call does (docs/PLIVO_TESTING.md).
"""

import base64
import json

import pytest

from app.media.audio_codec import pcm16_to_mulaw
from app.providers.telephony.plivo import PlivoTelephonyProvider, parse_start_event


class _FakeWS:
    client_state = None

    async def send_text(self, _):
        pass

    async def close(self):
        pass


def _provider():
    received: list[bytes] = []

    async def handler(chunk: bytes):
        received.append(chunk)

    p = PlivoTelephonyProvider("c", _FakeWS())
    p._handler = handler
    return p, received


def _payload(n_samples: int = 160) -> str:
    return base64.b64encode(pcm16_to_mulaw(b"\x10\x00" * n_samples)).decode()


# --- start event ----------------------------------------------------------------


def test_start_event_nested_form():
    info = parse_start_event(
        json.dumps({"event": "start", "start": {"callId": "u-1", "streamId": "s", "from": "+9198"}})
    )
    assert (info.call_id, info.caller_number) == ("u-1", "+9198")


@pytest.mark.parametrize("key", ["callId", "callUUID", "callUuid", "call_uuid", "call_id"])
def test_start_event_call_id_casings(key):
    info = parse_start_event(json.dumps({"event": "start", "start": {key: "u-1"}}))
    assert info.call_id == "u-1"


def test_start_event_flat_fallback():
    info = parse_start_event(json.dumps({"event": "start", "callId": "u-2", "From": "+91"}))
    assert (info.call_id, info.caller_number) == ("u-2", "+91")


def test_start_event_without_ids_returns_empty_info_not_a_guess():
    info = parse_start_event(json.dumps({"event": "start", "start": {"streamId": "s"}}))
    assert info.call_id is None and info.caller_number is None


@pytest.mark.parametrize(
    "raw", ["", "not json", "[]", "null", "42", json.dumps({"event": "media"}), None]
)
def test_non_start_or_garbage_returns_none(raw):
    assert parse_start_event(raw) is None


def test_non_string_ids_are_ignored():
    info = parse_start_event(json.dumps({"event": "start", "start": {"callId": 12345}}))
    assert info.call_id is None


# --- media events ---------------------------------------------------------------


async def test_nested_media_payload_is_decoded_and_resampled_to_16k():
    p, received = _provider()
    msg = json.dumps(
        {
            "event": "media",
            "sequenceNumber": "3",
            "streamId": "s",
            "media": {"track": "inbound", "chunk": "2", "timestamp": "40", "payload": _payload()},
        }
    )
    assert await p.feed_inbound_message(msg) is True
    assert len(received) == 1
    assert len(received[0]) == 160 * 2 * 2  # 160 mulaw samples @8k -> 320 samples @16k, 2 bytes each


async def test_flat_payload_fallback():
    p, received = _provider()
    await p.feed_inbound_message(json.dumps({"event": "media", "payload": _payload()}))
    assert len(received) == 1


async def test_outbound_track_audio_is_never_fed_back_as_caller_speech():
    p, received = _provider()
    await p.feed_inbound_message(
        json.dumps({"event": "media", "media": {"track": "outbound", "payload": _payload()}})
    )
    assert received == []


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[1, 2]",
        "null",
        json.dumps({"event": "media"}),
        json.dumps({"event": "media", "media": {"payload": ""}}),
        json.dumps({"event": "media", "media": {"payload": "###not base64###"}}),
        json.dumps({"event": "media", "media": {"payload": 123}}),
        "OVERSIZED",
        json.dumps({"event": "dtmf", "dtmf": {"digit": "5"}}),
        json.dumps({"event": "playedStream"}),
        json.dumps({"event": "totally-new-event"}),
    ],
)
async def test_malformed_or_irrelevant_messages_never_raise_and_never_reach_stt(raw):
    if raw == "OVERSIZED":
        raw = json.dumps({"event": "media", "media": {"payload": "A" * 200_000}})
    p, received = _provider()
    assert await p.feed_inbound_message(raw) is True  # call goes on
    assert received == []


async def test_stop_event_ends_the_stream():
    p, _ = _provider()
    assert await p.feed_inbound_message(json.dumps({"event": "stop"})) is False


# --- outbound envelope ----------------------------------------------------------


async def test_play_audio_envelope_matches_plivos_documented_shape():
    sent: list[str] = []

    class WS(_FakeWS):
        async def send_text(self, text):
            sent.append(text)

    p = PlivoTelephonyProvider("c", WS())
    await p.send_audio("c", b"\x10\x00" * 1600, sample_rate=16000)
    msg = json.loads(sent[0])
    assert msg["event"] == "playAudio"
    assert msg["media"]["contentType"] == "audio/x-mulaw"
    assert msg["media"]["sampleRate"] == 8000
    assert len(base64.b64decode(msg["media"]["payload"])) == 800  # 1600 samples @16k -> 800 @8k
