"""Semantic/structural diversity scoring per label.

Real semantic diversity measurement (are these examples actually different
*ideas*, not just different words) needs embeddings, which this pipeline
deliberately doesn't depend on (see docs/DATASET.md "Scaling strategy" for
when that tradeoff should be revisited). This module measures a proxy that
is cheap and genuinely informative at this dataset's size: average
pairwise character-shingle similarity within a label's examples, and
vocabulary richness (type-token ratio). A label with low pairwise
similarity and high TTR is lexically/structurally diverse; a label that
looks like the same sentence with one word swapped repeatedly (the
templating pattern this whole pipeline exists to catch) will score high
similarity and low TTR.
"""

import random
from collections import defaultdict
from dataclasses import dataclass

from training.pipeline.dedup import _jaccard, _shingles
from training.pipeline.normalize import normalize_for_comparison
from training.pipeline.schema import RawExample

MAX_PAIRS_SAMPLED = 200  # caps the O(n^2) cost for large labels


@dataclass
class LabelDiversity:
    label: str
    count: int
    avg_pairwise_similarity: float
    type_token_ratio: float
    templating_risk: str  # "low" | "medium" | "high"


def _type_token_ratio(texts: list[str]) -> float:
    tokens = []
    for t in texts:
        tokens.extend(normalize_for_comparison(t).split())
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def _avg_pairwise_similarity(texts: list[str], seed: int = 42) -> float:
    if len(texts) < 2:
        return 0.0
    shingle_sets = [_shingles(t) for t in texts]
    n = len(shingle_sets)
    all_pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    if len(all_pairs) > MAX_PAIRS_SAMPLED:
        rng = random.Random(seed)
        all_pairs = rng.sample(all_pairs, MAX_PAIRS_SAMPLED)
    sims = [_jaccard(shingle_sets[i], shingle_sets[j]) for i, j in all_pairs]
    return sum(sims) / len(sims) if sims else 0.0


def diversity_by_intent(examples: list[RawExample]) -> list[LabelDiversity]:
    by_label: dict[str, list[str]] = defaultdict(list)
    for ex in examples:
        by_label[ex.intent].append(ex.text)

    reports = []
    for label, texts in sorted(by_label.items()):
        avg_sim = _avg_pairwise_similarity(texts)
        ttr = _type_token_ratio(texts)
        if avg_sim > 0.45 or ttr < 0.2:
            risk = "high"
        elif avg_sim > 0.25 or ttr < 0.35:
            risk = "medium"
        else:
            risk = "low"
        reports.append(LabelDiversity(
            label=label, count=len(texts),
            avg_pairwise_similarity=round(avg_sim, 3),
            type_token_ratio=round(ttr, 3),
            templating_risk=risk,
        ))
    return reports
