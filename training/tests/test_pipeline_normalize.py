from training.pipeline.normalize import normalize_for_comparison, normalize_text


def test_normalize_text_trims_and_collapses_whitespace():
    assert normalize_text("  hello   world  ") == "hello world"


def test_normalize_text_preserves_case_and_punctuation():
    assert normalize_text("Call Rahul, please!") == "Call Rahul, please!"


def test_normalize_for_comparison_lowercases_and_strips_trailing_punct():
    assert normalize_for_comparison("Call Rahul.") == "call rahul"
    assert normalize_for_comparison("call rahul") == "call rahul"


def test_normalize_for_comparison_handles_devanagari_danda():
    assert normalize_for_comparison("नमस्ते।") == normalize_for_comparison("नमस्ते")
