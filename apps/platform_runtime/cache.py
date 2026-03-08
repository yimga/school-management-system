"""
Runtime cache: request-scope and per-tenant cache for stable runtime segments.
Invalidate on: policy change, blueprint change, branding change, feature flag change,
workflow/dashboard assignment change, marketplace install/uninstall, entitlement change.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

# Request-scope cache key (thread/local or request attribute)
_REQUEST_RUNTIME_KEY = "_platform_runtime_request_cache"


def get_request_runtime_cache(request: Any) -> dict:
    """Get or create request-scoped runtime cache (one runtime per request)."""
    if request is None:
        return {}
    cache = getattr(request, _REQUEST_RUNTIME_KEY, None)
    if cache is None:
        cache = {}
        setattr(request, _REQUEST_RUNTIME_KEY, cache)
    return cache


def get_cached_runtime_for_request(request: Any, tenant_ctx: Any, school: Any) -> Optional[Any]:
    """
    Return cached TenantRuntime for this request if present.
    Used to avoid rebuilding runtime multiple times in the same request.
    """
    cache = get_request_runtime_cache(request)
    key = _request_cache_key(tenant_ctx, school)
    entry = cache.get(key)
    if entry is None:
        return None
    return entry.get("runtime")


def set_cached_runtime_for_request(request: Any, tenant_ctx: Any, school: Any, runtime: Any) -> None:
    """Store runtime in request-scoped cache."""
    cache = get_request_runtime_cache(request)
    key = _request_cache_key(tenant_ctx, school)
    cache[key] = {"runtime": runtime, "ts": time.time()}


def _request_cache_key(tenant_ctx: Any, school: Any) -> str:
    tid = getattr(tenant_ctx, "tenant_id", None) or getattr(tenant_ctx, "school_id", None)
    sid = getattr(school, "id", None) if school else None
    return f"rt:{tid}:{sid}"


# --- Per-tenant cache (Django cache backend) ---

RUNTIME_TENANT_CACHE_PREFIX = "platform_runtime:tenant:"
RUNTIME_TENANT_CACHE_TTL = 300  # 5 minutes; stable segments only


def tenant_runtime_cache_key(school_id: Any, segment: str) -> str:
    """Cache key for a tenant's runtime segment (e.g. registry, blueprint)."""
    return f"{RUNTIME_TENANT_CACHE_PREFIX}{school_id}:{segment}"


def get_tenant_cached_segment(school_id: Any, segment: str, loader: Callable[[], Any]) -> Any:
    """
    Return cached segment for tenant, or compute via loader and cache.
    Use for stable segments (registry, blueprint, policy snapshot) when TTL is set.
    """
    try:
        from django.core.cache import cache
        from django.conf import settings
        ttl = getattr(settings, "RUNTIME_TENANT_CACHE_TTL", RUNTIME_TENANT_CACHE_TTL)
        if ttl <= 0:
            return loader()
        key = tenant_runtime_cache_key(school_id, segment)
        value = cache.get(key)
        if value is not None:
            return value
        value = loader()
        cache.set(key, value, timeout=ttl)
        return value
    except Exception:
        return loader()


def invalidate_tenant_runtime_cache(school_id: Any) -> None:
    """
    Invalidate all runtime cache entries for a tenant.
    Call after: policy change, blueprint change, branding change, workflow/dashboard
    assignment change, marketplace install/uninstall, entitlement change.
    """
    try:
        from django.core.cache import cache
        # Delete by pattern if backend supports it (Redis); otherwise delete known segments
        key_prefix = f"{RUNTIME_TENANT_CACHE_PREFIX}{school_id}:"
        for segment in ("registry", "blueprint", "policy", "branding", "workflows", "dashboards", "marketplace"):
            cache.delete(f"{key_prefix}{segment}")
    except Exception:
        pass


def invalidate_policy_and_runtime_caches(school: Any) -> None:
    """Convenience: invalidate policy cache (policies app) and tenant runtime cache."""
    try:
        from apps.policies.policy_registry import invalidate_policy_cache
        invalidate_policy_cache(school)
    except Exception:
        pass
    sid = getattr(school, "id", None)
    if sid is not None:
        invalidate_tenant_runtime_cache(sid)
