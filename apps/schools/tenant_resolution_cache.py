"""
Tenant host/subdomain resolution cache keys (AWS pillar).

Maps public host or subdomain labels to school primary keys. Keys are global
(not school-prefixed) because the lookup input is the host string itself.
Uses a versioned namespace so cache busts do not collide with legacy keys.
"""

from __future__ import annotations

_CACHE_VERSION = "v1"
_MAX_LABEL_LEN = 253


def tenant_resolution_cache_key(host_or_sub: str, kind: str = "host") -> str:
    """
    Return a stable cache key for tenant resolution by host or subdomain.

    ``kind`` must be ``host`` or ``subdomain``.
    """
    label = (host_or_sub or "").strip().lower()[:_MAX_LABEL_LEN]
    if not label:
        label = "_empty"
    resolved_kind = kind if kind in ("host", "subdomain") else "host"
    return f"rmc:{_CACHE_VERSION}:tenant_resolve:{resolved_kind}:{label}"


def invalidate_tenant_resolution_cache(
    *,
    host: str | None = None,
    subdomain: str | None = None,
) -> None:
    """Best-effort delete of resolution cache entries after domain changes."""
    from apps.schools.middleware import _cache_delete_optional

    if host:
        _cache_delete_optional(tenant_resolution_cache_key(host, "host"))
    if subdomain:
        _cache_delete_optional(tenant_resolution_cache_key(subdomain, "subdomain"))


__all__ = [
    "invalidate_tenant_resolution_cache",
    "tenant_resolution_cache_key",
]
