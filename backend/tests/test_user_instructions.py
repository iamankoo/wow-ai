"""app.agent.user_instructions - real directive extraction from the
owner's literal context instructions."""

from app.agent.user_instructions import parse_user_instructions


def test_none_or_blank_text_returns_all_false():
    result = parse_user_instructions(None)
    assert result == parse_user_instructions("")
    assert result.ask_caller_reason is False
    assert result.take_message is False
    assert result.mark_urgent_only_if_necessary is False
    assert result.raw_text is None


def test_the_product_spec_s_own_example_sentence():
    text = "I am sleeping. Ask why they called, take a message, and only mark it urgent if necessary."
    result = parse_user_instructions(text)

    assert result.ask_caller_reason is True
    assert result.take_message is True
    assert result.mark_urgent_only_if_necessary is True
    assert result.raw_text == text


def test_plain_instruction_with_no_directives_is_all_false():
    result = parse_user_instructions("I am in a meeting.")
    assert result.ask_caller_reason is False
    assert result.take_message is False


def test_do_not_disturb_phrase_is_detected():
    result = parse_user_instructions("I am sleeping, please do not disturb me unless it's urgent.")
    assert result.do_not_disturb is True


def test_take_message_alternate_phrasing():
    assert parse_user_instructions("leave a message for me").take_message is True
    assert parse_user_instructions("collect a message if they call").take_message is True


def test_ask_reason_alternate_phrasing():
    assert parse_user_instructions("find out why they are calling").ask_caller_reason is True
