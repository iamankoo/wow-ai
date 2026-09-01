import os
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "model_config.yaml"


@dataclass
class HeadConfig:
    name: str
    label_field: str
    required: bool = False


@dataclass
class TrainingConfig:
    base_model: str
    seed: int
    max_length: int
    batch_size: int
    learning_rate: float
    epochs: int
    val_fraction: float
    heads: list[HeadConfig]
    dataset_dir: Path
    model_version: str
    output_dir: Path
    # early_stopping_patience=0 disables early stopping (always train the
    # configured number of epochs). class_weighting=False reproduces the
    # v0 training behavior exactly (plain unweighted cross-entropy).
    early_stopping_patience: int = 0
    class_weighting: bool = False
    # "auto" (CUDA -> MPS -> CPU), "cpu", "cuda", or "mps". See
    # training/training/device.py and docs/TRAINING.md "GPU training".
    training_device: str = "auto"

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> "TrainingConfig":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        heads = [HeadConfig(**h) for h in data["heads"]]
        return cls(
            base_model=data["base_model"],
            seed=data["seed"],
            max_length=data["max_length"],
            batch_size=data["batch_size"],
            learning_rate=data["learning_rate"],
            epochs=data["epochs"],
            val_fraction=data["val_fraction"],
            heads=heads,
            dataset_dir=REPO_ROOT / data["dataset_dir"],
            model_version=data["model_version"],
            output_dir=REPO_ROOT / data["output_dir"],
            early_stopping_patience=data.get("early_stopping_patience", 0),
            class_weighting=data.get("class_weighting", False),
            # TRAINING_DEVICE env var takes priority over the config file,
            # which takes priority over "auto" - so `$env:TRAINING_DEVICE="cuda"`
            # works without editing any YAML. See docs/TRAINING.md.
            training_device=os.environ.get("TRAINING_DEVICE") or data.get("training_device", "auto"),
        )
