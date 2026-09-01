"""Exact and near-duplicate detection.

Exact: content-hash based (normalize_for_comparison + language), O(n) via a
seen-set - this is what scales to millions of examples cheaply.

Near-duplicate: character-shingle Jaccard similarity. This is a real,
lightweight technique (no embeddings/ML dependency), but it's O(n^2) in the
naive form used here, so it's bucketed by (language, first-shingle) to keep
comparisons local rather than all-pairs - still not embedding-based
semantic similarity. See docs/DATASET.md "Deduplication" for the documented
limitation (catches near-identical phrasing, not paraphrases with the same
meaning in different words) and the scaling note for what would replace
this at real 1M+ scale (MinHash/LSH or embedding-based ANN search).
"""

from collections import defaultdict
from dataclasses import dataclass

from training.pipeline.normalize import normalize_for_comparison
from training.pipeline.schema import RawExample

NEAR_DUP_THRESHOLD = 0.85
SHINGLE_SIZE = 4


@dataclass
class DedupReport:
    total: int
    exact_duplicates: list[tuple[int, int]]   # (kept_index, duplicate_index)
    near_duplicates: list[tuple[int, int, float]]  # (index_a, index_b, similarity)
    unique_count: int


def _shingles(text: str, n: int = SHINGLE_SIZE) -> set[str]:
    text = normalize_for_comparison(text)
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_exact_duplicates(examples: list[RawExample]) -> list[tuple[int, int]]:
    """Returns (first_index, duplicate_index) pairs - the duplicate_index
    entries are what a caller would drop, keeping the first occurrence."""
    seen: dict[str, int] = {}
    duplicates = []
    for i, ex in enumerate(examples):
        key = ex.example_id()
        if key in seen:
            duplicates.append((seen[key], i))
        else:
            seen[key] = i
    return duplicates


def find_near_duplicates(
    examples: list[RawExample], threshold: float = NEAR_DUP_THRESHOLD
) -> list[tuple[int, int, float]]:
    """Buckets by (language, first shingle) so only plausibly-similar pairs
    are ever compared - not a full O(n^2) scan."""
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    shingle_cache: dict[int, set[str]] = {}

    for i, ex in enumerate(examples):
        shingles = _shingles(ex.text)
        shingle_cache[i] = shingles
        if not shingles:
            continue
        bucket_key = (ex.language, next(iter(sorted(shingles))))
        buckets[bucket_key].append(i)

    seen_pairs: set[tuple[int, int]] = set()
    results: list[tuple[int, int, float]] = []
    for indices in buckets.values():
        if len(indices) < 2:
            continue
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                i, j = indices[a], indices[b]
                pair = (min(i, j), max(i, j))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                sim = _jaccard(shingle_cache[i], shingle_cache[j])
                if sim >= threshold:
                    results.append((pair[0], pair[1], round(sim, 3)))
    return results


def deduplicate(examples: list[RawExample], near_dup_threshold: float = NEAR_DUP_THRESHOLD) -> DedupReport:
    exact = find_exact_duplicates(examples)
    near = find_near_duplicates(examples, near_dup_threshold)
    dup_indices = {j for _, j in exact} | {j for _, j, _ in near}
    return DedupReport(
        total=len(examples),
        exact_duplicates=exact,
        near_duplicates=near,
        unique_count=len(examples) - len(dup_indices),
    )
