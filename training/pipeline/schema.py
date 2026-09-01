"""Canonical raw-example schema for the v3+ dataset pipeline.

Every source (hand-authored batches, and any future vetted external
dataset) is adapted into this one shape before entering the pipeline -
normalization, language ID, PII scanning, dedup, quality scoring, and
splitting all operate on RawExample, never on a source-specific format.

Fields map onto the existing WOW taxonomy (training/wow_taxonomy.py /
backend/app/brain/taxonomy.py) - intent/context_mode/action are validated
against it (see label_validate.py), never a parallel label set.
"""

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

SCHEMA_VERSION = "3.0.0"


@dataclass
class RawExample:
    text: str
    language: str  # "en" | "hi" | "hinglish"
    intent: str
    context_mode: str | None = None
    action: str | None = None

    # Provenance
    source: str = "hand_authored"  # e.g. "hand_authored", or an external dataset id
    synthetic: bool = True         # False only for verbatim real (licensed, vetted) data
    collected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Hard-negative bookkeeping (see label_validate.py:validate_hard_negatives)
    hard_negative: bool = False
    confusable_pair: str | None = None  # e.g. "URGENT_CALL_vs_NON_URGENT_CALL"

    notes: str | None = None

    def example_id(self) -> str:
        """Stable content hash - the basis for exact-duplicate detection and
        a reproducible per-example identifier independent of file order.
        Uses the same normalization as dedup's exact-match key
        (normalize.normalize_for_comparison) so "Call Rahul." and
        "call rahul" hash identically."""
        from training.pipeline.normalize import normalize_for_comparison

        basis = f"{normalize_for_comparison(self.text)}|{self.language}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RawExample":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class QualityFlags:
    """Output of the quality pipeline for one example - see quality.py."""

    example_id: str
    language_consistent: bool
    valid_labels: bool
    has_pii: bool
    is_exact_duplicate: bool
    is_near_duplicate: bool
    length_ok: bool
    score: float  # 0.0-1.0
    status: str   # "pass" | "review" | "reject"
    reasons: list[str] = field(default_factory=list)
