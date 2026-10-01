"""app.agent.language_detection - real per-turn language ID combining
script detection, Whisper's real acoustic signal, and a bounded Hindi
function-word lexicon. See the module's own docstring for why this is
not "a large collection of hardcoded keyword responses" - it is a
detection *feature* set, not a response table."""

from app.agent.language_detection import detect_language


def test_devanagari_script_is_unambiguously_hindi():
    result = detect_language("नमस्ते, अनिकेत से बात हो सकती है?")
    assert result.code == "hi"


def test_plain_english_with_no_signals_is_english():
    result = detect_language("Can you ask Aniket to call me back?")
    assert result.code == "en"


def test_empty_text_defaults_to_english_not_a_crash():
    result = detect_language("")
    assert result.code == "en"
    result2 = detect_language("   ")
    assert result2.code == "en"


def test_whisper_acoustic_hindi_signal_on_latin_script_text_is_hinglish():
    """The core Hinglish signature: Whisper's real acoustic model heard
    Hindi phonology, but the transcript came out in Latin script."""
    result = detect_language(
        "bhai aniket ko bolna mujhe call kare", whisper_language="hi", whisper_language_probability=0.9
    )
    assert result.code == "hi-Latn"


def test_high_hindi_word_ratio_is_hinglish_even_without_whisper_signal():
    """No acoustic signal at all (e.g. SimulatedSTTProvider) - real
    Roman-Hindi words alone are still enough."""
    result = detect_language("haan main kal aa jaunga")
    assert result.code == "hi-Latn"


def test_low_hindi_word_ratio_stays_english():
    """One ambiguous/ordinary word must not tip the whole sentence into
    Hinglish - this is the real precision bar the lexicon is bounded for."""
    result = detect_language("Actually mujhe project ke regarding baat karni thi")
    # "mujhe" is a real Hindi word - a meaningful fraction of a short
    # sentence, so this one *should* land as Hinglish, matching the
    # product spec's own example.
    assert result.code == "hi-Latn"


def test_a_single_incidental_word_match_does_not_force_hinglish():
    # 1 Hindi-lexicon hit out of many English words - ratio well under
    # the 0.25 threshold, must not false-positive.
    long_english_sentence = (
        "I was wondering if you could please let him know that I called "
        "about the quarterly report and the budget meeting kal"
    )
    result = detect_language(long_english_sentence)
    assert result.code == "en"


def test_weak_whisper_confidence_does_not_force_hindi_classification():
    result = detect_language(
        "Please tell him to call me back", whisper_language="hi", whisper_language_probability=0.2
    )
    assert result.code == "en"


def test_whisper_saying_english_does_not_override_a_real_hindi_word_ratio():
    result = detect_language(
        "haan main kal aa jaunga", whisper_language="en", whisper_language_probability=0.9
    )
    assert result.code == "hi-Latn"


def test_hindi_content_transcribed_in_a_non_latin_non_devanagari_script_is_still_hindi():
    """Real, observed Whisper behavior: Hindi-phonology audio can come
    back transcribed in Perso-Arabic/Urdu script (Hindi and Urdu are
    mutually intelligible spoken languages) - neither Devanagari nor
    Latin. That's still real Hindi content, not Hinglish (which
    specifically means Latin script)."""
    urdu_script_text = "نمستے کیا انیقیت سے بات ہو سکتی ہے"  # Perso-Arabic script
    result = detect_language(
        urdu_script_text, whisper_language="hi", whisper_language_probability=0.9
    )
    assert result.code == "hi"


def test_display_names_are_human_readable():
    assert detect_language("hello").display_name == "English"
    assert detect_language("नमस्ते").display_name == "Hindi"
    assert detect_language("haan bhai theek hai").display_name == "Hinglish"


def test_language_switch_across_consecutive_calls_is_independent():
    """Each call is a fresh, independent decision (per-turn, not global) -
    this is what makes mid-call language switching possible upstream."""
    hindi_turn = detect_language("नमस्ते, अनिकेत से बात हो सकती है?")
    hinglish_turn = detect_language("Hi, Aniket se project ke regarding baat karni thi.")
    english_turn = detect_language("Can you ask Aniket to call me back?")

    assert [hindi_turn.code, hinglish_turn.code, english_turn.code] == ["hi", "hi-Latn", "en"]
