"""Tests for the pure-Python training helpers in training/training/train.py -
class-weight computation, early stopping, and config loading. These do not
load torch/transformers or any model, so they run fast and without the
optional ML dependencies.
"""

import pytest

from training.training.config import TrainingConfig
from training.training.train import EarlyStopper, _read_dataset_version, compute_class_weights


def test_compute_class_weights_balanced_classes_get_equal_weight():
    records = [{"intent": "A"}, {"intent": "A"}, {"intent": "B"}, {"intent": "B"}]
    label2id = {"A": 0, "B": 1}
    weights = compute_class_weights(records, "intent", label2id)
    assert weights[0] == pytest.approx(weights[1])


def test_compute_class_weights_gives_rare_class_a_higher_weight():
    records = [{"intent": "MAJORITY"}] * 18 + [{"intent": "MINORITY"}] * 2
    label2id = {"MAJORITY": 0, "MINORITY": 1}
    weights = compute_class_weights(records, "intent", label2id)
    assert weights[1] > weights[0]
    # balanced formula: total / (num_classes * count)
    assert weights[0] == pytest.approx(20 / (2 * 18))
    assert weights[1] == pytest.approx(20 / (2 * 2))


def test_compute_class_weights_ignores_records_missing_the_label_field():
    records = [{"intent": "A"}, {"action": "SOMETHING_ELSE"}]
    label2id = {"A": 0}
    weights = compute_class_weights(records, "intent", label2id)
    assert weights == [pytest.approx(1.0)]


def test_compute_class_weights_zero_for_unseen_label():
    records = [{"intent": "A"}, {"intent": "A"}]
    label2id = {"A": 0, "NEVER_SEEN": 1}
    weights = compute_class_weights(records, "intent", label2id)
    assert weights[1] == 0.0


def test_early_stopper_tracks_best_and_reports_improvement():
    stopper = EarlyStopper(patience=2)
    assert stopper.step(1, 0.5) is True
    assert stopper.step(2, 0.6) is True
    assert stopper.best == 0.6
    assert stopper.best_epoch == 2
    assert stopper.should_stop is False


def test_early_stopper_stops_after_patience_exhausted():
    stopper = EarlyStopper(patience=2)
    stopper.step(1, 0.8)
    assert stopper.step(2, 0.7) is False  # no improvement, bad_epochs=1
    assert stopper.should_stop is False
    assert stopper.step(3, 0.75) is False  # still below best, bad_epochs=2
    assert stopper.should_stop is True
    assert stopper.best == 0.8
    assert stopper.best_epoch == 1


def test_early_stopper_disabled_when_patience_is_zero():
    stopper = EarlyStopper(patience=0)
    for epoch, value in enumerate([0.9, 0.1, 0.05, 0.01], start=1):
        stopper.step(epoch, value)
        assert stopper.should_stop is False


def test_training_config_defaults_for_v0_style_yaml_without_v1_fields(tmp_path):
    config_path = tmp_path / "model_config.yaml"
    config_path.write_text(
        """
base_model: "prajjwal1/bert-tiny"
seed: 42
max_length: 64
batch_size: 8
learning_rate: 0.00005
epochs: 8
val_fraction: 0.15
heads:
  - name: intent
    label_field: intent
    required: true
dataset_dir: "training/datasets/processed"
model_version: "v0"
output_dir: "training/models/wow-brain/v0"
""",
        encoding="utf-8",
    )
    cfg = TrainingConfig.load(config_path)
    assert cfg.early_stopping_patience == 0
    assert cfg.class_weighting is False


def test_training_config_reads_v1_style_fields(tmp_path):
    config_path = tmp_path / "model_config_v1.yaml"
    config_path.write_text(
        """
base_model: "distilbert-base-multilingual-cased"
seed: 42
max_length: 64
batch_size: 16
learning_rate: 0.00003
epochs: 20
val_fraction: 0.15
class_weighting: true
early_stopping_patience: 4
heads:
  - name: intent
    label_field: intent
    required: true
dataset_dir: "training/datasets/processed"
model_version: "v1"
output_dir: "training/models/wow-brain/v1"
""",
        encoding="utf-8",
    )
    cfg = TrainingConfig.load(config_path)
    assert cfg.early_stopping_patience == 4
    assert cfg.class_weighting is True
    assert cfg.base_model == "distilbert-base-multilingual-cased"
    assert cfg.training_device == "auto"


def test_training_device_defaults_to_auto_without_env_or_yaml_field(tmp_path, monkeypatch):
    monkeypatch.delenv("TRAINING_DEVICE", raising=False)
    config_path = tmp_path / "model_config.yaml"
    config_path.write_text(
        """
base_model: "prajjwal1/bert-tiny"
seed: 42
max_length: 64
batch_size: 8
learning_rate: 0.00005
epochs: 8
val_fraction: 0.15
heads:
  - name: intent
    label_field: intent
    required: true
dataset_dir: "training/datasets/processed"
model_version: "v0"
output_dir: "training/models/wow-brain/v0"
""",
        encoding="utf-8",
    )
    assert TrainingConfig.load(config_path).training_device == "auto"


def test_read_dataset_version_prefers_versioned_dataset_dir_name(tmp_path):
    dataset_dir = tmp_path / "v3.2.0-train-ready"
    dataset_dir.mkdir()
    (dataset_dir / "MANIFEST.json").write_text("{}", encoding="utf-8")
    assert _read_dataset_version(dataset_dir) == "v3.2.0-train-ready"


def test_read_dataset_version_falls_back_when_no_manifest(tmp_path, monkeypatch):
    import training.training.train as train_module

    monkeypatch.setattr(train_module, "REPO_ROOT", tmp_path)  # isolate from the real repo's DATASET_METADATA.json
    dataset_dir = tmp_path / "processed"
    dataset_dir.mkdir()
    assert _read_dataset_version(dataset_dir) == "unknown"


def test_training_device_env_var_overrides_yaml_field(tmp_path, monkeypatch):
    config_path = tmp_path / "model_config_v1_1.yaml"
    config_path.write_text(
        """
base_model: "distilbert-base-multilingual-cased"
seed: 42
max_length: 64
batch_size: 16
learning_rate: 0.00003
epochs: 20
val_fraction: 0.15
training_device: "cpu"
heads:
  - name: intent
    label_field: intent
    required: true
dataset_dir: "training/datasets/processed"
model_version: "v1.1"
output_dir: "training/models/wow-brain/v1.1"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("TRAINING_DEVICE", "cuda")
    assert TrainingConfig.load(config_path).training_device == "cuda"
