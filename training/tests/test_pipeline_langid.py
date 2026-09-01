from training.pipeline.langid import detect_language


def test_devanagari_text_detected_as_hi():
    r = detect_language("मैं सो रहा हूँ।", declared="hi")
    assert r.detected == "hi"
    assert r.matches_declared


def test_plain_english_detected_as_en():
    r = detect_language("Call Rahul for me.", declared="en")
    assert r.detected == "en"
    assert r.matches_declared


def test_roman_hindi_with_english_loanwords_still_detected_as_hi():
    r = detect_language("Main so raha hoon, calls sambhaal lena.", declared="hi")
    assert r.detected == "hi"


def test_code_mixed_text_detected_as_hinglish():
    r = detect_language("Bhai mere calls handle kar lena thodi der.", declared="hinglish")
    assert r.detected == "hinglish"


def test_matches_declared_is_true_when_no_declared_language_given():
    r = detect_language("anything", declared=None)
    assert r.matches_declared is True


def test_matches_declared_false_on_mismatch():
    r = detect_language("मैं सो रहा हूँ।", declared="en")
    assert r.matches_declared is False


def test_neutral_loanwords_dont_cause_false_english_positive():
    # "Set my status to busy." is pure English despite "status"/"busy" being
    # common in Hindi text too - shouldn't misfire due to the neutral list.
    r = detect_language("Set my status to busy.", declared="en")
    assert r.detected == "en"
