"""Lightweight, rule-based language identification for en/hi/hinglish.

This is NOT a claim of ML-grade language detection. It exists to catch a
specific, real failure mode: an example mislabeled as the wrong language
(e.g. tagged "en" but is actually Hindi, or tagged "hi" for a sentence
that's really code-mixed hinglish). It is deliberately conservative,
documented, and used as a *consistency check* against the declared label
(flagging mismatches for review) rather than as ground truth that silently
overwrites what a human author declared - see docs/DATASET.md "Language
classification" for why, and its known limitations.

Method: Devanagari-script ratio for "hi" (script-based, high confidence).
For Latin-script text, a curated list of common Romanized-Hindi function
words/particles (postpositions, verb forms, pronouns) - present + no/few
would give "hi" (Roman Hindi), present + significant English content gives
"hinglish", absent gives "en".
"""

import re
from dataclasses import dataclass

_DEVANAGARI_RANGE = range(0x0900, 0x097F + 1)

# Common Romanized-Hindi function words/particles - postpositions, copulas,
# pronouns, common verb forms. Deliberately high-frequency, low-ambiguity
# words (not content words, which are far more likely to be borrowed/
# ambiguous between languages).
## NOTE: deliberately excludes short words that collide with extremely
## common English words ("to", "the", "is", "a", "so") even though Hindi/
## Hinglish equivalents exist - those collisions cause more false positives
## on English text than they gain on Hindi text. See docs/DATASET.md.
_HINDI_MARKERS = frozenset("""
hai hain hoon hun tha thi raha rahi rahe rha
nahi nahin kya kaun kaha kahan kab kyun kyu kaise kitna kitni
mein mai main tum aap hum tumhe aapko humein unhe usse ise isse unse
ka ki ke ko se pe par tak bhi
karo kardo karna kiya kijiye kijiyega karenge karega karegi
liye wala wali wale
abhi yeh ye woh wo yahan wahan waha
bhai yaar beta didi bhaiya
zaroori jaldi turant thoda thodi bahut kaafi
sambhal sambhalo sambhaal bata batao bolo dena lena
gaya gayi gaye paunga paoge
""".split())

# Common English loanwords used constantly in everyday spoken Hindi
# (especially in a phone/call-assistant domain) - excluded from the
# denominator entirely rather than counted as "English signal", since
# using them doesn't make a sentence any less Hindi in practice.
_NEUTRAL_LOANWORDS = frozenset("""
call calls message number phone office meeting status mode busy normal
ok okay please sorry thanks thank you time minute minutes hour
""".split())

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass
class LanguageAssessment:
    detected: str            # "en" | "hi" | "hinglish"
    devanagari_ratio: float
    hindi_marker_ratio: float
    matches_declared: bool


def _devanagari_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    devanagari = sum(1 for c in letters if ord(c) in _DEVANAGARI_RANGE)
    return devanagari / len(letters)


def _hindi_marker_ratio(text: str) -> float:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    counted = [w for w in words if w not in _NEUTRAL_LOANWORDS]
    if not counted:
        return 0.0
    hits = sum(1 for w in counted if w in _HINDI_MARKERS)
    return hits / len(counted)


def detect_language(text: str, declared: str | None = None) -> LanguageAssessment:
    dev_ratio = _devanagari_ratio(text)
    marker_ratio = _hindi_marker_ratio(text)

    if dev_ratio > 0.3:
        detected = "hi"
    elif marker_ratio == 0.0:
        detected = "en"
    elif marker_ratio >= 0.5:
        detected = "hi"
    else:
        detected = "hinglish"

    return LanguageAssessment(
        detected=detected,
        devanagari_ratio=round(dev_ratio, 3),
        hindi_marker_ratio=round(marker_ratio, 3),
        matches_declared=(declared is None or detected == declared),
    )
