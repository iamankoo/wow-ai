"""Dataset management CLI - lets you personally inspect, validate,
deduplicate, score, and version the dataset without writing throwaway
scripts. See docs/DATASET.md "Dataset management CLI" for full usage.

Usage:
    python -m training.pipeline.cli validate <input.jsonl>
    python -m training.pipeline.cli stats <input.jsonl> [--output report.json]
    python -m training.pipeline.cli inspect <input.jsonl> --index 0
    python -m training.pipeline.cli inspect <input.jsonl> --id <example_id>
    python -m training.pipeline.cli filter <input.jsonl> --status pass --output out.jsonl
    python -m training.pipeline.cli dedupe <input.jsonl>
    python -m training.pipeline.cli split <input.jsonl> --version v3.0.0
    python -m training.pipeline.cli version list
    python -m training.pipeline.cli version verify v3.0.0
"""

import argparse
import json
import sys
from pathlib import Path

from training.pipeline.label_validate import validate_hard_negative, validate_labels
from training.pipeline.quality import ScoredExample, score_batch
from training.pipeline.schema import RawExample
from training.pipeline.split import stratified_three_way_split
from training.pipeline.stats import compute_pipeline_stats
from training.pipeline.versioning import VERSIONS_DIR, verify_manifest, version_dir_for, write_manifest


def _load_examples(path: Path) -> list[RawExample]:
    examples = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                examples.append(RawExample.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError) as e:
                raise SystemExit(f"{path}:{line_no}: malformed record - {e}")
    return examples


def _write_examples(path: Path, examples: list[RawExample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")


def cmd_validate(args: argparse.Namespace) -> int:
    examples = _load_examples(args.input)
    errors = 0
    for i, ex in enumerate(examples):
        label_result = validate_labels(ex)
        hard_neg_result = validate_hard_negative(ex)
        for e in label_result.errors + hard_neg_result.errors:
            print(f"  [{i}] {ex.text!r}: {e}")
            errors += 1
    print(f"Validated {len(examples)} examples, {errors} problem(s) found.")
    return 1 if errors else 0


def cmd_stats(args: argparse.Namespace) -> int:
    examples = _load_examples(args.input)
    scored = score_batch(examples)
    report = compute_pipeline_stats(scored)
    output = args.output or args.input.with_suffix(".stats.json")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Total: {report['total_scored']}  Passing: {report['passing_count']}")
    print(f"Status distribution: {report['status_distribution']}")
    print(f"Hard negatives: {report['hard_negative_count']}")
    print(f"Exact duplicates: {report['exact_duplicate_count']}  Near duplicates: {report['near_duplicate_count']}")
    print(f"PII flagged: {report['pii_flagged_count']}  Language mismatches: {report['language_mismatch_count']}")
    print(f"Average quality score: {report['avg_quality_score']}")
    print(f"Full report written to {output}")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    examples = _load_examples(args.input)
    if args.index is not None:
        if not 0 <= args.index < len(examples):
            raise SystemExit(f"index {args.index} out of range (0-{len(examples) - 1})")
        target = [(args.index, examples[args.index])]
    elif args.id is not None:
        target = [(i, e) for i, e in enumerate(examples) if e.example_id() == args.id]
        if not target:
            raise SystemExit(f"no example with id {args.id}")
    else:
        raise SystemExit("pass --index or --id")

    for i, ex in target:
        scored = score_batch([ex])[0]
        print(f"[{i}] id={ex.example_id()}")
        print(json.dumps({**ex.to_dict(), "quality": vars(scored.flags)}, indent=2, ensure_ascii=False))
    return 0


def cmd_filter(args: argparse.Namespace) -> int:
    examples = _load_examples(args.input)
    scored = score_batch(examples)
    kept = [s.example for s in scored if s.flags.status == args.status]
    _write_examples(args.output, kept)
    print(f"Kept {len(kept)}/{len(examples)} examples with status={args.status} -> {args.output}")
    return 0


def cmd_dedupe(args: argparse.Namespace) -> int:
    from training.pipeline.dedup import deduplicate

    examples = _load_examples(args.input)
    report = deduplicate(examples)
    print(f"Total: {report.total}  Unique: {report.unique_count}")
    print(f"Exact duplicates: {len(report.exact_duplicates)}")
    print(f"Near duplicates: {len(report.near_duplicates)}")
    for i, j, sim in report.near_duplicates[:10]:
        print(f"  {sim:.2f}: [{i}] {examples[i].text!r}  ~=  [{j}] {examples[j].text!r}")
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    examples = _load_examples(args.input)
    scored = score_batch(examples)
    passing = [s.example for s in scored if s.flags.status == "pass"]
    reviewed = [s for s in scored if s.flags.status == "review"]
    rejected = [s for s in scored if s.flags.status == "reject"]

    print(f"Scored {len(examples)}: pass={len(passing)} review={len(reviewed)} reject={len(rejected)}")
    if reviewed:
        print(f"  ({len(reviewed)} 'review' examples excluded from the split - fix or explicitly re-include)")
    if rejected:
        print(f"  ({len(rejected)} 'reject' examples excluded - see --output-rejected to inspect)")

    split_result = stratified_three_way_split(passing, seed=args.seed)

    version_dir = version_dir_for(args.version)
    processed_dir = version_dir / "processed"
    raw_path = version_dir / "raw.jsonl"
    train_path = processed_dir / "train.jsonl"
    val_path = processed_dir / "val.jsonl"
    test_path = processed_dir / "test.jsonl"

    _write_examples(raw_path, examples)
    _write_examples(train_path, split_result.train)
    _write_examples(val_path, split_result.val)
    _write_examples(test_path, split_result.test)

    stats_path = processed_dir / "STATS.json"
    stats_path.write_text(
        json.dumps(compute_pipeline_stats(scored), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    manifest_path = write_manifest(version_dir, [raw_path, train_path, val_path, test_path, stats_path])

    print(f"train={len(split_result.train)} val={len(split_result.val)} test={len(split_result.test)}")
    print(f"Written to {version_dir}")
    print(f"Manifest: {manifest_path}")
    return 0


def cmd_version_list(args: argparse.Namespace) -> int:
    if not VERSIONS_DIR.exists():
        print("No versions directory found.")
        return 0
    for d in sorted(VERSIONS_DIR.iterdir()):
        if d.is_dir():
            manifest = d / "MANIFEST.json"
            status = "has manifest" if manifest.exists() else "no manifest"
            print(f"  {d.name}  ({status})")
    return 0


def cmd_version_verify(args: argparse.Namespace) -> int:
    ok, mismatches = verify_manifest(version_dir_for(args.version))
    if ok:
        print(f"{args.version}: all checksums verified OK.")
        return 0
    print(f"{args.version}: {len(mismatches)} problem(s):")
    for m in mismatches:
        print(f"  {m}")
    return 1


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser(prog="python -m training.pipeline.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="Check schema/taxonomy/hard-negative validity.")
    p.add_argument("input", type=Path)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("stats", help="Full quality-scored statistics report.")
    p.add_argument("input", type=Path)
    p.add_argument("--output", type=Path)
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("inspect", help="Show one example's full record + quality flags.")
    p.add_argument("input", type=Path)
    p.add_argument("--index", type=int)
    p.add_argument("--id", type=str)
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("filter", help="Write only examples matching a quality status.")
    p.add_argument("input", type=Path)
    p.add_argument("--status", choices=["pass", "review", "reject"], required=True)
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(func=cmd_filter)

    p = sub.add_parser("dedupe", help="Report exact and near-duplicates.")
    p.add_argument("input", type=Path)
    p.set_defaults(func=cmd_dedupe)

    p = sub.add_parser("split", help="Score, filter to 'pass', stratified 3-way split, version + manifest.")
    p.add_argument("input", type=Path)
    p.add_argument("--version", required=True, help="e.g. v3.0.0")
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_split)

    version_parser = sub.add_parser("version", help="Version management.")
    version_sub = version_parser.add_subparsers(dest="version_command", required=True)
    vp = version_sub.add_parser("list")
    vp.set_defaults(func=cmd_version_list)
    vp = version_sub.add_parser("verify")
    vp.add_argument("version")
    vp.set_defaults(func=cmd_version_verify)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
