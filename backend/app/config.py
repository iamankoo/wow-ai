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


@lru_cache
def get_settings() -> Settings:
    return Settings()
