"""Tenant self-service offboarding (school admin / proprietor on tenant host)."""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.compliance.models_audit import AuditLog
from apps.schools.control_plane import log_control_plane_action
from apps.accounts.effective_access import school_permission_access
from apps.schools.tenant_offboarding import (
    cancel_self_service_closure,
    get_offboarding_snapshot,
    get_self_service_snapshot,
    latest_export_zip_path,
    request_tenant_offboarding,
    run_wind_down_export,
)
from apps.siteconfig.control_plane_render import render_siteconfig_stem

logger = logging.getLogger(__name__)


def _parse_json(request) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _require_school_admin(request):
    try:
        from apps.lifecycle.tenant_school_resolve import (
            can_access_tenant_lifecycle,
            resolve_request_school,
        )

        school = resolve_request_school(request)
        if school is None:
            return None, JsonResponse({"ok": False, "error": "No school context"}, status=403)
        if not can_access_tenant_lifecycle(request, school):
            return None, HttpResponseForbidden(
                "School administrator permission required for offboarding."
            )
        return school, None
    except ImportError:
        school = getattr(request, "school", None)
        if school is None:
            return None, JsonResponse({"ok": False, "error": "No school context"}, status=403)
        if not school_permission_access(request.user, school, "admin"):
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
    offboarding_playbook_api_url = ""
    try:
        from django.urls import reverse

        offboarding_playbook_api_url = reverse("api:ai-offboarding-playbook")
    except Exception:
        pass
    return render_siteconfig_stem(
        request,
        "tenant_self_offboarding",
        {
            "school": school,
            "offboarding": snapshot,
            "self_service": self_svc,
            "has_export": bool(export_path),
            "offboarding_playbook_api_url": offboarding_playbook_api_url,
        },
        cp_title="Close school account",
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
        result = request_tenant_offboarding(
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
        reason="Tenant offboarding request submitted",
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
    except Exception:
        logger.exception(
            "tenant offboarding export failed school_id=%s",
            getattr(school, "pk", None),
        )
        return JsonResponse(
            {
                "ok": False,
                "error": "export_failed",
                "message": "Portability export could not be generated. Try again or contact support.",
            },
            status=500,
        )
    log_control_plane_action(
        request,
        AuditLog.Action.EXPORT,
        "School",
        str(school.id),
        object_repr=school.name,
        reason="Tenant self-service portability export",
        sensitivity=AuditLog.Sensitivity.HIGH,
        new_values={"student_export_count": result.student_export_count},
    )
    try:
        from django.urls import reverse

        download_url = reverse("tenant_offboarding_export_download")
    except Exception:
        download_url = ""
    return JsonResponse(
        {
            "ok": True,
            "student_export_count": result.student_export_count,
            "download_url": download_url,
            "ready": bool(latest_export_zip_path(school)),
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
    try:
        export_file = open(path, "rb")
    except OSError:
        logger.warning(
            "tenant offboarding export missing on disk school_id=%s",
            getattr(school, "pk", None),
        )
        return JsonResponse(
            {
                "ok": False,
                "error": "export_stale",
                "message": "Export file is no longer available. Generate a new export.",
            },
            status=410,
        )
    return FileResponse(
        export_file,
        as_attachment=True,
        filename=f"{school.slug}-portability-export.zip",
    )
