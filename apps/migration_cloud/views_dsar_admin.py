"""v3.40.0 Agent 13 — DSAR runbook operator view.

GET ``/super/migration/dsar/runbook/`` — staff-only.

Shows:

  * The last 30 DSAR runs (read from ``var/dsar-runs/*.json``,
    newest-first).
  * The latest UTC-ISO timestamp from ``var/dsar-last-run.txt``.
  * A POST form that records a new DSAR run (calls
    :func:`apps.migration_cloud.management.commands.dsar_runbook_record.record_dsar_run`).

Security:

  * Staff-only via ``@method_decorator(require_control_plane_access,
    name="dispatch")``.
  * The notes field is persisted to the per-run JSON file ONLY; the
    response page truncates notes to 120 chars in the table display
    (defense-in-depth — the operator that submitted them is the same
    operator viewing them, but we still keep the surface narrow).
  * NEVER renders the raw request_id; only the sha256 prefix.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from django.conf import settings
from apps.schools.control_plane import require_control_plane_access
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)


_MAX_RUNS_DISPLAYED = 30
_NOTES_DISPLAY_TRUNCATE = 120


def _var_dir() -> Path:
    base = getattr(settings, "BASE_DIR", None)
    if base is None:
        return Path("var")
    return Path(base) / "var"


def _read_last_run_pointer() -> str:
    path = _var_dir() / "dsar-last-run.txt"
    try:
        if not path.exists():
            return ""
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if line:
                    return line
    except (OSError, ValueError):
        return ""
    return ""


def _list_recent_runs(limit: int = _MAX_RUNS_DISPLAYED) -> list[dict]:
    """Read up to ``limit`` recent DSAR run JSON files, newest-first.

    Filenames are UTC-ISO stamped; sort by filename to get newest-first
    without parsing each file. Graceful empty state when the directory
    is missing (returns ``[]``).
    """
    runs_dir = _var_dir() / "dsar-runs"
    if not runs_dir.exists() or not runs_dir.is_dir():
        return []
    candidates = sorted(
        runs_dir.glob("*.json"),
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
        notes_raw = payload.get("notes", "") or ""
        rows.append({
            "filename": path.name,
            "recorded_at_utc_iso": payload.get("recorded_at_utc_iso", ""),
            "completed_at_utc_iso": payload.get("completed_at_utc_iso", ""),
            "request_id_prefix": payload.get("request_id_prefix", "")[:12],
            "has_notes": bool(payload.get("has_notes", False)),
            "notes_truncated": (notes_raw[:_NOTES_DISPLAY_TRUNCATE]
                                if notes_raw else ""),
        })
    return rows


# rbac-allow: super-staff-dsar-runbook-view-record
@method_decorator(require_control_plane_access, name="dispatch")
class DSARRunbookView(View):
    """GET + POST /super/migration/dsar/runbook/ — operator DSAR runbook.

    GET renders the table + form. POST records a run via the same code
    path the CLI uses, then redirects back to GET (post/redirect/get).
    """

    template_name = "migration_cloud/operator/dsar_runbook.html"

    def get(self, request, *args, **kwargs):
        runs = _list_recent_runs()
        last_run_ptr = _read_last_run_pointer()
        ctx = {
            "page_title": "DSAR runbook",
            "runs": runs,
            "runs_count": len(runs),
            "last_run_pointer": last_run_ptr,
            "max_runs_displayed": _MAX_RUNS_DISPLAYED,
            "shell": kwargs.get("shell", "super"),
        }
        resp = render(request, self.template_name, ctx)
        # Conservative: never let a downstream cache pin this list.
        resp["Cache-Control"] = "no-store"
        return resp

    def post(self, request, *args, **kwargs):
        request_id = (request.POST.get("request_id") or "").strip()
        completed_at = (request.POST.get("completed_at") or "").strip()
        notes = request.POST.get("notes") or ""
        if not request_id or not completed_at:
            return HttpResponseBadRequest(
                "request_id and completed_at are both required"
            )
        try:
            from apps.migration_cloud.management.commands.dsar_runbook_record import (
                record_dsar_run,
            )
            record_dsar_run(
                request_id=request_id,
                completed_at=completed_at,
                notes=notes,
            )
        except ValueError as exc:
            return HttpResponseBadRequest(str(exc))
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                "migration_cloud.dsar_runbook.post_failed err_type=%s",
                type(exc).__name__,
            )
            return HttpResponseBadRequest(
                f"failed to record DSAR run: {type(exc).__name__}"
            )

        shell = kwargs.get("shell", "super")
        url_name = (
            "migration_cloud_super:migration_cloud_dsar_runbook"
            if shell == "super"
            else "migration_cloud_portal:migration_cloud_dsar_runbook"
        )
        try:
            return redirect(reverse(url_name))
        except Exception:
            return redirect(request.path)


__all__ = ["DSARRunbookView"]
