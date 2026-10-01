"""Real TelephonyProvider implementation for Plivo's Audio Streaming
product (see docs/ARCHITECTURE.md "Real telephony") - the first real
(non-simulated) implementation of app.interfaces.telephony.TelephonyProvider
in this project.

One instance is constructed per active call by the WebSocket route
(app/api/routes/telephony_plivo.py) once Plivo's `<Stream bidirectional=
"true">` connects, wrapping that one real `WebSocket` for the life of the
call. Every other layer (MediaPipeline, VAD, STT, TTS, CallRecorder) only
ever sees PCM16 16kHz, matching this project's existing convention
throughout - Plivo's wire format (mu-law, 8kHz, JSON `media`/`playAudio`
envelopes, verified against Plivo's official docs this round - see
docs/ARCHITECTURE.md) is entirely private to this class via
app.media.audio_codec.

`answer_call`/`end_call` map onto Plivo's model with real caveats, stated
honestly rather than glossed over - see each method's docstring.
"""

import base64
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.interfaces.telephony import TelephonyProvider
from app.media.audio_codec import mulaw_to_pcm16, pcm16_to_mulaw, resample_pcm16

logger = logging.getLogger("app.providers.telephony.plivo")

PLIVO_STREAM_SAMPLE_RATE = 8000
# This project's internal convention (WebRtcVoiceActivityDetector /
# LocalWhisperSTTProvider both assume this) - inbound audio handed to a
# registered on_audio_received handler is always resampled to this rate
# first, so nothing above this layer ever has to know Plivo exists.
INTERNAL_SAMPLE_RATE = 16000
# A real Plivo media frame is ~20ms of mu-law (~160 bytes -> ~216 base64
# chars). Anything wildly larger is not a normal frame; dropping it bounds
# per-message CPU/memory from a misbehaving peer.
_MAX_MEDIA_PAYLOAD_CHARS = 64 * 1024


class PlivoTelephonyProvider(TelephonyProvider):
    def __init__(self, call_id: str, websocket: WebSocket):
        self._call_id = call_id
        self._websocket = websocket
        self._handler: Callable[[bytes], Awaitable[None]] | None = None

    async def answer_call(self, call_id: str) -> None:
        """No-op, and deliberately so: unlike a traditional telephony API
        with a separate "answer" step, Plivo already considers the call
        answered by the time this WebSocket exists - PLIVOXML returned
        from the Answer URL webhook (app/api/routes/telephony_plivo.py's
        `answer` route) *is* the answer, and Plivo only opens the Stream
        connection after that. Logged so the call is still traceable."""
        logger.info("plivo call %s: already answered via PLIVOXML response", call_id)

    async def end_call(self, call_id: str) -> None:
        """Closes this call's WebSocket, ending the media stream.

        Honest caveat, not glossed over: whether closing the WebSocket
        also hangs up the underlying PSTN call (versus Plivo falling
        through to whatever XML/behavior `keepCallAlive` implies) was not
        independently verified against a real call this round - only the
        documented request/response shapes were (see docs/ARCHITECTURE.md).
        If a real test shows the call doesn't actually disconnect, ending
        it for real needs Plivo's REST Call-hangup API - a real follow-up,
        not guessed at here."""
        with contextlib.suppress(Exception):
            if self._websocket.client_state != WebSocketState.DISCONNECTED:
                await self._websocket.close()

    async def send_audio(
        self, call_id: str, audio_chunk: bytes, *, sample_rate: int = INTERNAL_SAMPLE_RATE
    ) -> None:
        """Sends synthesized reply audio out to the caller.

        `audio_chunk` must be PCM16 little-endian at `sample_rate` (default
        16000, this project's convention - e.g. LocalPiperTTSProvider's
        real per-voice rate, often 22050, so callers with a different rate
        must pass it explicitly rather than relying on the default).
        Converts to Plivo's wire format (mu-law, 8kHz) and sends as one
        `playAudio` JSON message - the exact envelope Plivo's docs specify
        (see docs/ARCHITECTURE.md's quoted XML/JSON)."""
        if not audio_chunk:
            return
        wire_pcm = resample_pcm16(
            audio_chunk, from_rate=sample_rate, to_rate=PLIVO_STREAM_SAMPLE_RATE
        )
        mulaw = pcm16_to_mulaw(wire_pcm)
        message = {
            "event": "playAudio",
            "media": {
                "contentType": "audio/x-mulaw",
                "sampleRate": PLIVO_STREAM_SAMPLE_RATE,
                "payload": base64.b64encode(mulaw).decode("ascii"),
            },
        }
        await self._websocket.send_text(json.dumps(message))

    async def on_audio_received(
        self, call_id: str, handler: Callable[[bytes], Awaitable[None]]
    ) -> None:
        """Registers `handler` to be invoked with each inbound caller
        utterance chunk, already converted to this project's internal
        PCM16 16kHz convention - see feed_inbound_message, which is what
        actually calls this handler as Plivo `media` events arrive."""
        self._handler = handler

    async def feed_inbound_message(self, raw_message: str) -> bool:
        """Not part of the TelephonyProvider ABC (no real telephony
        provider's raw wire protocol belongs in that generic interface) -
        called by the WebSocket route for every message received from
        Plivo. Parses Plivo's documented `media` event, converts its
        mu-law/8kHz payload to this project's PCM16/16kHz convention, and
        invokes whatever handler on_audio_received registered.

        Returns False when this message signals the stream ended (a
        `stop` event, or something unparseable enough that the caller
        should stop reading), True otherwise. Defensive by design: an
        unrecognized message shape is logged and skipped, never crashes
        the call - Plivo's exact inbound JSON field nesting was
        documented (event/media/payload) but not independently replayed
        against a real call yet this round (see docs/ARCHITECTURE.md
        "Real telephony" for what was and wasn't verified), so this is
        deliberately tolerant rather than presented as guaranteed-exact.
        """
        try:
            message = json.loads(raw_message)
        except (json.JSONDecodeError, TypeError):
            logger.warning("plivo call %s: non-JSON WebSocket message, ignoring", self._call_id)
            return True

        if not isinstance(message, dict):
            logger.warning("plivo call %s: non-object WebSocket message, ignoring", self._call_id)
            return True

        event = message.get("event")
        if event == "stop":
            return False
        if event != "media":
            # "start"/"checkpoint"/anything else Plivo may send - no
            # inbound audio to act on, but not an error.
            logger.debug("plivo call %s: event=%s (no audio)", self._call_id, event)
            return True

        media = message.get("media")
        if isinstance(media, dict) and media.get("track") == "outbound":
            # Only possible if the Stream was configured with audioTrack=
            # outbound/both - never feed WOW its own voice back as caller
            # speech.
            return True

        payload_b64 = _extract_media_payload(message)
        if payload_b64 is None:
            logger.warning(
                "plivo call %s: media event with no recognizable payload field: %s",
                self._call_id,
                sorted(message.keys()),
            )
            return True

        if not payload_b64 or len(payload_b64) > _MAX_MEDIA_PAYLOAD_CHARS:
            logger.warning(
                "plivo call %s: empty or oversized media payload (%d chars), ignoring",
                self._call_id,
                len(payload_b64 or ""),
            )
            return True

        try:
            mulaw = base64.b64decode(payload_b64, validate=True)
        except (ValueError, TypeError):
            logger.warning("plivo call %s: media payload was not valid base64", self._call_id)
            return True

        pcm16_8k = mulaw_to_pcm16(mulaw)
        pcm16_16k = resample_pcm16(
            pcm16_8k, from_rate=PLIVO_STREAM_SAMPLE_RATE, to_rate=INTERNAL_SAMPLE_RATE
        )
        if self._handler is not None:
            await self._handler(pcm16_16k)
        return True


@dataclass(frozen=True)
class StartInfo:
    call_id: str | None
    caller_number: str | None


_CALL_ID_KEYS = ("callId", "callUUID", "callUuid", "call_uuid", "call_id", "CallUUID")
_FROM_KEYS = ("from", "From", "caller_number", "callerNumber")


def parse_start_event(raw_message: str) -> StartInfo | None:
    """Parses Plivo's `start` event (sent once, before any `media`) into the
    call id + caller number. Plivo's public docs name the fields (`start`
    carries streamId, callId, from, to, mediaFormat) but do not publish a
    verbatim JSON sample, so this reads them from the nested `start` object
    first (how Plivo's own SDK accesses them: event["start"]["callId"]) and
    falls back to the top level and a few casings - tolerant, never
    guessing a value that is not present. Returns None when the message is
    not a start event at all."""
    try:
        message = json.loads(raw_message)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(message, dict) or message.get("event") != "start":
        return None
    sources = []
    if isinstance(message.get("start"), dict):
        sources.append(message["start"])
    sources.append(message)

    def _first(keys: tuple[str, ...]) -> str | None:
        for source in sources:
            for key in keys:
                value = source.get(key)
                if isinstance(value, str) and value:
                    return value
        return None

    return StartInfo(call_id=_first(_CALL_ID_KEYS), caller_number=_first(_FROM_KEYS))


def _extract_media_payload(message: dict) -> str | None:
    """Plivo's outbound `playAudio` envelope nests payload under `media`
    (verified, quoted in docs/ARCHITECTURE.md); the inbound `media` event's
    exact nesting was documented as "base64 payload" without the full
    nested shape being quoted verbatim, so this checks the documented-
    likely nested form first (media.payload, matching the outbound
    convention and Plivo's own Twilio-Media-Streams-shaped protocol) and
    falls back to a flat top-level `payload` - real defensiveness for a
    detail worth confirming against the first real test's logged raw
    messages, not a guess presented as fact."""
    media = message.get("media")
    if isinstance(media, dict) and isinstance(media.get("payload"), str):
        return media["payload"]
    payload = message.get("payload")
    if isinstance(payload, str):
        return payload
    return None


async def queue_to_async_iterator(queue) -> AsyncIterator[bytes]:
    """Pull-based adapter over PlivoTelephonyProvider's push-based
    on_audio_received callback: MediaPipeline.stream_call_audio() wants an
    async iterator of chunks, not a registered handler. The WebSocket
    route registers a handler that does `queue.put_nowait(chunk)`; this
    function is what stream_call_audio actually iterates, pulling from
    that same queue. A `None` item is the real end-of-call sentinel (put
    by the route once Plivo sends `stop` or the socket disconnects)."""
    while True:
        chunk = await queue.get()
        if chunk is None:
            return
        yield chunk
