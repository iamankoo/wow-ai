"""Builds v3.3.0-answer-call: the existing v3.2.0-train-ready 33K PLUS a
bounded, deterministic, diverse sample of the new ANSWER_CALL data PLUS all
new hard negatives.

Source files (huge - 3M/3M/4M/3K lines, combinatorially template-generated,
see the Phase 1 inspection report):
    training/datasets/answer_call_english.jsonl   (label=ANSWER_CALL always)
    training/datasets/answer_call_hindi.jsonl
    training/datasets/answer_call_hinglish.jsonl
    training/datasets/hard_negatives.jsonl        (label mixes intents/actions)

Sampling: exactly 10,000 per language (30,000 total), stratified evenly
across each file's 100 context buckets (100/bucket - buckets are ~100x
larger than that, so this is a genuine subsample, not "take everything"),
via seeded reservoir sampling (Algorithm R) so the selection is uniform
within each bucket - not just the first N rows, which would bias toward
whichever caller-identity fillers happen to appear earliest in generation
order. All 3,000 hard negatives are included (no sampling - small enough
to use in full).

Taxonomy mapping (no new categories):
- ANSWER_CALL data: intent=HANDLE_CALLS ("authorizing WOW to answer/handle
  incoming calls" - matches this data's actual content), action=ANSWER_CALL
  (given), context_mode mapped from the 100 context phrases via keyword
  rules (see map_context_phrase()), CUSTOM as the catch-all for anything
  that doesn't cleanly fit one of the other 6 modes.
- Hard negatives: the source `label` field is inconsistently either an
  intent (CALL_PERSON/SCHEDULE_REQUEST/URGENT_CALL) or an action
  (END_CALL/COLLECT_MESSAGE) depending on the record. Whichever field
  `label` supplies is preserved as-is (never overridden); the other field
  is derived by reusing the existing RuleBasedLanguageModelProvider,
  exactly the same inference-only, no-training reuse pattern used
  throughout the annotation phase.

This module never trains a model and never touches v0/v1, the v2
checkpoints, or v3.2.0-train-ready - it only ever writes new files under
training/datasets/versions/v3.3.0-answer-call/.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.brain.taxonomy import is_valid_action, is_valid_context, is_valid_intent  # noqa: E402
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider  # noqa: E402

from training.pipeline.annotation.prepare_training_set import (  # noqa: E402
    build_duplicate_clusters,
    stratified_group_split,
)
from training.pipeline.dedup import find_exact_duplicates, find_near_duplicates  # noqa: E402
from training.pipeline.quality import score_example  # noqa: E402
from training.pipeline.schema import RawExample  # noqa: E402
from training.pipeline.versioning import version_dir_for, write_manifest  # noqa: E402

DATASETS_DIR = REPO_ROOT / "training" / "datasets"
ANSWER_CALL_FILES = {
    "en": DATASETS_DIR / "answer_call_english.jsonl",
    "hi": DATASETS_DIR / "answer_call_hindi.jsonl",
    "hinglish": DATASETS_DIR / "answer_call_hinglish.jsonl",
}
HARD_NEGATIVES_FILE = DATASETS_DIR / "hard_negatives.jsonl"
EXISTING_DATASET_DIR = DATASETS_DIR / "versions" / "v3.2.0-train-ready"

SAMPLES_PER_LANGUAGE = 10_000
SEED = 42

_LANGUAGE_NORMALIZE = {"english": "en", "hindi": "hi", "hinglish": "hinglish"}


# ---------------------------------------------------------------------------
# Context-phrase -> ContextMode mapping. Rules are checked in priority
# order (first match wins); BUSY is the default for "doing some ordinary
# activity/errand/social thing", not a fallback for "no signal" - every one
# of the 100 phrases describes the user doing something, so NORMAL never
# applies here (see build_answer_call_dataset docstring / DATASET_ANSWER_CALL
# report for the full audited mapping table).
# ---------------------------------------------------------------------------

def map_context_phrase(context_phrase_en: str) -> str:
    p = context_phrase_en.lower()
    if "asleep" in p or "sleeping" in p:
        return "SLEEPING"
    if any(k in p for k in [
        "driving", "traffic", "petrol station", "bike", "bus", "train",
        "railway station", "airport", "flight", "taxi", "hotel",
        "travelling", "luggage", "vacation",
    ]):
        return "TRAVELLING"
    if any(k in p for k in [
        "hospital", "waiting for the doctor", "medical test", "sick relative",
        "medical appointment", "reproductive-health", "pregnancy-related",
        "passport", "renewing my id", "visa update",
    ]):
        return "UNAVAILABLE"
    if any(k in p for k in [
        "in a meeting", "lecture", "presenting to my team", "job interview",
        "video call", "in class", "taking an exam",
    ]):
        return "MEETING"
    if any(k in p for k in [
        "phone battery", "internet is down", "wi-fi", "unexpected problem",
        "family emergency",
    ]):
        return "CUSTOM"
    return "BUSY"


def build_context_mode_index(english_path: Path) -> list[str]:
    """Returns the 100 ContextMode values in first-occurrence order from the
    English file. Hindi/Hinglish context phrases are the same 100 situations
    translated, in the same generation order (verified by inspection), so
    this same ordered list applies positionally to all three languages."""
    modes = []
    seen = set()
    with english_path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            ctx = rec["context"]
            if ctx not in seen:
                seen.add(ctx)
                modes.append(map_context_phrase(ctx))
            if len(modes) >= 100:
                break
    return modes


# ---------------------------------------------------------------------------
# Stratified reservoir sampling: exactly 100 records per context bucket per
# language file (100 buckets x 100 = 10,000/language), uniform within each
# bucket via Algorithm R, seeded for reproducibility.
# ---------------------------------------------------------------------------

def sample_answer_call_file(path: Path, lang_code: str, context_mode_index: dict[str, str], per_bucket: int = 100) -> list[dict]:
    rng = random.Random(SEED)
    reservoirs: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    seen_count: dict[str, int] = defaultdict(int)

    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            rec = json.loads(line)
            ctx = rec["context"]
            seen_count[ctx] += 1
            reservoir = reservoirs[ctx]
            item = (line_no, rec)
            if len(reservoir) < per_bucket:
                reservoir.append(item)
            else:
                j = rng.randint(0, seen_count[ctx] - 1)
                if j < per_bucket:
                    reservoir[j] = item

    sampled = []
    for ctx, items in reservoirs.items():
        context_mode = context_mode_index.get(ctx)
        for line_no, rec in items:
            sampled.append({
                "source_line": line_no,
                "text": rec["text"],
                "context_phrase": ctx,
                "context_mode": context_mode,
            })
    return sampled


def convert_answer_call_records(sampled: list[dict], lang_code: str, source_file: str) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for i, s in enumerate(sorted(sampled, key=lambda r: r["source_line"])):
        out.append({
            "id": f"answer_call_{lang_code}_{s['source_line']:08d}",
            "text": s["text"],
            "language": lang_code,
            "intent": "HANDLE_CALLS",
            "context_mode": s["context_mode"],
            "action": "ANSWER_CALL",
            "label_source": "candidate",
            "approved_by": "answer_call_dataset_import",
            "candidate_source": "synthetic_template_dataset",
            "candidate_confidence": None,
            "review_status": "approved",
            "source_file": source_file,
            "source_line": s["source_line"],
            "source_order": s["source_line"],
            "annotated_at": now,
        })
    return out


# ---------------------------------------------------------------------------
# Hard negatives: `label` is either an intent or an action depending on the
# record - never overridden, whichever field it fills is authoritative. The
# other field is derived via the existing rule-based classifier.
# ---------------------------------------------------------------------------

def convert_hard_negative_records(path: Path) -> tuple[list[dict], list[dict]]:
    """Returns (converted_records, issues) - issues lists any record whose
    label didn't resolve to a known intent OR action (none expected, but
    not assumed)."""
    provider = RuleBasedLanguageModelProvider()
    now = datetime.now(timezone.utc).isoformat()
    out = []
    issues = []

    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            rec = json.loads(line)
            label = rec.get("label")
            text = rec["text"]
            lang_code = _LANGUAGE_NORMALIZE.get(rec.get("language"), rec.get("language"))

            rb_intent, rb_context, rb_action = provider.classify_wow_taxonomy(text)

            if is_valid_intent(label):
                intent = label
                action = rb_action.value
                context_mode = rb_context.value if rb_context else None
            elif is_valid_action(label):
                action = label
                intent = rb_intent.value
                context_mode = rb_context.value if rb_context else None
            else:
                issues.append({"line": line_no, "text": text, "label": label, "reason": "label is neither a valid intent nor a valid action"})
                intent = rb_intent.value
                action = rb_action.value
                context_mode = rb_context.value if rb_context else None

            if action == "ANSWER_CALL":
                issues.append({"line": line_no, "text": text, "label": label, "reason": "derived action was ANSWER_CALL for a hard-negative record - forced to NO_ACTION"})
                action = "NO_ACTION"

            out.append({
                "id": f"hard_negative_{line_no:05d}",
                "text": text,
                "language": lang_code,
                "intent": intent,
                "context_mode": context_mode,
                "action": action,
                "label_source": "candidate",
                "approved_by": "hard_negative_dataset_import",
                "candidate_source": "given_label_plus_rule_based",
                "candidate_confidence": None,
                "review_status": "approved",
                "source_file": "hard_negatives.jsonl",
                "source_line": line_no,
                "source_order": line_no,
                "annotated_at": now,
            })
    return out, issues


# ---------------------------------------------------------------------------
# Quality gates + duplicate clustering + split, over the new ~33K records
# (small enough now to run the full existing mega-pipeline exhaustively,
# unlike the raw 10M-record source files).
# ---------------------------------------------------------------------------

def run_quality_gates(records: list[dict]) -> tuple[dict, list, list]:
    examples = [
        RawExample(text=r["text"], language=r["language"], intent=r["intent"],
                   context_mode=r["context_mode"], action=r["action"],
                   source=r["source_file"], synthetic=True)
        for r in records
    ]
    exact_pairs = find_exact_duplicates(examples)
    near_pairs = find_near_duplicates(examples)
    exact_idx = {j for _, j in exact_pairs}
    near_idx = {j for _, j, _ in near_pairs}

    status_counts: Counter = Counter()
    scores = []
    for i, ex in enumerate(examples):
        scored = score_example(ex, is_exact_duplicate=i in exact_idx, is_near_duplicate=i in near_idx)
        status_counts[scored.flags.status] += 1
        scores.append(scored.flags.score)

    summary = {
        "total_scored": len(examples),
        "status_counts": dict(status_counts),
        "avg_quality_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "exact_duplicate_pairs": len(exact_pairs),
        "near_duplicate_pairs": len(near_pairs),
    }
    return summary, exact_pairs, near_pairs


def validate_schema(records: list[dict]) -> dict:
    bad_intent = bad_action = bad_context = blank_text = missing_field = 0
    required = {"id", "text", "language", "intent", "context_mode", "action", "source_file", "source_line"}
    for r in records:
        if not required.issubset(r.keys()):
            missing_field += 1
            continue
        if not r["text"] or not str(r["text"]).strip():
            blank_text += 1
        if not is_valid_intent(r["intent"]):
            bad_intent += 1
        if r["context_mode"] is not None and not is_valid_context(r["context_mode"]):
            bad_context += 1
        if not is_valid_action(r["action"]):
            bad_action += 1
    return {
        "missing_field": missing_field, "blank_text": blank_text,
        "bad_intent": bad_intent, "bad_context": bad_context, "bad_action": bad_action,
    }


def _distribution(records: list[dict], field: str) -> dict:
    c: Counter = Counter()
    for r in records:
        v = r.get(field)
        if v:
            c[v] += 1
    return dict(c.most_common())


def build_and_write(version: str = "v3.3.0-answer-call") -> dict:
    context_index_ordered = None
    # Build the ordered ContextMode list once from English, apply positionally.
    modes_in_order = build_context_mode_index(ANSWER_CALL_FILES["en"])

    new_records_by_lang: dict[str, list[dict]] = {}
    per_language_report = {}
    for lang_code, path in ANSWER_CALL_FILES.items():
        # Rebuild THIS file's own context->mode map, positionally aligned to
        # the English-derived mode list (each file's contexts appear in the
        # same generation order as English's, verified by inspection).
        ctx_to_mode = {}
        seen = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                ctx = rec["context"]
                if ctx not in ctx_to_mode:
                    idx = len(seen)
                    seen.append(ctx)
                    ctx_to_mode[ctx] = modes_in_order[idx] if idx < len(modes_in_order) else "CUSTOM"
                if len(seen) >= 100:
                    break

        sampled = sample_answer_call_file(path, lang_code, ctx_to_mode, per_bucket=100)
        converted = convert_answer_call_records(sampled, lang_code, path.name)
        new_records_by_lang[lang_code] = converted
        per_language_report[lang_code] = {
            "sampled_count": len(converted),
            "unique_context_buckets_sampled_from": len(ctx_to_mode),
            "context_mode_distribution": _distribution(converted, "context_mode"),
        }

    hard_negatives, hn_issues = convert_hard_negative_records(HARD_NEGATIVES_FILE)

    new_all = new_records_by_lang["en"] + new_records_by_lang["hi"] + new_records_by_lang["hinglish"] + hard_negatives

    schema_report = validate_schema(new_all)
    quality_report, exact_pairs, near_pairs = run_quality_gates(new_all)
    clusters = build_duplicate_clusters(len(new_all), exact_pairs, near_pairs)
    split = stratified_group_split(new_all, clusters, seed=SEED)

    def load_jsonl(p: Path) -> list[dict]:
        with p.open(encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    existing_train = load_jsonl(EXISTING_DATASET_DIR / "train.jsonl")
    existing_val = load_jsonl(EXISTING_DATASET_DIR / "val.jsonl")
    existing_test = load_jsonl(EXISTING_DATASET_DIR / "test.jsonl")

    new_train = [new_all[i] for i in split["train_idx"]]
    new_val = [new_all[i] for i in split["val_idx"]]
    new_test = [new_all[i] for i in split["test_idx"]]

    combined_train = existing_train + new_train
    combined_val = existing_val + new_val
    combined_test = existing_test + new_test

    version_dir = version_dir_for(version)
    version_dir.mkdir(parents=True, exist_ok=True)
    train_path = version_dir / "train.jsonl"
    val_path = version_dir / "val.jsonl"
    test_path = version_dir / "test.jsonl"

    for path, records in ((train_path, combined_train), (val_path, combined_val), (test_path, combined_test)):
        with path.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    combined_all = combined_train + combined_val + combined_test
    answer_call_by_lang = Counter(r["language"] for r in new_records_by_lang["en"] + new_records_by_lang["hi"] + new_records_by_lang["hinglish"])

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "final_total_count": len(combined_all),
        "existing_33k_count": len(existing_train) + len(existing_val) + len(existing_test),
        "answer_call_count_by_language": dict(answer_call_by_lang),
        "answer_call_total": sum(answer_call_by_lang.values()),
        "hard_negative_count": len(hard_negatives),
        "hard_negative_issues": hn_issues,
        "new_records_total": len(new_all),
        "per_language_sampling_report": per_language_report,
        "combined_intent_distribution": _distribution(combined_all, "intent"),
        "combined_context_distribution": _distribution(combined_all, "context_mode"),
        "combined_action_distribution": _distribution(combined_all, "action"),
        "combined_language_distribution": _distribution(combined_all, "language"),
        "train_count": len(combined_train),
        "val_count": len(combined_val),
        "test_count": len(combined_test),
        "existing_train_count": len(existing_train),
        "existing_val_count": len(existing_val),
        "existing_test_count": len(existing_test),
        "new_train_count": len(new_train),
        "new_val_count": len(new_val),
        "new_test_count": len(new_test),
        "schema_validation": schema_report,
        "mega_pipeline_quality_gates": quality_report,
        "answer_call_in_train": sum(1 for r in new_train if r["action"] == "ANSWER_CALL"),
        "answer_call_in_val": sum(1 for r in new_val if r["action"] == "ANSWER_CALL"),
        "answer_call_in_test": sum(1 for r in new_test if r["action"] == "ANSWER_CALL"),
    }
    stats_path = version_dir / "STATS.json"
    stats_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest_path = write_manifest(version_dir, [train_path, val_path, test_path, stats_path])

    return {
        "version_dir": str(version_dir),
        "manifest_path": str(manifest_path),
        "stats_path": str(stats_path),
        "report": report,
    }


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    result = build_and_write()
    print(json.dumps(result["report"], indent=2, ensure_ascii=False))
