"""Annotation record schema and enums for the WOW 33K human-assisted
labeling workflow.

This schema describes ONE annotation record per example in
wow_33k_relevant.jsonl. It never adds new taxonomy categories - intent,
context, and action values are always one of the members defined in
backend/app/brain/taxonomy.py (imported here, not re-declared) so the
annotation tool and the runtime provider can never drift apart.

label_source describes the ORIGIN of the currently-active label:
  - "candidate": a machine-suggested label nobody has reviewed yet.
  - "human":     a human typed/selected a label from scratch (the Correct
                 action), different from whatever candidate existed.
  - "reviewed":  a human looked at the candidate and confirmed it correct
                 as-is (the Approve action) - still human-verified truth.
  - "rejected":  a human decided this example is not usable at all (bad
                 text, unlabelable, out of scope) - the Reject action.

review_status is the WORKFLOW state, independent of where the label came
from:
  - "pending":   not yet reviewed by a human.
  - "approved":  human confirmed the candidate (label_source -> "reviewed").
  - "corrected": human supplied a different label (label_source -> "human").
  - "rejected":  human marked the example unusable (label_source -> "rejected").

Skipping an example leaves review_status "pending" and label_source
untouched - skip never writes a label.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.brain.taxonomy import Action, ContextMode, Intent  # noqa: E402

VALID_INTENTS: set[str] = {i.value for i in Intent}
VALID_CONTEXTS: set[str] = {c.value for c in ContextMode}
VALID_ACTIONS: set[str] = {a.value for a in Action}

LABEL_SOURCES = ("candidate", "human", "reviewed", "rejected")
REVIEW_STATUSES = ("pending", "approved", "corrected", "rejected")
CANDIDATE_ORIGINS = ("rule_based", "v1", "merged", "none")


def is_valid_intent(value: Optional[str]) -> bool:
    return value in VALID_INTENTS


def is_valid_context(value: Optional[str]) -> bool:
    return value is None or value in VALID_CONTEXTS


def is_valid_action(value: Optional[str]) -> bool:
    return value in VALID_ACTIONS


def resolve_active_label(row) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Given a stored record (sqlite3.Row or dict) returns the (intent,
    context, action) that should be treated as its current label, given its
    label_source:
      - "human"/"reviewed": a human supplied or confirmed the label -> the
        human_* columns.
      - "candidate": nobody (human) has touched the label. This also covers
        an automated bulk-approval (review_status="approved",
        approved_by="automated_high_confidence") - approved_by marks WHO
        approved it, but the label values themselves still live in
        candidate_* because no human_* fields were ever written for an
        automated approval; using candidate_* is correct and does not
        imply human review happened.
      - "rejected"/anything else: no usable label.
    Used consistently by quality_gates.py and export.py so an automated
    approval is never silently treated as having no label.
    """
    label_source = row["label_source"]
    if label_source in ("human", "reviewed"):
        return row["human_intent"], row["human_context"], row["human_action"]
    if label_source == "candidate":
        return row["candidate_intent"], row["candidate_context"], row["candidate_action"]
    return None, None, None


@dataclass
class AnnotationRecord:
    # Immutable lineage - copied verbatim from wow_33k_relevant.jsonl, never
    # modified by this package.
    id: str
    text: str
    language: str
    source_file: str
    source_line: int
    source_order: int

    # Candidate labels - advisory only, never ground truth.
    candidate_intent: Optional[str] = None
    candidate_context: Optional[str] = None
    candidate_action: Optional[str] = None
    candidate_confidence: Optional[float] = None
    candidate_source: str = "none"

    # Human-verified labels - null until a human has acted on this record.
    human_intent: Optional[str] = None
    human_context: Optional[str] = None
    human_action: Optional[str] = None

    label_source: str = "candidate"
    review_status: str = "pending"
    confidence: Optional[int] = None  # 1-5 human-provided rating
    annotator: Optional[str] = None
    notes: Optional[str] = None
    priority_score: float = 0.0
    annotated_at: Optional[str] = None

    def active_intent(self) -> Optional[str]:
        return self.human_intent if self.label_source in ("human", "reviewed") else self.candidate_intent

    def active_context(self) -> Optional[str]:
        return self.human_context if self.label_source in ("human", "reviewed") else self.candidate_context

    def active_action(self) -> Optional[str]:
        return self.human_action if self.label_source in ("human", "reviewed") else self.candidate_action

    def validate(self) -> list[str]:
        errors = []
        if self.label_source not in LABEL_SOURCES:
            errors.append(f"invalid label_source: {self.label_source}")
        if self.review_status not in REVIEW_STATUSES:
            errors.append(f"invalid review_status: {self.review_status}")
        if self.review_status in ("approved", "corrected"):
            intent = self.active_intent()
            action = self.active_action()
            context = self.active_context()
            if not is_valid_intent(intent):
                errors.append(f"invalid/missing intent for {self.review_status} record: {intent!r}")
            if not is_valid_action(action):
                errors.append(f"invalid/missing action for {self.review_status} record: {action!r}")
            if not is_valid_context(context):
                errors.append(f"invalid context value: {context!r}")
        if self.confidence is not None and not (1 <= self.confidence <= 5):
            errors.append(f"confidence must be 1-5, got {self.confidence}")
        return errors
