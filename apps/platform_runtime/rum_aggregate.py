"""
Aggregate RUM beacons stored as PlatformEventLog rows (event_type=rum_web_vitals).
Used by staff-only internal API (N10 measured read path).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Tuple

from django.utils import timezone

from apps.platform_runtime.layout_observability import sanitize_layout_observation
from apps.platform_runtime.models import PlatformEventLog

_METRIC_KEYS = ("lcp", "cls", "inp", "fcp", "ttfb", "fid", "tbt", "nav")


def _percentile(sorted_vals: List[float], q: float) -> float | None:
    if not sorted_vals:
        return None
    i = int(round((len(sorted_vals) - 1) * q))
    i = max(0, min(i, len(sorted_vals) - 1))
    return round(sorted_vals[i], 4)


def summarize_rum_web_vitals(
    *,
    hours: int = 24,
    limit_rows: int = 2000,
) -> Dict[str, Any]:
    """
    Pull recent rum_web_vitals events and compute path histogram + numeric percentiles.
    """
    h = max(1, min(int(hours), 168))
    cap = max(1, min(int(limit_rows), 5000))
    since = timezone.now() - timedelta(hours=h)

    rows = list(
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        PlatformEventLog.objects.filter(
            event_type="rum_web_vitals",
            created_at__gte=since,
        ).order_by("-created_at")[:cap]
    )

    paths_count: Dict[str, int] = {}
    series: Dict[str, List[float]] = {k: [] for k in _METRIC_KEYS}
    layout_summary: Dict[str, Any] = {
        "sample_count": 0,
        "overflow_beacon_count": 0,
        "observed_count": 0,
        "overflow_count": 0,
        "max_inline_overflow_px": 0,
        "max_block_overflow_px": 0,
        "viewport_classes": {"A": 0, "B": 0, "C": 0, "U": 0},
    }

    for row in rows:
        payload = row.payload or {}
        if not isinstance(payload, dict):
            continue
        path = str(payload.get("path") or "")[:256] or "(empty)"
        paths_count[path] = paths_count.get(path, 0) + 1
        m = payload.get("metrics")
        if isinstance(m, dict):
            for key in _METRIC_KEYS:
                v = m.get(key)
                if v is None:
                    continue
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if -1e9 < fv < 1e9:
                    series[key].append(fv)
        layout = sanitize_layout_observation(payload.get("layout"))
        if layout:
            layout_summary["sample_count"] += 1
            observed = max(0, int(layout.get("observed_count") or 0))
            overflow = max(0, int(layout.get("overflow_count") or 0))
            layout_summary["observed_count"] += observed
            layout_summary["overflow_count"] += overflow
            if overflow:
                layout_summary["overflow_beacon_count"] += 1
            layout_summary["max_inline_overflow_px"] = max(
                layout_summary["max_inline_overflow_px"],
                max(0, int(layout.get("max_inline_overflow_px") or 0)),
            )
            layout_summary["max_block_overflow_px"] = max(
                layout_summary["max_block_overflow_px"],
                max(0, int(layout.get("max_block_overflow_px") or 0)),
            )
            viewport_class = str(layout.get("viewport_class") or "U")
            if viewport_class not in layout_summary["viewport_classes"]:
                viewport_class = "U"
            layout_summary["viewport_classes"][viewport_class] += 1

    paths_top: List[Tuple[str, int]] = sorted(
        paths_count.items(), key=lambda x: -x[1]
    )[:25]

    metrics_summary: Dict[str, Any] = {}
    for key, vals in series.items():
        if not vals:
            metrics_summary[key] = {"n": 0, "p50": None, "p95": None}
        else:
            s = sorted(vals)
            metrics_summary[key] = {
                "n": len(s),
                "p50": _percentile(s, 0.50),
                "p95": _percentile(s, 0.95),
            }

    return {
        "window_hours": h,
        "sample_cap": cap,
        "beacon_count": len(rows),
        "paths_top": [{"path": p, "count": c} for p, c in paths_top],
        "metrics": metrics_summary,
        "layout": layout_summary,
    }
