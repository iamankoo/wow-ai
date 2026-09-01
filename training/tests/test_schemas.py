"""Schema tests for the expanded (v1) dataset examples.

Run from the repo root: python -m pytest training/tests
"""

import pytest
from pydantic import ValidationError

from training.datasets.schemas.call_scenario_example import CallScenarioExample
from training.datasets.schemas.intent_example import IntentExample
from training.wow_taxonomy import Action, CallerRelationship, ContextMode, Intent


def test_intent_example_accepts_a_valid_record():
    ex = IntentExample(
        text="I'm busy right now, take messages instead.",
        language="en",
        intent=Intent.SET_CONTEXT,
        context_mode=ContextMode.BUSY,
        action=Action.SET_CONTEXT,
    )
    assert ex.intent == Intent.SET_CONTEXT
    assert ex.context_mode == ContextMode.BUSY


def test_intent_example_rejects_blank_text():
    with pytest.raises(ValidationError):
        IntentExample(text="   ", language="en", intent=Intent.UNKNOWN)


def test_intent_example_rejects_unknown_intent_string():
    with pytest.raises(ValidationError):
        IntentExample(text="hello", language="en", intent="NOT_A_REAL_INTENT")


def test_intent_example_rejects_unsupported_language():
    with pytest.raises(ValidationError):
        IntentExample(text="hello", language="fr", intent=Intent.GENERAL_CONVERSATION)


def test_intent_example_optional_fields_default_sensibly():
    ex = IntentExample(text="hi", language="en", intent=Intent.GENERAL_CONVERSATION)
    assert ex.context_mode is None
    assert ex.action is None
    assert ex.parameters == {}
    assert ex.notes is None


def test_call_scenario_example_accepts_a_valid_record():
    ex = CallScenarioExample(
        caller_description="Caller is saved as 'Mom' in contacts.",
        caller_relationship=CallerRelationship.FAMILY,
        language="en",
        expected_intent=Intent.KNOWN_CALLER,
        expected_action=Action.ANSWER_CALL,
        urgency="urgent",
    )
    assert ex.caller_relationship == CallerRelationship.FAMILY


def test_call_scenario_example_rejects_invalid_urgency():
    with pytest.raises(ValidationError):
        CallScenarioExample(
            caller_description="x",
            caller_relationship=CallerRelationship.UNKNOWN,
            language="en",
            expected_intent=Intent.UNKNOWN_CALLER,
            expected_action=Action.END_CALL,
            urgency="kind_of_urgent",
        )


def test_save_memory_is_a_valid_action_on_general_conversation():
    ex = IntentExample(
        text="Just so you know, I moved to Pune last month.",
        language="en",
        intent=Intent.GENERAL_CONVERSATION,
        action=Action.SAVE_MEMORY,
    )
    assert ex.action == Action.SAVE_MEMORY
