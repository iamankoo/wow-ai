import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os  # noqa: E402

# Tests must not depend on a developer's local, git-ignored backend/.env
# (which may hold real Plivo/API secrets and select the real STT/TTS/Brain
# providers). Environment variables outrank the .env file in Settings, so pin
# the test baseline here, BEFORE any app module reads settings. Individual
# tests override with monkeypatch.setenv (never delenv - that would fall back
# to the .env value).
for _k, _v in {
    "API_ACCESS_KEY": "",
    "PLIVO_AUTH_TOKEN": "",
    "PLIVO_AUTH_ID": "",
    "PUBLIC_BASE_URL": "",
    "MODEL_PROVIDER": "rule_based",
    "STT_PROVIDER": "simulated",
    "TTS_PROVIDER": "simulated",
    "AGENT_RUNTIME": "wow_brain",
    "WOW_MODEL_DIR": "training/models/wow-brain/v0",
}.items():
    os.environ[_k] = _v


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_stream_token_store():
    """The Plivo stream token store is a process-wide singleton - never let
    one test's pending/consumed tokens leak into another."""
    from app.providers.telephony.stream_tokens import get_stream_token_store

    get_stream_token_store.cache_clear()
    yield
    get_stream_token_store.cache_clear()


def authorized_stream_path(call_uuid: str = "test-call-uuid") -> str:
    """A Stream WebSocket path carrying a freshly minted, valid single-use
    token - what the signed Answer webhook would have put in the URL."""
    from app.providers.telephony.stream_tokens import get_stream_token_store

    return f"/telephony/plivo/stream?token={get_stream_token_store().issue(call_uuid)}"
