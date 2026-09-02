"""Explicit, serializable conversation/session state for the WOW Agent
orchestrator (see docs/ARCHITECTURE.md "Agent state").

This is deliberately distinct from `app.models.agent_state.AgentState` (the
SQLAlchemy row): that table is a generic key/value blob store, this module
is the structured, typed object every WowAgent orchestration step reads and
writes explicitly. It is loaded from and persisted back to AgentState as a
plain JSON dict (see `ConversationStateStore`) - never held only in a
process-local variable, so a restart or a second replica never loses a
call's working state.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum


class CallLifecycleStatus(str, Enum):
    CREATED = "created"
    RINGING = "ringing"
    CONNECTED = "connected"
    LISTENING = "listening"
    THINKING = "thinking"
    RESPONDING = "responding"
    ENDING = "ending"
    ENDED = "ended"
    PROCESSING = "processing"
    STORED = "stored"
    EXPIRED = "expired"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ConversationTurn:
    speaker: str  # "caller" | "assistant"
    text: str
    at: str = field(default_factory=_now_iso)


@dataclass
class ConversationState:
    """The full working state for one call/session.

    Threaded explicitly through every WowAgent step (never a hidden
    global): each step receives the current state and returns the updated
    one, and the orchestrator is the only thing that persists it.
    """

    session_id: str
    user_id: str
    call_direction: str | None = None
    lifecycle: CallLifecycleStatus = CallLifecycleStatus.CREATED
    turn_count: int = 0
    transcript: list[ConversationTurn] = field(default_factory=list)
    current_text: str | None = None
    detected_language: str | None = None
    intent: str | None = None
    context_mode: str | None = None
    candidate_action: str | None = None
    selected_action: str | None = None
    memory_results: list[dict] = field(default_factory=list)
    contact: dict | None = None
    pending_tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    response_text: str | None = None
    policy_decision: str | None = None
    confidence: dict = field(default_factory=dict)
    updated_at: str = field(default_factory=_now_iso)

    def record_turn(self, speaker: str, text: str) -> None:
        self.transcript.append(ConversationTurn(speaker=speaker, text=text))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["lifecycle"] = self.lifecycle.value
        data["updated_at"] = _now_iso()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationState":
        raw_transcript = data.get("transcript") or []
        transcript = [
            ConversationTurn(
                speaker=t["speaker"], text=t["text"], at=t.get("at", _now_iso())
            )
            for t in raw_transcript
        ]
        known_fields = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in data.items() if k in known_fields}
        kwargs["transcript"] = transcript
        kwargs["lifecycle"] = CallLifecycleStatus(data.get("lifecycle", "created"))
        return cls(**kwargs)

    @classmethod
    def new(cls, *, user_id: str, conversation_id: str | None = None) -> "ConversationState":
        return cls(
            session_id=str(conversation_id) if conversation_id else str(uuid.uuid4()),
            user_id=str(user_id),
        )
