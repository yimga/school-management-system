"""Fleet-wide live status JSON + SSE for operator monitoring surfaces."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Iterator

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_GET

from apps.schools.fleet_live_payload import (
    build_fleet_live_payload,
    build_fleet_sse_payload,
    parse_fleet_live_query,
)

logger = logging.getLogger(__name__)

_FLEET_SSE_INTERVAL_SECONDS = float(os.environ.get("FLEET_SSE_INTERVAL_SECONDS", "5"))
_FLEET_SSE_MAX_SECONDS = float(os.environ.get("FLEET_SSE_MAX_SECONDS", "3600"))


@staff_member_required
@require_GET
def fleet_live_json(request):
    """GET /super/api/fleet/live.json — paginated fleet rows + summary for live tables."""
    page, page_size, q = parse_fleet_live_query(request)
    payload = build_fleet_live_payload(page=page, page_size=page_size, q=q, include_rows=True)
    return JsonResponse(payload)


def _fleet_sse_stream(request) -> Iterator[str]:
    started = time.monotonic()
    while time.monotonic() - started < _FLEET_SSE_MAX_SECONDS:
        payload = build_fleet_sse_payload(request)
        yield f"data: {json.dumps(payload, default=str)}\n\n"
        time.sleep(_FLEET_SSE_INTERVAL_SECONDS)


@method_decorator(staff_member_required, name="dispatch")
class FleetStreamView(View):
    """SSE fleet heartbeat — GET /super/api/fleet/stream/."""

    def get(self, request):
        response = StreamingHttpResponse(
            _fleet_sse_stream(request),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
