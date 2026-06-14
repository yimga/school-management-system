"""Global Footprint globe API — live bundle, bbox markers, SSE (batch 1653 + 1656)."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Iterator

from django.contrib.admin.views.decorators import staff_member_required
from django.db import InterfaceError, OperationalError, close_old_connections
from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)

_SSE_HEARTBEAT_SECONDS = float(os.environ.get("GLOBE_SSE_INTERVAL_SECONDS", "5"))
_SSE_MAX_SECONDS = float(os.environ.get("GLOBE_SSE_MAX_SECONDS", "3600"))


def _school_rows_for_globe() -> list[dict[str, Any]]:
    from apps.siteconfig.cockpit_panels_realdata_service import _world_map_school_rows
    from apps.schools.models import School

    # tenant-isolation-allow: platform-cockpit-cross-tenant-world-map
    active = School.objects.filter(is_active=True)
    return _world_map_school_rows(active)


def _platform_status_counts() -> tuple[int, int, int]:
    from apps.schools.models import School

    try:
        # tenant-isolation-allow: platform-cockpit-cross-tenant-world-map
        active = School.objects.filter(is_active=True).count()
        # tenant-isolation-allow: platform-cockpit-cross-tenant-world-map
        suspended = School.objects.filter(is_active=False, deleted_at__isnull=True, is_frozen=False).count()
        # tenant-isolation-allow: platform-cockpit-cross-tenant-world-map
        frozen = School.objects.filter(is_frozen=True, deleted_at__isnull=True).count()
    except Exception as exc:
        logger.warning("globe.status_counts_failed err_type=%s", type(exc).__name__)
        return 0, 0, 0
    return active, suspended, frozen


def _parse_bbox(request: HttpRequest) -> tuple[float | None, float | None, float | None, float | None]:
    def _f(key: str) -> float | None:
        raw = request.GET.get(key)
        if raw is None or raw == "":
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    return _f("lat_min"), _f("lat_max"), _f("lng_min"), _f("lng_max")


def _globe_query_bundle(request: HttpRequest) -> dict[str, Any]:
    from apps.siteconfig.cockpit_panels_realdata_service import _world_map_footprint_stats
    from apps.siteconfig.world_map_geo import build_globe_live_bundle, build_globe_markers
    from apps.schools.models import School

    region = (request.GET.get("region") or "").strip() or None
    status = (request.GET.get("status") or "").strip().lower() or None
    zoom_raw = request.GET.get("zoom")
    try:
        zoom = float(zoom_raw) if zoom_raw else 1.35
    except (TypeError, ValueError):
        zoom = 1.35

    lat_min, lat_max, lng_min, lng_max = _parse_bbox(request)
    bbox = None
    if None not in (lat_min, lat_max, lng_min, lng_max):
        bbox = (lat_min, lat_max, lng_min, lng_max)

    rows = _school_rows_for_globe()
    markers = build_globe_markers(rows)
    bundle = build_globe_live_bundle(
        markers,
        zoom=zoom,
        region=region,
        status=status,
        bbox=bbox,
    )
    active, suspended, frozen = _platform_status_counts()
    # tenant-isolation-allow: platform-cockpit-cross-tenant-world-map
    stats = _world_map_footprint_stats(School.objects.filter(is_active=True))
    return {
        **bundle,
        **stats,
        "schools_live": active,
        "suspended": suspended,
        "frozen": frozen,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@staff_member_required
def globe_markers_api(request: HttpRequest) -> JsonResponse:
    """GET /super/api/globe/markers/ — filtered + clustered markers (legacy alias)."""
    data = _globe_query_bundle(request)
    return JsonResponse(
        {
            "markers": data["markers"],
            "country_labels": data["country_labels"],
            "region_labels": data.get("region_labels", []),
            "arcs": data.get("arcs", []),
            "revision": data.get("revision"),
            "count": data.get("display_count", len(data["markers"])),
            "marker_count": data.get("marker_count"),
            "updated_at": data["updated_at"],
        }
    )


@staff_member_required
def globe_live_api(request: HttpRequest) -> JsonResponse:
    """GET /super/api/globe/live/ — full live footprint bundle for realtime globe sync."""
    return JsonResponse(_globe_query_bundle(request))


def _globe_live_snapshot() -> dict[str, Any]:
    from django.utils import timezone

    from apps.siteconfig.world_map_geo import build_globe_live_bundle, build_globe_markers, compute_globe_revision

    active, suspended, frozen = _platform_status_counts()
    rows = _school_rows_for_globe()
    markers = build_globe_markers(rows)
    revision = compute_globe_revision(markers)
    bundle = build_globe_live_bundle(markers, zoom=1.35)
    return {
        "ts": timezone.now().isoformat(),
        "schools_live": active,
        "suspended": suspended,
        "frozen": frozen,
        "marker_count": bundle["marker_count"],
        "display_count": bundle["display_count"],
        "revision": revision,
    }


def _globe_sse_stream() -> Iterator[str]:
    started = time.monotonic()
    while time.monotonic() - started < _SSE_MAX_SECONDS:
        try:
            payload = _globe_live_snapshot()
        except (OperationalError, InterfaceError) as exc:
            # Render Postgres drops long-lived connections; the broken conn must
            # be closed explicitly (no request_finished signal on a generator)
            # or every subsequent tick fails. Degrade instead of crashing the
            # worker; the next tick reconnects.
            logger.warning("globe_sse.transient_db err_type=%s", type(exc).__name__)
            close_old_connections()
            yield f'data: {json.dumps({"transient_db": True})}\n\n'
            time.sleep(_SSE_HEARTBEAT_SECONDS)
            continue
        yield f"data: {json.dumps(payload, default=str)}\n\n"
        time.sleep(_SSE_HEARTBEAT_SECONDS)


@method_decorator(staff_member_required, name="dispatch")
class GlobeStreamView(View):
    """SSE live footprint counts — GET /super/api/globe/stream/."""

    def get(self, request: HttpRequest) -> StreamingHttpResponse:
        response = StreamingHttpResponse(_globe_sse_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
