"""Shared fleet live payload builder for JSON + SSE endpoints."""
from __future__ import annotations

import hashlib
import json
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


def fleet_row_revision(row: dict[str, Any]) -> str:
    """Stable per-school fingerprint for SSE row deltas."""
    payload = {
        "fleet_state": row.get("fleet_state"),
        "heatmap_tier": row.get("heatmap_tier"),
        "roster_state": row.get("roster_state"),
        "is_active": row.get("is_active"),
        "is_approved": row.get("is_approved"),
        "is_frozen": row.get("is_frozen"),
        "lifecycle_state": row.get("lifecycle_state"),
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _build_fleet_row_dict(school, *, cached_subscription) -> dict[str, Any]:
    # cached_subscription is REQUIRED (no default): every caller resolves it via
    # batch_current_subscriptions(). A bare None default would mean "no
    # subscription" to get_lifecycle_snapshot and silently mask billing_exception
    # — fail loud instead. See apps/schools/fleet_status.py::_SUBSCRIPTION_UNSET.
    status = resolve_school_fleet_status(
        school, cached_subscription=cached_subscription
    )
    tile = resolve_fleet_tile(school, cached_subscription=cached_subscription)
    row = {
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
    row["row_revision"] = fleet_row_revision(row)
    return row


def _partition_fleet_row_delta(
    rows: list[dict[str, Any]],
    since_row_revisions: dict[str, str] | None,
) -> tuple[list[dict[str, Any]], bool]:
    """Return changed rows for the current page; ``True`` when a full snapshot is required."""
    if not since_row_revisions:
        return rows, True
    changed: list[dict[str, Any]] = []
    for row in rows:
        row_id = str(row.get("id") or "")
        current = row.get("row_revision") or fleet_row_revision(row)
        if since_row_revisions.get(row_id) != current:
            changed.append(row)
    return changed, False


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
            rows.append(
                _build_fleet_row_dict(school, cached_subscription=subs.get(school.pk))
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


def build_fleet_sse_payload(
    request,
    *,
    since_revision: str | None = None,
    since_row_revisions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """SSE snapshot — summary-only, full page snapshot, or row deltas on repeat ticks."""
    since = (since_revision or "").strip() or None
    if since is None and request is not None:
        since = str(request.GET.get("since_revision") or "").strip() or None

    if _request_wants_fleet_rows(request):
        page, page_size, q = parse_fleet_live_query(request)
        payload = build_fleet_live_payload(
            page=page,
            page_size=page_size,
            q=q,
            include_rows=True,
        )
        revision = payload["revision"]
        if since and since == revision:
            return {
                "generated_at": payload["generated_at"],
                "revision": revision,
                "unchanged": True,
                "poll_interval_seconds": payload["poll_interval_seconds"],
            }

        base = {
            "generated_at": payload["generated_at"],
            "revision": revision,
            "summary": payload["summary"],
            "summary_label": payload["summary_label"],
            "poll_interval_seconds": payload["poll_interval_seconds"],
            "pagination": payload["pagination"],
        }
        changed_rows, needs_snapshot = _partition_fleet_row_delta(
            payload["rows"],
            since_row_revisions,
        )
        if needs_snapshot:
            return {**base, "snapshot": True, "rows": payload["rows"]}
        return {**base, "delta": True, "changed_rows": changed_rows}

    payload = build_fleet_live_payload(include_rows=False)
    revision = payload["revision"]
    if since and since == revision:
        return {
            "generated_at": payload["generated_at"],
            "revision": revision,
            "unchanged": True,
            "poll_interval_seconds": payload["poll_interval_seconds"],
        }
    return {
        "generated_at": payload["generated_at"],
        "revision": revision,
        "summary": payload["summary"],
        "summary_label": payload["summary_label"],
        "poll_interval_seconds": payload["poll_interval_seconds"],
    }


def row_revision_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Build id → row_revision map for SSE stream state on the connection."""
    mapping: dict[str, str] = {}
    for row in rows:
        row_id = str(row.get("id") or "")
        if not row_id:
            continue
        mapping[row_id] = str(row.get("row_revision") or fleet_row_revision(row))
    return mapping
