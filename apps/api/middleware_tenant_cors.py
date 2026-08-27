"""
Pass 12.C: per-tenant CORS allowlist sourced from SiteConfig.

The base `corsheaders.middleware.CorsMiddleware` reads a static
`CORS_ALLOWED_ORIGINS` from settings — fine for first-party origins, but
the marketplace lane needs tenants to add their own integrators
(school district SSO portals, gradebook iframes, …) without a redeploy.

It pulls per-tenant origins from the central school-settings accessor key
`cors_allowed_origins` (JSON list) and, when the requesting Origin is one of
them, grants it on that RESPONSE. Empty / missing list → no change.

It does NOT modify `settings.CORS_ALLOWED_ORIGINS`. An earlier version did, and
that is a process-global: the merge never reset and accumulated across requests,
so every tenant in a worker inherited every other tenant's origins. See the
class docstring. (An earlier version of THIS docstring described the merge as a
"thread-local override"; there was no thread-local in the file.)

CorsMiddleware keeps ownership of the static first-party allowlist and the
regex allowlist (always-on for *.runmycampus.com); if it has already answered,
this middleware leaves the response alone, so credentials are never downgraded.
"""

from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.utils.cache import patch_vary_headers

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
    """Grant a tenant's own configured origins, on the RESPONSE, per request.

    WHY THIS DOES NOT TOUCH settings
    --------------------------------
    It used to. The body was::

        settings.CORS_ALLOWED_ORIGINS = _merge_origins(static, tenant_origins)

    ``settings`` is a process-global. That assignment never reset, and because
    ``static`` was re-read from the already-mutated value on the next request,
    the list GREW monotonically: after a request for tenant A, every subsequent
    request served by that worker -- for any tenant -- carried A's origins, then
    A+B's, then A+B+C's. One tenant naming an origin made it a valid CORS origin
    for every other tenant in the process.

    It never fired in production for one reason only: this middleware is not in
    MIDDLEWARE, and the ordering note said it must be mounted ABOVE tenant
    resolution, so ``request.school`` was None and ``tenant_origins`` was empty.
    "Fixing the ordering" -- the obvious next step, and the one the finding
    originally asked for -- would have ACTIVATED the leak rather than closing it.

    The module docstring claimed the merge happened "via thread-local override".
    There was no thread-local anywhere in the file. Under a threaded worker the
    global assignment was also a plain data race.

    So the merge is gone. An origin is now matched against the requesting
    tenant's own list and, if it matches, granted on THAT response only. Nothing
    is shared between requests, so there is nothing to leak and nothing to race,
    and it is safe to mount wherever tenant resolution has already run.

    ``CorsMiddleware`` keeps ownership of the static first-party allowlist and
    the regex: if it already answered, this leaves the response untouched.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            origin = _normalize_origin(request.headers.get("Origin", ""))
            if not origin:
                return response
            # CorsMiddleware already allowed this one (static list or regex).
            if response.has_header("Access-Control-Allow-Origin"):
                return response

            school = getattr(request, "school", None)
            if origin not in _extract_tenant_origins(school):
                return response

            response["Access-Control-Allow-Origin"] = origin
            # The answer depends on the request's Origin, so a shared cache must
            # not serve one tenant's integrator the header minted for another.
            patch_vary_headers(response, ("Origin",))
            if getattr(settings, "CORS_ALLOW_CREDENTIALS", False):
                response["Access-Control-Allow-Credentials"] = "true"

            if request.method == "OPTIONS" and request.headers.get(
                "Access-Control-Request-Method"
            ):
                # A preflight CorsMiddleware declined to answer: complete it, or
                # the browser blocks the real request no matter what the simple
                # response would have said.
                requested_headers = request.headers.get(
                    "Access-Control-Request-Headers"
                )
                if requested_headers:
                    response["Access-Control-Allow-Headers"] = requested_headers
                response["Access-Control-Allow-Methods"] = ", ".join(
                    getattr(settings, "CORS_ALLOW_METHODS", None)
                    or ("DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT")
                )
                max_age = getattr(settings, "CORS_PREFLIGHT_MAX_AGE", 86400)
                if max_age:
                    response["Access-Control-Max-Age"] = str(max_age)
        except Exception:  # noqa: BLE001 - cors must never break a request
            logger.debug("TenantCorsAllowlistMiddleware skipped", exc_info=True)
        return response
