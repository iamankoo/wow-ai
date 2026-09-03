from collections.abc import AsyncGenerator
from pathlib import Path

from app.agent.call_recorder import CallRecorder
from app.agent.context_profile_repository import SqlContextProfileRepository
from app.agent.orchestrator import WowAgent, build_default_tool_registry
from app.agent.policy import PolicyEngine
from app.agent.summary_repository import SqlSummaryRepository
from app.agent.user_settings_repository import SqlUserSettingsRepository
from app.brain.context_engine import DefaultContextEngine
from app.brain.state_repository import SqlStateRepository
from app.brain.wow_brain import WowBrain
from app.config import get_settings
from app.db.session import AsyncSessionLocal, get_db
from app.interfaces.agent_runtime import AgentRuntime
from app.interfaces.llm import LanguageModelProvider
from app.learning.feedback_repository import SqlFeedbackRepository
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider
from app.providers.memory.pgvector_store import PgVectorMemoryStore
from app.providers.otp.logging_provider import LoggingOtpDeliveryProvider
from app.services.verification_service import VerificationService

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
    """FastAPI dependency: yields a request-scoped AgentRuntime wired to its
    own DB session, committing on success.

    Selects between `WowBrain` (default - v0's straight-line flow) and
    `WowAgent` (opt-in via `AGENT_RUNTIME=wow_agent` - the fuller
    state/memory/policy/tool orchestrator, see app/agent/orchestrator.py).
    Both implement the same AgentRuntime contract, so no other layer
    branches on which one is active.
    """
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        memory_store = PgVectorMemoryStore(session)
        context_engine = DefaultContextEngine(session, memory_store)
        state_repo = SqlStateRepository(session)

        if settings.agent_runtime == "wow_agent":
            summary_repo = SqlSummaryRepository(session)
            context_profile_repo = SqlContextProfileRepository(session)
            user_settings_repo = SqlUserSettingsRepository(session)
            tool_registry = build_default_tool_registry(
                memory_store, summary_repo, context_profile_repo, user_settings_repo
            )
            policy_engine = PolicyEngine(
                min_sensitive_confidence=settings.policy_min_sensitive_confidence
            )
            yield WowAgent(
                _llm_provider,
                context_engine,
                state_repo,
                tool_registry,
                policy_engine=policy_engine,
                feedback_repository=SqlFeedbackRepository(session),
            )
        elif settings.agent_runtime == "wow_brain":
            yield WowBrain(_llm_provider, context_engine, state_repo)
        else:
            raise ValueError(
                f"Unknown AGENT_RUNTIME '{settings.agent_runtime}'. "
                "Expected 'wow_brain' or 'wow_agent'."
            )
        await session.commit()


# Stateless, safe to share across requests - see app/interfaces/otp.py's
# docstring for why this is the only OtpDeliveryProvider wired in today.
_otp_delivery_provider = LoggingOtpDeliveryProvider()


async def get_verification_service() -> AsyncGenerator[VerificationService, None]:
    """FastAPI dependency: a request-scoped VerificationService wired to
    its own DB session, committing on success - same shape as get_brain."""
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        yield VerificationService(
            session,
            _otp_delivery_provider,
            code_ttl_seconds=settings.otp_code_ttl_seconds,
            max_attempts=settings.otp_max_attempts,
            expose_dev_code=settings.otp_expose_dev_code,
        )
        await session.commit()


async def get_call_recorder() -> AsyncGenerator[CallRecorder, None]:
    """FastAPI dependency: a request-scoped CallRecorder (Phase 6 Part M)
    wired to its own DB session, committing on success - same shape as
    get_brain/get_verification_service. Its own transaction, independent
    of get_brain's - call recording is a separate concern from the
    agent's own state writes, and doesn't need to share one."""
    async with AsyncSessionLocal() as session:
        yield CallRecorder(session, SqlSummaryRepository(session))
        await session.commit()


__all__ = [
    "get_db",
    "get_brain",
    "get_verification_service",
    "get_call_recorder",
    "build_llm_provider",
]
