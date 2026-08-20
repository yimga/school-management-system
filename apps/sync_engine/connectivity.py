"""Cheap "is the operator reachable?" probe, and the offline->online wake it raises.

WHY A SEPARATE PROBE
--------------------
Backing a failing sync cycle off exponentially is correct — an offline box should not
burn CPU and battery building bundles for a socket that cannot open. But backoff alone
makes the thing the operator actually cares about WORSE: after a long outage the box is
sitting on a five-minute sleep at exactly the moment the network returns.

The fix is to stop conflating two questions that have wildly different costs:

  * *"Is the network back?"*  — a DNS lookup plus a TCP connect. Milliseconds, no auth,
    no bundle build, no database read, no load on the operator. Safe to ask often.
  * *"Run a full cycle."*     — scan the corpus, build and sign bundles, POST pages, pull,
    verify, apply, write cursors. Expensive. Only worth attempting when it can succeed.

So the probe runs on a short FIXED interval regardless of how far the cycle has backed
off, and the moment it flips offline->online it raises a cadence wake. The next tick then
runs a full cycle immediately, cancelling whatever backoff remained.

WHY TCP AND NOT HTTP
--------------------
A TCP connect to the operator's host:port needs no endpoint contract, no credential, and
no route that could be changed out from under us, and it costs the operator nothing. It
is a NETWORK liveness check, deliberately not a service health check — proving the app is
healthy is the full cycle's job, and the cycle reports that honestly.

The known false positive is a captive portal, which will accept a TCP connection and then
refuse the HTTP exchange. That costs one wasted cycle, which fails, which returns the box
to backoff. Cheap and self-correcting — and far better than the false NEGATIVE (missing a
restored network) that the alternative risks.
"""

from __future__ import annotations

import logging
import os
import socket
import time
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# How long a probe result is trusted. Short: this is the resolution at which the box
# notices the network came back.
_DEFAULT_PROBE_TTL_SECONDS = 10
# A connect that has not completed in this long is "not reachable" for our purposes; the
# full cycle uses its own, longer transport timeouts.
_DEFAULT_PROBE_TIMEOUT_SECONDS = 3

# "When did this box last see the cloud?" outlives the probe TTL by design — it is
# the first question asked after an outage.
_LAST_ONLINE_TTL_SECONDS = 30 * 24 * 3600  # magic-number-allow: last-online retention (30d, seconds)

_RESULT_KEY = "rmc:edge_sync:connectivity"
_LAST_ONLINE_KEY = "rmc:edge_sync:connectivity_last_online"

# The last online/offline value we OBSERVED, kept far longer than the probe result.
#
# Transition detection used to read the previous value out of the short-TTL result cache,
# which quietly broke in the one situation this module exists for: during an outage the
# cycle backs off, ticks spread out past the probe TTL, the cached result expires, and the
# next probe therefore sees "no previous state" — so the offline->online flip was NOT a
# transition, no wake was raised, and the box sat out the remaining backoff exactly as it
# did before any of this was built. Separating "what did we last see" (durable) from
# "is the current reading still fresh" (10s) fixes it.
_LAST_STATE_TTL_SECONDS = 7 * 24 * 3600  # magic-number-allow: last-observed-link retention (7d, seconds)
_LAST_STATE_KEY = "rmc:edge_sync:connectivity_last_state"

# magic-number-allow: IANA default ports for the operator base URL scheme
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def probe_ttl_seconds() -> int:
    return max(1, _env_int("RMC_EDGE_PROBE_TTL_SECONDS", _DEFAULT_PROBE_TTL_SECONDS))


def probe_timeout_seconds() -> float:
    return max(1, _env_int("RMC_EDGE_PROBE_TIMEOUT_SECONDS", _DEFAULT_PROBE_TIMEOUT_SECONDS))


def operator_target() -> tuple[str, int]:
    """``(host, port)`` of the cloud operator this box syncs against, or ``("", 0)``.

    Mirrors ``sync_runner._operator_base`` so the probe can never end up checking a
    different endpoint than the one the cycle actually uses.
    """
    from apps.sync_engine.edge_binding import operator_base

    base = operator_base()
    if not base:
        base = (getattr(settings, "RMC_HUB_BASE_URL", "") or "").strip()
    base = base.strip().rstrip("/")
    if not base:
        return "", 0
    if "://" not in base:
        base = "https://" + base
    try:
        parsed = urlparse(base)
    except (TypeError, ValueError):
        return "", 0
    host = (parsed.hostname or "").strip()
    if not host:
        return "", 0
    port = parsed.port or _DEFAULT_PORTS.get((parsed.scheme or "https").lower(), 443)
    return host, int(port)


def _tcp_reachable(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError):  # DNS failure, refused, unreachable, timeout
        return False


def _cache_get(key, default=None):
    try:
        value = cache.get(key)
    except Exception:  # noqa: BLE001
        logger.debug("connectivity cache read failed for %s", key, exc_info=True)
        return default
    return default if value is None else value


def _cache_set(key, value, ttl) -> None:
    try:
        cache.set(key, value, ttl)
    except Exception:  # noqa: BLE001
        logger.debug("connectivity cache write failed for %s", key, exc_info=True)


def last_known() -> dict:
    """The cached probe result without performing I/O. ``{}`` when nothing is cached."""
    value = _cache_get(_RESULT_KEY, None)
    return value if isinstance(value, dict) else {}


def check(*, force: bool = False) -> dict:
    """Probe reachability (respecting the cache TTL) and raise a wake on offline->online.

    Returns ``{"online", "host", "port", "checked_at", "cached", "transition"}``.
    ``transition`` is ``"restored"``, ``"lost"``, or ``""`` — it is set only on the probe
    that observed the change, so a caller can react exactly once.

    Never raises. With no operator base configured this reports ``online=False`` with
    ``host=""``; the cycle would fail on the same missing setting and says so plainly.
    """
    host, port = operator_target()
    if not host:
        return {
            "online": False,
            "host": "",
            "port": 0,
            "checked_at": time.time(),
            "cached": False,
            "transition": "",
            "reason": "no operator base configured (RMC_EDGE_OPERATOR_BASE)",
        }

    if not force:
        cached = last_known()
        if cached and cached.get("host") == host and cached.get("port") == port:
            return {**cached, "cached": True, "transition": ""}

    # Durable, NOT the short-TTL result cache — see _LAST_STATE_KEY.
    remembered = _cache_get(_LAST_STATE_KEY, None)
    was_online = None if remembered is None else bool(remembered)

    online = _tcp_reachable(host, port, probe_timeout_seconds())
    now = time.time()
    result = {
        "online": online,
        "host": host,
        "port": port,
        "checked_at": now,
        "cached": False,
        "reason": "",
    }
    _cache_set(_RESULT_KEY, result, probe_ttl_seconds())
    _cache_set(_LAST_STATE_KEY, bool(online), _LAST_STATE_TTL_SECONDS)
    if online:
        # Kept far longer than the probe TTL: "when did this box last see the cloud?" is
        # the question an operator asks after an outage, and it must outlive the probe.
        _cache_set(_LAST_ONLINE_KEY, now, _LAST_ONLINE_TTL_SECONDS)

    transition = ""
    if was_online is not None and was_online != online:
        transition = "restored" if online else "lost"
    result["transition"] = transition

    if transition == "restored":
        # THE point of this module: cancel any remaining backoff immediately.
        from apps.sync_engine import cadence

        cadence.request_wake("connectivity restored")
        logger.info("edge sync: operator %s:%s reachable again — sync wake raised", host, port)
    elif transition == "lost":
        logger.info("edge sync: operator %s:%s became unreachable", host, port)

    return result


def last_online_at() -> float | None:
    """Unix timestamp of the last successful probe, or ``None``."""
    value = _cache_get(_LAST_ONLINE_KEY, None)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def snapshot() -> dict:
    """Non-blocking view of connectivity for status surfaces (never probes)."""
    cached = last_known()
    host, port = operator_target()
    return {
        "online": bool(cached.get("online")) if cached else None,
        "host": host,
        "port": port,
        "checked_at": cached.get("checked_at") if cached else None,
        "last_online_at": last_online_at(),
        "configured": bool(host),
    }


def reset() -> None:
    """Forget everything this module remembers about the link.

    All three keys, not just the short-lived probe result: ``_LAST_STATE_KEY`` is
    DURABLE (7 days) precisely so a long outage still produces a restore transition, which
    means it is also the one most able to leak across a test boundary and make an
    unrelated test see a phantom "connectivity restored" wake.

    Used by the test isolation fixture in ``apps/sync_engine/tests/conftest.py`` and by
    operators re-probing a box after changing its operator target.
    """
    from django.core.cache import cache

    for key in (_RESULT_KEY, _LAST_ONLINE_KEY, _LAST_STATE_KEY):
        try:
            cache.delete(key)
        except Exception:  # noqa: BLE001 - a reset must never raise
            logger.debug("connectivity reset could not clear %s", key, exc_info=True)


__all__ = [
    "check",
    "last_known",
    "last_online_at",
    "operator_target",
    "probe_timeout_seconds",
    "probe_ttl_seconds",
    "reset",
    "snapshot",
]
