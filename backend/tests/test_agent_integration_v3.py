"""Full agent integration test using the actual recovered WOW Brain v3
model artifacts (training/models/wow-brain/v3) - not a fake, not the
rule-based provider. Proves the complete WowAgent stack (state -> context
-> LocalWOWModelProvider -> confidence assessment -> policy gate -> real
tool execution -> response) works end-to-end against real trained model
output, closing the loop on the held-out test evaluation
(training/evaluation/v3_test_report.json): that report proves the model
is accurate in isolation, this proves the *agent* built around it behaves
correctly when driven by real (not fake) predictions.

Skipped cleanly (not failed) if the v3 model directory or torch/
transformers are not available in this environment - training/models/ is
gitignored by design (see .gitignore), so a fresh checkout without the
recovered artifacts must not break the rest of the suite. This mirrors
the TEST_DATABASE_URL-gated pattern in test_integration_db.py: skip when
the required real infrastructure isn't present, never substitute a fake
and call it the same test.

MODEL_PROVIDER stays whatever app.config.Settings defaults to
("rule_based") regardless of whether this test runs - it constructs
LocalWOWModelProvider directly, independent of that setting, exactly as
this session's manual verification did in training/evaluation/evaluate.py
and the Kaggle recovery work (see docs/implementation-status.md "Model
artifact status").
"""

from pathlib import Path

import pytest

from app.agent.context_profile_repository import InMemoryContextProfileRepository
from app.agent.orchestrator import WowAgent, build_default_tool_registry
from app.agent.summary_repository import InMemorySummaryRepository
from app.agent.user_settings_repository import InMemoryUserSettingsRepository
from app.brain.state_repository import InMemoryStateRepository
from app.brain.taxonomy import is_valid_action
from tests.agent_fakes import FakeContextEngine, InMemoryMemoryStore

_REPO_ROOT = Path(__file__).resolve().parents[2]
_V3_MODEL_DIR = _REPO_ROOT / "training" / "models" / "wow-brain" / "v3"

pytestmark = pytest.mark.skipif(
    not (_V3_MODEL_DIR / "metadata.json").exists(),
    reason=(
        f"WOW Brain v3 artifacts not found at {_V3_MODEL_DIR} (gitignored) - "
        "recover or train them first (see docs/KAGGLE_TRAINING.md) to run this test"
    ),
)

pytest.importorskip(
    "transformers",
    reason="transformers/torch not installed - see backend/requirements-local-model.txt",
)


def _build_agent(context_profile_repo: InMemoryContextProfileRepository | None = None):
    from app.providers.llm.local_wow import LocalWOWModelProvider

    llm = LocalWOWModelProvider(_V3_MODEL_DIR, inference_device="cpu")
    memory_store = InMemoryMemoryStore()
    ctx_repo = context_profile_repo or InMemoryContextProfileRepository()
    tools = build_default_tool_registry(
        memory_store,
        InMemorySummaryRepository(),
        ctx_repo,
        InMemoryUserSettingsRepository(),
    )
    agent = WowAgent(llm, FakeContextEngine(), InMemoryStateRepository(), tools)
    return agent, ctx_repo, memory_store


async def test_real_v3_model_classifies_meeting_context_and_executes_set_context():
    agent, ctx_repo, _ = _build_agent()
    action = await agent.handle_input(
        user_id="u1", text="Please handle my calls, I am in a meeting", conversation_id="c1"
    )
    assert action.payload["candidate_action"] == "SET_CONTEXT"
    assert action.payload["policy_decision"] == "allow"
    assert action.payload["tool_results"] == [
        {"tool": "set_context", "success": True, "error": None}
    ]
    assert ctx_repo.active_name(user_id="u1") == "MEETING"


async def test_real_v3_model_classifies_hinglish_sleeping_context():
    agent, ctx_repo, _ = _build_agent()
    action = await agent.handle_input(
        user_id="u1", text="Main so raha hoon, please handle karo", conversation_id="c1"
    )
    assert action.payload["candidate_action"] == "SET_CONTEXT"
    assert action.payload["policy_decision"] == "allow"
    assert ctx_repo.active_name(user_id="u1") == "SLEEPING"


async def test_real_v3_model_no_action_prediction_executes_no_tool():
    agent, ctx_repo, _ = _build_agent()
    action = await agent.handle_input(
        user_id="u1", text="Can you tell him I called about the invoice?", conversation_id="c1"
    )
    assert action.payload["tool_results"] == []
    assert ctx_repo.active_name(user_id="u1") is None


async def test_real_v3_model_predictions_are_always_taxonomy_valid_or_none():
    """Regardless of what the model predicts for arbitrary/noisy input, the
    orchestrator's taxonomy validation must hold against real model
    output, not just fakes engineered to already be valid - and the turn
    must complete without raising."""
    agent, _, _ = _build_agent()
    action = await agent.handle_input(
        user_id="u1", text="asdlkjasldkj random gibberish 12345", conversation_id="c1"
    )
    candidate = action.payload["candidate_action"]
    assert candidate is None or is_valid_action(candidate)


async def test_real_v3_model_multi_turn_state_persists_across_calls():
    agent, _, _ = _build_agent()
    first = await agent.handle_input(user_id="u1", text="Hello?", conversation_id="c1")
    second = await agent.handle_input(
        user_id="u1", text="I'm in a meeting", conversation_id="c1"
    )
    assert first.payload["turn_count"] == 1
    assert second.payload["turn_count"] == 2
