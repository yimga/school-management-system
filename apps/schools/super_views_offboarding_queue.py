"""Operator offboarding queue and export download (control plane)."""

from __future__ import annotations

from datetime import date

from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from apps.schools.models import School
from apps.schools.tenant_offboarding import (
    get_offboarding_snapshot,
    latest_export_zip_path,
    operator_schedule_purge,
    run_scheduled_purges,
    schools_scheduled_for_purge,
)
from apps.schools.tenant_offboarding_policy import auto_purge_enabled, auto_purge_grace_days


@require_GET
def super_offboarding_queue(request):
    rows: list[dict] = []
    for school in School.objects.all().order_by("name")[:500]:
        off = (getattr(school, "settings", None) or {}).get("offboarding") or {}
        if not isinstance(off, dict):
            continue
        status = off.get("self_service_status") or ""
        if not status and not off.get("scheduled_purge_at"):
            continue
        snap = get_offboarding_snapshot(school)
        rows.append(
            {
                "school": school,
                "status": status or "—",
                "scheduled_purge_at": off.get("scheduled_purge_at"),
                "row_total": snap.get("row_total", 0),
                "legal_hold": snap.get("legal_hold_active"),
                "tenant_360_url": reverse("super:tenant_360", args=[school.id])
                + "#offboarding",
            }
        )
    due_today = schools_scheduled_for_purge(on_or_before=date.today())
    return render(
        request,
        "schools/super_offboarding_queue.html",
        {
            "rows": rows,
            "due_count": len(due_today),
            "auto_purge_enabled": auto_purge_enabled(),
            "grace_days": auto_purge_grace_days(),
            "dashboard_url": reverse("super:dashboard"),
        },
    )


@require_http_methods(["POST"])
def api_super_run_scheduled_purges(request):
    import json

    body = {}
    if request.body:
        try:
            body = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError, json.JSONDecodeError):
            body = {}
    dry_run = body.get("dry_run", True)
    if isinstance(dry_run, str):
        dry_run = dry_run.lower() in ("1", "true", "yes")
    result = run_scheduled_purges(
        actor=request.user,
        dry_run=bool(dry_run),
        limit=int(body.get("limit") or 10),
    )
    return JsonResponse(result)


@require_http_methods(["POST"])
def api_school_offboarding_schedule(request, school_id):
    import json

    school = get_object_or_404(School, id=school_id)
    body = {}
    if request.body:
        try:
            body = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError, json.JSONDecodeError):
            body = {}
    purge_at = str(body.get("scheduled_purge_at") or "").strip()
    if not purge_at:
        return JsonResponse({"ok": False, "error": "scheduled_purge_at required"}, status=400)
    state = operator_schedule_purge(school, purge_at=purge_at, actor=request.user)
    return JsonResponse({"ok": True, **state})


@require_GET
def api_school_offboarding_export_download(request, school_id):
    school = get_object_or_404(School, id=school_id)
    path = latest_export_zip_path(school)
    if not path:
        raise Http404("No export file")
    return FileResponse(
        open(path, "rb"),
        as_attachment=True,
        filename=f"{school.slug}-portability-export.zip",
    )
