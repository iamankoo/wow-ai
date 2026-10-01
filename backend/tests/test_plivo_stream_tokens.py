"""StreamTokenStore - short-lived, single-use, call-bound stream tokens."""

import pytest

from app.providers.telephony.stream_tokens import (
    StreamTokenError,
    StreamTokenStore,
    StreamTokenStoreFull,
)


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_issue_then_consume_returns_the_bound_call_uuid():
    store = StreamTokenStore()
    token = store.issue("call-1")
    assert store.consume(token) == "call-1"


def test_tokens_are_unpredictable_and_unique():
    store = StreamTokenStore()
    tokens = {store.issue("call-1") for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 40 for t in tokens)


def test_token_is_single_use():
    store = StreamTokenStore()
    token = store.issue("call-1")
    store.consume(token)
    with pytest.raises(StreamTokenError) as exc:
        store.consume(token)
    assert exc.value.reason == "invalid"


@pytest.mark.parametrize("bad", [None, ""])
def test_missing_token_is_rejected(bad):
    with pytest.raises(StreamTokenError) as exc:
        StreamTokenStore().consume(bad)
    assert exc.value.reason == "missing"


def test_unknown_token_is_rejected():
    with pytest.raises(StreamTokenError) as exc:
        StreamTokenStore().consume("nope")
    assert exc.value.reason == "invalid"


def test_expired_token_is_rejected_and_consumed():
    clock = _Clock()
    store = StreamTokenStore(ttl_seconds=60, clock=clock)
    token = store.issue("call-1")
    clock.now += 61
    with pytest.raises(StreamTokenError) as exc:
        store.consume(token)
    assert exc.value.reason == "expired"
    with pytest.raises(StreamTokenError):  # and is gone, not retryable
        store.consume(token)


def test_token_valid_right_up_to_the_ttl():
    clock = _Clock()
    store = StreamTokenStore(ttl_seconds=60, clock=clock)
    token = store.issue("call-1")
    clock.now += 59
    assert store.consume(token) == "call-1"


def test_expired_entries_are_purged_so_the_store_cannot_grow_forever():
    clock = _Clock()
    store = StreamTokenStore(ttl_seconds=10, max_pending=3, clock=clock)
    for _ in range(3):
        store.issue("c")
    with pytest.raises(StreamTokenStoreFull):
        store.issue("c")
    clock.now += 11
    store.issue("c")  # purge made room
    assert store.pending_count() == 1


def test_raw_token_is_never_stored():
    store = StreamTokenStore()
    token = store.issue("call-1")
    assert token not in store._entries  # only a digest is kept
