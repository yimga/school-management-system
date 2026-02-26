"""Small cache-backed throttling helpers for unauthenticated API surfaces."""

from __future__ import annotations

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


def client_ip(request) -> str:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.META.get("REMOTE_ADDR") or "unknown").strip()


def throttle_ip_request(
    request,
    *,
    scope: str,
    max_count: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """
    Fixed-window per-IP throttling.

    Returns:
      (allowed, retry_after_seconds)
    """
    ip = client_ip(request)
    key = f"rate_limit:{scope}:{ip}"
    try:
        if cache.add(key, 1, timeout=window_seconds):
            return True, 0
        try:
            count = int(cache.incr(key))
        except Exception:
            count = int(cache.get(key, 0) or 0) + 1
            cache.set(key, count, timeout=window_seconds)
        if count > int(max_count):
            return False, int(window_seconds)
        return True, 0
    except Exception:
        # Never block critical auth/discovery flows if cache backend is unavailable.
        logger.debug("Rate-limit cache unavailable for scope=%s ip=%s", scope, ip)
        return True, 0
