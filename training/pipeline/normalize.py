"""Text normalization - the first pipeline stage. Deliberately conservative:
it standardizes representation without touching meaning or register (never
lowercases, never strips punctuation that carries meaning), since register
diversity (formal/casual/short/spoken) is a deliberate dataset property,
not noise to clean away.
"""

import re
import unicodedata

_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{2,}")


def normalize_text(text: str) -> str:
    """Unicode NFC normalization (canonicalizes Devanagari combining-mark
    sequences that can otherwise look identical but compare unequal),
    trims edge whitespace, and collapses runs of internal whitespace."""
    text = unicodedata.normalize("NFC", text)
    text = text.strip()
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_NEWLINE.sub("\n", text)
    return text


def normalize_for_comparison(text: str) -> str:
    """A more aggressive normalization used ONLY for duplicate-detection
    keys (dedup.py) - never used to alter stored text. Lowercases (ASCII/
    Latin case folding only affects en/hinglish; Devanagari has no case)
    and strips trailing sentence-ending punctuation, so "Call Rahul." and
    "call rahul" hash identically for exact-dup purposes."""
    text = normalize_text(text).lower()
    text = text.rstrip(".!?।،")
    text = _MULTI_SPACE.sub(" ", text).strip()
    return text
