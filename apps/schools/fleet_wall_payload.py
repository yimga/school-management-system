"""Fleet wall SSE payloads — chunked full-fleet load + fleet-wide row deltas."""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.schools.control_plane_lifecycle import batch_current_subscriptions
from apps.schools.fleet_live_payload import (
    FLEET_POLL_INTERVAL_SECONDS,
    _build_fleet_row_dict,
    _partition_fleet_row_delta,
    _parse_int,
    fleet_row_revision,
    row_revision_map,
)
from apps.schools.fleet_status import (
    build_fleet_queryset,
    fleet_revision,
    format_fleet_summary_label,
    resolve_fleet_summary,
    resolve_fleet_tiles,
)

FLEET_WALL_DEFAULT_CHUNK_SIZE = 50
FLEET_WALL_MAX_CHUNK_SIZE = 100


def request_is_fleet_wall_mode(request) -> bool:
    if request is None:
        return False
    return str(request.GET.get("mode") or "").strip().lower() == "wall"


def parse_fleet_wall_query(request) -> tuple[int, str]:
    chunk_size = _parse_int(
        getattr(request, "GET", {}).get("chunk_size") if request else None,
        FLEET_WALL_DEFAULT_CHUNK_SIZE,
        minimum=25,
        maximum=FLEET_WALL_MAX_CHUNK_SIZE,
    )
    q = str(getattr(request, "GET", {}).get("q") or "").strip() if request else ""
    return chunk_size, q


def _filter_fleet_schools(q: str = ""):
    schools = list(build_fleet_queryset())
    q_norm = (q or "").strip().lower()
    if not q_norm:
        return schools
    return [
        s
        for s in schools
        if q_norm in (getattr(s, "name", "") or "").lower()
        or q_norm in (getattr(s, "slug", "") or "").lower()
    ]


def build_fleet_wall_rows(q: str = "") -> list[dict[str, Any]]:
    schools = _filter_fleet_schools(q)
    subs = batch_current_subscriptions(schools)
    return [
        _build_fleet_row_dict(school, cached_subscription=subs.get(school.pk))
        for school in schools
    ]


def build_fleet_wall_context(*, q: str = "") -> dict[str, Any]:
    schools = _filter_fleet_schools(q)
    summary = resolve_fleet_summary(schools)
    heatmap_tiles, _ = resolve_fleet_tiles(max_tiles=max(len(schools), 500))
    revision = fleet_revision(heatmap_tiles, summary)
    return {
        "generated_at": timezone.now().isoformat(),
        "poll_interval_seconds": FLEET_POLL_INTERVAL_SECONDS,
        "summary": summary,
        "summary_label": format_fleet_summary_label(summary),
        "revision": revision,
        "total": len(schools),
    }


def iter_fleet_wall_sse_events(
    request,
    *,
    since_revision: str | None,
    since_row_revisions: dict[str, str] | None,
    wall_bootstrapped: bool,
) -> list[dict[str, Any]]:
    """One SSE tick for fleet wall — summary/chunks on bootstrap, deltas afterward."""
    chunk_size, q = parse_fleet_wall_query(request)
    ctx = build_fleet_wall_context(q=q)
    revision = ctx["revision"]
    since = (since_revision or "").strip() or None

    if wall_bootstrapped and since and since == revision:
        return [
            {
                "type": "unchanged",
                "revision": revision,
                "generated_at": ctx["generated_at"],
                "poll_interval_seconds": ctx["poll_interval_seconds"],
            }
        ]

    all_rows = build_fleet_wall_rows(q)
    total_chunks = (
        max(1, (len(all_rows) + chunk_size - 1) // chunk_size) if all_rows else 0
    )

    if not wall_bootstrapped:
        events: list[dict[str, Any]] = [
            {
                "type": "summary",
                "revision": revision,
                "generated_at": ctx["generated_at"],
                "poll_interval_seconds": ctx["poll_interval_seconds"],
                "summary": ctx["summary"],
                "summary_label": ctx["summary_label"],
                "total": ctx["total"],
                "chunk_size": chunk_size,
                "total_chunks": total_chunks,
            }
        ]
        for index, start in enumerate(range(0, len(all_rows), chunk_size)):
            events.append(
                {
                    "type": "chunk",
                    "revision": revision,
                    "chunk_index": index,
                    "chunk_count": total_chunks,
                    "rows": all_rows[start : start + chunk_size],
                }
            )
        events.append(
            {
                "type": "wall_ready",
                "revision": revision,
                "total": len(all_rows),
            }
        )
        return events

    changed_rows, _ = _partition_fleet_row_delta(all_rows, since_row_revisions)
    return [
        {
            "type": "summary",
            "revision": revision,
            "generated_at": ctx["generated_at"],
            "poll_interval_seconds": ctx["poll_interval_seconds"],
            "summary": ctx["summary"],
            "summary_label": ctx["summary_label"],
            "total": ctx["total"],
        },
        {
            "type": "delta",
            "revision": revision,
            "generated_at": ctx["generated_at"],
            "poll_interval_seconds": ctx["poll_interval_seconds"],
            "changed_rows": changed_rows,
        },
    ]


def merge_wall_row_revisions(
    mapping: dict[str, str],
    events: list[dict[str, Any]],
) -> dict[str, str]:
    """Update connection row-revision map from wall SSE events."""
    merged = dict(mapping)
    for event in events:
        if event.get("type") == "chunk":
            merged.update(row_revision_map(event.get("rows") or []))
        elif event.get("type") == "delta":
            for row in event.get("changed_rows") or []:
                row_id = str(row.get("id") or "")
                if row_id:
                    merged[row_id] = str(
                        row.get("row_revision") or fleet_row_revision(row)
                    )
    return merged
