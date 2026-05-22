"""Tenant offboarding JSON API (manager control plane)."""

from __future__ import annotations

import json
from dataclasses import asdict

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from apps.compliance.models_audit import AuditLog
from apps.schools.control_plane import log_control_plane_action
from apps.schools.models import School
from apps.schools.tenant_offboarding import (
    apply_purge,
    dry_run_purge,
    get_offboarding_snapshot,
    record_dual_approval,
    record_primary_dual_approval,
    run_wind_down_deactivate,
    run_wind_down_export,
    set_legal_hold,
)


def _parse_json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _json_error(message: str, *, status: int = 400, code: str = "error") -> JsonResponse:
    return JsonResponse({"ok": False, "error": message, "code": code}, status=status)


@require_http_methods(["GET"])
def api_school_offboarding(request, school_id):
    school = get_object_or_404(School, id=school_id)
    return JsonResponse({"ok": True, **get_offboarding_snapshot(school)})


@require_http_methods(["POST"])
def api_school_offboarding_export(request, school_id):
    school = get_object_or_404(School, id=school_id)
    body = _parse_json_body(request)
    full = body.get("full", True)
    if isinstance(full, str):
        full = full.lower() not in ("0", "false", "no")
    try:
        result = run_wind_down_export(school, full=bool(full), actor=request.user)
    except Exception as exc:
        return _json_error(str(exc), status=500)

    log_control_plane_action(
        request,
        AuditLog.Action.EXPORT,
        "School",
        str(school.id),
        object_repr=school.name,
        reason="Tenant offboarding portability export",
        sensitivity=AuditLog.Sensitivity.CRITICAL,
        new_values={
            "export_zip": result.export_zip_path,
            "student_count": result.student_export_count,
        },
    )
    return JsonResponse(
        {
            "ok": True,
            "archive_dir": result.archive_dir,
            "export_zip_path": result.export_zip_path,
            "student_export_count": result.student_export_count,
            "manifest_path": result.manifest_path,
        }
    )


@require_http_methods(["POST"])
def api_school_offboarding_deactivate(request, school_id):
    school = get_object_or_404(School, id=school_id)
    try:
        outcome = run_wind_down_deactivate(school, actor=request.user)
    except ValueError as exc:
        return _json_error(str(exc))

    log_control_plane_action(
        request,
        AuditLog.Action.UPDATE,
        "School",
        str(school.id),
        object_repr=school.name,
        reason="Tenant offboarding deactivate",
        sensitivity=AuditLog.Sensitivity.HIGH,
        old_values=outcome.get("old_values"),
        new_values=outcome.get("new_values"),
        changed_fields=outcome.get("changed_fields"),
    )
    return JsonResponse({"ok": True, **outcome})


@require_http_methods(["POST"])
def api_school_offboarding_hold(request, school_id):
    school = get_object_or_404(School, id=school_id)
    body = _parse_json_body(request)
    hold_until = body.get("hold_until")
    if hold_until is not None:
        hold_until = str(hold_until).strip() or None
    state = set_legal_hold(school, hold_until=hold_until, actor=request.user)
    log_control_plane_action(
        request,
        AuditLog.Action.UPDATE,
        "School",
        str(school.id),
        object_repr=school.name,
        reason="Tenant offboarding legal hold",
        sensitivity=AuditLog.Sensitivity.HIGH,
        new_values=state,
    )
    return JsonResponse({"ok": True, **state})


@require_http_methods(["POST"])
def api_school_offboarding_purge(request, school_id):
    school = get_object_or_404(School, id=school_id)
    body = _parse_json_body(request)
    confirm_slug = str(body.get("confirm_slug") or "").strip()
    dry_run = body.get("dry_run", True)
    if isinstance(dry_run, str):
        dry_run = dry_run.lower() in ("1", "true", "yes")
    force_provisioning = body.get("force_provisioning", False)
    if isinstance(force_provisioning, str):
        force_provisioning = force_provisioning.lower() in ("1", "true", "yes")
    dual_approved = body.get("dual_approved", False)
    if isinstance(dual_approved, str):
        dual_approved = dual_approved.lower() in ("1", "true", "yes")

    if not confirm_slug:
        return _json_error("confirm_slug is required", code="confirm_slug_required")

    if dry_run:
        preview = dry_run_purge(
            school,
            confirm_slug=confirm_slug,
            force_provisioning=force_provisioning,
            dual_approved=dual_approved,
        )
        log_control_plane_action(
            request,
            AuditLog.Action.VIEW,
            "School",
            str(school.id),
            object_repr=school.name,
            reason="Tenant offboarding purge dry-run",
            sensitivity=AuditLog.Sensitivity.HIGH,
            new_values={"row_total": preview.row_total},
        )
        return JsonResponse({"ok": True, "dry_run": True, "preview": asdict(preview)})

    if dual_approved:
        try:
            record_dual_approval(school, actor=request.user)
        except ValueError as exc:
            return _json_error(str(exc), code="dual_approval_failed")

    try:
        receipt = apply_purge(
            school,
            actor=request.user,
            confirm_slug=confirm_slug,
            dry_run=False,
            force_provisioning=force_provisioning,
            dual_approved=dual_approved,
        )
    except ValueError as exc:
        return _json_error(str(exc), code="purge_blocked")

    log_control_plane_action(
        request,
        AuditLog.Action.DELETE,
        "School",
        receipt.school_id,
        object_repr=receipt.school_slug,
        reason="Tenant offboarding permanent purge",
        sensitivity=AuditLog.Sensitivity.CRITICAL,
        old_values={"slug": receipt.school_slug, "row_total": receipt.row_total},
        new_values=asdict(receipt),
    )
    return JsonResponse({"ok": True, "dry_run": False, "receipt": asdict(receipt)})


@require_http_methods(["POST"])
def api_school_offboarding_dual_approve(request, school_id):
    school = get_object_or_404(School, id=school_id)
    body = _parse_json_body(request)
    step = str(body.get("step") or "second").strip().lower()
    try:
        if step == "primary":
            result = record_primary_dual_approval(school, actor=request.user)
        else:
            result = record_dual_approval(school, actor=request.user)
    except ValueError as exc:
        return _json_error(str(exc), code="dual_approval_failed")
    log_control_plane_action(
        request,
        AuditLog.Action.UPDATE,
        "School",
        str(school.id),
        object_repr=school.name,
        reason=f"Tenant offboarding dual approval ({step})",
        sensitivity=AuditLog.Sensitivity.CRITICAL,
        new_values=result,
    )
    return JsonResponse({"ok": True, **result, **get_offboarding_snapshot(school)})
