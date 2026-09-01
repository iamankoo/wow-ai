"""Orchestrates ingestion of the 9 hand-collected TXT sources under
training/datasets/*.txt into the v3+ pipeline's canonical format.

Never loads a source file fully into memory - training.pipeline.ingest.
numbered_txt streams entries one at a time, and this module writes each
output JSONL incrementally rather than building an in-memory list of
millions of records. See docs/DATASET.md "Ingesting the hand-collected TXT
sources" for the full design and docs/DATASET.md "Scaling strategy" for how
each stage stays bounded at multi-million-row scale.

This module INGESTS AND VALIDATES ONLY. It never trains anything and never
writes to training/models/.

Run: python -m training.pipeline.ingest.merge_txt_sources
"""

import hashlib
import json
import random
import time
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from training.pipeline.ingest.numbered_txt import ParseReport, analyze_file, parse_numbered_txt
from training.pipeline.label_validate import VALID_LANGUAGES
from training.pipeline.langid import detect_language
from training.pipeline.normalize import normalize_for_comparison, normalize_text
from training.pipeline.pii import scan_and_redact
from training.pipeline.relevance import assess_relevance

DATASETS_DIR = Path(__file__).resolve().parents[2] / "datasets"
V3_RAW_DIR = DATASETS_DIR / "v3_raw"
REVIEW_DIR = DATASETS_DIR / "review"
REPORTS_DIR = DATASETS_DIR / "reports"
VERSIONS_DIR = DATASETS_DIR / "versions"

MASTER_PATH = V3_RAW_DIR / "wow_master_dataset.jsonl"
CLEAN_PATH = V3_RAW_DIR / "wow_master_clean.jsonl"
REVIEW_PATH = REVIEW_DIR / "wow_master_review.jsonl"
DEDUP_REPORT_PATH = REPORTS_DIR / "wow_master_dataset_dedup_report.json"
AUDIT_JSON_PATH = REPORTS_DIR / "full_dataset_audit.json"
AUDIT_MD_PATH = REPORTS_DIR / "full_dataset_audit.md"
SAMPLES_PATH = REPORTS_DIR / "review_samples.jsonl"

# Required processing order (section 2 of the ingestion request).
SOURCE_FILES: list[tuple[str, str]] = [
    ("hindi_dataset_1.txt", "hi"),
    ("hindi_dataset_2.txt", "hi"),
    ("hindi_dataset_3.txt", "hi"),
    ("hinglish_dataset_1.txt", "hinglish"),
    ("hinglish_dataset_2.txt", "hinglish"),
    ("hinglish_dataset_3.txt", "hinglish"),
    ("english_dataset_1.txt", "en"),
    ("english_dataset_2.txt", "en"),
    ("english_dataset_3.txt", "en"),
]

# Near-duplicate bucketing/sampling bounds - see docs/DATASET.md "Scaling
# strategy". Exact within a bucket up to this size; a statistically sampled
# estimate beyond it, always labeled as such.
NEAR_DUP_SHINGLE_SIZE = 4
MAX_BUCKET_RESERVOIR = 200
NEAR_DUP_THRESHOLD = 0.85

# Bounded diversity sample size per source file (not exhaustive at 1M rows -
# see docs/DATASET.md).
DIVERSITY_SAMPLE_PER_FILE = 3000


# ---------------------------------------------------------------------------
# Stage 1: verify all 9 source files exist and report their structure
# ---------------------------------------------------------------------------

def _sha256_of_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class SourceFileReport:
    filename: str
    exists: bool
    source_language: str
    size_bytes: int | None = None
    sha256: str | None = None
    encoding: str | None = None
    entry_count: int | None = None
    header_lines: list[str] = field(default_factory=list)
    blank_line_count: int | None = None
    wrapped_line_count: int | None = None
    min_source_order: int | None = None
    max_source_order: int | None = None
    duplicate_source_orders: list[int] = field(default_factory=list)
    appears_valid: bool = False
    error: str | None = None


def verify_source_files(compute_hash: bool = True) -> list[SourceFileReport]:
    """Section 2: existence + structure verification, BEFORE any ingestion.
    Never raises on a missing file - reports it and lets the caller decide
    (main() aborts with a clear message if any of the 9 are missing)."""
    results = []
    for filename, source_lang in SOURCE_FILES:
        path = DATASETS_DIR / filename
        report = SourceFileReport(filename=filename, exists=path.exists(), source_language=source_lang)
        if not report.exists:
            results.append(report)
            continue
        try:
            stat = path.stat()
            report.size_bytes = stat.st_size
            if compute_hash:
                report.sha256 = _sha256_of_file(path)
            with path.open(encoding="utf-8") as f:
                f.read(4096)  # cheap encoding sanity check - raises on invalid UTF-8
            report.encoding = "utf-8"
            parse_report: ParseReport = analyze_file(path)
            report.entry_count = parse_report.entry_count
            report.header_lines = parse_report.header_lines
            report.blank_line_count = parse_report.blank_line_count
            report.wrapped_line_count = parse_report.wrapped_entry_count
            report.min_source_order = parse_report.min_source_order
            report.max_source_order = parse_report.max_source_order
            report.duplicate_source_orders = parse_report.duplicate_source_orders
            report.appears_valid = parse_report.entry_count > 0 and not parse_report.duplicate_source_orders
        except UnicodeDecodeError as e:
            report.error = f"not valid UTF-8: {e}"
        except OSError as e:
            report.error = str(e)
        results.append(report)
    return results


# ---------------------------------------------------------------------------
# Stage 2: streaming ingest -> master raw JSONL (one pass per file, in order)
# ---------------------------------------------------------------------------

@dataclass
class IngestSummary:
    per_file_counts: dict[str, int]
    total_ingested: int
    empty_text_count: int
    elapsed_seconds: float


def ingest_to_master(output_path: Path, *, progress_every: int = 100_000) -> IngestSummary:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    per_file_counts: dict[str, int] = {}
    total = 0
    empty_count = 0
    start = time.monotonic()

    with output_path.open("w", encoding="utf-8") as out:
        for filename, source_lang in SOURCE_FILES:
            path = DATASETS_DIR / filename
            count = 0
            for entry in parse_numbered_txt(path):
                text = normalize_text(entry.text)
                original_text = entry.text if entry.text != text else None
                if not text:
                    empty_count += 1

                total += 1
                record = {
                    "id": f"wow_raw_{total:08d}",
                    "text": text,
                    "language": source_lang,
                    "source_file": filename,
                    "source_line": entry.source_line,
                    "source_order": entry.source_order,
                    "source_language": source_lang,
                    "source_type": "user_curated",
                    "status": "candidate",
                    "intent": None,
                    "context": None,
                    "action": None,
                    "label_source": None,
                }
                if original_text is not None:
                    record["original_text"] = original_text
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

                if progress_every and total % progress_every == 0:
                    elapsed = time.monotonic() - start
                    print(f"  ingested {total:,} records ({elapsed:.1f}s, {total / elapsed:.0f} rec/s)...")

            per_file_counts[filename] = count
            print(f"  {filename}: {count:,} records ingested")

    return IngestSummary(
        per_file_counts=per_file_counts,
        total_ingested=total,
        empty_text_count=empty_count,
        elapsed_seconds=time.monotonic() - start,
    )


# ---------------------------------------------------------------------------
# Stage 3: streaming quality pass - dedup, language check, PII, relevance,
# near-dup bucketing - single pass over the master file.
# ---------------------------------------------------------------------------

@dataclass
class QualityPassSummary:
    total: int
    exact_duplicates: int
    near_duplicates_estimated: int
    language_mismatches: int
    pii_detected: int
    relevant_count: int
    empty_or_invalid: int
    clean_count: int
    review_count: int
    per_file_language_mismatch: dict[str, int]
    per_file_exact_duplicates: dict[str, int]
    duplicate_groups_sample: list[dict]
    oversized_buckets: int
    elapsed_seconds: float


def _shingle_key(text: str, language: str) -> str | None:
    norm = normalize_for_comparison(text)
    if len(norm) < NEAR_DUP_SHINGLE_SIZE:
        return None
    return f"{language}|{norm[:NEAR_DUP_SHINGLE_SIZE]}"


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _shingles(text: str, n: int = NEAR_DUP_SHINGLE_SIZE) -> set:
    norm = normalize_for_comparison(text)
    if len(norm) < n:
        return {norm} if norm else set()
    return {norm[i:i + n] for i in range(len(norm) - n + 1)}


def run_quality_pass(
    master_path: Path, clean_path: Path, review_path: Path, *, progress_every: int = 100_000
) -> QualityPassSummary:
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.parent.mkdir(parents=True, exist_ok=True)

    seen_hashes: dict[str, str] = {}   # normalized-text hash -> id of first occurrence
    per_file_dup: Counter = Counter()
    per_file_mismatch: Counter = Counter()
    duplicate_groups_sample: list[dict] = []

    # Reservoir per near-dup bucket: bucket_key -> list[(id, text)], capped.
    bucket_reservoirs: dict[str, list[tuple[str, str]]] = {}
    bucket_counts: Counter = Counter()
    rng = random.Random(42)

    total = 0
    exact_dup_count = 0
    mismatch_count = 0
    pii_count = 0
    relevant_count = 0
    empty_or_invalid = 0
    clean_count = 0
    review_count = 0
    start = time.monotonic()

    with master_path.open(encoding="utf-8") as inp, \
         clean_path.open("w", encoding="utf-8") as clean_out, \
         review_path.open("w", encoding="utf-8") as review_out:
        for line in inp:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            total += 1
            text = record["text"]
            language = record["language"]
            record_id = record["id"]
            source_file = record["source_file"]

            reasons: list[str] = []

            if not text or len(text) < 2:
                empty_or_invalid += 1
                reasons.append("empty_or_too_short")

            norm_hash = hashlib.sha256(f"{normalize_for_comparison(text)}|{language}".encode("utf-8")).hexdigest()[:16]
            is_exact_dup = norm_hash in seen_hashes
            if is_exact_dup:
                exact_dup_count += 1
                per_file_dup[source_file] += 1
                reasons.append("exact_duplicate")
                if len(duplicate_groups_sample) < 50:
                    duplicate_groups_sample.append({
                        "text": text, "id": record_id,
                        "duplicate_of_id": seen_hashes[norm_hash],
                    })
            else:
                seen_hashes[norm_hash] = record_id

            lang_assessment = detect_language(text, declared=language)
            if not lang_assessment.matches_declared:
                mismatch_count += 1
                per_file_mismatch[source_file] += 1
                reasons.append(
                    f"language_mismatch:declared={language},detected={lang_assessment.detected}"
                )

            redacted_text, had_pii, pii_types = scan_and_redact(text)
            if had_pii:
                pii_count += 1
                reasons.append(f"pii:{','.join(pii_types)}")

            relevance = assess_relevance(text)
            if relevance.relevant:
                relevant_count += 1

            bucket_key = _shingle_key(text, language)
            if bucket_key is not None:
                bucket_counts[bucket_key] += 1
                reservoir = bucket_reservoirs.setdefault(bucket_key, [])
                if len(reservoir) < MAX_BUCKET_RESERVOIR:
                    reservoir.append((record_id, text))
                else:
                    j = rng.randint(0, bucket_counts[bucket_key] - 1)
                    if j < MAX_BUCKET_RESERVOIR:
                        reservoir[j] = (record_id, text)

            record["redacted_text"] = redacted_text
            record["has_pii"] = had_pii
            record["wow_relevant"] = relevance.relevant
            record["matched_relevance_keywords"] = relevance.matched_keywords
            record["language_detected"] = lang_assessment.detected
            record["language_consistent"] = lang_assessment.matches_declared
            record["is_exact_duplicate"] = is_exact_dup

            # PII is redacted-not-fatal (matches quality.py's convention);
            # everything else (empty, exact dup, language mismatch) routes to review.
            fatal = any(r in ("empty_or_too_short", "exact_duplicate") or r.startswith("language_mismatch") for r in reasons)

            if fatal:
                record["status"] = "review"
                record["review_reasons"] = reasons
                review_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                review_count += 1
            else:
                record["status"] = "candidate_clean"
                if reasons:
                    record["review_reasons"] = reasons
                clean_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                clean_count += 1

            if progress_every and total % progress_every == 0:
                elapsed = time.monotonic() - start
                print(f"  scored {total:,} records ({elapsed:.1f}s, {total / elapsed:.0f} rec/s)...")

    # Near-duplicate estimation from bucket reservoirs (exact for buckets
    # within the reservoir cap, sampled-estimate beyond it).
    near_dup_estimate = 0
    oversized_buckets = 0
    for key, count in bucket_counts.items():
        if count < 2:
            continue
        reservoir = bucket_reservoirs.get(key, [])
        if len(reservoir) < 2:
            continue
        pairs_checked = 0
        near_dup_hits = 0
        shingle_cache = {rid: _shingles(t) for rid, t in reservoir}
        ids = list(shingle_cache)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pairs_checked += 1
                if _jaccard(shingle_cache[ids[i]], shingle_cache[ids[j]]) >= NEAR_DUP_THRESHOLD:
                    near_dup_hits += 1
        if pairs_checked:
            rate = near_dup_hits / pairs_checked
            if count > MAX_BUCKET_RESERVOIR:
                oversized_buckets += 1
                # Extrapolate the sampled rate to the full bucket size.
                near_dup_estimate += round(rate * (count * (count - 1) / 2))
            else:
                near_dup_estimate += near_dup_hits

    return QualityPassSummary(
        total=total,
        exact_duplicates=exact_dup_count,
        near_duplicates_estimated=near_dup_estimate,
        language_mismatches=mismatch_count,
        pii_detected=pii_count,
        relevant_count=relevant_count,
        empty_or_invalid=empty_or_invalid,
        clean_count=clean_count,
        review_count=review_count,
        per_file_language_mismatch=dict(per_file_mismatch),
        per_file_exact_duplicates=dict(per_file_dup),
        duplicate_groups_sample=duplicate_groups_sample,
        oversized_buckets=oversized_buckets,
        elapsed_seconds=time.monotonic() - start,
    )


# ---------------------------------------------------------------------------
# Stage 4: bounded diversity / template-concentration analysis per source
# file - reservoir-samples each file rather than reading all of it, so this
# stays cheap even for the 1M-row files.
# ---------------------------------------------------------------------------

@dataclass
class FileDiversityReport:
    source_file: str
    sample_size: int
    unique_text_ratio: float
    type_token_ratio: float
    distinct_first3_ratio: float
    distinct_last3_ratio: float
    avg_pairwise_shingle_similarity: float
    template_risk: str  # "low" | "medium" | "high"


def _reservoir_sample_texts(path: Path, source_lang: str, k: int, seed: int = 42) -> list[str]:
    rng = random.Random(seed)
    sample: list[str] = []
    n = 0
    for entry in parse_numbered_txt(path):
        n += 1
        text = normalize_text(entry.text)
        if len(sample) < k:
            sample.append(text)
        else:
            j = rng.randint(0, n - 1)
            if j < k:
                sample[j] = text
    return sample


def analyze_file_diversity(filename: str, source_lang: str, sample_size: int = DIVERSITY_SAMPLE_PER_FILE) -> FileDiversityReport:
    path = DATASETS_DIR / filename
    sample = _reservoir_sample_texts(path, source_lang, sample_size)
    n = len(sample)
    if n == 0:
        return FileDiversityReport(filename, 0, 0.0, 0.0, 0.0, 0.0, 0.0, "unknown")

    unique_ratio = len({normalize_for_comparison(t) for t in sample}) / n

    all_tokens = []
    first3, last3 = set(), set()
    for t in sample:
        toks = normalize_for_comparison(t).split()
        all_tokens.extend(toks)
        if toks:
            first3.add(" ".join(toks[:3]))
            last3.add(" ".join(toks[-3:]))
    ttr = len(set(all_tokens)) / len(all_tokens) if all_tokens else 0.0
    distinct_first3_ratio = len(first3) / n
    distinct_last3_ratio = len(last3) / n

    # Bounded pairwise similarity on a sub-sample of the sample.
    pair_sample_size = min(400, n)
    rng = random.Random(7)
    idxs = rng.sample(range(n), pair_sample_size) if n > pair_sample_size else list(range(n))
    shingle_sets = [_shingles(sample[i]) for i in idxs]
    pairs = [(a, b) for a in range(len(idxs)) for b in range(a + 1, len(idxs))]
    if len(pairs) > 5000:
        pairs = rng.sample(pairs, 5000)
    sims = [_jaccard(shingle_sets[a], shingle_sets[b]) for a, b in pairs]
    avg_sim = sum(sims) / len(sims) if sims else 0.0

    if avg_sim > 0.45 or ttr < 0.05 or distinct_first3_ratio < 0.05:
        risk = "high"
    elif avg_sim > 0.2 or ttr < 0.15 or distinct_first3_ratio < 0.2:
        risk = "medium"
    else:
        risk = "low"

    return FileDiversityReport(
        source_file=filename, sample_size=n, unique_text_ratio=round(unique_ratio, 4),
        type_token_ratio=round(ttr, 4), distinct_first3_ratio=round(distinct_first3_ratio, 4),
        distinct_last3_ratio=round(distinct_last3_ratio, 4),
        avg_pairwise_shingle_similarity=round(avg_sim, 4), template_risk=risk,
    )


# ---------------------------------------------------------------------------
# Stage 5: manifest + reports
# ---------------------------------------------------------------------------

def write_manifest(version: str, file_reports: list[SourceFileReport], output_files: list[Path]) -> Path:
    version_dir = VERSIONS_DIR / version
    version_dir.mkdir(parents=True, exist_ok=True)

    output_entries = []
    for f in output_files:
        if not f.exists():
            continue
        output_entries.append({
            "path": str(f.relative_to(DATASETS_DIR)).replace("\\", "/"),
            "sha256": _sha256_of_file(f),
            "size_bytes": f.stat().st_size,
        })

    manifest = {
        "dataset_version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_files": [
            {
                "filename": r.filename, "sha256": r.sha256, "size_bytes": r.size_bytes,
                "entry_count": r.entry_count, "source_language": r.source_language,
            }
            for r in file_reports
        ],
        "output_files": output_entries,
    }
    manifest_path = version_dir / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest_path


def write_samples(review_path: Path, clean_path: Path, output_path: Path, per_bucket: int = 15) -> None:
    """Section 20: representative samples without dumping millions of rows."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    samples: dict[str, list[dict]] = {
        "clean_relevant": [], "clean_irrelevant": [], "review_duplicate": [],
        "review_language_mismatch": [], "review_empty": [], "has_pii": [],
    }

    def _maybe_add(bucket: str, record: dict) -> None:
        if len(samples[bucket]) < per_bucket:
            samples[bucket].append({
                "id": record["id"], "text": record["text"], "source_file": record["source_file"],
                "source_line": record["source_line"], "language": record["language"],
            })

    with clean_path.open(encoding="utf-8") as f:
        for line in f:
            if all(len(v) >= per_bucket for v in samples.values()):
                break
            record = json.loads(line)
            if record.get("wow_relevant"):
                _maybe_add("clean_relevant", record)
            else:
                _maybe_add("clean_irrelevant", record)
            if record.get("has_pii"):
                _maybe_add("has_pii", record)

    with review_path.open(encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            reasons = record.get("review_reasons", [])
            if any(r == "exact_duplicate" for r in reasons):
                _maybe_add("review_duplicate", record)
            if any(r.startswith("language_mismatch") for r in reasons):
                _maybe_add("review_language_mismatch", record)
            if any(r == "empty_or_too_short" for r in reasons):
                _maybe_add("review_empty", record)

    with output_path.open("w", encoding="utf-8") as out:
        for bucket, items in samples.items():
            for item in items:
                out.write(json.dumps({"bucket": bucket, **item}, ensure_ascii=False) + "\n")


def main() -> None:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    print("=" * 70)
    print("STAGE 1: Verifying source files")
    print("=" * 70)
    file_reports = verify_source_files()
    missing = [r.filename for r in file_reports if not r.exists]
    if missing:
        raise SystemExit(f"Missing source files, aborting: {missing}")
    for r in file_reports:
        print(f"  {r.filename}: {r.size_bytes:,} bytes, {r.entry_count:,} entries, "
              f"valid={r.appears_valid}, header={bool(r.header_lines)}, "
              f"wraps={r.wrapped_line_count}, dup_orders={len(r.duplicate_source_orders)}")

    print()
    print("=" * 70)
    print("STAGE 2: Streaming ingest -> master raw JSONL")
    print("=" * 70)
    ingest_summary = ingest_to_master(MASTER_PATH)
    print(f"  Total ingested: {ingest_summary.total_ingested:,} in {ingest_summary.elapsed_seconds:.1f}s")

    print()
    print("=" * 70)
    print("STAGE 3: Quality pass (dedup, language, PII, relevance)")
    print("=" * 70)
    quality_summary = run_quality_pass(MASTER_PATH, CLEAN_PATH, REVIEW_PATH)
    print(f"  Total scored: {quality_summary.total:,} in {quality_summary.elapsed_seconds:.1f}s")
    print(f"  Clean: {quality_summary.clean_count:,}  Review: {quality_summary.review_count:,}")
    print(f"  Exact duplicates: {quality_summary.exact_duplicates:,}")
    print(f"  Near-duplicates (estimated): {quality_summary.near_duplicates_estimated:,}")
    print(f"  Language mismatches: {quality_summary.language_mismatches:,}")
    print(f"  PII detected: {quality_summary.pii_detected:,}")
    print(f"  WOW-relevant: {quality_summary.relevant_count:,}")

    print()
    print("=" * 70)
    print("STAGE 4: Diversity / template-concentration analysis (sampled)")
    print("=" * 70)
    diversity_reports = []
    for filename, source_lang in SOURCE_FILES:
        d = analyze_file_diversity(filename, source_lang)
        diversity_reports.append(d)
        print(f"  {filename}: n={d.sample_size} unique_ratio={d.unique_text_ratio} "
              f"ttr={d.type_token_ratio} distinct_first3={d.distinct_first3_ratio} "
              f"avg_sim={d.avg_pairwise_shingle_similarity} risk={d.template_risk}")

    print()
    print("=" * 70)
    print("STAGE 5: Manifest, reports, samples")
    print("=" * 70)
    manifest_path = write_manifest("v3.1.0-merged", file_reports, [MASTER_PATH, CLEAN_PATH, REVIEW_PATH])
    print(f"  Manifest: {manifest_path}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    dedup_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_examples": quality_summary.total,
        "exact_duplicates": quality_summary.exact_duplicates,
        "near_duplicates_estimated": quality_summary.near_duplicates_estimated,
        "unique_examples": quality_summary.total - quality_summary.exact_duplicates,
        "duplicate_percentage": round(100 * quality_summary.exact_duplicates / quality_summary.total, 3) if quality_summary.total else 0,
        "duplicates_by_source_file": quality_summary.per_file_exact_duplicates,
        "oversized_buckets_sampled_not_exhaustive": quality_summary.oversized_buckets,
        "duplicate_groups_sample": quality_summary.duplicate_groups_sample,
    }
    DEDUP_REPORT_PATH.write_text(json.dumps(dedup_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  Dedup report: {DEDUP_REPORT_PATH}")

    write_samples(REVIEW_PATH, CLEAN_PATH, SAMPLES_PATH)
    print(f"  Samples: {SAMPLES_PATH}")

    lang_counts = Counter(r.source_language for r in file_reports for _ in range(r.entry_count or 0))
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_files": [asdict(r) for r in file_reports],
        "ingest": asdict(ingest_summary),
        "quality": asdict(quality_summary),
        "diversity_by_file": [asdict(d) for d in diversity_reports],
        "language_distribution_raw": dict(lang_counts),
    }
    AUDIT_JSON_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  Audit JSON: {AUDIT_JSON_PATH}")

    _write_audit_markdown(audit, AUDIT_MD_PATH)
    print(f"  Audit Markdown: {AUDIT_MD_PATH}")

    print()
    print("DONE. No model was trained. No model weights were created or modified.")


def _write_audit_markdown(audit: dict, path: Path) -> None:
    lines = ["# WOW Master Dataset Audit", "", f"Generated: {audit['generated_at']}", ""]
    lines.append("## Source files")
    lines.append("")
    lines.append("| File | Size | Entries | Language | Valid |")
    lines.append("|---|---|---|---|---|")
    for r in audit["source_files"]:
        lines.append(f"| {r['filename']} | {r['size_bytes']:,} | {r['entry_count']:,} | {r['source_language']} | {r['appears_valid']} |")
    lines.append("")
    q = audit["quality"]
    lines.append("## Quality summary")
    lines.append("")
    for k, v in q.items():
        if isinstance(v, (int, float, str, bool)):
            lines.append(f"- **{k}**: {v}")
    lines.append("")
    lines.append("## Diversity by file")
    lines.append("")
    lines.append("| File | Sample | Unique ratio | TTR | Distinct first-3 | Avg similarity | Risk |")
    lines.append("|---|---|---|---|---|---|---|")
    for d in audit["diversity_by_file"]:
        lines.append(
            f"| {d['source_file']} | {d['sample_size']} | {d['unique_text_ratio']} | "
            f"{d['type_token_ratio']} | {d['distinct_first3_ratio']} | "
            f"{d['avg_pairwise_shingle_similarity']} | {d['template_risk']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
