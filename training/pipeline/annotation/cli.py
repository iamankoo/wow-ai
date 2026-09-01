"""Interactive terminal CLI for human-assisted annotation of the WOW 33K
dataset.

    python -m training.pipeline.annotation.cli init
    python -m training.pipeline.annotation.cli annotate --annotator yourname
    python -m training.pipeline.annotation.cli stats
    python -m training.pipeline.annotation.cli export --version v3.2.0-annotated
    python -m training.pipeline.annotation.cli hard-negatives

This tool never trains a model, never modifies v0/v1 weights, and never
promotes anything - it only helps a human build a labeled dataset. Every
label a human enters is validated against backend/app/brain/taxonomy.py
before it is accepted; the tool cannot write an invalid or off-taxonomy
label.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from training.pipeline.annotation import hard_negatives as hn
from training.pipeline.annotation.bulk_approve import (
    execute_bulk_approval,
    execute_bulk_approve_all_pending,
    post_approval_report,
    preview_bulk_approval,
)
from training.pipeline.annotation.export import export_version
from training.pipeline.annotation.prepare_training_set import prepare_and_write
from training.pipeline.annotation.quality_gates import balance_report, evaluate_quality_gates
from training.pipeline.annotation.schema import Action, ContextMode, Intent
from training.pipeline.annotation.store import (
    DEFAULT_DB_PATH,
    apply_action,
    connect,
    get_stats,
    init_store,
    next_pending,
)
from training.pipeline.taxonomy_analysis import (
    _load_33k,
    scan_hard_negative_opportunities,
)

INTENT_LIST = [i.value for i in Intent]
CONTEXT_LIST = [c.value for c in ContextMode]
ACTION_LIST = [a.value for a in Action]


def _print_numbered(label: str, values: list[str]) -> None:
    print(f"  {label}:")
    for i, v in enumerate(values, start=1):
        print(f"    {i:>2}. {v}")


def _pick_from_list(prompt: str, values: list[str], allow_none: bool = False, default: str | None = None) -> str | None:
    while True:
        raw = input(f"{prompt} > ").strip()
        if raw == "":
            return default
        if allow_none and raw.lower() in ("none", "n/a", "-"):
            return None
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(values):
                return values[idx - 1]
        elif raw.upper() in values:
            return raw.upper()
        print(f"  invalid choice: {raw!r} (enter a number 1-{len(values)}, a full name, or blank to keep default)")


def cmd_init(args: argparse.Namespace) -> None:
    print("Computing hard-negative-opportunity ids from the real 33K data...")
    records = _load_33k()
    findings = scan_hard_negative_opportunities(records, max_samples=100_000)
    hard_ids = set()
    text_to_id = {r["text"]: r["id"] for r in records}
    for f in findings:
        for q in f.sample_quotes:
            rid = text_to_id.get(q["text"])
            if rid:
                hard_ids.add(rid)

    result = init_store(hard_negative_ids=hard_ids)
    print(json.dumps(result, indent=2))
    print(f"Store ready at {DEFAULT_DB_PATH}")


def cmd_stats(args: argparse.Namespace) -> None:
    conn = connect()
    print(json.dumps(get_stats(conn), indent=2, ensure_ascii=False))
    conn.close()


def _show_record(row, queue_position: int) -> None:
    from training.pipeline.annotation.ordering import TIER_NAMES

    print()
    print(f"Example (tier={row['tier']}:{TIER_NAMES.get(row['tier'], '?')})  queue_position~{queue_position}")
    print(f"ID: {row['id']}")
    print(f"Language: {row['language']}   Source: {row['source_file']}:{row['source_line']}")
    print(f"Text: {row['text']}")
    print()
    print(f"  Rule-based candidate : intent={row['rb_intent']} context={row['rb_context']} action={row['rb_action']} "
          f"({'committed' if row['rb_committed'] else 'no match'})")
    if row["v1_intent"]:
        print(f"  v1 model candidate   : intent={row['v1_intent']} (conf {row['v1_intent_conf']:.2f})  "
              f"context={row['v1_context']} (conf {row['v1_context_conf']:.2f})  "
              f"action={row['v1_action']} (conf {row['v1_action_conf']:.2f})")
    else:
        print("  v1 model candidate   : (not yet computed)")
    print(f"  >> Primary candidate : intent={row['candidate_intent']} context={row['candidate_context']} "
          f"action={row['candidate_action']}  (source={row['candidate_source']})")


def cmd_annotate(args: argparse.Namespace) -> None:
    conn = connect()
    annotator = args.annotator
    print(f"Annotating as: {annotator}")
    print("Commands: [A]pprove  [C]orrect  [R]eject  [S]kip  [Q]uit")

    count = 0
    while True:
        row = next_pending(conn)
        if row is None:
            print("No pending examples left. Queue is empty.")
            break
        _show_record(row, count)
        cmd = input("\nAction [A/C/R/S/Q] > ").strip().lower()

        if cmd in ("q", "quit"):
            print("Stopping. Progress is saved - resume any time with 'annotate'.")
            break
        if cmd in ("s", "skip", ""):
            apply_action(conn, row["id"], "skip", annotator)
            continue
        if cmd in ("a", "approve"):
            if row["candidate_intent"] is None:
                print("  No candidate to approve for this record - use Correct instead.")
                continue
            confidence = input("  Confidence 1-5 (blank=skip) > ").strip()
            conf_val = int(confidence) if confidence.isdigit() else None
            result = apply_action(conn, row["id"], "approve", annotator, confidence=conf_val)
        elif cmd in ("c", "correct"):
            print()
            _print_numbered("Intent", INTENT_LIST)
            intent = _pick_from_list("Intent", INTENT_LIST, default=row["candidate_intent"])
            _print_numbered("Context (blank/none allowed)", CONTEXT_LIST)
            context = _pick_from_list("Context", CONTEXT_LIST, allow_none=True, default=row["candidate_context"])
            _print_numbered("Action", ACTION_LIST)
            wow_action = _pick_from_list("Action", ACTION_LIST, default=row["candidate_action"])
            confidence = input("  Confidence 1-5 (blank=skip) > ").strip()
            conf_val = int(confidence) if confidence.isdigit() else None
            notes = input("  Notes (optional) > ").strip() or None
            result = apply_action(
                conn, row["id"], "correct", annotator,
                intent=intent, context=context, wow_action=wow_action,
                confidence=conf_val, notes=notes,
            )
        elif cmd in ("r", "reject"):
            notes = input("  Reason (optional) > ").strip() or None
            result = apply_action(conn, row["id"], "reject", annotator, notes=notes)
        else:
            print(f"  unrecognized command: {cmd!r}")
            continue

        if not result["ok"]:
            print(f"  REJECTED by validation: {result['errors']}")
            continue
        if result["hard_negative"]:
            hn.append_hard_negative(result["hard_negative"])
            print("  Hard negative captured (predicted label was wrong).")
        count += 1
        print(f"  saved. ({count} annotated this session)")

    conn.close()


def cmd_export(args: argparse.Namespace) -> None:
    conn = connect()
    result = export_version(conn, args.version, annotator_notes=args.notes or "")
    print(json.dumps(result, indent=2))
    conn.close()


def cmd_quality_gate(args: argparse.Namespace) -> None:
    conn = connect()
    gate = evaluate_quality_gates(conn)
    print(json.dumps(asdict(gate), indent=2, ensure_ascii=False))
    conn.close()


def cmd_balance(args: argparse.Namespace) -> None:
    conn = connect()
    print(json.dumps(balance_report(conn), indent=2, ensure_ascii=False))
    conn.close()


def cmd_hard_negatives(args: argparse.Namespace) -> None:
    print(json.dumps(hn.summarize(), indent=2, ensure_ascii=False))


def cmd_bulk_approve(args: argparse.Namespace) -> None:
    conn = connect()
    preview = preview_bulk_approval(conn)
    print(json.dumps(asdict(preview), indent=2, ensure_ascii=False))

    if not args.apply:
        print("\nPreview only - no records were changed. Re-run with --apply to execute.")
        conn.close()
        return

    result = execute_bulk_approval(conn)
    print("\nApplied:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("\nQuality gate after bulk approval:")
    print(json.dumps(asdict(evaluate_quality_gates(conn)), indent=2, ensure_ascii=False))
    conn.close()


def cmd_prepare_training_set(args: argparse.Namespace) -> None:
    conn = connect()
    result = prepare_and_write(conn, args.version, seed=args.seed)
    print(json.dumps({k: v for k, v in result.items() if k != "report"}, indent=2, ensure_ascii=False))
    print("\nFull report also written to:", result["stats_path"])
    conn.close()


def cmd_bulk_approve_all(args: argparse.Namespace) -> None:
    conn = connect()
    pending = conn.execute(
        "SELECT COUNT(*) FROM annotations WHERE review_status='pending' AND label_source='candidate'"
    ).fetchone()[0]
    print(f"{pending} pending records would be approved AS-IS (no confidence filter), "
          f"approved_by={args.approved_by!r}, confidence={args.confidence}.")

    if not args.confirm:
        print("\nPreview only - no records were changed. Re-run with --confirm to execute.")
        conn.close()
        return

    result = execute_bulk_approve_all_pending(conn, approved_by=args.approved_by, confidence=args.confidence)
    print("\nApplied:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("\nPost-approval dataset report:")
    print(json.dumps(post_approval_report(conn), indent=2, ensure_ascii=False))
    print("\nQuality gate after bulk approval:")
    print(json.dumps(asdict(evaluate_quality_gates(conn)), indent=2, ensure_ascii=False))
    conn.close()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser(prog="wow-annotate")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Seed/refresh the annotation store from the 33K + candidate labels")

    p_annotate = sub.add_parser("annotate", help="Start the interactive annotation session")
    p_annotate.add_argument("--annotator", default="anonymous")

    sub.add_parser("stats", help="Show current annotation progress statistics")

    p_export = sub.add_parser("export", help="Export a versioned snapshot")
    p_export.add_argument("--version", required=True, help="e.g. v3.2.0-annotated")
    p_export.add_argument("--notes", default="")

    sub.add_parser("quality-gate", help="Check TRAIN_READY quality gates")
    sub.add_parser("balance", help="Show label distribution / balance report (no rebalancing performed)")
    sub.add_parser("hard-negatives", help="Summarize captured hard negatives")

    p_bulk = sub.add_parser(
        "bulk-approve",
        help="Preview (default) or apply automated high-confidence candidate approval",
    )
    p_bulk.add_argument(
        "--apply", action="store_true",
        help="Actually apply the bulk approval. Without this flag, only a preview is shown.",
    )

    p_bulk_all = sub.add_parser(
        "bulk-approve-all",
        help="Approve ALL remaining pending candidates as-is (no confidence filter) - requires explicit human authorization",
    )
    p_bulk_all.add_argument("--approved-by", required=True, help='e.g. "Aniket_bulk_approval" - who authorized this')
    p_bulk_all.add_argument("--confidence", type=int, default=None, help="1-5, the authorizer's own rating of this decision (not model confidence)")
    p_bulk_all.add_argument("--confirm", action="store_true", help="Actually apply. Without this flag, only a preview is shown.")

    p_prepare = sub.add_parser(
        "prepare-training-set",
        help="Build a versioned, stratified, leakage-free train/val/test split from the approved records",
    )
    p_prepare.add_argument("--version", required=True, help="e.g. v3.2.0-train-ready")
    p_prepare.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()
    {
        "init": cmd_init,
        "annotate": cmd_annotate,
        "stats": cmd_stats,
        "export": cmd_export,
        "quality-gate": cmd_quality_gate,
        "balance": cmd_balance,
        "hard-negatives": cmd_hard_negatives,
        "bulk-approve": cmd_bulk_approve,
        "bulk-approve-all": cmd_bulk_approve_all,
        "prepare-training-set": cmd_prepare_training_set,
    }[args.command](args)


if __name__ == "__main__":
    main()
