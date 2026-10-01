"""Short-lived, single-use correlation tokens for the Plivo Stream
WebSocket (WS /telephony/plivo/stream).

Why this exists: Plivo documents X-Plivo-Signature-V3 for its HTTP
webhooks (the Answer URL) but documents no signature on the WebSocket
handshake (its `extraHeaders` Stream attribute is delivered inside the
`start` event, after the socket is already open). Without something else,
anyone who discovers the stream URL could open it and drive STT/TTS/Brain
and write fake call records.

Mechanism: the *signed* Answer webhook (so only genuine Plivo can reach
this point) mints an unpredictable token bound to that call's CallUUID and
puts it in the Stream URL it returns. The WebSocket must present it; it is
checked server-side before the socket is accepted, expires after a short
TTL, and is consumed on first use (replay -> rejected). The token is never
a long-lived credential, is stored only as a SHA-256 digest, and is never
logged.

Limits (stated, not hidden): state is in-process memory, so this assumes one
backend process/worker (true for the single-tenant uvicorn deployment this
project documents); a multi-worker deployment needs a shared store (Redis)
- Phase 3.
"""

import hashlib
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache


class StreamTokenError(Exception):
    """Raised on any token validation failure. `reason` is one of:
    missing, invalid, expired - safe to log (never contains the token)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class StreamTokenStoreFull(Exception):
    pass


@dataclass
class _Entry:
    call_uuid: str
    expires_at: float


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class StreamTokenStore:
    def __init__(
        self,
        ttl_seconds: float = 120.0,
        max_pending: int = 1000,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._ttl = ttl_seconds
        self._max_pending = max_pending
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def _purge_expired(self, now: float) -> None:
        for key in [k for k, e in self._entries.items() if e.expires_at <= now]:
            del self._entries[key]

    def issue(self, call_uuid: str) -> str:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            if len(self._entries) >= self._max_pending:
                raise StreamTokenStoreFull()
            token = secrets.token_urlsafe(32)
            self._entries[_digest(token)] = _Entry(call_uuid, now + self._ttl)
            return token

    def consume(self, token: str | None) -> str:
        """Validates and CONSUMES `token`; returns the CallUUID it was
        minted for. Raises StreamTokenError otherwise. A token is consumed
        even if a later check (the start event's call id) fails - it is
        never reusable."""
        if not token:
            raise StreamTokenError("missing")
        now = self._clock()
        with self._lock:
            entry = self._entries.pop(_digest(token), None)
        if entry is None:
            raise StreamTokenError("invalid")  # unknown, or already used (replay)
        if entry.expires_at <= now:
            raise StreamTokenError("expired")
        return entry.call_uuid

    def pending_count(self) -> int:
        with self._lock:
            self._purge_expired(self._clock())
            return len(self._entries)


@lru_cache
def get_stream_token_store() -> StreamTokenStore:
    from app.config import get_settings

    return StreamTokenStore(ttl_seconds=get_settings().plivo_stream_token_ttl_seconds)
