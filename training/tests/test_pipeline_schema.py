from training.pipeline.schema import RawExample


def test_example_id_is_stable_for_identical_text_and_language():
    a = RawExample(text="Call Rahul.", language="en", intent="CALL_PERSON")
    b = RawExample(text="Call Rahul.", language="en", intent="CALL_PERSON")
    assert a.example_id() == b.example_id()


def test_example_id_is_case_and_whitespace_insensitive():
    a = RawExample(text="Call Rahul.", language="en", intent="CALL_PERSON")
    b = RawExample(text="  call rahul.  ", language="en", intent="CALL_PERSON")
    assert a.example_id() == b.example_id()


def test_example_id_differs_by_language():
    a = RawExample(text="hai", language="en", intent="UNKNOWN")
    b = RawExample(text="hai", language="hi", intent="UNKNOWN")
    assert a.example_id() != b.example_id()


def test_to_dict_and_from_dict_round_trip():
    ex = RawExample(
        text="Urgent hai yaar.", language="hinglish", intent="URGENT_CALL",
        action="MARK_URGENT", hard_negative=True, confusable_pair="URGENT_CALL_vs_NON_URGENT_CALL",
        notes="test",
    )
    restored = RawExample.from_dict(ex.to_dict())
    assert restored == ex


def test_from_dict_ignores_unknown_fields():
    d = {"text": "x", "language": "en", "intent": "UNKNOWN", "unexpected_field": 123}
    ex = RawExample.from_dict(d)
    assert ex.text == "x"
