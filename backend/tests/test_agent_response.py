"""generate_response: the seam between (model content, policy verdict, tool
outcome, resolved action) and the text WOW actually says - see
app/agent/response.py."""

from app.agent.policy import PolicyVerdict
from app.agent.response import CANCELLED_ACKNOWLEDGEMENT, generate_response


def test_allow_with_llm_content_returns_it_verbatim():
    reply = generate_response(llm_content="Sure, I can do that.", verdict=PolicyVerdict.ALLOW)
    assert reply == "Sure, I can do that."


def test_allow_with_no_content_and_no_action_returns_default_fallback():
    reply = generate_response(llm_content=None, verdict=PolicyVerdict.ALLOW)
    assert "not sure how to respond" in reply


def test_allow_with_no_content_uses_action_template_when_one_exists():
    reply = generate_response(llm_content="", verdict=PolicyVerdict.ALLOW, action="ASK_CALLER_REASON")
    assert reply == "Could you tell me the reason for your call?"


def test_allow_with_no_content_and_unmapped_action_falls_back_to_default():
    reply = generate_response(llm_content="", verdict=PolicyVerdict.ALLOW, action="SAVE_MEMORY")
    assert "not sure how to respond" in reply


def test_tool_failure_wins_over_llm_content_and_action_template():
    reply = generate_response(
        llm_content="I did it!",
        verdict=PolicyVerdict.ALLOW,
        tool_failed=True,
        action="ASK_CALLER_REASON",
    )
    assert "something went wrong" in reply


def test_clarify_verdict_uses_its_own_template_regardless_of_content():
    reply = generate_response(llm_content="ignored", verdict=PolicyVerdict.CLARIFY)
    assert "could you say it again" in reply.lower()


def test_refuse_verdict_uses_its_own_template():
    reply = generate_response(llm_content=None, verdict=PolicyVerdict.REFUSE)
    assert "not able to do that" in reply.lower()


def test_handoff_verdict_uses_its_own_template():
    reply = generate_response(llm_content=None, verdict=PolicyVerdict.HANDOFF)
    assert "right person" in reply.lower()


def test_confirmed_action_with_no_content_gets_the_confirmed_acknowledgement():
    reply = generate_response(llm_content=None, verdict=PolicyVerdict.ALLOW, confirmed=True)
    assert "taken care of" in reply.lower()


def test_confirmed_flag_wins_over_action_template():
    reply = generate_response(
        llm_content=None, verdict=PolicyVerdict.ALLOW, confirmed=True, action="ASK_CALLER_REASON"
    )
    assert "taken care of" in reply.lower()


def test_tool_failure_wins_over_confirmed_flag():
    reply = generate_response(
        llm_content=None, verdict=PolicyVerdict.ALLOW, confirmed=True, tool_failed=True
    )
    assert "something went wrong" in reply.lower()


def test_cancelled_acknowledgement_is_a_fixed_exported_string():
    assert CANCELLED_ACKNOWLEDGEMENT == "Okay, I won't do that."
