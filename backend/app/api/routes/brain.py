import base64

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.agent.call_recorder import CallRecorder
from app.api.deps import get_brain, get_call_recorder, get_media_pipeline
from app.interfaces.agent_runtime import AgentRuntime
from app.media.pipeline import MediaPipeline, chunk_pcm16
from app.models.call import CallDirection
from app.schemas.brain import BrainCommandRequest, BrainCommandResponse
from app.schemas.voice import VoiceCommandResponse

router = APIRouter(prefix="/brain", tags=["brain"])


@router.post("/command", response_model=BrainCommandResponse)
async def send_command(
    payload: BrainCommandRequest,
    brain: AgentRuntime = Depends(get_brain),
    recorder: CallRecorder = Depends(get_call_recorder),
) -> BrainCommandResponse:
    action = await brain.handle_input(
        user_id=payload.user_id,
        text=payload.text,
        conversation_id=payload.conversation_id,
        caller_number=payload.caller_number,
    )

    # Phase 6 Part M - real call history. A caller_number is only ever
    # present on the real Android call-screening path (WowCallScreeningService.kt)
    # - the mobile app's own text/voice commands never send one - so this
    # reliably marks "a real call happened" without a second signal. No
    # real caller audio/transcript exists yet for this event (Android
    # blocks a non-privileged app from capturing live call audio - see
    # WowCallScreeningService's class doc); recording a fabricated
    # transcript would misrepresent what happened, so this stores only
    # the real, known facts - who called, when, and that WOW screened it -
    # as an honest summary rather than inventing dialogue.
    if payload.caller_number:
        contact = (action.payload or {}).get("contact") or {}
        call, conversation = await recorder.start_call(
            user_id=payload.user_id,
            caller_number=payload.caller_number,
            direction=CallDirection.INBOUND,
            contact_id=contact.get("id"),
        )
        await recorder.end_call(
            call=call,
            conversation=conversation,
            summary_text=f"WOW screened this call from {payload.caller_number} and allowed it through.",
        )

    return BrainCommandResponse(action_type=action.type, payload=action.payload)


@router.post("/voice-command", response_model=VoiceCommandResponse)
async def send_voice_command(
    request: Request,
    user_id: str = Query(...),
    conversation_id: str | None = Query(None),
    sample_rate: int = Query(16000),
    pipeline: MediaPipeline = Depends(get_media_pipeline),
) -> VoiceCommandResponse:
    """Phase 6 Part E/J - the real voice-command round trip the mobile
    app's Voice Command sheet uses once real on-device mic capture is
    wired in: the request body is one complete recording (raw PCM16
    mono, `sample_rate`Hz - the exact format Android's AudioRecord
    produces, deliberately no container/encoding so no server-side audio
    library is needed just to unwrap it), run through the same real
    VAD -> STT -> agent -> TTS MediaPipeline Block 5 already proved works
    end to end, just reached over HTTP instead of a raw audio stream.
    """
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="Request body must contain raw PCM16 audio")

    turns = await pipeline.process_call_audio(
        user_id=user_id,
        audio_chunks=chunk_pcm16(audio, sample_rate=sample_rate),
        conversation_id=conversation_id,
    )
    if not turns:
        # Real, honest outcome: VAD/STT found no actual speech in what was
        # recorded - not an error, just genuinely nothing to reply to.
        return VoiceCommandResponse(
            transcript="",
            reply_text="",
            reply_audio_base64="",
            reply_sample_rate=0,
            action_type="none",
        )

    turn = turns[-1]  # one mobile recording is one utterance; if VAD found several, the latest is what matters
    reply_text = (turn.agent_action.payload or {}).get("reply") or ""
    return VoiceCommandResponse(
        transcript=turn.transcript,
        reply_text=reply_text,
        reply_audio_base64=base64.b64encode(turn.reply_audio).decode("ascii"),
        reply_sample_rate=turn.reply_sample_rate,
        action_type=turn.agent_action.type,
    )
