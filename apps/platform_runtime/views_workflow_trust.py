"""Tenant-trusted workflow progress stream (wave 4)."""

from __future__ import annotations

import json
import time

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from services.http_auth_guards import login_required_api, login_required_sse
from services.sse_response import guarded_sse_response

from apps.platform_runtime.views_workflow_progress import _resolve_scope


@login_required_api
@require_GET
def tenant_trusted_active_view(request):
    """JSON list of tenant-safe active runs only."""

    from apps.platform_runtime.workflow_tenant_trust import list_tenant_trusted_runs

    schema, _actor = _resolve_scope(request)
    if not schema:
        return JsonResponse({"error": "tenant_required"}, status=400)
    runs = list_tenant_trusted_runs(tenant_schema=schema, limit=15)
    return JsonResponse(
        {
            "generated_at": timezone.now().isoformat(),
            "tenant_schema": schema,
            "runs": runs,
        }
    )


@login_required_sse
@require_GET
def tenant_trusted_stream_view(request):
    """SSE stream of tenant-safe workflows only."""

    from apps.platform_runtime.workflow_tenant_trust import list_tenant_trusted_runs

    schema, _actor = _resolve_scope(request)
    if not schema:
        return JsonResponse({"error": "tenant_required"}, status=400)

    def _stream():
        deadline = time.monotonic() + 25.0
        while time.monotonic() < deadline:
            runs = list_tenant_trusted_runs(tenant_schema=schema, limit=15)
            payload = json.dumps({"runs": runs, "ts": timezone.now().isoformat()})
            yield f"data: {payload}\n\n".encode("utf-8")
            time.sleep(3.0)
        yield b"event: bye\ndata: {}\n\n"

    return guarded_sse_response(_stream(), content_type="text/event-stream")
