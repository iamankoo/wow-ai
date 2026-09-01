"""WOW Brain v0 unit tests - use fakes for ContextEngine/StateRepository so
no database is required to verify the orchestration logic."""

import pytest

from app.brain.state_repository import InMemoryStateRepository
from app.brain.wow_brain import WowBrain
from app.interfaces.context_engine import ContextEngine, ConversationContext
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider


class FakeContextEngine(ContextEngine):
    def __init__(self, context: ConversationContext | None = None):
        self._context = context or ConversationContext(user_id="u1")

    async def build_context(
        self, *, user_id, caller_number=None, conversation_id=None
    ) -> ConversationContext:
        return self._context


@pytest.fixture
def brain() -> WowBrain:
    return WowBrain(
        RuleBasedLanguageModelProvider(),
        FakeContextEngine(),
        InMemoryStateRepository(),
    )


async def test_greeting_intent_is_classified(brain: WowBrain):
    action = await brain.handle_input(user_id="u1", text="Hi there!")
    assert action.type == "greeting"
    assert "reply" in action.payload


async def test_unknown_intent_falls_back(brain: WowBrain):
    action = await brain.handle_input(user_id="u1", text="qwertyuiop asdf")
    assert action.type == "unknown"


async def test_state_persists_turn_count_across_calls(brain: WowBrain):
    first = await brain.handle_input(user_id="u1", text="hello")
    second = await brain.handle_input(user_id="u1", text="bye")
    assert first.payload["turn_count"] == 1
    assert second.payload["turn_count"] == 2


async def test_take_message_intent(brain: WowBrain):
    action = await brain.handle_input(
        user_id="u1", text="Can you take a message for him?"
    )
    assert action.type == "take_message"
