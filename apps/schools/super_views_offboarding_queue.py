"""Operator offboarding queue and export download (control plane)."""

from __future__ import annotations

from datetime import date, timedelta

from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.schools.control_plane_pagination import paginate_for_request
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from apps.schools.models import School, SchoolProvisioningEvent
from apps.schools.tenant_offboarding import (
    get_offboarding_snapshot,
    latest_export_zip_path,
    operator_schedule_purge,
    run_scheduled_purges,
    schools_scheduled_for_purge,
)
from apps.schools.tenant_offboarding_policy import (
    auto_purge_enabled,
    auto_purge_grace_days,
    operator_only_offboarding,
    self_service_enabled,
)
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_AUDIT_EXPORT,
    PLATFORM_SCOPE_FLEET,
    PLATFORM_SCOPE_SECURITY_WRITE,
    require_platform_scope,
)
from apps.platform_runtime.workflow_tracker import track_workflow, workflow_step


@require_GET
@require_platform_scope(PLATFORM_SCOPE_FLEET)
def super_offboarding_queue(request):
    # Wave L6 (v3.61.6 — 2026-05-22): billing-clearance enrichment per row
    # so operators see outstanding-balance blockers before initiating purge.
    try:
        from apps.lifecycle.billing_gate import check_billing_clearance  # tenant-isolation-allow: operator-super-offboarding-billing-gate-import
    except Exception:  # noqa: BLE001
        check_billing_clearance = None  # type: ignore[assignment]

    rows: list[dict] = []
    not_cleared_count = 0
    for school in School.objects.all().order_by("name")[:500]:  # tenant-isolation-allow: operator-super-offboarding-queue-cross-tenant
        off = (getattr(school, "settings", None) or {}).get("offboarding") or {}
        if not isinstance(off, dict):
            continue
        status = off.get("self_service_status") or ""
        if not status and not off.get("scheduled_purge_at"):
            continue
        snap = get_offboarding_snapshot(school)
        clearance_state = "unknown"
        clearance_reason = ""
        if check_billing_clearance is not None:
            try:
                clearance = check_billing_clearance(school)
                clearance_state = clearance.state
                clearance_reason = clearance.reason
                if clearance.state == "outstanding":
                    not_cleared_count += 1
            except Exception:  # noqa: BLE001
                pass
        rows.append(
            {
                "school": school,
                "status": status or "—",
                "scheduled_purge_at": off.get("scheduled_purge_at"),
                "row_total": snap.get("row_total", 0),
                "legal_hold": snap.get("legal_hold_active"),
                "billing_state": clearance_state,
                "billing_reason": clearance_reason,
                "tenant_360_url": reverse("super:tenant_360", args=[school.id])
                + "#offboarding",
            }
        )
    due_today = schools_scheduled_for_purge(on_or_before=date.today())
    due_slugs = {s.slug for s in due_today}
    for row in rows:
        row["purge_due"] = row["school"].slug in due_slugs

    # v4.00.3 audit: surface SchoolProvisioningEvent.FAILED rows from the
    # last 7 days as a dashboard signal. The v4.00.2 wave started
    # recording these (verify_signup dispatch failures + data-residency
    # failures); without surfacing them on the offboarding queue, the
    # only path to seeing them is opening each tenant 360 individually.
    cutoff = timezone.now() - timedelta(days=7)
    recent_failed_qs = (
        SchoolProvisioningEvent.objects.filter(  # tenant-isolation-allow: operator-super-offboarding-failed-events-cross-tenant
            event_type=SchoolProvisioningEvent.EventType.FAILED,
            created_at__gte=cutoff,
        )
        .select_related("school")
        .order_by("-created_at")
    )
    seen: set = set()
    provisioning_failure_rows: list[dict] = []
    for ev in recent_failed_qs[:200]:
        if ev.school_id in seen:
            continue
        seen.add(ev.school_id)
        provisioning_failure_rows.append(
            {
                "school": ev.school,
                "phase": (ev.payload or {}).get("phase") or "—",
                "error_type": (ev.payload or {}).get("error_type") or "—",
                "message": ev.message or "",
                "created_at": ev.created_at,
                "tenant_360_url": reverse("super:tenant_360", args=[ev.school_id])
                + "#timeline",
            }
        )
        if len(provisioning_failure_rows) >= 25:
            break

    page_obj = paginate_for_request(request, rows, per_page=25)
    return render(
        request,
        "schools/super_offboarding_queue.html",
        {
            "rows": page_obj.object_list,
            "page_obj": page_obj,
            "due_count": len(due_today),
            "auto_purge_enabled": auto_purge_enabled(),
            "self_service_enabled": self_service_enabled(),
            "operator_only": operator_only_offboarding(),
            "grace_days": auto_purge_grace_days(),
            "dashboard_url": reverse("super:dashboard"),
            "billing_outstanding_count": not_cleared_count,
            "due_schools": due_today[:25],
            "provisioning_failure_count": len(seen),
            "provisioning_failure_rows": provisioning_failure_rows,
        },
    )


@require_http_methods(["POST"])
@require_platform_scope(PLATFORM_SCOPE_SECURITY_WRITE)
@track_workflow(
    "tenant_school_offboard_purge",
    steps=("scan", "purge", "notify"),
    expected_duration_seconds=120,
    email_on_failure=True,
)
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
    force_operator = body.get("force_operator", False)
    if isinstance(force_operator, str):
        force_operator = force_operator.lower() in ("1", "true", "yes")
    if force_operator and not dry_run:
        confirm = str(body.get("confirm") or "").strip().lower()
        if confirm != "purge-due-tenants":
            return JsonResponse(
                {
                    "ok": False,
                    "error": "confirm_required",
                    "detail": 'POST with confirm="purge-due-tenants" to apply when auto-purge is disabled.',
                },
                status=400,
            )
    from apps.platform_runtime.workflow_tracker import active_workflow_run

    run = active_workflow_run() or getattr(request, "_rmc_workflow_run", None)
    with workflow_step(run, "scan", payload={"dry_run": bool(dry_run)}):
        pass
    with workflow_step(run, "purge"):
        result = run_scheduled_purges(
            actor=request.user,
            dry_run=bool(dry_run),
            limit=int(body.get("limit") or 10),
            force_operator=bool(force_operator),
        )
    with workflow_step(run, "notify", payload={"processed": len(result.get("processed") or [])}):
        pass
    return JsonResponse(result)


@require_http_methods(["POST"])
@require_platform_scope(PLATFORM_SCOPE_FLEET)
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
@require_platform_scope(PLATFORM_SCOPE_AUDIT_EXPORT)
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
