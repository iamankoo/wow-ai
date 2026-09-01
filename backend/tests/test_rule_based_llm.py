import pytest

from app.interfaces.llm import LLMMessage
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider


@pytest.fixture
def provider() -> RuleBasedLanguageModelProvider:
    return RuleBasedLanguageModelProvider()


@pytest.mark.parametrize(
    "text,expected_intent",
    [
        ("Hello!", "greeting"),
        ("Can I schedule a callback for tomorrow?", "schedule_callback"),
        ("Is she available right now?", "check_availability"),
        ("Okay, goodbye", "goodbye"),
        ("xyz nonsense input", "unknown"),
    ],
)
async def test_intent_classification(provider, text, expected_intent):
    response = await provider.generate([LLMMessage(role="user", content=text)])
    assert response.intent == expected_intent
    assert response.content
