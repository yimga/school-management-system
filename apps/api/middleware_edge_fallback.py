"""Django-side SWR fallback for /api/v1/runtime/* (v4.00.0).

When Cloudflare Workers is provisioned, the edge intercepts these requests
and serves from KV. When it is NOT provisioned (single-region deploys,
local dev, staging), this middleware mimics the Worker's SWR behavior using
Django's cache backend. Same Surrogate-Key contract, same SWR window.

Off by default — flip ``RMC_EDGE_FALLBACK_ENABLED=1`` to activate. Operators
who run behind Cloudflare want the edge to do this work, not Django.

Path match: ``/api/v1/runtime/`` prefix. Other paths pass through unchanged.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)

_RUNTIME_PREFIX = "/api/v1/runtime/"
_CACHE_KEY_PREFIX = "rmc:edge_fallback:"
_STALE_SECONDS = 15
_REVALIDATE_SECONDS = 300


def _is_enabled() -> bool:
    return str(getattr(settings, "RMC_EDGE_FALLBACK_ENABLED", "")).strip().lower() in {"1", "true", "yes"}


def _viewport(request: HttpRequest) -> str:
    return (request.META.get("HTTP_X_RMC_VIEWPORT", "") or "A").strip().upper()[:1] or "A"


def _cache_key(request: HttpRequest) -> str:
    school = getattr(request, "school", None)
    tenant = (
        getattr(school, "slug", None)
        or getattr(school, "subdomain", None)
        or request.get_host().split(":", 1)[0]
    )
    return f"{_CACHE_KEY_PREFIX}{tenant}::{request.path}::v={_viewport(request)}"


class EdgeSWRFallbackMiddleware:
    """SWR cache for /api/v1/runtime/* when no CDN is in front of Django."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not _is_enabled() or request.method not in ("GET", "HEAD"):
            return self.get_response(request)
        if not request.path.startswith(_RUNTIME_PREFIX):
            return self.get_response(request)
        # Don't double-cache if the real edge already served this — the Worker
        # stamps X-RMC-Edge-Origin so we can detect that case.
        if request.META.get("HTTP_X_RMC_EDGE_ORIGIN") == "1":
            return self.get_response(request)
        key = _cache_key(request)
        cached = cache.get(key)
        now = time.time()
        if cached and (now - cached.get("stored_at", 0)) < _STALE_SECONDS:
            return _replay(cached, marker="HIT")
        # Compute fresh response. If we have stale-but-not-too-old, we could
        # serve stale + refresh async — but Django middleware is sync; we just
        # refresh inline. The Cloudflare Worker is where the true SWR lives.
        response = self.get_response(request)
        if 200 <= response.status_code < 300 and "Surrogate-Key" in response:
            try:
                cache.set(
                    key,
                    {
                        "body": response.content,
                        "status": response.status_code,
                        "headers": {k: v for k, v in response.items()},
                        "stored_at": now,
                    },
                    timeout=_REVALIDATE_SECONDS,
                )
            except (TypeError, ValueError) as exc:
                logger.debug("edge_fallback.cache_set_failed: %s", exc)
        response["X-RMC-Edge-Fallback"] = "MISS"
        return response


def _replay(cached: dict, marker: str) -> HttpResponse:
    resp = HttpResponse(cached.get("body", b""), status=cached.get("status", 200))
    for k, v in (cached.get("headers") or {}).items():
        resp[k] = v
    resp["X-RMC-Edge-Fallback"] = marker
    return resp
