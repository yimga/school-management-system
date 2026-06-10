"""Shared fleet live payload builder for JSON + SSE endpoints."""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.schools.control_plane_lifecycle import batch_current_subscriptions
from apps.schools.fleet_status import (
    FLEET_POLL_INTERVAL_SECONDS,
    build_fleet_queryset,
    fleet_revision,
    format_fleet_summary_label,
    resolve_fleet_summary,
    resolve_fleet_tile,
    resolve_fleet_tiles,
    resolve_school_fleet_status,
)


def _parse_int(raw, default: int, *, minimum: int = 1, maximum: int = 500) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def build_fleet_live_payload(
    *,
    page: int = 1,
    page_size: int = 50,
    q: str = "",
    include_rows: bool = True,
) -> dict[str, Any]:
    qs = build_fleet_queryset()
    schools = list(qs)
    q_norm = (q or "").strip().lower()
    if q_norm:
        schools = [
            s
            for s in schools
            if q_norm in (getattr(s, "name", "") or "").lower()
            or q_norm in (getattr(s, "slug", "") or "").lower()
        ]

    summary = resolve_fleet_summary(schools)
    total = len(schools)
    start = (page - 1) * page_size
    end = start + page_size
    page_schools = schools[start:end]

    rows: list[dict[str, Any]] = []
    if include_rows:
        subs = batch_current_subscriptions(page_schools)
        for school in page_schools:
            status = resolve_school_fleet_status(
                school, cached_subscription=subs.get(school.pk)
            )
            tile = resolve_fleet_tile(school, cached_subscription=subs.get(school.pk))
            rows.append(
                {
                    "id": str(school.pk),
                    "name": getattr(school, "name", "") or "",
                    "slug": getattr(school, "slug", "") or "",
                    "sector": (getattr(school, "primary_sector", None) or "").strip(),
                    "fleet_state": status["fleet_state"],
                    "fleet_state_label": status["fleet_state_label"],
                    "heatmap_tier": status["heatmap_tier"],
                    "lifecycle_state": status["lifecycle_state"],
                    "is_active": status["is_active"],
                    "is_approved": status["is_approved"],
                    "is_frozen": status["is_frozen"],
                    "tooltip": tile.get("tooltip") or "",
                    "roster_state": _roster_state_from_fleet(status),
                }
            )

    heatmap_tiles, _ = resolve_fleet_tiles(max_tiles=500)
    revision = fleet_revision(heatmap_tiles, summary)

    return {
        "generated_at": timezone.now().isoformat(),
        "poll_interval_seconds": FLEET_POLL_INTERVAL_SECONDS,
        "summary": summary,
        "summary_label": format_fleet_summary_label(summary),
        "revision": revision,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_next": end < total,
        },
        "rows": rows,
    }


def _roster_state_from_fleet(status: dict[str, Any]) -> str:
    tier = status.get("heatmap_tier") or ""
    if tier == "idle":
        return "inactive"
    if tier == "danger":
        return "attention"
    if tier == "warn":
        return "pending" if status.get("fleet_state") == "pending_approval" else "attention"
    return "healthy"


def parse_fleet_live_query(request) -> tuple[int, int, str]:
    page = _parse_int(request.GET.get("page"), 1, minimum=1, maximum=10_000)
    page_size = _parse_int(request.GET.get("page_size"), 50, minimum=10, maximum=200)
    q = str(request.GET.get("q") or "").strip()
    return page, page_size, q


def _request_wants_fleet_rows(request) -> bool:
    if request is None:
        return False
    flag = str(request.GET.get("include_rows") or "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    return request.GET.get("page") is not None or bool(str(request.GET.get("q") or "").strip())


def build_fleet_sse_payload(request) -> dict[str, Any]:
    """SSE snapshot — summary-only by default; paginated rows when client passes page/q."""
    if _request_wants_fleet_rows(request):
        page, page_size, q = parse_fleet_live_query(request)
        payload = build_fleet_live_payload(
            page=page,
            page_size=page_size,
            q=q,
            include_rows=True,
        )
        return {
            "generated_at": payload["generated_at"],
            "revision": payload["revision"],
            "summary": payload["summary"],
            "summary_label": payload["summary_label"],
            "poll_interval_seconds": payload["poll_interval_seconds"],
            "pagination": payload["pagination"],
            "rows": payload["rows"],
        }

    payload = build_fleet_live_payload(include_rows=False)
    return {
        "generated_at": payload["generated_at"],
        "revision": payload["revision"],
        "summary": payload["summary"],
        "summary_label": payload["summary_label"],
        "poll_interval_seconds": payload["poll_interval_seconds"],
    }
