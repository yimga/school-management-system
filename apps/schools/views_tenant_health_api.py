"""Tenant operational health JSON + SSE for dashboard widgets."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Iterator

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_GET

from apps.schools.tenant_operational_health import resolve_tenant_operational_health

logger = logging.getLogger(__name__)

_TENANT_HEALTH_SSE_INTERVAL_SECONDS = float(
    os.environ.get("TENANT_HEALTH_SSE_INTERVAL_SECONDS", "5")
)
_TENANT_HEALTH_SSE_MAX_SECONDS = float(os.environ.get("TENANT_HEALTH_SSE_MAX_SECONDS", "3600"))


def _parse_health_surface(request) -> str:
    return str(request.GET.get("surface") or "admin").strip().lower()[:20]


def build_tenant_health_payload(request) -> dict:
    school = getattr(request, "school", None)
    surface = _parse_health_surface(request)
    return resolve_tenant_operational_health(school, request=request, surface=surface)


@login_required
@require_GET
def tenant_operational_health_json(request):
    """GET …/api/operational-health.json — tenant-scoped health for dashboards."""
    return JsonResponse(build_tenant_health_payload(request))


def _tenant_health_sse_stream(request) -> Iterator[str]:
    started = time.monotonic()
    while time.monotonic() - started < _TENANT_HEALTH_SSE_MAX_SECONDS:
        payload = build_tenant_health_payload(request)
        yield f"data: {json.dumps(payload, default=str)}\n\n"
        time.sleep(_TENANT_HEALTH_SSE_INTERVAL_SECONDS)


@method_decorator(login_required, name="dispatch")
class TenantHealthStreamView(View):
    """SSE tenant health heartbeat — GET …/api/operational-health/stream/."""

    def get(self, request):
        response = StreamingHttpResponse(
            _tenant_health_sse_stream(request),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
