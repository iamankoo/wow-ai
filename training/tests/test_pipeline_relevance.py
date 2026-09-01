from training.pipeline.relevance import assess_relevance, _tokenize


def test_call_domain_english_text_is_relevant():
    r = assess_relevance("Are you calling Vivek about a report?")
    assert r.relevant is True
    assert "calling" in r.matched_keywords


def test_off_domain_english_text_is_not_relevant():
    r = assess_relevance("I need to make tea in the morning because I have to leave very early today.")
    assert r.relevant is False
    assert r.matched_keywords == []


def test_off_domain_devanagari_text_is_not_relevant():
    r = assess_relevance("मुझे सुबह चाय बनानी है क्योंकि आज बहुत जल्दी निकलना है।")
    assert r.relevant is False


def test_devanagari_multi_syllable_word_matches_correctly():
    """Regression test: Python's \\w-based regex splits Devanagari words at
    combining marks (matras/virama), silently corrupting tokenization -
    e.g. "उपलब्ध" (available) used to split into "उपलब" + "ध" and never
    match. _tokenize (whitespace-based) must keep it as one token."""
    r = assess_relevance("अभी अनिकेत उपलब्ध नहीं हैं, आप उनसे थोड़ी देर बाद बात कर सकते हैं।")
    assert r.relevant is True
    assert "उपलब्ध" in r.matched_keywords


def test_tokenize_preserves_devanagari_words_intact():
    tokens = _tokenize("अभी उपलब्ध नहीं हैं।")
    assert "उपलब्ध" in tokens


def test_tokenize_strips_edge_punctuation_not_internal_characters():
    tokens = _tokenize("Hello, call me please!")
    assert tokens == ["Hello", "call", "me", "please"]


def test_relevant_hinglish_call_scenario():
    r = assess_relevance("Aniket abhi so raha hai, kya message dena hai?")
    assert r.relevant is True


def test_empty_text_is_not_relevant():
    r = assess_relevance("")
    assert r.relevant is False
    assert r.matched_keywords == []
