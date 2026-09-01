from collections.abc import AsyncGenerator
from pathlib import Path

from app.brain.context_engine import DefaultContextEngine
from app.brain.state_repository import SqlStateRepository
from app.brain.wow_brain import WowBrain
from app.config import get_settings
from app.db.session import AsyncSessionLocal, get_db
from app.interfaces.agent_runtime import AgentRuntime
from app.interfaces.llm import LanguageModelProvider
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider
from app.providers.memory.pgvector_store import PgVectorMemoryStore

_REPO_ROOT = Path(__file__).resolve().parents[3]


def build_llm_provider() -> LanguageModelProvider:
    """Selects the active LanguageModelProvider from settings.model_provider.

    "rule_based" (default) needs no ML dependencies. "local_wow" loads WOW's
    own trained model (see training/) and raises a clear error immediately
    if it isn't available - it never silently substitutes a different
    provider. Neither option ever calls a hosted third-party AI API.
    """
    settings = get_settings()

    if settings.model_provider == "rule_based":
        return RuleBasedLanguageModelProvider()

    if settings.model_provider == "local_wow":
        from app.providers.llm.local_wow import LocalWOWModelProvider

        model_dir = _REPO_ROOT / settings.wow_model_dir
        return LocalWOWModelProvider(model_dir, inference_device=settings.inference_device)

    raise ValueError(
        f"Unknown MODEL_PROVIDER '{settings.model_provider}'. "
        "Expected 'rule_based' or 'local_wow'."
    )


# Stateless, safe to share across requests.
_llm_provider = build_llm_provider()


async def get_brain() -> AsyncGenerator[AgentRuntime, None]:
    """FastAPI dependency: yields a request-scoped WowBrain wired to its own
    DB session, committing on success."""
    async with AsyncSessionLocal() as session:
        memory_store = PgVectorMemoryStore(session)
        context_engine = DefaultContextEngine(session, memory_store)
        state_repo = SqlStateRepository(session)
        yield WowBrain(_llm_provider, context_engine, state_repo)
        await session.commit()


__all__ = ["get_db", "get_brain", "build_llm_provider"]
