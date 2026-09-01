"""Exports the current annotation store state to a versioned, checksummed
dataset snapshot under training/datasets/versions/<version>/ - reusing the
existing versioning.py manifest machinery. The original 33K
(wow_33k_relevant.jsonl) and the master/clean datasets are never modified;
this only ever writes new, separately versioned files.

Each export is a point-in-time snapshot, so re-exporting later under a new
version name (v3.2.0-annotated, v3.3.0, ...) is the expected way to track
annotation progress over multiple sessions.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from training.pipeline.annotation.quality_gates import balance_report, evaluate_quality_gates
from training.pipeline.annotation.schema import resolve_active_label
from training.pipeline.versioning import version_dir_for, write_manifest

USABLE_STATUSES = ("approved", "corrected")


def export_version(conn: sqlite3.Connection, version: str, annotator_notes: str = "") -> dict:
    version_dir = version_dir_for(version)
    version_dir.mkdir(parents=True, exist_ok=True)

    all_path = version_dir / "wow_annotation_snapshot_all.jsonl"
    train_ready_path = version_dir / "wow_annotation_train_ready.jsonl"
    hard_negatives_path = version_dir / "wow_annotation_hard_negatives_reference.jsonl"

    rows = conn.execute("SELECT * FROM annotations ORDER BY source_order ASC").fetchall()
    written_all = 0
    written_ready = 0
    with all_path.open("w", encoding="utf-8") as all_f, train_ready_path.open("w", encoding="utf-8") as ready_f:
        for r in rows:
            record = {k: r[k] for k in r.keys()}
            all_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            written_all += 1
            if r["review_status"] in USABLE_STATUSES:
                intent, context, action = resolve_active_label(r)
                ready_f.write(json.dumps({
                    "id": r["id"], "text": r["text"], "language": r["language"],
                    "intent": intent, "context_mode": context, "action": action,
                    "label_source": r["label_source"], "approved_by": r["approved_by"],
                    "source_file": r["source_file"],
                    "source_line": r["source_line"], "source_order": r["source_order"],
                    "annotator": r["annotator"], "annotated_at": r["annotated_at"],
                }, ensure_ascii=False) + "\n")
                written_ready += 1

    gate_result = evaluate_quality_gates(conn)
    balance = balance_report(conn)

    stats = {
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "annotator_notes": annotator_notes,
        "total_snapshotted": written_all,
        "train_ready_count": written_ready,
        "quality_gates": asdict(gate_result),
        "balance": balance,
    }
    stats_path = version_dir / "STATS.json"
    stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest_path = write_manifest(version_dir, [all_path, train_ready_path, stats_path])

    return {
        "version_dir": str(version_dir),
        "all_path": str(all_path),
        "train_ready_path": str(train_ready_path),
        "stats_path": str(stats_path),
        "manifest_path": str(manifest_path),
        "written_all": written_all,
        "written_ready": written_ready,
        "train_ready": gate_result.train_ready,
    }
