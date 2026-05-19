"""Per-tenant leaky-bucket rate limiter for third-party social API calls."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _BucketState:
    tokens: float
    last_refill: float


_lock = threading.Lock()
_buckets: dict[str, _BucketState] = {}

# Default: 30 API calls per minute per tenant scope (platform vs school id).
DEFAULT_CAPACITY = 30.0
DEFAULT_REFILL_PER_SEC = 0.5


def _bucket_key(scope_key: str, provider: str) -> str:
    return f"{scope_key}:{provider}"


def try_consume(
    scope_key: str,
    provider: str,
    *,
    cost: float = 1.0,
    capacity: float = DEFAULT_CAPACITY,
    refill_per_sec: float = DEFAULT_REFILL_PER_SEC,
) -> bool:
    """Return True if the request may proceed; False if throttled."""
    key = _bucket_key(scope_key, provider)
    now = time.monotonic()
    with _lock:
        state = _buckets.get(key)
        if state is None:
            state = _BucketState(tokens=capacity, last_refill=now)
            _buckets[key] = state
        elapsed = max(0.0, now - state.last_refill)
        state.tokens = min(capacity, state.tokens + elapsed * refill_per_sec)
        state.last_refill = now
        if state.tokens < cost:
            return False
        state.tokens -= cost
        return True


def reset_scope(scope_key: str) -> None:
    """Test helper — clear buckets for a scope prefix."""
    with _lock:
        for key in list(_buckets):
            if key.startswith(scope_key):
                del _buckets[key]
