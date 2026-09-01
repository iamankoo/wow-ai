"""Model registry: tracks every trained WOW Brain model version, its
provenance, its evaluation metrics, and its lifecycle status. Backed by a
single JSON file (no database needed - this is small, append-mostly data)
so it lives alongside the model artifacts themselves
(training/models/wow-brain/REGISTRY.json by default).

Status lifecycle (docs/SELF_LEARNING.md "Model registry"):

    TRAINING -> EVALUATING -> CANDIDATE -> (REJECTED | CANARY -> PRODUCTION)
    PRODUCTION -> ROLLED_BACK (when a later version is promoted, or on
                                explicit rollback)

CANARY is a status only here - this module does not implement live
percentage-based traffic routing to a canary version. That's real
follow-on infra work; see docs/SELF_LEARNING.md "What canary means today".
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class ModelStatus(str, Enum):
    TRAINING = "training"
    EVALUATING = "evaluating"
    CANDIDATE = "candidate"
    CANARY = "canary"
    PRODUCTION = "production"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


@dataclass
class ModelRegistryEntry:
    model_id: str
    version: str
    base_model: str
    dataset_version: str
    training_config: dict
    training_timestamp: str
    metrics: dict = field(default_factory=dict)
    dataset_commit_ref: str | None = None
    status: ModelStatus = ModelStatus.TRAINING
    promoted_at: str | None = None
    promoted_from: str | None = None
    rejection_reason: str | None = None


class ModelRegistry:
    def __init__(self, path: Path):
        self._path = Path(path)

    def _load(self) -> dict[str, ModelRegistryEntry]:
        if not self._path.exists():
            return {}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return {
            v: ModelRegistryEntry(**{**entry, "status": ModelStatus(entry["status"])})
            for v, entry in raw.items()
        }

    def _save(self, entries: dict[str, ModelRegistryEntry]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {v: {**asdict(e), "status": e.status.value} for v, e in entries.items()}
        self._path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def register(self, entry: ModelRegistryEntry) -> None:
        entries = self._load()
        entries[entry.version] = entry
        self._save(entries)

    def get(self, version: str) -> ModelRegistryEntry | None:
        return self._load().get(version)

    def list(self) -> list[ModelRegistryEntry]:
        return sorted(self._load().values(), key=lambda e: e.training_timestamp)

    def get_production(self) -> ModelRegistryEntry | None:
        for entry in self._load().values():
            if entry.status == ModelStatus.PRODUCTION:
                return entry
        return None

    def set_status(self, version: str, status: ModelStatus, **extra) -> ModelRegistryEntry:
        entries = self._load()
        entry = entries.get(version)
        if entry is None:
            raise ValueError(f"No registered model version '{version}'")
        entries[version] = ModelRegistryEntry(**{**asdict(entry), "status": status, **extra})
        self._save(entries)
        return entries[version]

    def promote_to_canary(self, version: str) -> ModelRegistryEntry:
        return self.set_status(version, ModelStatus.CANARY)

    def promote_to_production(self, version: str) -> ModelRegistryEntry:
        """Promotes `version` to PRODUCTION, rolling back whatever was
        PRODUCTION before it (if anything)."""
        entries = self._load()
        current_prod = next((e for e in entries.values() if e.status == ModelStatus.PRODUCTION), None)
        if current_prod is not None:
            entries[current_prod.version] = ModelRegistryEntry(
                **{**asdict(current_prod), "status": ModelStatus.ROLLED_BACK}
            )
        target = entries.get(version)
        if target is None:
            raise ValueError(f"No registered model version '{version}'")
        entries[version] = ModelRegistryEntry(**{
            **asdict(target),
            "status": ModelStatus.PRODUCTION,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "promoted_from": current_prod.version if current_prod else None,
        })
        self._save(entries)
        return entries[version]

    def rollback_to(self, version: str) -> ModelRegistryEntry:
        """Explicit rollback: makes `version` PRODUCTION again (it must
        already be registered, typically as ROLLED_BACK)."""
        return self.promote_to_production(version)

    def reject(self, version: str, *, reason: str) -> ModelRegistryEntry:
        return self.set_status(version, ModelStatus.REJECTED, rejection_reason=reason)
