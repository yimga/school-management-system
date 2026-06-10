"""
Per-school JSON and lifecycle APIs for the control plane (BR-12 extraction from super_views).
"""

from __future__ import annotations

import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .control_plane_lifecycle import apply_school_lifecycle_action
from .models import School, SchoolProvisioningEvent
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_FLEET,
    PLATFORM_SCOPE_PROVISION,
    PLATFORM_SCOPE_SECURITY_READ,
    PLATFORM_SCOPE_SECURITY_WRITE,
    PLATFORM_SCOPE_TENANT_READ,
    require_platform_scope,
)


def _clamp_int(value, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


@require_http_methods(["GET"])
@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def api_school_lens_snapshot(request, school_id):
    """Lightweight health + provisioning train for operator copilot Lens."""
    from apps.schools.operator_school_lens import build_operator_lens_snapshot

    school = get_object_or_404(School, id=school_id)
    return JsonResponse(build_operator_lens_snapshot(school))


@require_http_methods(["POST"])
@require_platform_scope(PLATFORM_SCOPE_PROVISION)
def api_school_requeue_provision(request, school_id):
    """Operator requeue for stuck / inactive tenant provisioning."""
    from apps.compliance.models_audit import AuditLog
    from apps.schools.control_plane import log_control_plane_action
    from apps.schools.operator_school_lens import (
        build_operator_lens_snapshot,
        operator_requeue_provisioning,
    )

    school = get_object_or_404(School, id=school_id)
    try:
        outcome = operator_requeue_provisioning(school, actor=request.user)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    log_control_plane_action(
        request,
        AuditLog.Action.UPDATE,
        "School",
        str(school.id),
        object_repr=getattr(school, "name", "") or str(school.id),
        reason="Operator requeued tenant provisioning",
        sensitivity=AuditLog.Sensitivity.HIGH,
    )
    snapshot = build_operator_lens_snapshot(school)
    return JsonResponse({**outcome, "lens": snapshot})


@require_http_methods(["GET"])
@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def api_school_timeline(request, school_id):
    school = get_object_or_404(School, id=school_id)
    limit = _clamp_int(request.GET.get("limit"), 80, minimum=1, maximum=500)
    events = list(
        SchoolProvisioningEvent.objects.filter(school=school)
        .order_by("-created_at", "-id")
        .values("event_type", "status", "message", "payload", "created_at")[:limit]
    )
    for event in events:
        created_at = event.get("created_at")
        event["created_at"] = created_at.isoformat() if created_at else ""
    return JsonResponse(
        {
            "school_id": str(school.id),
            "school_name": school.name,
            "events": events,
        }
    )


@require_http_methods(["POST"])
@require_platform_scope(PLATFORM_SCOPE_PROVISION)
def api_approve_school(request, school_id):
    """Phase H optional: Set school is_approved=True. Super Admin only."""
    from apps.compliance.models_audit import AuditLog
    from apps.schools.control_plane import log_control_plane_action

    school = get_object_or_404(School, id=school_id)
    outcome = apply_school_lifecycle_action(school, action="approve")
    log_control_plane_action(
        request,
        AuditLog.Action.APPROVE,
        "School",
        str(school.id),
        object_repr=getattr(school, "name", "") or str(school.id),
        reason="School approved",
        sensitivity=AuditLog.Sensitivity.HIGH,
        old_values=outcome["old_values"],
        new_values=outcome["new_values"],
        changed_fields=outcome["changed_fields"],
    )
    return JsonResponse(
        {"ok": True, "school_id": str(school.id), "message": outcome["message"]}
    )


@require_http_methods(["POST"])
@require_platform_scope(PLATFORM_SCOPE_FLEET)
def school_lifecycle_action(request, school_id):
    from apps.compliance.models_audit import AuditLog
    from apps.schools.control_plane import log_control_plane_action

    school = get_object_or_404(School, id=school_id)
    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}

    action = str(payload.get("action") or request.POST.get("action") or "").strip()
    reason = str(payload.get("reason") or request.POST.get("reason") or "").strip()
    trial_end_date = payload.get("trial_end_date") or request.POST.get("trial_end_date")
    next_url = str(
        request.POST.get("next") or reverse("super:tenant_360", args=[school.id])
    ).strip()
    expects_json = str(request.content_type or "").startswith("application/json")

    try:
        outcome = apply_school_lifecycle_action(
            school,
            action=action,
            reason=reason,
            trial_end_date=trial_end_date,
        )
    except ValueError as exc:
        if expects_json:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        messages.error(request, str(exc))
        return redirect(next_url)

    audit_action = (
        AuditLog.Action.APPROVE
        if str(action).strip().lower() == "approve"
        else AuditLog.Action.UPDATE
    )
    log_control_plane_action(
        request,
        audit_action,
        "School",
        str(school.id),
        object_repr=getattr(school, "name", "") or str(school.id),
        reason=f"School lifecycle action: {action}",
        sensitivity=AuditLog.Sensitivity.HIGH,
        old_values=outcome["old_values"],
        new_values=outcome["new_values"],
        changed_fields=outcome["changed_fields"],
    )
    if expects_json:
        return JsonResponse({"ok": True, "school_id": str(school.id), **outcome})

    messages.success(request, outcome["message"])
    return redirect(next_url)


@require_http_methods(["GET"])
@require_platform_scope(PLATFORM_SCOPE_SECURITY_READ)
def api_school_policy_bundles(request, school_id):
    """List policy bundles for a school (for pack versioning rollback UI)."""
    from apps.policies.models import TenantBlueprint
    from apps.policies.rollback import list_policy_bundles_for_school

    school = get_object_or_404(School, id=school_id)
    bundles = list_policy_bundles_for_school(school)
    tb = (
        TenantBlueprint.objects.filter(school=school)
        .select_related("active_bundle")
        .first()
    )
    active_id = tb.active_bundle_id if tb else None
    items = [
        {
            "id": b.id,
            "version": b.version,
            "applied_pack_version": getattr(b, "applied_pack_version", "") or "",
            "code": getattr(b, "code", "") or "",
            "name": getattr(b, "name", "") or "",
            "created_at": b.created_at.isoformat()
            if hasattr(b.created_at, "isoformat")
            else str(b.created_at),
            "is_active": b.id == active_id,
        }
        for b in bundles[:50]
    ]
    return JsonResponse(
        {"school_id": str(school.id), "active_bundle_id": active_id, "bundles": items}
    )


@require_http_methods(["POST"])
@require_platform_scope(PLATFORM_SCOPE_SECURITY_WRITE)
def api_school_policy_bundle_activate(request, school_id, bundle_id):
    """Set the active policy bundle for a school (rollback to previous version)."""
    from apps.policies.models import PolicyBundle
    from apps.policies.rollback import set_active_policy_bundle

    school = get_object_or_404(School, id=school_id)
    bundle = get_object_or_404(PolicyBundle, id=bundle_id, school=school)
    ok = set_active_policy_bundle(school, bundle)
    if not ok:
        return JsonResponse(
            {"ok": False, "error": "Could not set active bundle"}, status=400
        )
    return JsonResponse(
        {
            "ok": True,
            "school_id": str(school.id),
            "active_bundle_id": bundle.id,
            "message": "Active policy bundle updated.",
        }
    )
