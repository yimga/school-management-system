"""
World Engine: tenant-scoped cache key prefix to prevent cross-tenant leakage.
Prepend this to any cache key that stores tenant-specific data when using shared Redis.
"""
from typing import Optional


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
