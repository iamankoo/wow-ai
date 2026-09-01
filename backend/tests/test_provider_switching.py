"""Tests for provider selection (app/api/deps.py:build_llm_provider) and, for
the local_wow branch, a real end-to-end inference call against a trained
model - not a mock. Uses the v0 model artifacts (training/models/wow-brain/v0)
since those are always present in this repo; v1 (once trained) is exercised
the same way in training/evaluation/evaluate.py.
"""

from pathlib import Path

import pytest

from app.api import deps
from app.config import Settings
from app.interfaces.llm import LLMMessage
from app.providers.llm.local_wow import LocalWOWModelProvider
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider

_REPO_ROOT = Path(__file__).resolve().parents[2]
_V0_MODEL_DIR = _REPO_ROOT / "training" / "models" / "wow-brain" / "v0"


def test_build_llm_provider_defaults_to_rule_based(monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(model_provider="rule_based"))
    provider = deps.build_llm_provider()
    assert isinstance(provider, RuleBasedLanguageModelProvider)


def test_build_llm_provider_selects_local_wow(monkeypatch):
    monkeypatch.setattr(
        deps, "get_settings",
        lambda: Settings(model_provider="local_wow", wow_model_dir="training/models/wow-brain/v0"),
    )
    provider = deps.build_llm_provider()
    assert isinstance(provider, LocalWOWModelProvider)


def test_build_llm_provider_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(model_provider="openai"))
    with pytest.raises(ValueError, match="Unknown MODEL_PROVIDER"):
        deps.build_llm_provider()


@pytest.mark.skipif(not _V0_MODEL_DIR.exists(), reason="v0 model artifacts not present")
async def test_local_wow_provider_produces_structured_output_end_to_end():
    provider = LocalWOWModelProvider(_V0_MODEL_DIR)
    response = await provider.generate([LLMMessage(role="user", content="I'm busy right now, take messages instead.")])

    assert response.metadata["provider"] == "local_wow_v0"
    assert response.metadata["model_version"] == "v0"
    # v0's predictions may well be wrong (see docs/TRAINING.md), but the
    # provider contract - producing a well-formed, non-crashing structured
    # response - must always hold regardless of model quality.
    assert isinstance(response.intent, str)
    assert "context_mode" in response.slots
    assert "action" in response.slots
    assert set(response.metadata["confidence"]) == {"intent", "context_mode", "action"}
