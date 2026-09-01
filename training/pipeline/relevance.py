"""WOW-domain relevance heuristic - a lightweight lexical scorer, same
spirit and same documented limitations as langid.py: not ML-grade, used to
*bucket* large volumes of ingested text for human review, never to
silently delete anything. WOW is a real-time personal call/voice
assistant, not a generic chatbot - this exists to answer "how much of a
large ingested source is actually about call-handling" without reading
every row by hand.

Method: keyword presence across an English/Devanagari-Hindi/Romanized-
Hindi-Hinglish lexicon covering the call-assistant domain (call handling,
caller identification, urgency, context/mode switching, messages,
scheduling, spam/scam). A hit on any keyword marks a row "directly
relevant"; no hits marks it "ambiguous_or_irrelevant" - deliberately a
binary bucket rather than a fake-precision score, since a keyword-absence
signal is much weaker evidence than a keyword-presence one.

Tokenization deliberately does NOT use `\\w`/`\\W` regex classes: Python's
Unicode `\\w` excludes combining marks (category Mn), which is exactly what
Devanagari matras (ी, ु, ि, ...) and virama (्) are - `re.findall(r"\\w+", ...)`
silently splits "अभी" into "अभ" + a dropped "ी" and "उपलब्ध" into "उपलब" + "ध"
with the ् dropped, corrupting every multi-syllable Devanagari word. Verified
by hand while calibrating this module. Tokenizing on whitespace and manually
stripping edge punctuation avoids the bug entirely.
"""

import unicodedata
from dataclasses import dataclass

_EDGE_PUNCT = ".,!?;:()\"'“”‘’।،…-–—[]{}"

# English + Romanized Hindi/Hinglish call-domain terms.
_DOMAIN_KEYWORDS_LATIN = frozenset("""
call calls caller callers calling phone ring rings ringing dial dialing
message messages messaging busy meeting meetings sleep sleeping asleep
travel travelling traveling driving urgent emergency available unavailable
context mode modes handle handling handler assistant transfer transferred
hold callback callbacks schedule scheduled scheduling appointment
appointments cancel cancelled cancelling summary summarize summarizing
contact contacts known unknown spam scam fraud fraudulent otp pin bank
family friend friends colleague colleagues office reachable unreachable
answer answering respond reply voicemail missed redial reject rejected
sambhal sambhalo sambhalna uthana lena dena connect kar karo
zaroori jaroori turant abhi baad callkaro
""".split())

# Devanagari call-domain terms.
_DOMAIN_KEYWORDS_DEVANAGARI = frozenset("""
कॉल कॉल्स फोन घंटी संदेश व्यस्त मीटिंग सोना सो सोया सोई सोते सोए सोती
यात्रा सफर आपातकाल जरूरी ज़रूरी उपलब्ध अनुपलब्ध संभाल संभालो संभालना संभालूं
सहायक स्थानांतरण होल्ड अपॉइंटमेंट शेड्यूल रद्द सारांश संपर्क परिचित अनजान
धोखाधड़ी फ्रॉड बैंक परिवार दोस्त सहकर्मी ऑफिस पहुंच पहुँच जवाब कॉलबैक छूटी
""".split())


@dataclass
class RelevanceAssessment:
    relevant: bool
    matched_keywords: list[str]


def _tokenize(text: str) -> list[str]:
    """Whitespace-split with manual edge-punctuation stripping - safe for
    Devanagari (see module docstring), unlike a \\w-based regex."""
    tokens = []
    for raw in text.split():
        w = raw.strip(_EDGE_PUNCT)
        if w:
            tokens.append(w)
    return tokens


def assess_relevance(text: str) -> RelevanceAssessment:
    text = unicodedata.normalize("NFC", text)
    tokens = _tokenize(text)

    matched = sorted({w.lower() for w in tokens} & _DOMAIN_KEYWORDS_LATIN)
    devanagari_tokens = {w for w in tokens if any(0x0900 <= ord(c) <= 0x097F for c in w)}
    matched.extend(sorted(devanagari_tokens & _DOMAIN_KEYWORDS_DEVANAGARI))

    return RelevanceAssessment(relevant=bool(matched), matched_keywords=matched)
