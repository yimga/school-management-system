"""
Domain resolution service — single place for base host, tenant subdomain, and env-specific routing.

Use this module (or its documented imports) instead of scattering request.get_host(),
build_absolute_uri, or hardcoded runmycampus.com / manager.runmycampus.com / localhost.

Canonical entry points:
- Base domain: get_canonical_base_domain(), get_base_domain(request)
- Tenant URL: build_tenant_backend_url(request, school, path=...)
- Host classification: is_public_host(host), public_host_kind(host), is_base_domain(request)
- Local/dev: is_local_dev_host(host)

All implementations live in host_routing and tenant_url; this module re-exports them
so callers can import from one place. New host/domain logic should be added there
and re-exported here.
"""
from __future__ import annotations

from apps.schools.host_routing import (
    get_canonical_base_domain,
    get_legacy_base_domains,
    is_local_dev_host,
    is_public_host,
    normalize_host,
    public_host_kind,
)
from apps.schools.tenant_url import (
    build_tenant_backend_url,
    get_base_domain,
    get_tenant_prefix,
    is_base_domain,
)

__all__ = [
    "get_canonical_base_domain",
    "get_legacy_base_domains",
    "get_base_domain",
    "get_tenant_prefix",
    "is_base_domain",
    "is_public_host",
    "normalize_host",
    "public_host_kind",
    "build_tenant_backend_url",
    "is_local_dev_host",
]
