"""Always-on, dependency-free login lockout (brute-force / credential-stuffing).

A lightweight failed-attempt lockout layered on top of the per-IP
``@ratelimit`` already guarding ``login_view``. Unlike ``django-defender`` this
needs no extra package and no Redis: it uses the configured Django cache
backend, and **fails open** if the cache is unavailable so a cache outage can
never lock legitimate users out of sign-in.

Keyed by ``(client-ip, username)`` so a single targeted account on a shared
NAT is throttled without nuking every user behind that IP. Distributed
attackers rotating IPs are still slowed by the per-username dimension.

Settings (defaults are sane; override via env in ``config/settings.py``):

- ``LOGIN_LOCKOUT_ENABLED``          — bool, default True
- ``LOGIN_LOCKOUT_THRESHOLD``        — int, failed attempts before lockout (default 5)
- ``LOGIN_LOCKOUT_COOLOFF_SECONDS``  — int, lockout window (default 900 = 15 min)
"""

from __future__ import annotations

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "login-guard:v1"


def _enabled() -> bool:
    return bool(getattr(settings, "LOGIN_LOCKOUT_ENABLED", True))


def _threshold() -> int:
    return int(getattr(settings, "LOGIN_LOCKOUT_THRESHOLD", 5))


def _cooloff_seconds() -> int:
    return int(getattr(settings, "LOGIN_LOCKOUT_COOLOFF_SECONDS", 900))  # magic-number-allow: 15-min default cooloff


_backend_warned = False


def _warn_if_per_process_cache() -> None:
    """One-time warning when the cache is LocMemCache (per-gunicorn-worker).

    With a per-process cache the lockout counter is NOT shared across workers,
    so the effective threshold is multiplied by the worker count. A shared
    cache (set ``REDIS_URL``) makes the lockout globally correct.
    """
    global _backend_warned
    if _backend_warned:
        return
    _backend_warned = True
    backend = str(
        (getattr(settings, "CACHES", {}) or {}).get("default", {}).get("BACKEND", "")
    ).lower()
    if "locmem" in backend:
        logger.warning(
            "login_guard: cache backend is LocMemCache (per-process); lockout is "
            "only globally enforced with a shared cache — set REDIS_URL for "
            "multi-worker deployments."
        )


def client_ip(request) -> str:
    """Best-effort client IP. Leftmost X-Forwarded-For is proxy-trusted only."""
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return (request.META.get("REMOTE_ADDR") or "").strip()


def _key(request, username: str) -> str:
    ip = client_ip(request) or "noip"
    uname = (username or "").strip().lower() or "nouser"
    digest = hashlib.sha256(f"{ip}|{uname}".encode("utf-8")).hexdigest()[:24]
    return f"{_CACHE_PREFIX}:{digest}"


def lockout_state(request, username: str) -> tuple[bool, int]:
    """Return ``(is_locked, retry_after_seconds)`` for this (ip, username).

    Fails open (``(False, 0)``) on any cache error.
    """
    if not _enabled():
        return (False, 0)
    try:
        count = int(cache.get(_key(request, username)) or 0)
    except Exception:  # noqa: BLE001 - cache outage must never block sign-in
        logger.warning("login_guard_cache_read_failed", exc_info=True)
        return (False, 0)
    if count >= _threshold():
        return (True, _cooloff_seconds())
    return (False, 0)


def attempt_count(request, username: str) -> int:
    """Current failed-attempt count for this (ip, username). 0 on error/disabled.

    Lets the login view escalate to a bot challenge even from a fresh, cookie-less
    session — the counter is keyed by IP+username, not the session.
    """
    if not _enabled():
        return 0
    try:
        return int(cache.get(_key(request, username)) or 0)
    except Exception:  # noqa: BLE001 - never block sign-in on a cache read error
        return 0


def record_failed_attempt(request, username: str) -> int:
    """Increment the failed-attempt counter; return the new count (0 on error)."""
    if not _enabled():
        return 0
    _warn_if_per_process_cache()
    key = _key(request, username)
    try:
        # add() seeds the key+TTL only if absent, so the window is anchored to
        # the FIRST failure and does not slide forward on every miss.
        cache.add(key, 0, _cooloff_seconds())
        try:
            return int(cache.incr(key))
        except ValueError:
            # Key expired between add() and incr(); reseed at 1.
            cache.set(key, 1, _cooloff_seconds())
            return 1
    except Exception:  # noqa: BLE001 - never break the login path on cache error
        logger.warning("login_guard_cache_write_failed", exc_info=True)
        return 0


def clear_attempts(request, username: str) -> None:
    """Reset the counter after a successful sign-in. Best-effort."""
    if not _enabled():
        return
    try:
        cache.delete(_key(request, username))
    except Exception:  # noqa: BLE001 - best-effort cleanup
        logger.warning("login_guard_cache_clear_failed", exc_info=True)


__all__ = [
    "client_ip",
    "lockout_state",
    "record_failed_attempt",
    "clear_attempts",
]
