"""interpret_confirmation: the deterministic yes/no matcher behind the
multi-turn clarification loop - see app/agent/confirmation.py."""

import pytest

from app.agent.confirmation import interpret_confirmation


@pytest.mark.parametrize(
    "text",
    ["yes", "Yes", "YES!", "yeah", "yep", "sure", "ok", "okay", "correct", "confirm", "go ahead", "yes please"],
)
def test_affirmative_replies_return_true(text):
    assert interpret_confirmation(text) is True


@pytest.mark.parametrize(
    "text",
    ["no", "No", "nope", "nah", "cancel", "cancel that", "never mind", "stop", "wrong"],
)
def test_negative_replies_return_false(text):
    assert interpret_confirmation(text) is False


@pytest.mark.parametrize(
    "text",
    ["I'm in a meeting", "call John instead", "what time is it", ""],
)
def test_unrelated_replies_return_none(text):
    assert interpret_confirmation(text) is None


def test_none_input_returns_none():
    assert interpret_confirmation(None) is None
