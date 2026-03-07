"""
World Engine: tenant-scoped cache key prefix to prevent cross-tenant leakage.
Prepend this to any cache key that stores tenant-specific data when using shared Redis.
Redis-backed tenant resolution: when cache backend is Redis, tenant resolution
(schema/domain -> school id) can be cached to avoid DB on every request.
"""
from typing import Any, Optional

from django.core.cache import cache


def get_tenant_cache_prefix(request=None) -> str:
    """
    Return a string to prepend to tenant-scoped cache keys (e.g. schema name or school id).
    Use for evals, dashboard widgets, portal, reports, compliance, backend status fragment.
    """
    try:
        from django.db import connection
        tenant = getattr(connection, "tenant", None)
        if tenant is not None:
            schema = getattr(tenant, "schema_name", None)
            if schema:
                return f"tenant:{schema}"
    except Exception:
        pass
    if request is not None:
        school = getattr(request, "school", None)
        if school is not None:
            return f"school:{getattr(school, 'id', '')}"
    return "public"


def tenant_cache_key(base_key: str, request=None) -> str:
    """Return base_key prefixed with tenant/school identifier for tenant-scoped caches."""
    prefix = get_tenant_cache_prefix(request)
    return f"{prefix}:{base_key}"


# Redis-backed tenant resolution (RUNMYCAMPUS_ROADMAP_TASKS)
TENANT_RESOLUTION_CACHE_PREFIX = "tenant_resolution"
TENANT_RESOLUTION_TIMEOUT = 300  # 5 minutes


def get_tenant_cached(lookup_key: str) -> Optional[Any]:
    """
    Return cached tenant payload for lookup_key (e.g. schema_name or domain).
    Use when cache backend is Redis for fast tenant resolution without DB hit.
    Returns None if not cached or cache unavailable.
    """
    key = f"{TENANT_RESOLUTION_CACHE_PREFIX}:{lookup_key}"
    try:
        return cache.get(key)
    except Exception:
        return None


def set_tenant_cached(lookup_key: str, payload: Any, timeout: int = TENANT_RESOLUTION_TIMEOUT) -> None:
    """
    Cache tenant payload for lookup_key. Use after resolving tenant from DB
    so subsequent requests can use get_tenant_cached(lookup_key) without DB.
    """
    key = f"{TENANT_RESOLUTION_CACHE_PREFIX}:{lookup_key}"
    try:
        cache.set(key, payload, timeout=timeout)
    except Exception:
        pass
