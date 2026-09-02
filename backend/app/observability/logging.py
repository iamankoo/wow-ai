"""Structured, PII-safe logging for one agent turn (see docs
"Observability" / "Privacy").

`log_agent_turn`'s signature deliberately has no `text`/`reply`/transcript
parameter - IDs, enums, booleans, and numbers only - so a caller cannot
accidentally log conversation content through it. If a future caller needs
to log free text for debugging, it must go through `RegexPrivacyFilter`
first and use a distinctly-named function so it's never confused with this
one's "always safe by construction" guarantee.
"""

import logging

logger = logging.getLogger("wow_ai.agent")


def log_agent_turn(
    *,
    user_id: str,
    conversation_id: str | None,
    intent: str | None,
    candidate_action: str | None,
    policy_decision: str | None,
    policy_reason: str | None,
    tool_names: list[str],
    tool_success: bool,
    durations_ms: dict[str, float],
) -> None:
    logger.info(
        "agent_turn",
        extra={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "intent": intent,
            "candidate_action": candidate_action,
            "policy_decision": policy_decision,
            "policy_reason": policy_reason,
            "tool_names": tool_names,
            "tool_success": tool_success,
            "durations_ms": durations_ms,
        },
    )
