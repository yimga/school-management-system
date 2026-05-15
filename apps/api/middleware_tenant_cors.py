"""
Pass 12.C: per-tenant CORS allowlist sourced from SiteConfig.

The base `corsheaders.middleware.CorsMiddleware` reads a static
`CORS_ALLOWED_ORIGINS` from settings — fine for first-party origins, but
the marketplace lane needs tenants to add their own integrators
(school district SSO portals, gradebook iframes, …) without a redeploy.

This middleware runs BEFORE CorsMiddleware. It pulls per-tenant origins
from the central school-settings accessor key `cors_allowed_origins`
(JSON list) and injects them into `settings.CORS_ALLOWED_ORIGINS` on the
fly via thread-local override. Empty / missing list → no change.

For safety we never override the regex allowlist (always-on for
*.runmycampus.com) or downgrade credentials. The injected origins are
union-merged with the static allowlist.
"""

from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings

from apps.platform_runtime.school_settings_kv import get_school_settings_dict

logger = logging.getLogger(__name__)


def _normalize_origin(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value or value == "*":
        return ""
    if not value.startswith(("http://", "https://")):
        return ""
    return value


def _extract_tenant_origins(school) -> list[str]:
    if school is None:
        return []
    tenant_settings = get_school_settings_dict(school)
    raw = tenant_settings.get("cors_allowed_origins")
    if not isinstance(raw, (list, tuple)):
        return []
    return [o for o in (_normalize_origin(item) for item in raw) if o]


def _merge_origins(static: Iterable[str], dynamic: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for origin in list(static) + list(dynamic):
        norm = _normalize_origin(origin)
        if norm and norm not in seen:
            seen.add(norm)
            merged.append(norm)
    return merged


class TenantCorsAllowlistMiddleware:
    """
    Process request: merge tenant allowlist into CORS_ALLOWED_ORIGINS just
    in time so CorsMiddleware (mounted after this one) honors the merged set.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            school = getattr(request, "school", None)
            tenant_origins = _extract_tenant_origins(school)
            if tenant_origins:
                static_origins = list(
                    getattr(settings, "CORS_ALLOWED_ORIGINS", []) or []
                )
                settings.CORS_ALLOWED_ORIGINS = _merge_origins(
                    static_origins, tenant_origins
                )
        except Exception:  # noqa: BLE001 - cors must never break a request
            logger.debug("TenantCorsAllowlistMiddleware skipped", exc_info=True)
        return self.get_response(request)
