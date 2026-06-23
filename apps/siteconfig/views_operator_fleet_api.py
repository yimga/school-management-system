"""Operator fleet snapshot + context APIs (platform-wide bus)."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Iterator

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views import View

from apps.siteconfig.fleet_context_service import (
    build_fleet_context,
    build_tour_narrator_line,
    should_use_llm_brief,
    should_use_tour_narrator_llm,
)
from apps.siteconfig.globe_viewport_presence import (
    GLOBE_PRESENCE_HEARTBEAT,
    compute_region_hash,
    count_globe_viewport_viewers,
    heartbeat_globe_viewport,
)
from apps.siteconfig.operator_fleet_snapshot import build_operator_fleet_snapshot
from services.sse_response import guarded_sse_response

logger = logging.getLogger(__name__)

_SSE_HEARTBEAT_SECONDS = float(os.environ.get("OPERATOR_FLEET_SSE_INTERVAL_SECONDS", "5"))
_SSE_MAX_SECONDS = float(os.environ.get("OPERATOR_FLEET_SSE_MAX_SECONDS", "30"))


@staff_member_required
def operator_fleet_snapshot_api(request: HttpRequest) -> JsonResponse:
    """GET /super/api/operator/fleet/snapshot/ — unified fleet + globe + pulse bundle."""
    return JsonResponse(build_operator_fleet_snapshot())


@staff_member_required
def operator_fleet_context_api(request: HttpRequest) -> JsonResponse:
    """GET /super/api/operator/fleet/context/ — globe-aware context for AI surfaces."""
    viewport = {}
    if request.GET.get("lat") and request.GET.get("lng"):
        try:
            viewport = {
                "lat": float(request.GET["lat"]),
                "lng": float(request.GET["lng"]),
                "altitude": float(request.GET.get("altitude") or 1.02),
                "region": (request.GET.get("region") or "").strip(),
                "pins_in_view": int(request.GET.get("pins_in_view") or 0),
            }
        except (TypeError, ValueError):
            viewport = {}
    selection = {}
    if request.GET.get("region") or request.GET.get("school_id"):
        selection = {
            "region": (request.GET.get("region") or "").strip(),
            "school_id": (request.GET.get("school_id") or "").strip(),
            "slug": (request.GET.get("slug") or "").strip(),
            "status": (request.GET.get("status") or "").strip(),
            "name": (request.GET.get("name") or "").strip()[:48],
        }
    use_llm = should_use_llm_brief(request)
    return JsonResponse(
        build_fleet_context(
            request,
            viewport=viewport or None,
            selection=selection or None,
            use_llm_brief=use_llm,
        )
    )


@staff_member_required
def operator_fleet_tour_narrator_api(request: HttpRequest) -> JsonResponse:
    """GET /super/api/operator/fleet/tour-narrator/ — W12 opt-in tour waypoint one-liner."""
    label = (request.GET.get("label") or "").strip()[:64]
    region = (request.GET.get("region") or label).strip()[:64]
    try:
        step_index = int(request.GET.get("step") or request.GET.get("step_index") or 0)
    except (TypeError, ValueError):
        step_index = 0
    lat = lng = None
    if request.GET.get("lat") and request.GET.get("lng"):
        try:
            lat = float(request.GET["lat"])
            lng = float(request.GET["lng"])
        except (TypeError, ValueError):
            lat = lng = None
    use_llm = should_use_tour_narrator_llm(request)
    return JsonResponse(
        build_tour_narrator_line(
            request,
            label=label,
            region=region,
            lat=lat,
            lng=lng,
            step_index=step_index,
            use_llm=use_llm,
        )
    )


@staff_member_required
def operator_fleet_globe_presence_api(request: HttpRequest) -> JsonResponse:
    """GET/POST /super/api/operator/fleet/globe-presence/ — W17 viewport viewers."""
    region = (request.GET.get("region") or request.POST.get("region") or "").strip()
    lat = request.GET.get("lat") or request.POST.get("lat")
    lng = request.GET.get("lng") or request.POST.get("lng")
    altitude = request.GET.get("altitude") or request.POST.get("altitude")
    try:
        lat_f = float(lat) if lat not in (None, "") else None
        lng_f = float(lng) if lng not in (None, "") else None
        alt_f = float(altitude) if altitude not in (None, "") else None
    except (TypeError, ValueError):
        lat_f = lng_f = alt_f = None
    region_hash = compute_region_hash(region=region, lat=lat_f, lng=lng_f, altitude=alt_f)
    user_id = getattr(request.user, "pk", None) or 0
    if request.method == "POST":
        payload = heartbeat_globe_viewport(user_id=user_id, region_hash=region_hash)
        payload["others_viewing"] = max(0, int(payload.get("viewers") or 0) - 1)
        return JsonResponse(payload)
    others = count_globe_viewport_viewers(region_hash=region_hash, exclude_user_id=user_id)
    return JsonResponse(
        {
            "region_hash": region_hash,
            "viewers": others + 1,
            "others_viewing": others,
            "heartbeat_seconds": GLOBE_PRESENCE_HEARTBEAT,
        }
    )


def _operator_fleet_sse_stream() -> Iterator[str]:
    started = time.monotonic()
    while time.monotonic() - started < _SSE_MAX_SECONDS:
        try:
            payload = build_operator_fleet_snapshot()
        except Exception as exc:
            logger.warning("operator_fleet_sse.failed err_type=%s", type(exc).__name__)
            yield f'data: {json.dumps({"transient_error": True})}\n\n'
            time.sleep(_SSE_HEARTBEAT_SECONDS)
            continue
        yield f"data: {json.dumps(payload, default=str)}\n\n"
        time.sleep(_SSE_HEARTBEAT_SECONDS)


@method_decorator(staff_member_required, name="dispatch")
class OperatorFleetStreamView(View):
    """SSE — GET /super/api/operator/fleet/stream/."""

    def get(self, request: HttpRequest) -> StreamingHttpResponse:
        return guarded_sse_response(_operator_fleet_sse_stream, content_type="text/event-stream")
