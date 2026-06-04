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


# ── Shared (cross-worker) breaker state via cache (audit P2) ────────────────
# The in-memory dict below is a per-process fallback; on a shared cache
# backend (Redis in prod) all gunicorn workers + dynos see one breaker, so the
# 3-failures threshold is real instead of 3×N, and state survives restarts.


def _cache_key(school_id: Any, channel: str) -> str:
    sid, ch = _key(school_id, channel)
    return f"cb:{sid}:{ch}"


def _cache_record_failure(school_id: Any, channel: str) -> bool:
    """Returns True if handled via cache, False to fall back to in-memory."""
    try:
        from django.core.cache import cache
    except Exception:  # noqa: BLE001
        return False
    key = _cache_key(school_id, channel)
    try:
        if cache.add(key, 1, OPEN_SECONDS):
            count = 1
        else:
            count = cache.incr(key)
        if count >= FAILURE_THRESHOLD:
            logger.warning(
                "Circuit breaker open channel=%s (failures=%s)", channel, count,
            )
        return True
    except Exception:  # noqa: BLE001
        return False


def record_failure(school_id: Any, channel: str) -> None:
    """Record a provider failure for (school_id, channel)."""
    if _cache_record_failure(school_id, channel):
        return
    with _lock:
        k = _key(school_id, channel)
        count, first = _breakers.get(k, (0, 0.0))
        now = time.monotonic()
        if first == 0 or (now - first) > OPEN_SECONDS:
            _breakers[k] = (1, now)
        else:
            _breakers[k] = (count + 1, first)
        if _breakers[k][0] >= FAILURE_THRESHOLD:
            logger.warning(
                "Circuit breaker open for %s channel=%s (failures=%s)",
                school_id,
                channel,
                _breakers[k][0],
            )


def record_success(school_id: Any, channel: str) -> None:
    """On success, reset the failure count for (school_id, channel)."""
    try:
        from django.core.cache import cache

        cache.delete(_cache_key(school_id, channel))
    except Exception:  # noqa: BLE001
        pass
    with _lock:
        k = _key(school_id, channel)
        if k in _breakers:
            del _breakers[k]


def is_open(school_id: Any, channel: str) -> bool:
    """Return True if the circuit is open (skip provider, use fallback)."""
    try:
        from django.core.cache import cache

        val = cache.get(_cache_key(school_id, channel))
        if val is not None:
            return int(val) >= FAILURE_THRESHOLD
    except Exception:  # noqa: BLE001
        pass
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
