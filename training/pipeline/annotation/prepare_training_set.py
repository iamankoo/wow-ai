"""Builds a training-ready, versioned, stratified train/val/test split from
the APPROVED subset of the annotation store.

Pipeline:
  1. Load every approved/corrected record (label resolved via
     schema.resolve_active_label - correct for human AND automated
     approvals alike).
  2. Run the existing mega-dataset quality gates (training/pipeline/quality.py)
     over the whole set - label validity, PII, language-consistency,
     length, exact/near-duplicate detection. Nothing is silently dropped;
     every record's quality flags are recorded in the output stats.
  3. Cluster exact/near-duplicates (union-find over the same duplicate
     pairs quality.py finds) so that no duplicate cluster is ever split
     across train/validation/test - the anti-leakage guarantee.
  4. Stratify at the CLUSTER level by (intent, language) wherever a stratum
     is large enough to support a real val/test allocation, falling back
     to intent-only pooling when a specific (intent, language) pair is too
     small, and to "whole class goes to train" only if the intent's total
     count can't support 2 val + 2 test examples at all (does not happen
     for any of the 17 intents in the current 33K - the smallest,
     CANCEL_REQUEST, has 9). Action and context are NOT used as direct
     stratification keys - several action classes have as few as 2 total
     examples, and joint (intent, action, context, language) strata would
     be almost entirely singletons. Their resulting per-split distribution
     is instead measured and reported after the split, which is the
     honest way to represent "stratified where statistically possible."

This module never trains anything, never touches v0/v1, never touches the
original 33K or master datasets - it only ever writes new files under
training/datasets/versions/<version>/.
"""

from __future__ import annotations

import json
import random
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from training.pipeline.annotation.quality_gates import USABLE_STATUSES
from training.pipeline.annotation.schema import resolve_active_label
from training.pipeline.dedup import find_exact_duplicates, find_near_duplicates
from training.pipeline.quality import score_example
from training.pipeline.schema import RawExample
from training.pipeline.versioning import version_dir_for, write_manifest

VAL_FRACTION = 0.10
TEST_FRACTION = 0.10
MIN_VAL_PER_CLASS = 2
MIN_TEST_PER_CLASS = 2
MIN_CLASS_SIZE_FOR_SPLIT = 6
MIN_LANG_SUBGROUP_FOR_JOINT_STRATIFICATION = MIN_CLASS_SIZE_FOR_SPLIT


# ---------------------------------------------------------------------------
# Step 1: load the approved set with full lineage.
# ---------------------------------------------------------------------------

def load_approved_records(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM annotations WHERE review_status IN (?, ?) ORDER BY source_order ASC",
        USABLE_STATUSES,
    ).fetchall()
    records = []
    for r in rows:
        intent, context, action = resolve_active_label(r)
        records.append({
            "id": r["id"],
            "text": r["text"],
            "language": r["language"],
            "intent": intent,
            "context_mode": context,
            "action": action,
            "label_source": r["label_source"],
            "approved_by": r["approved_by"],
            "candidate_source": r["candidate_source"],
            "candidate_confidence": r["candidate_confidence"],
            "review_status": r["review_status"],
            "source_file": r["source_file"],
            "source_line": r["source_line"],
            "source_order": r["source_order"],
            "annotated_at": r["annotated_at"],
        })
    return records


# ---------------------------------------------------------------------------
# Step 2: existing mega-dataset quality gates.
# ---------------------------------------------------------------------------

def run_quality_gates(records: list[dict]) -> dict:
    examples = [
        RawExample(
            text=r["text"], language=r["language"], intent=r["intent"],
            context_mode=r["context_mode"], action=r["action"],
            source=r["source_file"], synthetic=False,
        )
        for r in records
    ]
    exact_dup_pairs = find_exact_duplicates(examples)
    near_dup_pairs = find_near_duplicates(examples)
    exact_dup_indices = {j for _, j in exact_dup_pairs}
    near_dup_indices = {j for _, j, _ in near_dup_pairs}

    status_counts: Counter = Counter()
    reject_reasons: Counter = Counter()
    review_reasons: Counter = Counter()
    scores = []
    per_example_flags: list[dict] = []
    for i, ex in enumerate(examples):
        scored = score_example(ex, is_exact_duplicate=i in exact_dup_indices, is_near_duplicate=i in near_dup_indices)
        status_counts[scored.flags.status] += 1
        scores.append(scored.flags.score)
        per_example_flags.append({
            "quality_status": scored.flags.status,
            "quality_score": scored.flags.score,
            "is_exact_duplicate": scored.flags.is_exact_duplicate,
            "is_near_duplicate": scored.flags.is_near_duplicate,
            "language_consistent": scored.flags.language_consistent,
            "has_pii": scored.flags.has_pii,
        })
        if scored.flags.status == "reject":
            for reason in scored.flags.reasons:
                reject_reasons[reason.split(":")[0]] += 1
        elif scored.flags.status == "review":
            for reason in scored.flags.reasons:
                review_reasons[reason.split(":")[0]] += 1

    quality_summary = {
        "total_scored": len(examples),
        "status_counts": dict(status_counts),
        "avg_quality_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "reject_reason_counts": dict(reject_reasons.most_common()),
        "review_reason_counts": dict(review_reasons.most_common()),
        "exact_duplicate_pairs": len(exact_dup_pairs),
        "near_duplicate_pairs": len(near_dup_pairs),
    }
    return quality_summary, exact_dup_pairs, near_dup_pairs, per_example_flags


# ---------------------------------------------------------------------------
# Step 3: duplicate clustering (union-find) so a cluster never crosses a
# split boundary.
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def build_duplicate_clusters(n: int, exact_pairs: list[tuple[int, int]], near_pairs: list[tuple[int, int, float]]) -> list[list[int]]:
    uf = _UnionFind(n)
    for a, b in exact_pairs:
        uf.union(a, b)
    for a, b, _ in near_pairs:
        uf.union(a, b)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)
    return list(groups.values())


# ---------------------------------------------------------------------------
# Step 4: stratified, group-aware, leakage-free split.
# ---------------------------------------------------------------------------

def stratified_group_split(
    records: list[dict],
    clusters: list[list[int]],
    *,
    val_fraction: float = VAL_FRACTION,
    test_fraction: float = TEST_FRACTION,
    seed: int = 42,
) -> dict:
    rng = random.Random(seed)
    intent_totals: Counter = Counter(r["intent"] for r in records)
    intent_lang_totals: Counter = Counter((r["intent"], r["language"]) for r in records)

    def stratum_key(cluster: list[int]) -> tuple:
        rep = records[cluster[0]]
        intent, lang = rep["intent"], rep["language"]
        if intent_totals[intent] < MIN_CLASS_SIZE_FOR_SPLIT:
            return ("train_only", intent)
        if intent_lang_totals[(intent, lang)] >= MIN_LANG_SUBGROUP_FOR_JOINT_STRATIFICATION:
            return ("intent_lang", intent, lang)
        return ("intent_only", intent)

    strata: dict[tuple, list[list[int]]] = defaultdict(list)
    for cluster in clusters:
        strata[stratum_key(cluster)].append(cluster)

    train_idx: list[int] = []
    val_idx: list[int] = []
    test_idx: list[int] = []
    train_only_intents: set = set()

    for key in sorted(strata, key=repr):
        stratum_clusters = strata[key][:]
        rng.shuffle(stratum_clusters)

        if key[0] == "train_only":
            train_only_intents.add(key[1])
            for c in stratum_clusters:
                train_idx.extend(c)
            continue

        total_examples = sum(len(c) for c in stratum_clusters)
        n_val_target = max(MIN_VAL_PER_CLASS, round(total_examples * val_fraction))
        n_test_target = max(MIN_TEST_PER_CLASS, round(total_examples * test_fraction))
        while n_val_target + n_test_target >= total_examples and (n_val_target > 0 or n_test_target > 0):
            if n_val_target >= n_test_target and n_val_target > 0:
                n_val_target -= 1
            elif n_test_target > 0:
                n_test_target -= 1
            else:
                break

        val_count = test_count = 0
        for c in stratum_clusters:
            if val_count < n_val_target:
                val_idx.extend(c)
                val_count += len(c)
            elif test_count < n_test_target:
                test_idx.extend(c)
                test_count += len(c)
            else:
                train_idx.extend(c)

    rng.shuffle(train_idx)
    rng.shuffle(val_idx)
    rng.shuffle(test_idx)

    return {
        "train_idx": train_idx,
        "val_idx": val_idx,
        "test_idx": test_idx,
        "train_only_intents": sorted(train_only_intents),
    }


# ---------------------------------------------------------------------------
# Step 5: statistics report.
# ---------------------------------------------------------------------------

def _distribution(records: list[dict], idx: list[int], field: str) -> dict:
    counter: Counter = Counter()
    for i in idx:
        v = records[i][field]
        if v:
            counter[v] += 1
    return dict(counter.most_common())


def _imbalance_summary(dist: dict) -> dict:
    if not dist:
        return {}
    counts = list(dist.values())
    return {
        "max_class": max(dist, key=dist.get),
        "max_count": max(counts),
        "min_class": min(dist, key=dist.get),
        "min_count": min(counts),
        "imbalance_ratio": round(max(counts) / min(counts), 2) if min(counts) else None,
    }


def compute_leakage_check(records: list[dict], split: dict) -> dict:
    """Independent verification (recomputed, not just trusted from the
    split step) that no exact-duplicate example text appears in more than
    one split."""
    text_key = lambda i: (records[i]["text"].strip().lower(), records[i]["language"])
    split_of: dict = {}
    for name, idx_list in (("train", split["train_idx"]), ("val", split["val_idx"]), ("test", split["test_idx"])):
        for i in idx_list:
            split_of.setdefault(text_key(i), set()).add(name)
    leaked = {k: sorted(v) for k, v in split_of.items() if len(v) > 1}
    return {
        "exact_text_leakage_groups": len(leaked),
        "leaked_examples": [{"text_language_key": str(k), "splits": v} for k, v in list(leaked.items())[:20]],
    }


def build_report(records: list[dict], split: dict, clusters: list[list[int]], quality: dict) -> dict:
    train_idx, val_idx, test_idx = split["train_idx"], split["val_idx"], split["test_idx"]
    total = len(records)

    def split_stats(idx: list[int]) -> dict:
        machine = sum(1 for i in idx if records[i]["approved_by"] is not None)
        human = len(idx) - machine
        return {
            "count": len(idx),
            "pct_of_total": round(100 * len(idx) / total, 2) if total else 0.0,
            "intent_distribution": _distribution(records, idx, "intent"),
            "context_distribution": _distribution(records, idx, "context_mode"),
            "action_distribution": _distribution(records, idx, "action"),
            "language_distribution": _distribution(records, idx, "language"),
            "machine_approved_count": machine,
            "human_reviewed_count": human,
        }

    cluster_sizes = Counter(len(c) for c in clusters)
    multi_member_clusters = [c for c in clusters if len(c) > 1]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_approved_records": total,
        "splits": {
            "train": split_stats(train_idx),
            "val": split_stats(val_idx),
            "test": split_stats(test_idx),
        },
        "overall_intent_distribution": _distribution(records, range(total), "intent"),
        "overall_context_distribution": _distribution(records, range(total), "context_mode"),
        "overall_action_distribution": _distribution(records, range(total), "action"),
        "overall_language_distribution": _distribution(records, range(total), "language"),
        "class_imbalance": {
            "intent": _imbalance_summary(_distribution(records, range(total), "intent")),
            "action": _imbalance_summary(_distribution(records, range(total), "action")),
            "context": _imbalance_summary(_distribution(records, range(total), "context_mode")),
        },
        "stratification": {
            "primary_key": "intent",
            "secondary_key": "language (joint intent+language stratification when a stratum has >= "
                              f"{MIN_LANG_SUBGROUP_FOR_JOINT_STRATIFICATION} examples, else pooled across languages)",
            "not_directly_stratified": ["action", "context"],
            "not_directly_stratified_reason": (
                "action and context distributions are highly skewed (action classes range from 2 to 19,394 "
                "examples) - a joint (intent, action, context, language) key would produce almost entirely "
                "singleton strata, which cannot be split into train/val/test at all. Their per-split "
                "distributions are measured and reported above instead of enforced."
            ),
            "intents_below_min_class_size_forced_to_train_only": split["train_only_intents"],
            "min_class_size_for_split": MIN_CLASS_SIZE_FOR_SPLIT,
        },
        "duplicate_clustering": {
            "total_clusters": len(clusters),
            "singleton_clusters": cluster_sizes.get(1, 0),
            "multi_member_clusters": len(multi_member_clusters),
            "examples_in_multi_member_clusters": sum(len(c) for c in multi_member_clusters),
            "largest_cluster_size": max(cluster_sizes) if cluster_sizes else 0,
        },
        "leakage_check": compute_leakage_check(records, split),
        "mega_pipeline_quality_gates": quality,
    }


# ---------------------------------------------------------------------------
# Step 6: write the versioned dataset.
# ---------------------------------------------------------------------------

def _write_split_file(path: Path, records: list[dict], idx: list[int]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for i in idx:
            f.write(json.dumps(records[i], ensure_ascii=False) + "\n")


def _attach_quality_and_cluster_info(records: list[dict], per_example_flags: list[dict], clusters: list[list[int]]) -> None:
    """Mutates each record in place so the per-example quality flags and
    duplicate-cluster id travel with the record into train/val/test.jsonl -
    without this, a downstream consumer could not filter by quality_status
    or trace which examples share a duplicate cluster without re-running
    the whole pipeline."""
    for i, flags in enumerate(per_example_flags):
        records[i].update(flags)
    for cluster_id, cluster in enumerate(clusters):
        for i in cluster:
            records[i]["duplicate_cluster_id"] = cluster_id
            records[i]["duplicate_cluster_size"] = len(cluster)


def prepare_and_write(conn: sqlite3.Connection, version: str, seed: int = 42) -> dict:
    records = load_approved_records(conn)
    quality, exact_pairs, near_pairs, per_example_flags = run_quality_gates(records)
    clusters = build_duplicate_clusters(len(records), exact_pairs, near_pairs)
    _attach_quality_and_cluster_info(records, per_example_flags, clusters)
    split = stratified_group_split(records, clusters, seed=seed)
    report = build_report(records, split, clusters, quality)

    version_dir = version_dir_for(version)
    version_dir.mkdir(parents=True, exist_ok=True)
    train_path = version_dir / "train.jsonl"
    val_path = version_dir / "val.jsonl"
    test_path = version_dir / "test.jsonl"

    _write_split_file(train_path, records, split["train_idx"])
    _write_split_file(val_path, records, split["val_idx"])
    _write_split_file(test_path, records, split["test_idx"])

    stats_path = version_dir / "STATS.json"
    stats_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest_path = write_manifest(version_dir, [train_path, val_path, test_path, stats_path])

    return {
        "version": version,
        "version_dir": str(version_dir),
        "train_path": str(train_path),
        "val_path": str(val_path),
        "test_path": str(test_path),
        "stats_path": str(stats_path),
        "manifest_path": str(manifest_path),
        "report": report,
    }
