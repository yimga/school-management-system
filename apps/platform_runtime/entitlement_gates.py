"""
Centralized plan / feature / role / policy gates with safe caching.

Prefer this module over ad-hoc ``is_feature_enabled`` or direct Entitlement ORM reads
in request paths. Cache is keyed per school + capability; invalidate after entitlement
or policy mutations.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "rmc:entitlement_gate:v1"
_CACHE_TTL_SECONDS = 300
_GATE_SOFT_FAILURES = (ImportError, AttributeError, TypeError, ValueError)


def _school_cache_key(school, capability: str) -> str:
    school_id = getattr(school, "pk", None) or "none"
    return f"{_CACHE_PREFIX}:{school_id}:{str(capability or '').strip().lower()}"


def invalidate_entitlement_cache(school=None) -> None:
    """Drop cached capability decisions for one tenant or all tenants."""
    if school is None:
        try:
            cache.delete_pattern(f"{_CACHE_PREFIX}:*")
        except AttributeError:
            cache.clear()
        return
    school_id = getattr(school, "pk", None)
    if school_id is None:
        return
    try:
        cache.delete_pattern(f"{_CACHE_PREFIX}:{school_id}:*")
    except AttributeError:
        # LocMemCache: no pattern delete — rely on TTL for single-tenant invalidation.
        pass


def can_capability(school, capability: str, *, use_cache: bool = True) -> bool:
    """Plan + entitlement feature gate (tenant-scoped)."""
    if school is None:
        return False
    normalized = str(capability or "").strip().lower()
    if not normalized:
        return False
    cache_key = _school_cache_key(school, normalized)
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return bool(cached)
    try:
        from apps.billing.entitlements import can as billing_can

        allowed = bool(billing_can(school, normalized))
    except _GATE_SOFT_FAILURES as exc:
        logger.debug("can_capability failed school_id=%s cap=%s: %s", getattr(school, "pk", None), normalized, exc)
        allowed = False
    if use_cache:
        cache.set(cache_key, allowed, _CACHE_TTL_SECONDS)
    return allowed


def can_role(user, *roles: str) -> bool:
    """Role membership gate using platform role registry / User.Role."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    wanted = {str(r or "").strip().upper() for r in roles if str(r or "").strip()}
    if not wanted:
        return False
    try:
        from apps.platform_runtime.role_registry import normalize_role

        user_role = normalize_role(getattr(user, "role", None))
        return user_role in wanted
    except _GATE_SOFT_FAILURES:
        return str(getattr(user, "role", "") or "").strip().upper() in wanted


def can_policy(
    subject: Any,
    action: str,
    resource: dict[str, Any] | None,
    *,
    school=None,
    context: dict[str, Any] | None = None,
) -> bool:
    """ABAC/PDP gate — never bypasses tenant school on resource decisions."""
    if school is None and isinstance(resource, dict):
        school = resource.get("school")
    try:
        from apps.policies.pdp import decide

        decision = decide(subject, action, resource or {}, school=school, context=context)
        return bool(decision.allowed)
    except _GATE_SOFT_FAILURES as exc:
        logger.debug("can_policy failed action=%s: %s", action, exc)
        return False


def gate_summary(school) -> dict[str, Any]:
    """Non-mutating snapshot for audits (no secrets)."""
    school_id = getattr(school, "pk", None)
    policy = {}
    if school is not None:
        try:
            from apps.policies.policy_registry import get_effective_policy

            policy = get_effective_policy(school) or {}
        except _GATE_SOFT_FAILURES:
            policy = {}
    entitlements = (policy.get("entitlements") if isinstance(policy, dict) else None) or {}
    return {
        "school_id": school_id,
        "policy_keys": sorted(policy.keys()) if isinstance(policy, dict) else [],
        "entitlement_keys": sorted(entitlements.keys()) if isinstance(entitlements, dict) else [],
        "cache_prefix": _CACHE_PREFIX,
        "cache_ttl_seconds": _CACHE_TTL_SECONDS,
    }


# Canonical aliases for migration from scattered imports.
can = can_capability

__all__ = [
    "can",
    "can_capability",
    "can_policy",
    "can_role",
    "gate_summary",
    "invalidate_entitlement_cache",
]
