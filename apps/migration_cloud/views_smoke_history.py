"""v3.40.0 Agent 13 — smoke-run history operator view.

GET ``/super/migration/smoke/history/`` — staff-only.

Reads the last 30 archived smoke runs from ``var/smoke-results/*.json``
(written by :mod:`apps.migration_cloud.tasks_smoke_archival`) and
renders a table with a numeric sparkline of sections-passed over time.

Filters:

  * ``?status=clean|failed|disabled|...`` — exact match on the summary
    ``status`` key.

The sparkline is pure HTML/CSS (a row of bars sized by sections_passed)
— no JS chart lib, no remote-served font, no per-run hover. The goal
is privacy-conscious trend visualization, not a deep dashboard.

Graceful empty state: when ``var/smoke-results/`` doesn't exist, the
template renders an empty-state hint instead of 500-ing.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from django.conf import settings
from apps.schools.control_plane import require_control_plane_access
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)


_MAX_RUNS_DISPLAYED = 30
# Sparkline bar widths are clamped so an outlier run with a huge
# section count doesn't squash the others into invisible nubs.
_SPARKLINE_BAR_MAX_PX = 28
_SPARKLINE_BAR_MIN_PX = 2


def _var_dir() -> Path:
    base = getattr(settings, "BASE_DIR", None)
    if base is None:
        return Path("var")
    return Path(base) / "var"


def _list_recent_runs(limit: int = _MAX_RUNS_DISPLAYED) -> list[dict]:
    """Read archived smoke-run files, newest-first.

    Returns rows with normalized keys; missing keys default to safe
    blanks. Bad JSON files are silently skipped — the disk-write path
    has its own error-handling.
    """
    results_dir = _var_dir() / "smoke-results"
    if not results_dir.exists() or not results_dir.is_dir():
        return []
    candidates = sorted(
        results_dir.glob("*.json"),
        key=lambda p: p.name,
        reverse=True,
    )
    rows: list[dict] = []
    for path in candidates[:limit]:
        try:
            with path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        summary = payload.get("summary") or {}
        if not isinstance(summary, dict):
            summary = {}
        rows.append({
            "filename": path.name,
            "archived_at_utc_iso": payload.get("archived_at_utc_iso", ""),
            "status": str(summary.get("status", "") or ""),
            "exit_code": summary.get("exit_code"),
            "passed": int(summary.get("passed") or 0),
            "failed": int(summary.get("failed") or 0),
            "skipped": int(summary.get("skipped") or 0),
        })
    return rows


def _compute_sparkline(rows: list[dict]) -> list[dict]:
    """Compute per-row sparkline bar widths.

    Bars represent ``passed`` count. Widths are scaled relative to the
    max ``passed`` count in the visible window and clamped to a
    pleasing band. Reverses to oldest-first so the sparkline reads
    left-to-right chronologically.
    """
    if not rows:
        return []
    oldest_first = list(reversed(rows))
    max_passed = max((r["passed"] for r in oldest_first), default=0) or 1
    out = []
    for r in oldest_first:
        passed = max(0, int(r.get("passed", 0)))
        scaled = int(round((passed / max_passed) * _SPARKLINE_BAR_MAX_PX))
        scaled = max(_SPARKLINE_BAR_MIN_PX, min(_SPARKLINE_BAR_MAX_PX, scaled))
        out.append({
            "filename": r["filename"],
            "passed": passed,
            "failed": r.get("failed", 0),
            "bar_px": scaled,
        })
    return out


# rbac-allow: super-staff-migration-cloud-smoke-history
@method_decorator(require_control_plane_access, name="dispatch")
class SmokeRunHistoryView(View):
    """GET /super/migration/smoke/history/ — staff-only.

    Lists the last 30 archived smoke runs (newest-first table; oldest-
    first sparkline for chronological readability). Filter via
    ``?status=<keyword>``.
    """

    template_name = "migration_cloud/operator/smoke_history.html"

    def get(self, request, *args, **kwargs):
        status_filter = (request.GET.get("status") or "").strip().lower()

        all_rows = _list_recent_runs()
        if status_filter:
            rows = [r for r in all_rows if r["status"].lower() == status_filter]
        else:
            rows = all_rows

        # Distinct statuses for the filter dropdown — sorted, no blanks.
        distinct_statuses = sorted({r["status"] for r in all_rows if r["status"]})

        ctx = {
            "page_title": "Smoke run history",
            "rows": rows,
            "rows_count": len(rows),
            "total_count": len(all_rows),
            "sparkline": _compute_sparkline(rows),
            "distinct_statuses": distinct_statuses,
            "status_filter": status_filter,
            "max_runs_displayed": _MAX_RUNS_DISPLAYED,
            "shell": kwargs.get("shell", "super"),
        }
        resp = render(request, self.template_name, ctx)
        resp["Cache-Control"] = "no-store"
        return resp


__all__ = ["SmokeRunHistoryView"]
