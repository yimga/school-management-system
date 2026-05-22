"""Tenant self-service offboarding (school admin / proprietor on tenant host)."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.compliance.models_audit import AuditLog
from apps.schools.control_plane import log_control_plane_action
from apps.schools.tenant_access import has_school_permission
from apps.schools.tenant_offboarding import (
    cancel_self_service_closure,
    get_offboarding_snapshot,
    get_self_service_snapshot,
    latest_export_zip_path,
    request_self_service_closure,
    run_wind_down_export,
)
from apps.siteconfig.control_plane_render import render_siteconfig_stem


def _parse_json(request) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _require_school_admin(request):
    school = getattr(request, "school", None)
    if school is None:
        return None, JsonResponse({"ok": False, "error": "No school context"}, status=403)
    if not has_school_permission(request.user, school, "admin"):
        return None, HttpResponseForbidden(
            "School administrator permission required for offboarding."
        )
    return school, None


@login_required
@require_http_methods(["GET"])
def tenant_offboarding_page(request):
    school, err = _require_school_admin(request)
    if err is not None:
        return err
    snapshot = get_offboarding_snapshot(school)
    self_svc = get_self_service_snapshot(school)
    export_path = latest_export_zip_path(school)
    return render_siteconfig_stem(
        request,
        "tenant_self_offboarding",
        {
            "school": school,
            "offboarding": snapshot,
            "self_service": self_svc,
            "has_export": bool(export_path),
        },
        page_title="Close school account",
    )


@login_required
@require_http_methods(["GET"])
def api_tenant_offboarding_snapshot(request):
    school, err = _require_school_admin(request)
    if err is not None:
        return err
    return JsonResponse(
        {
            "ok": True,
            "offboarding": get_offboarding_snapshot(school),
            "self_service": get_self_service_snapshot(school),
        }
    )


@login_required
@require_http_methods(["POST"])
def api_tenant_offboarding_request_closure(request):
    school, err = _require_school_admin(request)
    if err is not None:
        return err
    body = _parse_json(request)
    try:
        result = request_self_service_closure(
            school,
            actor=request.user,
            acknowledge=bool(body.get("acknowledge")),
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    log_control_plane_action(
        request,
        AuditLog.Action.UPDATE,
        "School",
        str(school.id),
        object_repr=school.name,
        reason="Tenant self-service closure requested",
        sensitivity=AuditLog.Sensitivity.CRITICAL,
        new_values=result,
    )
    return JsonResponse({"ok": True, **result})


@login_required
@require_http_methods(["POST"])
def api_tenant_offboarding_cancel(request):
    school, err = _require_school_admin(request)
    if err is not None:
        return err
    try:
        result = cancel_self_service_closure(school, actor=request.user)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse({"ok": True, **result})


@login_required
@require_http_methods(["POST"])
def api_tenant_offboarding_export(request):
    school, err = _require_school_admin(request)
    if err is not None:
        return err
    try:
        result = run_wind_down_export(school, full=True, actor=request.user)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)
    log_control_plane_action(
        request,
        AuditLog.Action.EXPORT,
        "School",
        str(school.id),
        object_repr=school.name,
        reason="Tenant self-service portability export",
        sensitivity=AuditLog.Sensitivity.HIGH,
        new_values={"export_zip": result.export_zip_path},
    )
    return JsonResponse(
        {
            "ok": True,
            "export_zip_path": result.export_zip_path,
            "student_export_count": result.student_export_count,
        }
    )


@login_required
@require_http_methods(["GET"])
def api_tenant_offboarding_export_download(request):
    school, err = _require_school_admin(request)
    if err is not None:
        return err
    path = latest_export_zip_path(school)
    if not path:
        return JsonResponse({"ok": False, "error": "No export available"}, status=404)
    return FileResponse(
        open(path, "rb"),
        as_attachment=True,
        filename=f"{school.slug}-portability-export.zip",
    )
