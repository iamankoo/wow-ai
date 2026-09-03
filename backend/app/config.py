from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central runtime configuration, sourced from environment variables / .env.

    Nothing here should point at a specific hosted AI vendor - provider choice
    is made by wiring a concrete implementation of the interfaces in
    app/interfaces, not by config flags that assume e.g. OpenAI.
    """

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", protected_namespaces=("settings_",)
    )

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = "postgresql+asyncpg://wow:wow@localhost:5432/wow_ai"
    redis_url: str = "redis://localhost:6379/0"

    memory_embedding_dim: int = 384

    secret_key: str = "dev-secret-change-me"

    # LanguageModelProvider selection - "rule_based" (default, no ML deps
    # required) or "local_wow" (our own trained model, see training/).
    # Never a hosted third-party AI API.
    model_provider: str = "rule_based"
    wow_model_dir: str = "training/models/wow-brain/v0"
    # Inference device for LocalWOWModelProvider - "cpu" (default), "cuda",
    # "mps", or "auto". Independent of whatever device trained the model:
    # see docs/TRAINING.md "Training vs inference device".
    inference_device: str = "cpu"

    # Confidence thresholds below which a prediction is flagged for the
    # active-learning review queue instead of being trusted outright - see
    # docs/SELF_LEARNING.md "Active learning".
    intent_confidence_threshold: float = 0.6
    context_confidence_threshold: float = 0.6
    action_confidence_threshold: float = 0.6

    # AgentRuntime selection - "wow_brain" (default, v0's straight-line
    # context -> generate -> persist flow) or "wow_agent" (opt-in, the
    # fuller state/memory/policy/tool orchestrator - see app/agent/).
    agent_runtime: str = "wow_brain"
    # Minimum overall model confidence required before a sensitive action
    # (see app.agent.policy.SENSITIVE_ACTIONS) is authorized outright,
    # rather than routed to CLARIFY. Only used by AGENT_RUNTIME=wow_agent.
    policy_min_sensitive_confidence: float = 0.75

    # How long a COMPLETED call's history (Call/Conversation/
    # TranscriptSegment/Summary/AgentState) stays in the database before
    # scheduled cleanup removes it (app.learning.call_retention). Default
    # matches the ~15 day retention originally designed for call data.
    call_retention_days: int = 15

    # Phase 6 Part C - mobile/email verification. No real SMS/email vendor
    # is wired in this repository yet (see
    # app/providers/otp/logging_provider.py); while that's true, the
    # generated code is echoed back in the request-code API response so the
    # real verify flow stays testable end to end. Set False the moment a
    # real OtpDeliveryProvider (Twilio/SendGrid/etc.) is wired in.
    otp_expose_dev_code: bool = True
    otp_code_ttl_seconds: int = 600
    otp_max_attempts: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
