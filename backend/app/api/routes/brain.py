from fastapi import APIRouter, Depends

from app.agent.call_recorder import CallRecorder
from app.api.deps import get_brain, get_call_recorder
from app.interfaces.agent_runtime import AgentRuntime
from app.models.call import CallDirection
from app.schemas.brain import BrainCommandRequest, BrainCommandResponse

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
