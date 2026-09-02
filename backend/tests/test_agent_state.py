"""ConversationState serialization round-trip tests - see app/agent/state.py."""

from app.agent.state import CallLifecycleStatus, ConversationState


def test_new_state_defaults():
    state = ConversationState.new(user_id="u1", conversation_id="c1")
    assert state.session_id == "c1"
    assert state.user_id == "u1"
    assert state.lifecycle == CallLifecycleStatus.CREATED
    assert state.turn_count == 0
    assert state.transcript == []


def test_new_state_without_conversation_id_generates_session_id():
    state = ConversationState.new(user_id="u1")
    assert state.session_id
    assert state.session_id != "u1"


def test_record_turn_appends_transcript():
    state = ConversationState.new(user_id="u1", conversation_id="c1")
    state.record_turn("caller", "hello")
    state.record_turn("assistant", "hi there")
    assert [t.speaker for t in state.transcript] == ["caller", "assistant"]
    assert [t.text for t in state.transcript] == ["hello", "hi there"]


def test_to_dict_from_dict_round_trip():
    state = ConversationState.new(user_id="u1", conversation_id="c1")
    state.lifecycle = CallLifecycleStatus.THINKING
    state.record_turn("caller", "hello")
    state.intent = "GENERAL_CONVERSATION"
    state.confidence = {"intent": 0.9}
    state.turn_count = 3

    restored = ConversationState.from_dict(state.to_dict())

    assert restored.session_id == state.session_id
    assert restored.lifecycle == CallLifecycleStatus.THINKING
    assert restored.intent == "GENERAL_CONVERSATION"
    assert restored.confidence == {"intent": 0.9}
    assert restored.turn_count == 3
    assert len(restored.transcript) == 1
    assert restored.transcript[0].speaker == "caller"
    assert restored.transcript[0].text == "hello"


def test_to_dict_is_json_serializable():
    import json

    state = ConversationState.new(user_id="u1", conversation_id="c1")
    state.record_turn("caller", "hello")
    json.dumps(state.to_dict())  # must not raise
