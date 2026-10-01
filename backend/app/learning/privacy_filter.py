"""Regex-based PII redaction.

This is defense-in-depth, not a guarantee: regex pattern matching will miss
PII that doesn't match a known shape (a name in running text, an address)
and can occasionally over-redact (a long non-PII number). It exists to
catch the common, high-confidence cases - phone numbers, emails, card-like
digit sequences, OTP/PIN codes - before anything reaches a human reviewer
or a training file. See docs/SELF_LEARNING.md "Privacy filter limitations"
for what this deliberately does not attempt (NER-based name detection,
address detection).
"""

import re

from app.interfaces.feedback import PrivacyFilter, RedactionResult

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    # Phone numbers: optional +country code, then 8-15 digits with optional
    # separators (spaces/hyphens/dots) - covers Indian mobile numbers
    # (+91 98765 43210), US-style, and plain 10-digit runs.
    ("phone_number", re.compile(r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?(?:\d[-.\s]?){8,14}\d(?!\d)")),
    # Card-like 13-19 digit sequences (with or without separators) - catches
    # what the phone pattern above wouldn't (very long digit runs).
    ("card_number", re.compile(r"(?<!\d)(?:\d[-\s]?){13,19}\d(?!\d)")),
    # OTP/PIN codes: a 4-8 digit number appearing within a few words of
    # "otp"/"pin"/"code" (either order), case-insensitive.
    ("otp_or_pin",
     re.compile(r"\b(?:otp|pin|code)\b[^\d]{0,15}\b\d{4,8}\b|\b\d{4,8}\b[^\d]{0,15}\b(?:otp|pin|code)\b", re.I)),
]


# Pattern names that are credentials/financial secrets with no legitimate
# reason to sit in a stored call transcript (unlike a callback phone number
# or email, which the owner needs). See app/agent/call_recorder.py.
SENSITIVE_STORAGE_PATTERNS = frozenset({"card_number", "otp_or_pin"})


class RegexPrivacyFilter(PrivacyFilter):
    def __init__(self, only: frozenset[str] | None = None):
        """`only` restricts redaction to the named patterns (default: all)."""
        self._only = only

    def redact(self, text: str) -> RedactionResult:
        redacted = text
        types: list[str] = []
        for name, pattern in _PATTERNS:
            if self._only is not None and name not in self._only:
                continue
            if pattern.search(redacted):
                types.append(name)
                redacted = pattern.sub(f"[REDACTED_{name.upper()}]", redacted)
        return RedactionResult(
            redacted_text=redacted,
            was_modified=redacted != text,
            redaction_types=types,
        )
