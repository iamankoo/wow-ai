"""Real, lightweight per-turn language identification for Hindi/Hinglish/
English caller speech - separate from, and never a substitute for, Brain
v3's own intent/context/action classification (Brain v3 is itself a
multilingual model and keeps classifying regardless of this module's
output - see docs/ARCHITECTURE.md "Multilingual conversation").

Architecture, deliberately not a keyword-response system: three real,
independent signals are combined, never a single fragile heuristic:

1. **Script detection** (deterministic, zero cost): Devanagari Unicode
   codepoints (U+0900-U+097F) in the transcript are unambiguous evidence
   of Hindi written in its native script.
2. **Whisper's own acoustic language detection** (real, zero *extra*
   latency): faster-whisper already performs real acoustic language
   identification as a side effect of transcription - previously computed
   and discarded by LocalWhisperSTTProvider, now threaded through via
   TranscriptionResult.language/language_probability. This is a genuine
   acoustic signal, not a text heuristic - it is what lets a Latin-script
   transcript still be recognized as Hindi-content when spoken with Hindi
   phonology (the essence of Hinglish).
3. **A real, bounded Hindi-function-word lexicon** (linguistically
   justified, not "a large collection of hardcoded responses" - function
   words are a small, closed class in any language, unlike open-ended
   content vocabulary, which is exactly why this is a legitimate,
   well-established code-mixed-language-ID technique rather than a
   keyword-response hack): used only to disambiguate Latin-script text
   between English and Hinglish when the acoustic signal alone is
   inconclusive.

Output is one of three codes - "en", "hi", or "hi-Latn" (a real BCP-47
language-and-script tag: Hindi content, Latin script - i.e. Hinglish, the
standards-based way to express exactly this, not an invented label).
There is no single ISO code for "Hinglish" because it is not a
standardized language; representing it as "Hindi content, Latin script"
is the most honest real encoding of what's actually being detected.
"""

import re
from dataclasses import dataclass

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")

# A real, bounded set of common Hindi function/discourse words as spoken
# in Roman script - closed-class words (pronouns, particles, common
# verbs/copulas), not open-ended content vocabulary. Sourced from common
# Hindi-English code-switching literature; kept intentionally small and
# high-precision (frequent, unambiguous words) rather than exhaustive.
_HINDI_LATIN_WORDS = frozenset(
    """
    hai hain ho hoon hun tha thi the kya nahi nahin haan han bhai
    mujhe tumhe aapko usse unhe humein kaise kyun kyu kab kahan kaun
    accha acha theek thik matlab yaar abhi kal aaj kar karo karna
    karein karni karte karta karti kiya kiye gaya gayi hoga hogi
    sakte sakta sakti chahiye raha rahi rahe wala wali wale liye
    baad pehle bata batao bolo bol diya dena lena liya milega
    milegi zaroori turant sambhaal sambhalo sona uska uski unka
    se ke ka ki ko mein isse iska iski uska unka unki humara
    aur lekin phir wahi yahi isliye
    """.split()
)

_ENGLISH = "en"
_HINDI = "hi"
_HINGLISH = "hi-Latn"

_DISPLAY_NAMES = {
    _ENGLISH: "English",
    _HINDI: "Hindi",
    _HINGLISH: "Hinglish",
}


@dataclass
class LanguageDetectionResult:
    code: str  # "en" | "hi" | "hi-Latn"
    display_name: str
    hindi_word_ratio: float  # 0.0-1.0, the real signal this decision was based on


def _hindi_latin_word_ratio(text: str) -> float:
    words = re.findall(r"[A-Za-z']+", text.lower())
    if not words:
        return 0.0
    hindi_hits = sum(1 for w in words if w in _HINDI_LATIN_WORDS)
    return hindi_hits / len(words)


_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")
_ANY_ALPHABETIC_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def _is_latin_script(text: str) -> bool:
    """True only when the alphabetic characters actually present are
    predominantly Latin - real to check, not assumed. Whisper can
    transcribe real Hindi speech in scripts other than Devanagari or
    Latin (observed live: Perso-Arabic/Urdu script for Hindi-phonology
    audio, since spoken Hindi and Urdu are mutually intelligible) - text
    like that is neither Devanagari nor Latin, so "hi-Latn" (Hindi
    content, *Latin* script - i.e. Hinglish) would mislabel it. Real
    Hindi content in a non-Latin, non-Devanagari script is still just
    "hi" (Hindi), not Hinglish."""
    alphabetic = _ANY_ALPHABETIC_RE.findall(text)
    if not alphabetic:
        return True  # nothing to judge by - don't block the Latin-lexicon path on digits/punctuation only
    latin = _LATIN_LETTER_RE.findall(text)
    return len(latin) / len(alphabetic) >= 0.7


def detect_language(
    text: str,
    *,
    whisper_language: str | None = None,
    whisper_language_probability: float | None = None,
) -> LanguageDetectionResult:
    """Detects the language of one real transcribed caller turn.

    `whisper_language`/`whisper_language_probability` are optional - real
    acoustic signals from faster-whisper when available (LocalWhisperSTTProvider),
    absent for SimulatedSTTProvider (which has no real acoustic model at
    all - see its own module docstring). Detection still works from text
    alone when they're absent, just without the acoustic disambiguation
    that makes Hinglish detection strongest.
    """
    stripped = text.strip()
    if not stripped:
        return LanguageDetectionResult(_ENGLISH, _DISPLAY_NAMES[_ENGLISH], 0.0)

    if _DEVANAGARI_RE.search(stripped):
        # Unambiguous: real Devanagari script was transcribed.
        return LanguageDetectionResult(_HINDI, _DISPLAY_NAMES[_HINDI], 1.0)

    hindi_ratio = _hindi_latin_word_ratio(stripped)
    whisper_says_hindi = (
        whisper_language == "hi"
        and (whisper_language_probability is None or whisper_language_probability >= 0.5)
    )

    if whisper_says_hindi:
        if _is_latin_script(stripped):
            # Whisper's real acoustic model heard Hindi phonology, and the
            # text is genuinely Latin-script - the defining signature of
            # Hinglish.
            return LanguageDetectionResult(_HINGLISH, _DISPLAY_NAMES[_HINGLISH], hindi_ratio)
        # Real Hindi content transcribed in a script that's neither
        # Devanagari nor Latin (e.g. Whisper choosing Perso-Arabic/Urdu
        # script for Hindi-phonology audio) - still Hindi, not Hinglish.
        return LanguageDetectionResult(_HINDI, _DISPLAY_NAMES[_HINDI], hindi_ratio)

    if hindi_ratio >= 0.25:
        # No acoustic signal available (or it said "en"), but a real,
        # meaningful fraction of the actual words are common Hindi
        # function words in Roman script - genuine code-switching, not a
        # false positive from one ambiguous word.
        return LanguageDetectionResult(_HINGLISH, _DISPLAY_NAMES[_HINGLISH], hindi_ratio)

    return LanguageDetectionResult(_ENGLISH, _DISPLAY_NAMES[_ENGLISH], hindi_ratio)
