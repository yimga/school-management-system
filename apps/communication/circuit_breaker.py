"""
Circuit breaker for notification providers (required, non-optional).
After N failures within a window, the circuit opens and we skip the provider (fallback or fail fast).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# (school_id or "global", channel) -> (failure_count, first_failure_time)
_breakers: dict[tuple[str, str], tuple[int, float]] = {}
_lock = threading.Lock()
FAILURE_THRESHOLD = 3
OPEN_SECONDS = 60


def _key(school_id: Any, channel: str) -> tuple[str, str]:
    return (str(school_id) if school_id else "global", channel)


def record_failure(school_id: Any, channel: str) -> None:
    """Record a provider failure for (school_id, channel)."""
    with _lock:
        k = _key(school_id, channel)
        count, first = _breakers.get(k, (0, 0.0))
        now = time.monotonic()
        if first == 0 or (now - first) > OPEN_SECONDS:
            _breakers[k] = (1, now)
        else:
            _breakers[k] = (count + 1, first)
        if _breakers[k][0] >= FAILURE_THRESHOLD:
            logger.warning("Circuit breaker open for %s channel=%s (failures=%s)", school_id, channel, _breakers[k][0])


def record_success(school_id: Any, channel: str) -> None:
    """On success, reset the failure count for (school_id, channel)."""
    with _lock:
        k = _key(school_id, channel)
        if k in _breakers:
            del _breakers[k]


def is_open(school_id: Any, channel: str) -> bool:
    """Return True if the circuit is open (skip provider, use fallback)."""
    with _lock:
        k = _key(school_id, channel)
        if k not in _breakers:
            return False
        count, first = _breakers[k]
        if count < FAILURE_THRESHOLD:
            return False
        if (time.monotonic() - first) >= OPEN_SECONDS:
            _breakers[k] = (0, 0.0)
            return False
        return True
