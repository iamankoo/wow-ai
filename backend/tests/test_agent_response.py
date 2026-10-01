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


# --- Context-aware conversational composition (new this round) ---


def test_active_context_produces_a_grounded_reply_instead_of_the_generic_fallback():
    reply = generate_response(
        llm_content=None,
        verdict=PolicyVerdict.ALLOW,
        active_context_profile={"name": "SLEEPING", "user_instructions": None},
    )
    assert "not sure how to respond" not in reply
    assert "asleep" in reply.lower()


def test_context_reply_reflects_the_user_s_literal_ask_reason_instruction():
    """The whole point of this round: user_instructions actually changes
    the reply, not just sits stored in Postgres."""
    with_instruction = generate_response(
        llm_content=None,
        verdict=PolicyVerdict.ALLOW,
        active_context_profile={
            "name": "SLEEPING",
            "user_instructions": "Ask why they called, take a message, only mark urgent if necessary.",
        },
    )
    without_instruction = generate_response(
        llm_content=None,
        verdict=PolicyVerdict.ALLOW,
        active_context_profile={"name": "SLEEPING", "user_instructions": None},
    )

    assert with_instruction != without_instruction
    assert "what this is about" in with_instruction.lower()
    assert "help you with something" in without_instruction.lower()


def test_context_reply_reflects_each_real_context_mode_distinctly():
    replies = {
        mode: generate_response(
            llm_content=None,
            verdict=PolicyVerdict.ALLOW,
            active_context_profile={"name": mode, "user_instructions": None},
        )
        for mode in ("SLEEPING", "BUSY", "MEETING", "TRAVELLING")
    }
    assert len(set(replies.values())) == 4  # every mode gets real, distinct phrasing


def test_llm_content_still_wins_over_the_new_contextual_composition():
    reply = generate_response(
        llm_content="Real generated content.",
        verdict=PolicyVerdict.ALLOW,
        active_context_profile={"name": "SLEEPING", "user_instructions": "ask why"},
    )
    assert reply == "Real generated content."


def test_language_none_is_byte_identical_to_pre_multilingual_english_output():
    """Every existing caller of generate_response (language=None) must see
    exactly the same strings as before this round."""
    assert generate_response(llm_content=None, verdict=PolicyVerdict.CLARIFY) == (
        "Sorry, I didn't quite catch that - could you say it again?"
    )
    assert generate_response(llm_content=None, verdict=PolicyVerdict.REFUSE) == (
        "I'm not able to do that right now."
    )


# --- Multilingual (new this round) ---


def test_hindi_language_selects_real_hindi_templates():
    reply = generate_response(llm_content=None, verdict=PolicyVerdict.CLARIFY, language="hi")
    assert reply == "माफ़ कीजिए, मैं समझ नहीं पाया - क्या आप दोबारा कह सकते हैं?"


def test_hinglish_language_selects_real_hinglish_templates():
    reply = generate_response(llm_content=None, verdict=PolicyVerdict.CLARIFY, language="hi-Latn")
    assert reply == "Sorry, main samajh nahi paaya - kya aap dobara keh sakte hain?"


def test_unknown_language_code_falls_back_to_english_not_a_crash():
    reply = generate_response(llm_content=None, verdict=PolicyVerdict.CLARIFY, language="fr")
    assert reply == "Sorry, I didn't quite catch that - could you say it again?"


def test_action_template_is_language_aware():
    en = generate_response(llm_content="", verdict=PolicyVerdict.ALLOW, action="ASK_CALLER_REASON")
    hi = generate_response(
        llm_content="", verdict=PolicyVerdict.ALLOW, action="ASK_CALLER_REASON", language="hi"
    )
    hinglish = generate_response(
        llm_content="", verdict=PolicyVerdict.ALLOW, action="ASK_CALLER_REASON", language="hi-Latn"
    )
    assert en == "Could you tell me the reason for your call?"
    assert hi != en and hinglish != en and hi != hinglish


def test_context_reply_is_language_aware_in_all_three_languages():
    profile = {"name": "MEETING", "user_instructions": None}
    en = generate_response(llm_content=None, verdict=PolicyVerdict.ALLOW, active_context_profile=profile)
    hi = generate_response(
        llm_content=None, verdict=PolicyVerdict.ALLOW, active_context_profile=profile, language="hi"
    )
    hinglish = generate_response(
        llm_content=None,
        verdict=PolicyVerdict.ALLOW,
        active_context_profile=profile,
        language="hi-Latn",
    )
    assert len({en, hi, hinglish}) == 3
