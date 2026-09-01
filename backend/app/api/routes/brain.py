from fastapi import APIRouter, Depends

from app.api.deps import get_brain
from app.interfaces.agent_runtime import AgentRuntime
from app.schemas.brain import BrainCommandRequest, BrainCommandResponse

router = APIRouter(prefix="/brain", tags=["brain"])


@router.post("/command", response_model=BrainCommandResponse)
async def send_command(
    payload: BrainCommandRequest, brain: AgentRuntime = Depends(get_brain)
) -> BrainCommandResponse:
    action = await brain.handle_input(
        user_id=payload.user_id,
        text=payload.text,
        conversation_id=payload.conversation_id,
        caller_number=payload.caller_number,
    )
    return BrainCommandResponse(action_type=action.type, payload=action.payload)
