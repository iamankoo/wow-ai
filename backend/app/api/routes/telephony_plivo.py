"""Real Plivo telephony bridge - the first real (non-simulated) caller
audio path in this project (see docs/ARCHITECTURE.md "Real telephony").

Two routes, matching Plivo's own two-step model:

- `POST /telephony/plivo/answer` - Plivo's Answer URL webhook. Plivo POSTs
  here the moment a call rings; the PLIVOXML this returns *is* the answer
  (there is no separate "answer" API call for Plivo the way there might be
  for other providers) and tells Plivo to open a bidirectional Audio
  Streaming WebSocket back to this same backend. Real request-signature
  validation (X-Plivo-Signature-V3) runs here first - it FAILS CLOSED when
  no PLIVO_AUTH_TOKEN is configured - and then WOW's own activation gate
  (call_assistant_enabled/active_until, the same fields the Android app's
  activation UI and WowAutoAnswer.kt's check already use): WOW must never
  activate itself, so an unactivated user's Plivo number just hangs up
  rather than answering, without ever starting STT/Brain/TTS.
- `WS /telephony/plivo/stream` - the actual bidirectional media bridge:
  inbound caller audio -> PlivoTelephonyProvider (mu-law/8kHz -> PCM16/16kHz)
  -> MediaPipeline.stream_call_audio() (VAD -> real STT -> WowAgent/Brain v3
  -> real TTS) -> PlivoTelephonyProvider (PCM16 -> mu-law/8kHz) -> Plivo ->
  caller, with CallRecorder writing real Call/Conversation/TranscriptSegment/
  Summary rows around it and a notification logged at the end. Robust to a
  receive-loop error, a mid-call pipeline exception, or start_call itself
  failing - cleanup (cancelling the receive task, closing the WebSocket,
  and recording whatever real history exists) always runs.

Stream authentication (Phase 1): Plivo documents no signature on the
WebSocket handshake, so the signed Answer webhook mints a short-lived,
single-use token bound to the call's CallUUID (see
app/providers/telephony/stream_tokens.py) and puts it in the Stream URL;
the WebSocket is rejected before it is accepted unless it presents a valid,
unexpired, unused token, and the `start` event's call id must then match
the one the token was minted for (when Plivo's start event carries one -
see parse_start_event).

Single-tenant by design (this project has no real account system yet -
see app.config.Settings.demo_user_id): every Plivo call is handled as the
one configured WOW user, the same convention the Android app's
CallScreeningService already hardcodes.
"""

import asyncio
import contextlib
import logging
import time
import uuid
from xml.sax.saxutils import escape as _xml_escape

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.call_recorder import CallRecorder
from app.api.deps import get_call_recorder, get_db, get_media_pipeline
from app.api.routes.users import apply_activation_expiry
from app.config import get_settings
from app.media.pipeline import MediaPipeline
from app.models.call import CallDirection
from app.models.transcript import Speaker
from app.models.user import User
from app.observability.notifications import notify_call_handled
from app.providers.telephony.plivo import (
    PlivoTelephonyProvider,
    parse_start_event,
    queue_to_async_iterator,
)
from app.providers.telephony.plivo_signature import validate_v3_signature
from app.providers.telephony.stream_tokens import (
    StreamTokenError,
    StreamTokenStoreFull,
    get_stream_token_store,
)

logger = logging.getLogger("app.api.routes.telephony_plivo")

router = APIRouter(prefix="/telephony/plivo", tags=["telephony"])

# Fixed call-opening line - not routed through Brain v3/Agent Core, since
# there is no caller utterance yet to classify (same precedent as
# app.agent.response.CANCELLED_ACKNOWLEDGEMENT's fixed reply text - still
# real Piper TTS, never fake/pre-recorded audio).
GREETING_TEXT = "Hello."

# Real, bounded backpressure: while WOW is "thinking" (STT/Brain/TTS for
# the previous turn), stream_call_audio's consumption loop isn't pulling
# from this queue, so inbound audio piles up. Bounding it (rather than
# leaving it unbounded) caps worst-case memory for a pathologically long
# stall instead of growing without limit - generous enough (roughly 40s
# of audio at Plivo's real ~50 frames/sec) that it should never bite
# during a normal call.
_AUDIO_QUEUE_MAXSIZE = 2000

_NOT_ACTIVATED_XML = '<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n  <Hangup/>\n</Response>'

# Live Stream WebSockets in this process - capped by
# Settings.plivo_max_concurrent_streams (resource-exhaustion guard).
_active_streams = 0


def _stream_url(request: Request, token: str) -> str:
    settings = get_settings()
    if settings.public_base_url:
        base = settings.public_base_url.rstrip("/")
        scheme = "wss" if base.startswith("https") else "ws"
        host = base.split("://", 1)[-1]
        return f"{scheme}://{host}/telephony/plivo/stream?token={token}"
    # Fallback: derive from the incoming request. Only correct if this
    # process is reachable exactly at the scheme/host the request shows -
    # true when uvicorn runs with --proxy-headers behind a tunnel that
    # forwards Host/X-Forwarded-Proto correctly (Cloudflare Tunnel/ngrok
    # both do by default), false otherwise. See Settings.public_base_url's
    # docstring - set that explicitly rather than relying on this.
    scheme = "wss" if request.url.scheme == "https" else "ws"
    return f"{scheme}://{request.url.netloc}/telephony/plivo/stream?token={token}"


def _signature_url(request: Request) -> str:
    """The URL Plivo signed. Behind a tunnel/reverse proxy uvicorn sees
    http://localhost:8000/..., but Plivo signed the public https URL it
    actually called - so when public_base_url is configured, rebuild the
    signed URL from it (path + query as received) instead of trusting the
    internal request URL, which would never match."""
    settings = get_settings()
    if not settings.public_base_url:
        return str(request.url)
    url = settings.public_base_url.rstrip("/") + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    return url


def _verify_plivo_signature(request: Request, form: dict) -> None:
    """Real X-Plivo-Signature-V3 validation (see plivo_signature.py) -
    raises HTTPException on failure. FAILS CLOSED: with no
    PLIVO_AUTH_TOKEN configured the webhook is refused (503), unless the
    operator explicitly set PLIVO_ALLOW_UNSIGNED_WEBHOOKS=true AND no
    PUBLIC_BASE_URL is set (a local, un-tunnelled test) - an unsigned
    Answer URL on a public tunnel would let anyone mint stream tokens."""
    settings = get_settings()
    if not settings.plivo_auth_token:
        if settings.plivo_allow_unsigned_webhooks and not settings.public_base_url:
            logger.warning(
                "PLIVO_AUTH_TOKEN not configured - accepting UNSIGNED webhook "
                "(PLIVO_ALLOW_UNSIGNED_WEBHOOKS, local-only mode)."
            )
            return
        logger.error("plivo answer webhook refused: PLIVO_AUTH_TOKEN is not configured")
        raise HTTPException(status_code=503, detail="Webhook authentication is not configured")

    signature = request.headers.get("X-Plivo-Signature-V3")
    nonce = request.headers.get("X-Plivo-Signature-V3-Nonce")
    if not signature or not nonce:
        logger.warning("plivo answer webhook: missing signature/nonce headers - rejecting")
        raise HTTPException(status_code=403, detail="Missing Plivo signature headers")

    if not validate_v3_signature(
        _signature_url(request), form, nonce, settings.plivo_auth_token, signature
    ):
        logger.warning("plivo answer webhook: signature validation failed - rejecting")
        raise HTTPException(status_code=403, detail="Invalid Plivo signature")


def _hangup_response() -> Response:
    return Response(content=_NOT_ACTIVATED_XML, media_type="text/xml")


@router.post("/answer")
async def plivo_answer(request: Request, session: AsyncSession = Depends(get_db)) -> Response:
    """Plivo's Answer URL webhook - see module docstring. Returns PLIVOXML
    starting a bidirectional Stream to /telephony/plivo/stream; no
    <Speak> greeting here (that would be Plivo's own hosted TTS voice) -
    the real "Hello." greeting is synthesized by our own Piper stack the
    moment the WebSocket connects (see plivo_stream below)."""
    form_data = await request.form()
    form = {k: str(v) for k, v in form_data.items()}
    _verify_plivo_signature(request, form)

    call_uuid = form.get("CallUUID")
    from_number = form.get("From")
    logger.info("plivo answer webhook: CallUUID=%s From=%s", call_uuid, from_number)
    if not call_uuid:
        # A genuine, signed Plivo request always carries CallUUID; without
        # it there is nothing to bind the stream token to.
        logger.warning("plivo answer webhook: no CallUUID - hanging up")
        return _hangup_response()

    settings = get_settings()
    try:
        result = await session.execute(
            select(User).where(User.id == uuid.UUID(settings.demo_user_id))
        )
        user = result.scalars().first()
        if user is not None:
            await apply_activation_expiry(user, session)
    except Exception as exc:  # noqa: BLE001 - a DB/config error must hang up, not 500 the caller
        logger.error(
            "plivo answer webhook: user lookup failed (%s) - hanging up", type(exc).__name__
        )
        return _hangup_response()

    activated = user is not None and user.call_assistant_enabled
    if not activated:
        # WOW must never activate itself - see module docstring. No Stream
        # is opened, no token minted, no history recorded, and none of
        # STT/Brain/TTS ever runs; the call simply isn't handled.
        logger.info(
            "plivo answer webhook: WOW is not activated (call_assistant_enabled=%s) - hanging up",
            user.call_assistant_enabled if user is not None else None,
        )
        return _hangup_response()

    if _active_streams >= settings.plivo_max_concurrent_streams:
        logger.warning("plivo answer webhook: at max concurrent streams - hanging up")
        return _hangup_response()

    try:
        token = get_stream_token_store().issue(call_uuid)
    except StreamTokenStoreFull:
        logger.error("plivo answer webhook: stream token store full - hanging up")
        return _hangup_response()

    stream_url = _xml_escape(_stream_url(request, token))
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f'  <Stream bidirectional="true" contentType="audio/x-mulaw;rate=8000" '
        f'keepCallAlive="true">{stream_url}</Stream>\n'
        "</Response>"
    )
    return Response(content=xml, media_type="text/xml")


async def authenticate_stream(websocket: WebSocket) -> str:
    """Runs BEFORE the WebSocket is accepted and before the heavier
    pipeline/recorder dependencies are built (it is the first parameter of
    plivo_stream): consumes the single-use token from the Stream URL and
    returns the CallUUID it was minted for. Any failure refuses the
    handshake (HTTP 403 to the peer); nothing else runs."""
    token = websocket.query_params.get("token")
    try:
        return get_stream_token_store().consume(token)
    except StreamTokenError as exc:
        logger.warning("plivo stream: connection rejected (%s)", exc.reason)
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION) from exc


@router.websocket("/stream")
async def plivo_stream(
    websocket: WebSocket,
    authorized_call_uuid: str = Depends(authenticate_stream),
    pipeline: MediaPipeline = Depends(get_media_pipeline),
    recorder: CallRecorder = Depends(get_call_recorder),
) -> None:
    global _active_streams

    settings = get_settings()
    if _active_streams >= settings.plivo_max_concurrent_streams:
        logger.warning("plivo stream: at max concurrent streams - refusing connection")
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    _active_streams += 1
    try:
        await _run_stream(websocket, authorized_call_uuid, pipeline, recorder)
    finally:
        _active_streams -= 1


async def _run_stream(
    websocket: WebSocket,
    authorized_call_uuid: str,
    pipeline: MediaPipeline,
    recorder: CallRecorder,
) -> None:
    await websocket.accept()

    settings = get_settings()
    user_id = settings.demo_user_id
    call_id = f"plivo-{uuid.uuid4()}"
    provider = PlivoTelephonyProvider(call_id, websocket)

    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=_AUDIO_QUEUE_MAXSIZE)
    state: dict = {"caller_number": None, "call_mismatch": False}
    # Plivo's documented protocol sends a "start" event (carrying the
    # caller's number) before any "media" event - set once the first
    # inbound message has been processed, so recorder.start_call below can
    # wait a bounded moment for the real caller number instead of racing
    # the concurrent receive_loop and almost always recording "unknown".
    first_message_seen = asyncio.Event()

    async def _on_audio(chunk: bytes) -> None:
        try:
            audio_queue.put_nowait(chunk)
        except asyncio.QueueFull:
            # Real, bounded backpressure (see _AUDIO_QUEUE_MAXSIZE) - drop
            # rather than block (a stuck receive_loop would stop draining
            # Plivo's own socket buffer) or grow without limit (the OOM
            # failure mode this project has already hit once for real, see
            # docs/DEPLOYMENT.md).
            logger.warning("plivo call %s: audio queue full, dropping a chunk", call_id)

    await provider.on_audio_received(call_id, _on_audio)

    async def receive_loop() -> None:
        try:
            while True:
                raw = await websocket.receive_text()
                _capture_start_info(raw, state, authorized_call_uuid)
                first_message_seen.set()
                if state["call_mismatch"]:
                    logger.warning(
                        "plivo call %s: start event call id does not match the authorized "
                        "call - closing",
                        call_id,
                    )
                    break
                keep_going = await provider.feed_inbound_message(raw)
                if not keep_going:
                    break
        except WebSocketDisconnect:
            logger.info("plivo call %s: WebSocket disconnected", call_id)
        except Exception as exc:  # noqa: BLE001 - a receive-loop error must never leak
            # cleanup (recorder.end_call/notify_call_handled/provider.end_call
            # in the finally block below) - it must always run, so this
            # task must never raise anything a bare `await receive_task`
            # would re-raise. Starlette can raise things other than
            # WebSocketDisconnect once a connection is already gone (e.g. a
            # RuntimeError from a receive() after a disconnect message was
            # already consumed) - caught here, not assumed away.
            logger.warning(
                "plivo call %s: receive_loop ended with %s: %s", call_id, type(exc).__name__, exc
            )
        finally:
            first_message_seen.set()  # unblock the waiter below even if nothing ever arrived
            with contextlib.suppress(asyncio.QueueFull):
                audio_queue.put_nowait(None)

    receive_task = asyncio.create_task(receive_loop())
    started = time.monotonic()

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(first_message_seen.wait(), timeout=2.0)

    call = None
    conversation = None
    turn_count = 0
    try:
        if state["call_mismatch"]:
            # Authorized for a different call than the one actually streaming
            # - never record or answer it.
            return

        # start_call itself is inside the try: if it fails (e.g. a real DB
        # error), the finally block below still cancels receive_task and
        # closes the WebSocket instead of leaking them - it just skips
        # recording history that was never actually created.
        call, conversation = await recorder.start_call(
            user_id=user_id, caller_number=state["caller_number"], direction=CallDirection.INBOUND
        )
        # Commit now (not only at teardown): the agent's own DB session writes
        # rows with a foreign key to this conversation - see CallRecorder.commit.
        await recorder.commit()

        # Greet first, via the real Piper stack, before consuming any
        # caller audio - matches the milestone's "caller hears Hello
        # first" requirement.
        greeting_audio, greeting_rate = await pipeline.synthesize_reply(
            user_id=user_id, text=GREETING_TEXT
        )
        if greeting_audio:
            await provider.send_audio(call_id, greeting_audio, sample_rate=greeting_rate)
            await recorder.record_turn(
                conversation_id=str(conversation.id), speaker=Speaker.ASSISTANT, text=GREETING_TEXT
            )

        async def _run_turns() -> None:
            nonlocal turn_count
            async for turn in pipeline.stream_call_audio(
                user_id=user_id,
                audio_chunks=queue_to_async_iterator(audio_queue),
                conversation_id=str(conversation.id),
                caller_number=state["caller_number"],
            ):
                turn_count += 1
                logger.info(
                    "plivo call %s turn %d: language=%s latency_ms=%s",
                    call_id,
                    turn_count,
                    turn.language,
                    {k: round(v, 1) for k, v in turn.stage_durations_ms.items()},
                )
                await recorder.record_turn(
                    conversation_id=str(conversation.id),
                    speaker=Speaker.CALLER,
                    text=turn.transcript,
                    language=turn.language,
                )
                reply_text = (turn.agent_action.payload or {}).get("reply") or ""
                if reply_text:
                    await recorder.record_turn(
                        conversation_id=str(conversation.id),
                        speaker=Speaker.ASSISTANT,
                        text=reply_text,
                        language=turn.language,
                    )
                await recorder.commit()  # history survives a crash; keeps the transaction short
                if turn.reply_audio:
                    await provider.send_audio(
                        call_id, turn.reply_audio, sample_rate=turn.reply_sample_rate
                    )

        try:
            await asyncio.wait_for(_run_turns(), timeout=settings.plivo_max_call_seconds)
        except asyncio.TimeoutError:
            logger.warning(
                "plivo call %s: hit max call duration (%ss) - ending",
                call_id,
                settings.plivo_max_call_seconds,
            )
    except Exception as exc:  # noqa: BLE001 - must not crash the ASGI connection uncleanly
        # Logged with the exception type/message only, never any
        # transcript/audio content - see module docstring "Privacy".
        logger.exception("plivo call %s: unexpected error mid-call: %s", call_id, exc)
    finally:
        # Every step below is independently guarded: one failing cleanup
        # step (e.g. a poisoned DB session) must never skip the others -
        # in particular the WebSocket close and receive-task cancellation.
        receive_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await receive_task

        duration = time.monotonic() - started
        try:
            if call is not None and conversation is not None:
                summary_text = (
                    f"WOW handled a call from {state['caller_number'] or 'an unknown number'} "
                    f"({turn_count} conversational turn{'s' if turn_count != 1 else ''})."
                )
                await recorder.end_call(
                    call=call, conversation=conversation, summary_text=summary_text
                )
                await recorder.commit()
                notify_call_handled(
                    caller_number=state["caller_number"],
                    duration_seconds=duration,
                    turn_count=turn_count,
                    summary_text=summary_text,
                )
            else:
                logger.warning(
                    "plivo call %s: no Call/Conversation was ever created - nothing to record",
                    call_id,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "plivo call %s: failed to finalize call history (%s)", call_id, type(exc).__name__
            )
            with contextlib.suppress(Exception):
                await recorder.rollback()
        finally:
            with contextlib.suppress(Exception):
                await provider.end_call(call_id)


def _capture_start_info(raw_message: str, state: dict, authorized_call_uuid: str) -> None:
    """Plivo's `start` event carries call metadata - the caller's number
    (so CallRecorder/notify_call_handled report the real caller rather
    than "unknown") and the call id, which must equal the CallUUID the
    stream token was minted for. A *present* id that differs flags
    `call_mismatch` (the connection is dropped). An absent id is tolerated
    with a warning: Plivo's docs name the field but publish no verbatim
    JSON, and the single-use token already authenticated the connection -
    see docs/PLIVO_TESTING.md for what the first real call must confirm."""
    info = parse_start_event(raw_message)
    if info is None:
        return
    if state["caller_number"] is None and info.caller_number:
        state["caller_number"] = info.caller_number
    if info.call_id is None:
        logger.warning("plivo stream: start event carried no recognizable call id")
    elif info.call_id != authorized_call_uuid:
        state["call_mismatch"] = True
