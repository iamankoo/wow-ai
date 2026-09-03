"""WOW Agent orchestrator - opt-in (`AGENT_RUNTIME=wow_agent`) - implements
the fuller multi-step flow from docs/ARCHITECTURE.md:

    state -> memory-aware context -> WOW Brain -> confidence/validation
          -> policy gate -> (authorized) tool execution -> response
          -> persisted state

versus `WowBrain` v0's straight-line 3-step flow (context -> generate ->
persist turn_count). It implements the same `AgentRuntime` contract, so
`app/api/routes/brain.py` needs zero changes to run either - selection is
one setting (`app.config.Settings.agent_runtime`), the same pattern already
used for `MODEL_PROVIDER` (`rule_based` default, `local_wow` opt-in).

Every step is defensive by design (see docs "Error handling"): a malformed
or out-of-taxonomy prediction is never trusted, low confidence never
authorizes a sensitive action, and a tool failure degrades to a spoken
apology rather than raising through to the caller.
"""

from app.agent.builtin_tools import (
    ClearContextTool,
    CollectMessageTool,
    CreateSummaryTool,
    DisableCallAssistantTool,
    EnableCallAssistantTool,
    MarkUrgentTool,
    SaveMemoryTool,
    SetContextTool,
)
from app.agent.context_profile_repository import ContextProfileRepository
from app.agent.user_settings_repository import UserSettingsRepository
from app.agent.policy import PolicyEngine, PolicyVerdict
from app.agent.response import generate_response
from app.agent.state import CallLifecycleStatus, ConversationState
from app.agent.summary_repository import SummaryRepository
from app.agent.tools import ToolContext, ToolRegistry
from app.brain.state_repository import StateRepository
from app.brain.taxonomy import Action, is_valid_action, is_valid_context
from app.interfaces.agent_runtime import AgentAction, AgentRuntime
from app.interfaces.context_engine import ContextEngine
from app.interfaces.feedback import FeedbackRepository, FeedbackStatus, FeedbackSubmission
from app.interfaces.llm import LanguageModelProvider, LLMMessage
from app.interfaces.memory_store import MemoryStore
from app.learning.confidence import ConfidencePolicy
from app.observability.logging import log_agent_turn
from app.observability.timing import StageTimings

_STATE_KEY = "conversation_state"

# Which tool (if any) a given resolved Action maps onto. Actions with no
# entry here are still reported to the caller (payload.candidate_action) but
# do not trigger a tool call - either because there is no side effect to
# perform (ASK_CALLER_REASON is purely conversational, see
# app.agent.response._ACTION_TEMPLATES; NO_ACTION is a no-op by definition),
# or because executing them needs real telephony (ANSWER_CALL, TRANSFER_CALL,
# END_CALL) that does not exist yet in this phase - reporting them without
# pretending to execute them is the honest option. This is every taxonomy
# action that can be given a genuine effect without telephony - see
# docs/implementation-status.md "Agent Core completion" for the full
# per-action rationale.
_ACTION_TOOL_MAP: dict[str, str] = {
    Action.SAVE_MEMORY.value: SaveMemoryTool.name,
    Action.CREATE_SUMMARY.value: CreateSummaryTool.name,
    Action.SET_CONTEXT.value: SetContextTool.name,
    Action.CLEAR_CONTEXT.value: ClearContextTool.name,
    Action.ENABLE_CALL_ASSISTANT.value: EnableCallAssistantTool.name,
    Action.DISABLE_CALL_ASSISTANT.value: DisableCallAssistantTool.name,
    Action.COLLECT_MESSAGE.value: CollectMessageTool.name,
    Action.MARK_URGENT.value: MarkUrgentTool.name,
}


def _first_slot(slots: dict, *names: str) -> str | None:
    for name in names:
        value = slots.get(name)
        if value:
            return value
    return None


def build_default_tool_registry(
    memory_store: MemoryStore,
    summary_repository: SummaryRepository,
    context_profile_repository: ContextProfileRepository,
    user_settings_repository: UserSettingsRepository,
) -> ToolRegistry:
    return ToolRegistry(
        [
            SaveMemoryTool(memory_store),
            CreateSummaryTool(summary_repository),
            SetContextTool(context_profile_repository),
            ClearContextTool(context_profile_repository),
            EnableCallAssistantTool(user_settings_repository),
            DisableCallAssistantTool(user_settings_repository),
            CollectMessageTool(memory_store),
            MarkUrgentTool(memory_store),
        ]
    )


class WowAgent(AgentRuntime):
    def __init__(
        self,
        llm_provider: LanguageModelProvider,
        context_engine: ContextEngine,
        state_repository: StateRepository,
        tool_registry: ToolRegistry,
        *,
        confidence_policy: ConfidencePolicy | None = None,
        policy_engine: PolicyEngine | None = None,
        feedback_repository: FeedbackRepository | None = None,
    ):
        self._llm = llm_provider
        self._context_engine = context_engine
        self._state_repo = state_repository
        self._tools = tool_registry
        self._confidence_policy = confidence_policy or ConfidencePolicy()
        self._policy = policy_engine or PolicyEngine()
        # Optional: when given, a low-confidence prediction is logged to the
        # active-learning review queue (docs/SELF_LEARNING.md) - never
        # required, and a failure here must never fail the turn (see
        # _log_for_review below).
        self._feedback_repo = feedback_repository

    async def handle_input(
        self,
        *,
        user_id: str,
        text: str,
        conversation_id: str | None = None,
        caller_number: str | None = None,
    ) -> AgentAction:
        timings = StageTimings()

        state = await self._load_state(user_id, conversation_id)
        state.lifecycle = CallLifecycleStatus.LISTENING
        state.current_text = text
        state.record_turn("caller", text)

        state.lifecycle = CallLifecycleStatus.THINKING
        with timings.measure("context"):
            context = await self._context_engine.build_context(
                user_id=user_id, caller_number=caller_number, conversation_id=conversation_id
            )
        state.contact = context.contact
        state.memory_results = [{"content": m} for m in context.recent_memories]

        with timings.measure("brain"):
            llm_response = await self._llm.generate(
                [LLMMessage(role="user", content=text)],
                context={
                    "contact": context.contact,
                    "context_profile": context.context_profile,
                    "recent_memories": context.recent_memories,
                },
            )

        confidence: dict = (llm_response.metadata or {}).get("confidence", {})
        assessment = self._confidence_policy.assess(
            intent_confidence=confidence.get("intent"),
            context_confidence=confidence.get("context_mode"),
            action_confidence=confidence.get("action"),
        )

        candidate_action = _first_slot(llm_response.slots, "action", "wow_action")
        if candidate_action is not None and not is_valid_action(candidate_action):
            # Never trust a prediction outside the known taxonomy, no
            # matter how confident the model claims to be.
            candidate_action = None
        context_mode = _first_slot(llm_response.slots, "context_mode", "wow_context_mode")
        if context_mode is not None and not is_valid_context(context_mode):
            context_mode = None
        state.candidate_action = candidate_action
        state.context_mode = context_mode
        state.intent = llm_response.intent
        state.confidence = confidence

        if assessment.needs_review:
            await self._log_for_review(
                user_id=user_id,
                conversation_id=conversation_id,
                text=text,
                intent=llm_response.intent,
                context_mode=context_mode,
                candidate_action=candidate_action,
                confidence=confidence,
                model_version=(llm_response.metadata or {}).get("model_version")
                or (llm_response.metadata or {}).get("provider"),
            )

        confidence_values = [v for v in confidence.values() if v is not None]
        overall_confidence = min(confidence_values) if confidence_values else None

        with timings.measure("policy"):
            decision = self._policy.evaluate(
                action=candidate_action,
                confidence_assessment=assessment,
                overall_confidence=overall_confidence,
                contact_known=state.contact is not None,
            )
        state.policy_decision = decision.verdict.value

        state.lifecycle = CallLifecycleStatus.RESPONDING
        tool_results: list[dict] = []
        tool_names: list[str] = []
        tool_failed = False
        if decision.verdict == PolicyVerdict.ALLOW and candidate_action:
            tool_name = _ACTION_TOOL_MAP.get(candidate_action)
            if tool_name == CreateSummaryTool.name and conversation_id is None:
                tool_results.append(
                    {"tool": tool_name, "success": False, "error": "no_conversation_id"}
                )
                tool_names.append(tool_name)
                tool_failed = True
            elif tool_name == SetContextTool.name and not context_mode:
                tool_results.append(
                    {"tool": tool_name, "success": False, "error": "no_context_mode"}
                )
                tool_names.append(tool_name)
                tool_failed = True
            elif tool_name:
                with timings.measure("tool"):
                    result = await self._tools.invoke(
                        tool_name,
                        ToolContext(
                            user_id=user_id,
                            conversation_id=conversation_id,
                            contact_id=state.contact["id"] if state.contact else None,
                        ),
                        _build_tool_arguments(tool_name, text, state),
                    )
                tool_results.append(
                    {"tool": tool_name, "success": result.success, "error": result.error}
                )
                tool_names.append(tool_name)
                tool_failed = not result.success
        state.tool_results = tool_results

        with timings.measure("response"):
            reply = generate_response(
                llm_content=llm_response.content,
                verdict=decision.verdict,
                tool_failed=tool_failed,
                action=candidate_action,
            )
        state.response_text = reply
        state.record_turn("assistant", reply)
        state.turn_count += 1
        state.lifecycle = CallLifecycleStatus.LISTENING

        await self._save_state(user_id, conversation_id, state)

        log_agent_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            intent=llm_response.intent,
            candidate_action=candidate_action,
            policy_decision=decision.verdict.value,
            policy_reason=decision.reason,
            tool_names=tool_names,
            tool_success=not tool_failed,
            durations_ms=timings.durations_ms,
        )

        return AgentAction(
            type=llm_response.intent or "unknown",
            payload={
                "reply": reply,
                "turn_count": state.turn_count,
                "contact": context.contact,
                "context_profile": context.context_profile,
                "candidate_action": candidate_action,
                "policy_decision": decision.verdict.value,
                "policy_reason": decision.reason,
                "tool_results": tool_results,
                "lifecycle": state.lifecycle.value,
                "durations_ms": timings.durations_ms,
            },
        )

    async def _load_state(self, user_id: str, conversation_id: str | None) -> ConversationState:
        raw = await self._state_repo.get(
            user_id=user_id, key=_STATE_KEY, conversation_id=conversation_id
        )
        if raw:
            return ConversationState.from_dict(raw)
        return ConversationState.new(user_id=user_id, conversation_id=conversation_id)

    async def _save_state(
        self, user_id: str, conversation_id: str | None, state: ConversationState
    ) -> None:
        await self._state_repo.set(
            user_id=user_id,
            key=_STATE_KEY,
            value=state.to_dict(),
            conversation_id=conversation_id,
        )

    async def _log_for_review(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
        text: str,
        intent: str | None,
        context_mode: str | None,
        candidate_action: str | None,
        confidence: dict,
        model_version: str | None,
    ) -> None:
        """Logs a low-confidence prediction to the active-learning review
        queue (docs/SELF_LEARNING.md). Never part of the turn's critical
        path: a repository failure here is swallowed, not raised - a
        missed review-queue entry is far cheaper than a failed call."""
        if self._feedback_repo is None:
            return
        try:
            await self._feedback_repo.create(
                FeedbackSubmission(
                    user_id=user_id,
                    text=text,
                    conversation_id=conversation_id,
                    predicted_intent=intent,
                    predicted_context_mode=context_mode,
                    predicted_action=candidate_action,
                    intent_confidence=confidence.get("intent"),
                    context_confidence=confidence.get("context_mode"),
                    action_confidence=confidence.get("action"),
                    model_version=model_version,
                    status=FeedbackStatus.NEEDS_REVIEW,
                )
            )
        except Exception:  # noqa: BLE001 - logging a review item must never fail the call
            pass


def _build_tool_arguments(tool_name: str, text: str, state: ConversationState) -> dict:
    if tool_name == SaveMemoryTool.name:
        return {"content": text}
    if tool_name == CreateSummaryTool.name:
        transcript_text = "\n".join(f"{t.speaker}: {t.text}" for t in state.transcript)
        return {"conversation_id": state.session_id, "summary_text": transcript_text}
    if tool_name == SetContextTool.name:
        return {"context_mode": state.context_mode}
    if tool_name in (ClearContextTool.name, EnableCallAssistantTool.name, DisableCallAssistantTool.name):
        return {}
    if tool_name in (CollectMessageTool.name, MarkUrgentTool.name):
        return {"content": text}
    return {}
