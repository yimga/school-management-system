"""v4.00.53 — LMS push-grade audit operator UI (Wedge 2).

Surfaces the v4.00.52 ``LMSPushGradeAudit`` append-only rows to staff:

  * ``GET /portal/super/integrations/lms/audit/`` — index, filterable by
    ``?provider=<slug>``, ``?ok=1|0``, ``?school=<id>``, ``?since=<iso>``.
  * ``GET /portal/super/integrations/lms/audit/?format=json`` — JSON
    rendering of the same filtered slice (operator API).

The view is staff-only and read-only. The model itself is append-only —
no UPDATE/DELETE surfaces are exposed.

v4.00.56 — Adds retention-export download UI:

  * ``GET /portal/super/integrations/lms/audit/exports/`` — lists the
    JSONL snapshots written by ``sweep_lms_audit_retention(export_dir=...)``
    so an operator can grab the forensic record of a purge.
  * ``GET /portal/super/integrations/lms/audit/exports/<filename>/`` —
    streams a single export with ``Content-Disposition: attachment``.

Both endpoints refuse to operate when ``RMC_LMS_AUDIT_RETENTION_EXPORT_DIR``
is unset — there's no implicit default directory (the retention sweep is
opt-in). Filename validation rejects path traversal AND any name that
doesn't match the ``lms_audit_purge_*.jsonl`` pattern emitted by the
sweep, so the endpoint cannot be coerced into serving unrelated files.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

_PAGE_CAP = 500


def _parse_since(raw: str):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# v4.00.55 — rotation rows are tagged with course_id="_rotation" by the
# token-rotation sweep (apps.integrations_marketplace.lms_token_rotation).
# The operator UI exposes 4-valued filtering: all / rotation-only / push-
# only / none. Default is "all" so the existing surface is unchanged.
_ROTATION_COURSE_ID_MARKER = "_rotation"


@staff_member_required
@require_http_methods(["GET"])
def lms_audit_index(request: HttpRequest):
    from apps.integrations_marketplace.models import LMSPushGradeAudit

    qs = LMSPushGradeAudit.objects.all().order_by("-created_at")  # tenant-isolation-allow: operator-audit-platform-scope-staff-required
    provider = (request.GET.get("provider") or "").strip()
    ok_raw = (request.GET.get("ok") or "").strip()
    school = (request.GET.get("school") or "").strip()
    since_raw = (request.GET.get("since") or "").strip()
    rotation_raw = (request.GET.get("rotation") or "").strip().lower()

    if provider:
        qs = qs.filter(provider=provider)
    if ok_raw in ("1", "true"):
        qs = qs.filter(ok=True)
    elif ok_raw in ("0", "false"):
        qs = qs.filter(ok=False)
    if school:
        qs = qs.filter(school_id=school)
    since_dt = _parse_since(since_raw)
    if since_dt is not None:
        qs = qs.filter(created_at__gte=since_dt)

    if rotation_raw in ("1", "true", "only"):
        qs = qs.filter(course_id=_ROTATION_COURSE_ID_MARKER)
    elif rotation_raw in ("0", "false", "exclude"):
        qs = qs.exclude(course_id=_ROTATION_COURSE_ID_MARKER)

    rows = list(qs[:_PAGE_CAP])
    rotation_count = sum(1 for r in rows if r.course_id == _ROTATION_COURSE_ID_MARKER)
    push_count = len(rows) - rotation_count
    totals = {
        "count": len(rows),
        "ok": sum(1 for r in rows if r.ok),
        "failed": sum(1 for r in rows if not r.ok),
        "rotation": rotation_count,
        "push": push_count,
    }

    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": True,
            "rows": [
                {
                    "id": r.pk,
                    "school_id": str(r.school_id) if r.school_id else "",
                    "provider": r.provider,
                    "course_id": r.course_id,
                    "assignment_id": r.assignment_id,
                    "user_hash": r.user_hash,
                    "score_text": r.score_text,
                    "ok": r.ok,
                    "status_code": r.status_code,
                    "detail": r.detail,
                    "actor_user_id": r.actor_user_id,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                    "is_rotation": r.course_id == _ROTATION_COURSE_ID_MARKER,
                }
                for r in rows
            ],
            "totals": totals,
            "filter": {
                "provider": provider,
                "ok": ok_raw,
                "school": school,
                "since": since_raw,
                "rotation": rotation_raw,
            },
        })

    return render(request, "super/integrations/lms_audit_index.html", {
        "rows": rows,
        "totals": totals,
        "filter_provider": provider,
        "filter_ok": ok_raw,
        "filter_school": school,
        "filter_since": since_raw,
        "filter_rotation": rotation_raw,
        "rotation_marker": _ROTATION_COURSE_ID_MARKER,
        "export_dir_configured": bool((os.environ.get("RMC_LMS_AUDIT_RETENTION_EXPORT_DIR") or "").strip()),
    })


# ---------------------------------------------------------------------------
# v4.00.56 — Retention-export download UI.
#
# Filename pattern from ``lms_audit_retention._write_export``:
#   ``lms_audit_purge_<cutoff_iso_safe>.jsonl``
# where the iso ts is sanitized (colons → ``-``, ``+`` → ``p``). We pin the
# whitelist regex tightly so no traversal / unrelated file can be served.
# ---------------------------------------------------------------------------

_EXPORT_FILENAME_RE = re.compile(r"^lms_audit_purge_[A-Za-z0-9_\-:.]+\.jsonl$")
_EXPORT_LIST_CAP = 1000


def _resolve_export_dir() -> Path | None:
    raw = (os.environ.get("RMC_LMS_AUDIT_RETENTION_EXPORT_DIR") or "").strip()
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve()
    except OSError:
        return None


def _validate_export_filename(name: str) -> bool:
    """Return True iff ``name`` is a plain filename matching the sweep output."""
    if not name or name != os.path.basename(name):
        return False
    if ".." in name or "/" in name or "\\" in name:
        return False
    return bool(_EXPORT_FILENAME_RE.match(name))


@staff_member_required
@require_http_methods(["GET"])
def lms_audit_export_index(request: HttpRequest):
    """v4.00.56 — List operator-visible retention-export JSONL files."""
    export_dir = _resolve_export_dir()

    files: list[dict] = []
    error_reason = ""
    if export_dir is None:
        error_reason = "export_dir_not_configured"
    elif not export_dir.exists():
        error_reason = "export_dir_missing"
    elif not export_dir.is_dir():
        error_reason = "export_dir_not_a_directory"
    else:
        try:
            for entry in sorted(export_dir.iterdir(), reverse=True)[:_EXPORT_LIST_CAP]:
                name = entry.name
                if not entry.is_file() or not _validate_export_filename(name):
                    continue
                try:
                    st = entry.stat()
                except OSError:
                    continue
                files.append({
                    "name": name,
                    "size_bytes": int(st.st_size),
                    "modified_iso": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                })
        except OSError as exc:
            error_reason = f"listing_failed: {exc}"

    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": not error_reason,
            "export_dir": str(export_dir) if export_dir else "",
            "files": files,
            "count": len(files),
            "error": error_reason,
        })

    return render(request, "super/integrations/lms_audit_exports.html", {
        "files": files,
        "export_dir": str(export_dir) if export_dir else "",
        "error_reason": error_reason,
    })


@staff_member_required
@require_http_methods(["GET"])
def lms_audit_export_download(request: HttpRequest, filename: str):
    """v4.00.56 — Stream a single export JSONL with Content-Disposition."""
    if not _validate_export_filename(filename):
        return JsonResponse({"error": "bad_filename"}, status=400)

    export_dir = _resolve_export_dir()
    if export_dir is None:
        return JsonResponse({"error": "export_dir_not_configured"}, status=404)
    if not export_dir.exists() or not export_dir.is_dir():
        return JsonResponse({"error": "export_dir_missing"}, status=404)

    target = (export_dir / filename).resolve()
    # Defense in depth: target MUST live inside export_dir after resolution
    # (covers symlink shenanigans on POSIX).
    try:
        target.relative_to(export_dir)
    except ValueError:
        return JsonResponse({"error": "path_traversal_refused"}, status=400)

    if not target.exists() or not target.is_file():
        return JsonResponse({"error": "not_found", "filename": filename}, status=404)

    try:
        fh = open(target, "rb")
    except OSError as exc:
        logger.warning("lms_audit_export_download: open failed %s: %s", filename, exc)
        return JsonResponse({"error": "open_failed"}, status=500)

    resp = FileResponse(fh, content_type="application/x-ndjson")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp["X-Audit-Export"] = "lms-retention-purge"
    return resp
