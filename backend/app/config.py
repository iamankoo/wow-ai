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

    # SpeechToTextProvider/TextToSpeechProvider selection for the real
    # voice-command endpoint (Phase 6 Part E/J) - "simulated" (default, no
    # heavy ML deps required, matches model_provider's zero-dependency
    # default) or the real self-hosted engine. Real voice actually
    # transcribing/synthesizing requires STT_PROVIDER=local_whisper and
    # TTS_PROVIDER=local_piper. Never a hosted third-party speech API.
    stt_provider: str = "simulated"
    tts_provider: str = "simulated"
    whisper_model_size: str = "base"

    # Real telephony (Plivo) - app/api/routes/telephony_plivo.py,
    # app/providers/telephony/plivo.py. This project has no real account
    # system yet (Phase 1), and a Plivo number maps to exactly one WOW
    # user for now - matches the same fixed demo-user convention the
    # Android app and mobile UI already hardcode (kDemoUserId in
    # mobile/lib/core/constants.dart, DEMO_USER_ID in
    # WowCallScreeningService.kt/WowAutoAnswer.kt) - defined here once so
    # the backend side of that same convention isn't duplicated per file.
    demo_user_id: str = "00000000-0000-0000-0000-000000000001"
    # The public https/wss base URL this backend is reachable at (e.g. a
    # Cloudflare Tunnel/ngrok URL during local testing, or the real
    # production domain later) - used to build the `<Stream>` wss:// URL
    # in the PLIVOXML answer response. Explicit config rather than
    # inferring from the incoming request's Host/scheme headers: those are
    # only trustworthy if uvicorn is run with --proxy-headers and a
    # correctly configured --forwarded-allow-ips behind the tunnel, which
    # this project does not assume is always set up correctly - an
    # explicit, operator-set value is safer than silently guessing wrong
    # and emitting ws:// instead of wss:// (which Plivo would reject).
    # None (the default) means "derive from the request" - documented in
    # app/api/routes/telephony_plivo.py as the less-safe fallback.
    public_base_url: str | None = None
    # Plivo Auth Token - ONLY ever sourced from the environment (this
    # field, like every other Settings field, is populated from env vars/
    # .env by pydantic-settings; never hardcoded in this repository, never
    # committed). Required to verify the real X-Plivo-Signature-V3 header
    # on the Answer URL webhook (app/api/routes/telephony_plivo.py,
    # app/providers/telephony/plivo_signature.py) - the exact mechanism
    # Plivo's own official docs describe (HMAC-SHA256 over the request,
    # keyed by this token). None (the default) means signature validation
    # is skipped with a loud warning logged on every request - safe for
    # initial local testing before a real Plivo account/token exists, but
    # must be set for any real/production use.
    plivo_auth_token: str | None = None
    # (Phase 1 update: unset no longer means "skip" - the Answer webhook now
    # fails closed unless plivo_allow_unsigned_webhooks is explicitly set
    # AND public_base_url is unset. See telephony_plivo._verify_plivo_signature.)

    # Plivo Auth ID - environment-only, like plivo_auth_token. Not used for
    # webhook verification (only the Auth Token is); reserved for Plivo REST
    # calls (e.g. the call-hangup follow-up noted in docs/PLIVO_TESTING.md).
    plivo_auth_id: str | None = None
    # Dev-only escape hatch: accept Answer-URL webhooks WITHOUT an
    # X-Plivo-Signature-V3 check when plivo_auth_token is unset. Ignored
    # (the webhook fails closed) whenever public_base_url is set, since a
    # public tunnel means anyone on the internet can reach the endpoint.
    plivo_allow_unsigned_webhooks: bool = False
    # Short-lived, single-use correlation token minted by the (signed)
    # Answer webhook and required on the Stream WebSocket URL - see
    # app/providers/telephony/stream_tokens.py.
    plivo_stream_token_ttl_seconds: int = 120
    # Resource caps for the media bridge: simultaneous live streams, and a
    # hard ceiling on one call's duration.
    plivo_max_concurrent_streams: int = 2
    plivo_max_call_seconds: int = 1800

    # Shared secret required (header X-WOW-API-Key) on every REST route
    # except /health and the Plivo routes (which have their own auth).
    # ENVIRONMENT-ONLY. None = not enforced (backward compatibility with
    # already-installed app builds) - but the backend refuses to start with
    # public_base_url set and this unset (app/security.py). This is a
    # single-tenant boundary, not per-user auth - see docs/SECURITY.md.
    api_access_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
