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
    row_revision_map,
)
from apps.schools.fleet_wall_payload import (
    iter_fleet_wall_sse_events,
    merge_wall_row_revisions,
    request_is_fleet_wall_mode,
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


def _fleet_table_sse_stream(request) -> Iterator[str]:
    started = time.monotonic()
    since_revision: str | None = str(request.GET.get("since_revision") or "").strip() or None
    since_row_revisions: dict[str, str] = {}
    while time.monotonic() - started < _FLEET_SSE_MAX_SECONDS:
        payload = build_fleet_sse_payload(
            request,
            since_revision=since_revision,
            since_row_revisions=since_row_revisions or None,
        )
        yield f"data: {json.dumps(payload, default=str)}\n\n"
        if not payload.get("unchanged"):
            since_revision = str(payload.get("revision") or "") or since_revision
            if payload.get("rows"):
                since_row_revisions = row_revision_map(payload["rows"])
            elif payload.get("delta"):
                for row in payload.get("changed_rows") or []:
                    row_id = str(row.get("id") or "")
                    if row_id:
                        since_row_revisions[row_id] = str(
                            row.get("row_revision") or ""
                        )
        time.sleep(_FLEET_SSE_INTERVAL_SECONDS)


def _fleet_wall_sse_stream(request) -> Iterator[str]:
    started = time.monotonic()
    since_revision: str | None = None
    since_row_revisions: dict[str, str] = {}
    wall_bootstrapped = False
    while time.monotonic() - started < _FLEET_SSE_MAX_SECONDS:
        events = iter_fleet_wall_sse_events(
            request,
            since_revision=since_revision,
            since_row_revisions=since_row_revisions or None,
            wall_bootstrapped=wall_bootstrapped,
        )
        for event in events:
            yield f"data: {json.dumps(event, default=str)}\n\n"

        if events and events[0].get("type") == "unchanged":
            time.sleep(_FLEET_SSE_INTERVAL_SECONDS)
            continue

        since_row_revisions = merge_wall_row_revisions(since_row_revisions, events)
        since_revision = str(events[0].get("revision") or "") or since_revision
        if not wall_bootstrapped and any(
            event.get("type") == "wall_ready" for event in events
        ):
            wall_bootstrapped = True
        time.sleep(_FLEET_SSE_INTERVAL_SECONDS)


def _fleet_sse_stream(request) -> Iterator[str]:
    if request_is_fleet_wall_mode(request):
        yield from _fleet_wall_sse_stream(request)
        return
    yield from _fleet_table_sse_stream(request)


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
