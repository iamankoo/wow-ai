"""Richer dataset statistics for the v3+ pipeline schema - extends
training/preprocessing/stats.py's intent/action/context/language counts
with source/quality/synthetic/hard-negative breakdowns and the diversity
report, since RawExample carries fields the v0/v1/v1.1 pipeline's records
don't.
"""

from collections import Counter
from dataclasses import asdict

from training.pipeline.diversity import diversity_by_intent
from training.pipeline.quality import ScoredExample


def _distribution(items, key) -> dict:
    counts = Counter(key(x) for x in items if key(x) is not None)
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def compute_pipeline_stats(scored: list[ScoredExample]) -> dict:
    examples = [s.example for s in scored]
    status_counts = _distribution(scored, lambda s: s.flags.status)

    passing = [s.example for s in scored if s.flags.status == "pass"]

    return {
        "total_scored": len(scored),
        "status_distribution": status_counts,
        "passing_count": len(passing),
        "intent_distribution": _distribution(examples, lambda e: e.intent),
        "action_distribution": _distribution(examples, lambda e: e.action),
        "context_distribution": _distribution(examples, lambda e: e.context_mode),
        "language_distribution": _distribution(examples, lambda e: e.language),
        "source_distribution": _distribution(examples, lambda e: e.source),
        "synthetic_distribution": _distribution(examples, lambda e: e.synthetic),
        "hard_negative_count": sum(1 for e in examples if e.hard_negative),
        "confusable_pair_distribution": _distribution(
            [e for e in examples if e.hard_negative], lambda e: e.confusable_pair
        ),
        "pii_flagged_count": sum(1 for s in scored if s.flags.has_pii),
        "exact_duplicate_count": sum(1 for s in scored if s.flags.is_exact_duplicate),
        "near_duplicate_count": sum(1 for s in scored if s.flags.is_near_duplicate),
        "language_mismatch_count": sum(1 for s in scored if not s.flags.language_consistent),
        "avg_quality_score": round(sum(s.flags.score for s in scored) / len(scored), 3) if scored else None,
        "diversity_by_intent": [asdict(d) for d in diversity_by_intent(passing)],
    }
