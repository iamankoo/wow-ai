import pytest

from app.learning.model_registry import ModelRegistry, ModelRegistryEntry, ModelStatus


def _entry(version: str, **kw) -> ModelRegistryEntry:
    defaults = dict(
        model_id="wow-brain", version=version, base_model="distilbert-base-multilingual-cased",
        dataset_version="2.0.0", training_config={"epochs": 20}, training_timestamp="2026-01-01T00:00:00Z",
        metrics={"intent_accuracy": 0.8},
    )
    defaults.update(kw)
    return ModelRegistryEntry(**defaults)


@pytest.fixture
def registry(tmp_path) -> ModelRegistry:
    return ModelRegistry(tmp_path / "REGISTRY.json")


def test_register_and_get_round_trips(registry):
    registry.register(_entry("v1"))
    entry = registry.get("v1")
    assert entry is not None
    assert entry.status == ModelStatus.TRAINING
    assert entry.metrics == {"intent_accuracy": 0.8}


def test_get_unknown_version_returns_none(registry):
    assert registry.get("v99") is None


def test_list_returns_all_registered_versions_ordered_by_timestamp(registry):
    registry.register(_entry("v1", training_timestamp="2026-01-01T00:00:00Z"))
    registry.register(_entry("v0", training_timestamp="2025-01-01T00:00:00Z"))
    versions = [e.version for e in registry.list()]
    assert versions == ["v0", "v1"]


def test_promote_to_production_sets_status_and_promoted_from(registry):
    registry.register(_entry("v1", status=ModelStatus.CANDIDATE))
    promoted = registry.promote_to_production("v1")
    assert promoted.status == ModelStatus.PRODUCTION
    assert promoted.promoted_at is not None
    assert registry.get_production().version == "v1"


def test_promoting_a_new_version_rolls_back_the_previous_production(registry):
    registry.register(_entry("v0", status=ModelStatus.PRODUCTION))
    registry.register(_entry("v1", status=ModelStatus.CANDIDATE))
    registry.promote_to_production("v1")

    assert registry.get("v0").status == ModelStatus.ROLLED_BACK
    assert registry.get("v1").status == ModelStatus.PRODUCTION
    assert registry.get("v1").promoted_from == "v0"


def test_rollback_restores_a_prior_version_to_production(registry):
    registry.register(_entry("v0", status=ModelStatus.PRODUCTION))
    registry.register(_entry("v1", status=ModelStatus.CANDIDATE))
    registry.promote_to_production("v1")
    registry.rollback_to("v0")

    assert registry.get("v0").status == ModelStatus.PRODUCTION
    assert registry.get("v1").status == ModelStatus.ROLLED_BACK


def test_reject_sets_status_and_reason(registry):
    registry.register(_entry("v1", status=ModelStatus.EVALUATING))
    rejected = registry.reject("v1", reason="action_accuracy_regressed")
    assert rejected.status == ModelStatus.REJECTED
    assert rejected.rejection_reason == "action_accuracy_regressed"


def test_promote_to_canary_sets_canary_status(registry):
    registry.register(_entry("v1", status=ModelStatus.CANDIDATE))
    canary = registry.promote_to_canary("v1")
    assert canary.status == ModelStatus.CANARY


def test_registry_persists_across_instances(tmp_path):
    path = tmp_path / "REGISTRY.json"
    ModelRegistry(path).register(_entry("v1"))
    reloaded = ModelRegistry(path)
    assert reloaded.get("v1") is not None


def test_set_status_on_unknown_version_raises(registry):
    with pytest.raises(ValueError):
        registry.promote_to_canary("v99")
