import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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
