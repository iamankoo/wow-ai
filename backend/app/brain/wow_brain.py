"""WOW Brain v0 - the minimal stateful agent runtime for Phase 1.

Flow (LangGraph-style, expressed as plain sequential steps for now):

    input text -> classify intent (LanguageModelProvider)
               -> build/refresh context (ContextEngine)
               -> update + persist agent state (StateRepository)
               -> return a structured AgentAction

Kept intentionally simple: no branching graph engine yet, but the seams
(provider interfaces + a persisted state repository keyed by
user/conversation) are exactly what a real multi-node graph would plug into
next, without changing the public handle_input contract.
"""

from app.interfaces.agent_runtime import AgentAction, AgentRuntime
from app.interfaces.context_engine import ContextEngine
from app.interfaces.llm import LanguageModelProvider, LLMMessage
from app.brain.state_repository import StateRepository


class WowBrain(AgentRuntime):
    def __init__(
        self,
        llm_provider: LanguageModelProvider,
        context_engine: ContextEngine,
        state_repository: StateRepository,
    ):
        self._llm = llm_provider
        self._context_engine = context_engine
        self._state_repo = state_repository

    async def handle_input(
        self,
        *,
        user_id: str,
        text: str,
        conversation_id: str | None = None,
        caller_number: str | None = None,
    ) -> AgentAction:
        context = await self._context_engine.build_context(
            user_id=user_id,
            caller_number=caller_number,
            conversation_id=conversation_id,
        )

        messages = [LLMMessage(role="user", content=text)]
        llm_response = await self._llm.generate(
            messages,
            context={
                "contact": context.contact,
                "context_profile": context.context_profile,
                "recent_memories": context.recent_memories,
            },
        )

        previous_state = (
            await self._state_repo.get(
                user_id=user_id, key="turn_count", conversation_id=conversation_id
            )
            or {"count": 0}
        )
        turn_count = previous_state.get("count", 0) + 1

        await self._state_repo.set(
            user_id=user_id,
            key="turn_count",
            value={"count": turn_count},
            conversation_id=conversation_id,
        )
        await self._state_repo.set(
            user_id=user_id,
            key="last_intent",
            value={"intent": llm_response.intent, "text": text},
            conversation_id=conversation_id,
        )

        return AgentAction(
            type=llm_response.intent or "unknown",
            payload={
                "reply": llm_response.content,
                "turn_count": turn_count,
                "contact": context.contact,
                "context_profile": context.context_profile,
            },
        )
