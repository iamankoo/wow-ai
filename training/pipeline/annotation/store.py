"""SQLite-backed annotation store for the WOW 33K dataset.

Why SQLite instead of rewriting a 33,000-line JSONL file on every single
annotation: the annotation workflow is fundamentally a long-running,
incrementally-updated, randomly-accessed state machine (one row's
review_status flips per keypress), and a flat-file rewrite-the-whole-thing
approach does not scale to that access pattern. SQLite is stdlib, gives us
indexed lookups and atomic single-row updates, and the store is exported to
plain JSONL for versioning/training-input purposes via export.py - so
downstream consumers never need to know SQLite was involved.

Human annotations already recorded in the database are NEVER overwritten by
re-running init/refresh - only rows still in label_source="candidate",
review_status="pending" have their candidate columns refreshed.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from training.pipeline.annotation.ordering import (
    PriorityContext,
    assign_tier,
    build_priority_context,
    priority_score,
)
from training.pipeline.annotation.schema import (
    LABEL_SOURCES,
    REVIEW_STATUSES,
    is_valid_action,
    is_valid_context,
    is_valid_intent,
)

DATASETS_DIR = Path(__file__).resolve().parents[2] / "datasets"
RELEVANT_PATH = DATASETS_DIR / "v3_raw" / "wow_33k_relevant.jsonl"
RULE_BASED_CANDIDATES_PATH = DATASETS_DIR / "v3_raw" / "wow_33k_candidate_labels.jsonl"
V1_CANDIDATES_PATH = DATASETS_DIR / "v3_raw" / "wow_33k_candidate_labels_v1.jsonl"
DEFAULT_DB_PATH = DATASETS_DIR / "annotation" / "wow_33k_annotation.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS annotations (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    language TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_line INTEGER NOT NULL,
    source_order INTEGER NOT NULL,

    rb_intent TEXT, rb_context TEXT, rb_action TEXT, rb_committed INTEGER DEFAULT 0,
    v1_intent TEXT, v1_context TEXT, v1_action TEXT,
    v1_intent_conf REAL, v1_context_conf REAL, v1_action_conf REAL,

    candidate_intent TEXT, candidate_context TEXT, candidate_action TEXT,
    candidate_confidence REAL, candidate_source TEXT DEFAULT 'none',

    human_intent TEXT, human_context TEXT, human_action TEXT,
    label_source TEXT NOT NULL DEFAULT 'candidate',
    review_status TEXT NOT NULL DEFAULT 'pending',
    confidence INTEGER,
    annotator TEXT,
    approved_by TEXT,
    notes TEXT,
    tier INTEGER NOT NULL DEFAULT 7,
    priority_score REAL NOT NULL DEFAULT 7.0,
    annotated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_status ON annotations(review_status);
CREATE INDEX IF NOT EXISTS idx_priority ON annotations(priority_score);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Adds columns introduced after the table was first created, without
    touching existing rows. Safe to call on every connect()."""
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(annotations)")}
    if "approved_by" not in existing_cols:
        conn.execute("ALTER TABLE annotations ADD COLUMN approved_by TEXT")
        conn.commit()


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _migrate(conn)
    return conn


def _read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _merge_candidate(rb: Optional[dict], v1: Optional[dict]) -> tuple:
    """Returns (intent, context, action, confidence, source)."""
    if rb and rb.get("label_source") == "candidate_rule_based":
        return rb["candidate_intent"], rb.get("candidate_context"), rb["candidate_action"], 1.0, "rule_based"
    if v1:
        return (
            v1["candidate_intent_v1"], v1["candidate_context_v1"], v1["candidate_action_v1"],
            v1["candidate_intent_v1_confidence"], "v1",
        )
    return None, None, None, None, "none"


def build_records(
    relevant_path: Path = RELEVANT_PATH,
    rb_path: Path = RULE_BASED_CANDIDATES_PATH,
    v1_path: Path = V1_CANDIDATES_PATH,
) -> list[dict]:
    """Loads and merges the raw 33K + both candidate sources into plain
    dicts, ready to seed or refresh the store. Pure function - no DB I/O -
    so it is directly unit-testable."""
    rb_by_id = {r["id"]: r for r in _read_jsonl(rb_path)}
    v1_by_id = {r["id"]: r for r in _read_jsonl(v1_path)}

    records = []
    for base in _read_jsonl(relevant_path):
        rb = rb_by_id.get(base["id"])
        v1 = v1_by_id.get(base["id"])
        cand_intent, cand_context, cand_action, cand_conf, cand_source = _merge_candidate(rb, v1)
        records.append({
            "id": base["id"],
            "text": base["text"],
            "language": base["language"],
            "source_file": base["source_file"],
            "source_line": base["source_line"],
            "source_order": base["source_order"],
            "rb_intent": rb["candidate_intent"] if rb else None,
            "rb_context": rb.get("candidate_context") if rb else None,
            "rb_action": rb["candidate_action"] if rb else None,
            "rb_committed": 1 if (rb and rb.get("label_source") == "candidate_rule_based") else 0,
            "v1_intent": v1["candidate_intent_v1"] if v1 else None,
            "v1_context": v1["candidate_context_v1"] if v1 else None,
            "v1_action": v1["candidate_action_v1"] if v1 else None,
            "v1_intent_conf": v1["candidate_intent_v1_confidence"] if v1 else None,
            "v1_context_conf": v1["candidate_context_v1_confidence"] if v1 else None,
            "v1_action_conf": v1["candidate_action_v1_confidence"] if v1 else None,
            "candidate_intent": cand_intent,
            "candidate_context": cand_context,
            "candidate_action": cand_action,
            "candidate_confidence": cand_conf,
            "candidate_source": cand_source,
        })
    return records


def compute_priorities(records: list[dict], hard_negative_ids: set) -> None:
    """Mutates each record in place, adding tier + priority_score."""
    ctx: PriorityContext = build_priority_context(records, hard_negative_ids)
    for r in records:
        tier = assign_tier(r, ctx)
        r["tier"] = tier
        r["priority_score"] = priority_score(tier, r["source_order"])


def init_store(
    db_path: Path = DEFAULT_DB_PATH,
    hard_negative_ids: Optional[set] = None,
    relevant_path: Path = RELEVANT_PATH,
    rb_path: Path = RULE_BASED_CANDIDATES_PATH,
    v1_path: Path = V1_CANDIDATES_PATH,
) -> dict:
    """Seeds (or refreshes) the annotation DB. Idempotent: existing rows
    with review_status != 'pending' or label_source != 'candidate' are left
    completely untouched - only fresh rows are inserted, and only the
    candidate_* columns of still-pending rows are refreshed."""
    records = build_records(relevant_path, rb_path, v1_path)
    compute_priorities(records, hard_negative_ids or set())

    conn = connect(db_path)
    inserted = 0
    refreshed = 0
    with conn:
        for r in records:
            existing = conn.execute("SELECT review_status, label_source FROM annotations WHERE id=?", (r["id"],)).fetchone()
            if existing is None:
                conn.execute(
                    """INSERT INTO annotations (
                        id, text, language, source_file, source_line, source_order,
                        rb_intent, rb_context, rb_action, rb_committed,
                        v1_intent, v1_context, v1_action, v1_intent_conf, v1_context_conf, v1_action_conf,
                        candidate_intent, candidate_context, candidate_action, candidate_confidence, candidate_source,
                        tier, priority_score
                    ) VALUES (?,?,?,?,?,?, ?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?, ?,?)""",
                    (
                        r["id"], r["text"], r["language"], r["source_file"], r["source_line"], r["source_order"],
                        r["rb_intent"], r["rb_context"], r["rb_action"], r["rb_committed"],
                        r["v1_intent"], r["v1_context"], r["v1_action"], r["v1_intent_conf"], r["v1_context_conf"], r["v1_action_conf"],
                        r["candidate_intent"], r["candidate_context"], r["candidate_action"], r["candidate_confidence"], r["candidate_source"],
                        r["tier"], r["priority_score"],
                    ),
                )
                inserted += 1
            elif existing["review_status"] == "pending" and existing["label_source"] == "candidate":
                conn.execute(
                    """UPDATE annotations SET
                        rb_intent=?, rb_context=?, rb_action=?, rb_committed=?,
                        v1_intent=?, v1_context=?, v1_action=?, v1_intent_conf=?, v1_context_conf=?, v1_action_conf=?,
                        candidate_intent=?, candidate_context=?, candidate_action=?, candidate_confidence=?, candidate_source=?,
                        tier=?, priority_score=?
                    WHERE id=?""",
                    (
                        r["rb_intent"], r["rb_context"], r["rb_action"], r["rb_committed"],
                        r["v1_intent"], r["v1_context"], r["v1_action"], r["v1_intent_conf"], r["v1_context_conf"], r["v1_action_conf"],
                        r["candidate_intent"], r["candidate_context"], r["candidate_action"], r["candidate_confidence"], r["candidate_source"],
                        r["tier"], r["priority_score"], r["id"],
                    ),
                )
                refreshed += 1
    conn.close()
    return {"total_records": len(records), "inserted": inserted, "refreshed_candidates": refreshed}


def next_pending(conn: sqlite3.Connection, annotator: Optional[str] = None) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM annotations WHERE review_status='pending' ORDER BY priority_score ASC LIMIT 1"
    ).fetchone()


def apply_action(
    conn: sqlite3.Connection,
    record_id: str,
    action: str,
    annotator: str,
    intent: Optional[str] = None,
    context: Optional[str] = None,
    wow_action: Optional[str] = None,
    confidence: Optional[int] = None,
    notes: Optional[str] = None,
) -> dict:
    """Applies one of approve/correct/reject/skip to a record. Pure
    state-transition logic, separated from any input()/terminal handling so
    it is directly unit-testable.

    Returns {"ok": bool, "errors": [...], "hard_negative": {...} | None}.
    """
    row = conn.execute("SELECT * FROM annotations WHERE id=?", (record_id,)).fetchone()
    if row is None:
        return {"ok": False, "errors": [f"no such record: {record_id}"], "hard_negative": None}

    now = datetime.now(timezone.utc).isoformat()
    hard_negative = None

    if action == "skip":
        return {"ok": True, "errors": [], "hard_negative": None}

    if action == "approve":
        final_intent = row["candidate_intent"]
        final_context = row["candidate_context"]
        final_action = row["candidate_action"]
        label_source = "reviewed"
        review_status = "approved"
    elif action == "correct":
        # context is nullable, so its caller-supplied value is taken as-is:
        # an explicit context=None means "this record has no context" and
        # must not be silently overwritten with the (possibly wrong)
        # candidate context. intent/action are never optional in the
        # taxonomy, so falling back to the candidate when unset is safe.
        final_intent = intent or row["candidate_intent"]
        final_context = context
        final_action = wow_action or row["candidate_action"]
        label_source = "human"
        review_status = "corrected"
        if row["candidate_intent"] and row["candidate_intent"] != final_intent:
            hard_negative = {
                "id": record_id,
                "text": row["text"],
                "language": row["language"],
                "predicted_intent": row["candidate_intent"],
                "correct_intent": final_intent,
                "predicted_context": row["candidate_context"],
                "correct_context": final_context,
                "predicted_action": row["candidate_action"],
                "correct_action": final_action,
                "candidate_source": row["candidate_source"],
                "corrected_at": now,
                "annotator": annotator,
            }
    elif action == "reject":
        final_intent, final_context, final_action = None, None, None
        label_source = "rejected"
        review_status = "rejected"
    else:
        return {"ok": False, "errors": [f"unknown action: {action}"], "hard_negative": None}

    errors = []
    if review_status in ("approved", "corrected"):
        if not is_valid_intent(final_intent):
            errors.append(f"invalid intent: {final_intent!r}")
        if not is_valid_action(final_action):
            errors.append(f"invalid action: {final_action!r}")
        if not is_valid_context(final_context):
            errors.append(f"invalid context: {final_context!r}")
    if confidence is not None and not (1 <= confidence <= 5):
        errors.append(f"confidence must be 1-5, got {confidence}")
    if errors:
        return {"ok": False, "errors": errors, "hard_negative": None}

    with conn:
        conn.execute(
            """UPDATE annotations SET
                human_intent=?, human_context=?, human_action=?,
                label_source=?, review_status=?, confidence=?, annotator=?, notes=?, annotated_at=?
            WHERE id=?""",
            (final_intent, final_context, final_action, label_source, review_status,
             confidence, annotator, notes, now, record_id),
        )

    return {"ok": True, "errors": [], "hard_negative": hard_negative}


def get_stats(conn: sqlite3.Connection) -> dict:
    from training.pipeline.annotation.schema import resolve_active_label

    total = conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0]
    by_status = dict(conn.execute("SELECT review_status, COUNT(*) FROM annotations GROUP BY review_status").fetchall())
    by_source = dict(conn.execute("SELECT label_source, COUNT(*) FROM annotations GROUP BY label_source").fetchall())
    by_tier_pending = dict(conn.execute(
        "SELECT tier, COUNT(*) FROM annotations WHERE review_status='pending' GROUP BY tier"
    ).fetchall())
    candidate_coverage = dict(conn.execute(
        "SELECT candidate_source, COUNT(*) FROM annotations GROUP BY candidate_source"
    ).fetchall())
    by_approved_by = dict(conn.execute(
        "SELECT approved_by, COUNT(*) FROM annotations WHERE approved_by IS NOT NULL GROUP BY approved_by"
    ).fetchall())
    usable_rows = conn.execute(
        "SELECT * FROM annotations WHERE review_status IN ('approved', 'corrected')"
    ).fetchall()
    intent_dist: dict = {}
    for r in usable_rows:
        intent, _, _ = resolve_active_label(r)
        if intent:
            intent_dist[intent] = intent_dist.get(intent, 0) + 1
    lang_dist = dict(conn.execute("SELECT language, COUNT(*) FROM annotations GROUP BY language").fetchall())
    return {
        "total": total,
        "by_review_status": by_status,
        "by_label_source": by_source,
        "by_approved_by": by_approved_by,
        "pending_by_tier": by_tier_pending,
        "candidate_coverage": candidate_coverage,
        "active_intent_distribution": intent_dist,
        "language_distribution": lang_dist,
        "progress_pct": round(100 * (total - by_status.get("pending", 0)) / total, 2) if total else 0.0,
    }
