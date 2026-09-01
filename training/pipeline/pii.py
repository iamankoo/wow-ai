"""PII detection/removal for the dataset pipeline - reuses
backend/app/learning/privacy_filter.py's RegexPrivacyFilter rather than
reimplementing redaction logic, so training data and production feedback
data (see docs/SELF_LEARNING.md) go through the exact same PII rules.
"""

import sys
from pathlib import Path

from training.training.config import REPO_ROOT

BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.learning.privacy_filter import RegexPrivacyFilter  # noqa: E402

_filter = RegexPrivacyFilter()


def scan_and_redact(text: str) -> tuple[str, bool, list[str]]:
    """Returns (redacted_text, had_pii, redaction_types). See
    RegexPrivacyFilter's docstring for what this catches (phones, emails,
    card-like digit runs, OTP/PIN codes) and its documented limitations
    (regex-based, not NER - won't catch a bare name in prose)."""
    result = _filter.redact(text)
    return result.redacted_text, result.was_modified, result.redaction_types
