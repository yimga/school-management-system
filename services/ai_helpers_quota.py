"""Per-tenant AI inference quota helper.

12-pillar audit P8 follow-up. The platform routes AI calls through
`services.ai_helpers.invoke_with_request`. Without a per-tenant
budget at that boundary, a runaway prompt / loop on one tenant can
exhaust the gateway for everyone else.

This module provides a thin token-bucket gate sized in **requests per
day**, keyed per-tenant. Budget resolution:

  1. ``request.school.settings["ai_inference_per_day"]`` (tenant override)
  2. ``settings.TENANT_AI_INFERENCE_PER_DAY`` (platform default, 5000)

The check uses Django's cache (same primitive as the marketplace
rate-limit). Fails open on cache outage — denying a customer's AI
call because Redis blipped is worse than serving over-quota for an
hour.

To wire into `services/ai_helpers.py::invoke_with_request`, call
:func:`check_inference_quota(school)` at the start of the function and
return early when ``allowed=False``; the existing fall-back-to-rules
path (per the AI gateway boundary) handles the deny.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("services.ai_helpers_quota")

PLATFORM_DEFAULT_PER_DAY = 5000

# Cache window in seconds — one full day. A token-bucket with a 24-hour
# refill is the cleanest semantic; rolling-hour budgets create a sawtooth
# the operator doesn't want to reason about.
WINDOW_SECONDS = 24 * 60 * 60


def _resolve_budget(school) -> int:
    """Return the per-day inference budget for a school, or
    ``PLATFORM_DEFAULT_PER_DAY`` when nothing else is configured."""
    if school is None:
        return PLATFORM_DEFAULT_PER_DAY
    school_settings = getattr(school, "settings", None) or {}
    override = school_settings.get("ai_inference_per_day")
    if isinstance(override, bool):
        pass  # bools aren't valid budgets
    elif isinstance(override, int) and override >= 0:
        return override
    elif isinstance(override, str) and override.isdigit():
        return int(override)
    # Platform default.
    try:
        from django.conf import settings
        fallback = getattr(settings, "TENANT_AI_INFERENCE_PER_DAY", PLATFORM_DEFAULT_PER_DAY)
        if isinstance(fallback, int) and fallback >= 0:
            return fallback
        if isinstance(fallback, str) and fallback.isdigit():
            return int(fallback)
    except (ImportError, Exception):  # noqa: BLE001
        pass
    return PLATFORM_DEFAULT_PER_DAY


def _cache_key(school) -> str:
    school_id = getattr(school, "id", None) or getattr(school, "pk", None) or "anon"
    return f"ai_quota:tenant:{school_id}"


def check_inference_quota(school) -> tuple[bool, int]:
    """Return ``(allowed, remaining)``.

    ``allowed`` is True when the request is within budget OR when the
    cache is unavailable (fail-open). ``remaining`` is the post-decrement
    count (>= 0 when allowed; the previous balance when denied).
    """
    budget = _resolve_budget(school)
    if budget <= 0:
        # Operator explicitly disabled throttling for this tenant.
        return True, budget
    try:
        from django.core.cache import cache
        key = _cache_key(school)
        # Atomically establish the bucket window before incrementing.
        # ``cache.add`` is a no-op when the key already exists, so two
        # concurrent cold-start callers can't each reset the counter to 1
        # (the lost-update race the old get-or-set-then-incr had). The TTL
        # is anchored here on the very first request of the window and the
        # subsequent ``incr`` preserves it (24h refill semantics).
        cache.add(key, 0, timeout=WINDOW_SECONDS)
        try:
            count = cache.incr(key)
        except ValueError:
            # Key expired between add and incr (window rolled over under us)
            # — re-seed at 1 and re-anchor the window.
            cache.set(key, 1, timeout=WINDOW_SECONDS)
            count = 1
        if count > budget:
            return False, max(0, budget - count + 1)
        return True, max(0, budget - count)
    except Exception:  # noqa: BLE001 — cache outage must not block AI traffic
        logger.warning("AI quota cache failed; falling open for school=%s", school)
        return True, budget


def get_inference_balance(school) -> int:
    """Best-effort read of the current inference balance for a school
    without decrementing. Returns -1 when the cache is unavailable or
    the school has no recorded count yet."""
    try:
        from django.core.cache import cache
        used = cache.get(_cache_key(school), 0)
        budget = _resolve_budget(school)
        return max(0, int(budget) - int(used or 0))
    except Exception:  # noqa: BLE001
        return -1


__all__ = [
    "PLATFORM_DEFAULT_PER_DAY",
    "WINDOW_SECONDS",
    "check_inference_quota",
    "get_inference_balance",
]
