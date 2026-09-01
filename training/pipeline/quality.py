"""Composite quality scoring - the pipeline stage that turns all the
individual checks (language consistency, label validity, PII, duplicates,
length) into one per-example status: "pass" (goes to the dataset),
"review" (flagged, needs a human look, excluded from the default
train/val/test build), or "reject" (excluded, reason recorded).

This never silently drops examples - every reject/review carries its
reasons, and the full scored set (not just the passing ones) is always
written to disk (see versioning.py) so nothing is thrown away un-audited.
"""

from dataclasses import dataclass

from training.pipeline.label_validate import validate_hard_negative, validate_labels
from training.pipeline.langid import detect_language
from training.pipeline.pii import scan_and_redact
from training.pipeline.schema import QualityFlags, RawExample

MIN_LENGTH = 2
MAX_LENGTH = 500


@dataclass
class ScoredExample:
    example: RawExample
    flags: QualityFlags
    redacted_text: str


def score_example(
    ex: RawExample,
    *,
    is_exact_duplicate: bool = False,
    is_near_duplicate: bool = False,
) -> ScoredExample:
    reasons: list[str] = []

    label_result = validate_labels(ex)
    if not label_result.valid:
        reasons.extend(label_result.errors)

    hard_neg_result = validate_hard_negative(ex)
    if not hard_neg_result.valid:
        reasons.extend(hard_neg_result.errors)

    lang = detect_language(ex.text, declared=ex.language)
    if not lang.matches_declared:
        reasons.append(
            f"language mismatch: declared '{ex.language}', heuristic detected "
            f"'{lang.detected}' (marker_ratio={lang.hindi_marker_ratio}, "
            f"devanagari_ratio={lang.devanagari_ratio})"
        )

    redacted_text, had_pii, pii_types = scan_and_redact(ex.text)
    if had_pii:
        reasons.append(f"PII detected and redacted: {', '.join(pii_types)}")

    length = len(ex.text.strip())
    length_ok = MIN_LENGTH <= length <= MAX_LENGTH
    if not length_ok:
        reasons.append(f"text length {length} outside [{MIN_LENGTH}, {MAX_LENGTH}]")

    if is_exact_duplicate:
        reasons.append("exact duplicate of an earlier example")
    if is_near_duplicate:
        reasons.append("near-duplicate of another example (see dedup report)")

    # Scoring: start at 1.0, subtract for each failed dimension. Hard
    # failures (invalid labels, duplicates) weigh more than soft ones
    # (language-heuristic mismatch, which is documented as approximate).
    score = 1.0
    if not label_result.valid:
        score -= 0.4
    if not hard_neg_result.valid:
        score -= 0.15
    if not lang.matches_declared:
        score -= 0.1
    if had_pii:
        score -= 0.15  # redacted, not fatal, but flagged for review
    if not length_ok:
        score -= 0.2
    if is_exact_duplicate:
        score -= 1.0
    if is_near_duplicate:
        score -= 0.5
    score = max(0.0, round(score, 3))

    if not label_result.valid or is_exact_duplicate or not length_ok:
        status = "reject"
    elif reasons:
        status = "review"
    else:
        status = "pass"

    return ScoredExample(
        example=ex,
        redacted_text=redacted_text,
        flags=QualityFlags(
            example_id=ex.example_id(),
            language_consistent=lang.matches_declared,
            valid_labels=label_result.valid,
            has_pii=had_pii,
            is_exact_duplicate=is_exact_duplicate,
            is_near_duplicate=is_near_duplicate,
            length_ok=length_ok,
            score=score,
            status=status,
            reasons=reasons,
        ),
    )


def score_batch(examples: list[RawExample]) -> list[ScoredExample]:
    from training.pipeline.dedup import find_exact_duplicates, find_near_duplicates

    exact_dup_indices = {j for _, j in find_exact_duplicates(examples)}
    near_dup_indices = {j for _, j, _ in find_near_duplicates(examples)}

    return [
        score_example(
            ex,
            is_exact_duplicate=i in exact_dup_indices,
            is_near_duplicate=i in near_dup_indices,
        )
        for i, ex in enumerate(examples)
    ]
