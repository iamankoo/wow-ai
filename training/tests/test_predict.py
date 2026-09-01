"""Tests for training/inference/predict.py against the real v0 model
artifacts (always present in this repo) - a genuine inference call, not a
mock, but fast since v0 is tiny.
"""

import pytest

from training.inference.predict import predict
from training.training.config import REPO_ROOT

_V0_MODEL_DIR = REPO_ROOT / "training" / "models" / "wow-brain" / "v0"


@pytest.mark.asyncio
@pytest.mark.skipif(not _V0_MODEL_DIR.exists(), reason="v0 model artifacts not present")
async def test_predict_returns_structured_output_for_v0():
    result = await predict(_V0_MODEL_DIR, "I'm busy right now, take messages instead.")
    assert result["text"] == "I'm busy right now, take messages instead."
    assert result["model_version"] == "v0"
    assert isinstance(result["intent"], str)
    assert "context_mode" in result
    assert "action" in result
    assert set(result["confidence"]) == {"intent", "context_mode", "action"}
