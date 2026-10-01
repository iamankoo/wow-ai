"""Minimum Phase 1 API security boundary (see docs/SECURITY.md).

Before this module every REST route was reachable by anyone who knew a
user UUID - including POST /users/{id}/activation (turn WOW on for
someone else) and every read of profile/call history. The Plivo test
exposes the backend through a public tunnel, so that is no longer
acceptable even "for development".

Scope, deliberately small: ONE shared secret (`API_ACCESS_KEY`, environment
only) checked in constant time against the `X-WOW-API-Key` header. This is a
single-tenant gate, not per-user authentication: whoever holds the key is the
owner. It stops the internet at the tunnel; it does not separate two users
from each other, which belongs to the real account system (Phase 3).
"""

import hmac
import logging

from fastapi import Header, HTTPException

from app.config import Settings, get_settings

logger = logging.getLogger("app.security")

API_KEY_HEADER = "X-WOW-API-Key"


async def require_api_key(x_wow_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().api_access_key
    if not expected:
        # Not enforced (legacy/dev). validate_security_config() makes sure
        # this can never be the case while a public tunnel URL is set.
        return
    if not x_wow_api_key or not hmac.compare_digest(x_wow_api_key, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")


def validate_security_config(settings: Settings) -> None:
    """Startup check - raises RuntimeError for configurations that would
    expose the backend publicly without authentication. Never logs values."""
    if settings.public_base_url:
        missing = []
        if not settings.api_access_key:
            missing.append("API_ACCESS_KEY")
        if not settings.plivo_auth_token:
            missing.append("PLIVO_AUTH_TOKEN")
        if missing:
            raise RuntimeError(
                "PUBLIC_BASE_URL is set (backend is publicly reachable) but "
                + " and ".join(missing)
                + (" is" if len(missing) == 1 else " are")
                + " not configured. Refusing to start: set them in the "
                "environment (never commit them)."
            )
    if settings.app_env == "production" and not settings.api_access_key:
        logger.warning(
            "API_ACCESS_KEY is not set in production - every REST route is "
            "unauthenticated. Set it together with a mobile build that sends "
            "X-WOW-API-Key (docs/SECURITY.md)."
        )
    if settings.secret_key == "dev-secret-change-me" and settings.app_env == "production":
        logger.warning("SECRET_KEY is the development default in production")
