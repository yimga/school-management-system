"""django-tenants TenantMainMiddleware with DB-free load-balancer health probes."""

from __future__ import annotations

import logging

from django.db import connection
from django.http import JsonResponse
from django_tenants.middleware.main import TenantMainMiddleware

from apps.platform_runtime.transient_db import (
    build_transient_db_unavailable_response,
    is_transient_database_error,
    reset_broken_database_state,
)

logger = logging.getLogger(__name__)

# Keep in sync with apps.schools.middleware.HEALTH_PREFIXES (+ healthz).
_HEALTH_PREFIXES = (
    "/health",
    "/ready",
    "/api/health",
    "/-/version",
    "/api/system/version",
    "/version.json",
    "/healthz",
)


def is_health_probe_path(path: str) -> bool:
    path = (path or "").strip()
    for prefix in _HEALTH_PREFIXES:
        normalized = prefix.rstrip("/")
        if path.startswith(prefix) or path == normalized:
            return True
    return False


def health_probe_degraded_response():
    """200 degraded liveness — Render keeps the web process up during Postgres blips."""
    response = JsonResponse(
        {
            "status": "degraded",
            "database": "unavailable",
            "retryable": True,
            "detail": "Database temporarily unavailable; web process is up.",
        },
        status=200,
    )
    response["Retry-After"] = "30"
    return response


class HealthAwareTenantMainMiddleware(TenantMainMiddleware):
    """Skip tenant domain lookup for /health/ so probes never 500 on SSL EOF blips."""

    def process_request(self, request):
        path = getattr(request, "path", "") or ""
        if is_health_probe_path(path):
            return self._process_health_probe(request)
        for attempt in range(2):
            try:
                return super().process_request(request)
            except Exception as exc:
                if not is_transient_database_error(exc):
                    raise
                logger.warning(
                    "tenant_main_transient_db path=%s attempt=%s error=%s",
                    path,
                    attempt + 1,
                    str(exc)[:200],
                )
                reset_broken_database_state()
                if attempt == 0:
                    continue
                break
        if is_health_probe_path(path):
            return health_probe_degraded_response()
        return build_transient_db_unavailable_response(
            request,
            source="tenant_main_middleware",
        )

    def _process_health_probe(self, request):
        try:
            connection.set_schema_to_public()
            self.setup_url_routing(request, force_public=True)
        except Exception as exc:
            if is_transient_database_error(exc):
                logger.warning(
                    "health_probe_transient_db path=%s error=%s",
                    getattr(request, "path", ""),
                    str(exc)[:200],
                )
                return health_probe_degraded_response()
            raise
        return None
