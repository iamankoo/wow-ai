"""Re-exports the canonical WOW taxonomy from the backend.

The backend (`backend/app/brain/taxonomy.py`) is the single source of truth
for intents, context modes, actions, and caller relationships - training
code must never redefine these. Backend has no dependency on training/, so
this one-directional import (training -> backend) does not pull any ML
dependency into the production backend.
"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.brain.taxonomy import (  # noqa: E402
    ACTION_DESCRIPTIONS,
    CONTEXT_DESCRIPTIONS,
    INTENT_DESCRIPTIONS,
    Action,
    CallerRelationship,
    ContextMode,
    Intent,
    is_valid_action,
    is_valid_context,
    is_valid_intent,
    is_valid_relationship,
)

__all__ = [
    "Action",
    "ACTION_DESCRIPTIONS",
    "CallerRelationship",
    "ContextMode",
    "CONTEXT_DESCRIPTIONS",
    "Intent",
    "INTENT_DESCRIPTIONS",
    "is_valid_action",
    "is_valid_context",
    "is_valid_intent",
    "is_valid_relationship",
]
