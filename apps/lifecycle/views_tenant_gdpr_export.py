"""Tenant GDPR portability export (export-only — no school closure). CEZGP Lane 2 P8b."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.schools.tenant_offboarding import latest_export_zip_path, run_wind_down_export


def _require_school_admin(request):
    try:
        from apps.lifecycle.tenant_school_resolve import (
            can_access_tenant_lifecycle,
            resolve_request_school,
        )

        school = resolve_request_school(request)
        if school is None:
            return None, render(
                request,
                "lifecycle/tenant_gdpr_data_export.html",
                {"error": "No tenant context resolved."},
                status=400,
            )
        if not can_access_tenant_lifecycle(request, school):
            return None, HttpResponseForbidden(
                "School administrator permission required for data export."
            )
        return school, None
    except ImportError:
        school = getattr(request, "school", None)
        if school is None:
            return None, render(
                request,
                "lifecycle/tenant_gdpr_data_export.html",
                {"error": "No tenant context resolved."},
                status=400,
            )
        from apps.schools.tenant_access import has_school_permission

        if not has_school_permission(request.user, school, "admin"):
            return None, HttpResponseForbidden(
                "School administrator permission required for data export."
            )
        return school, None


@login_required
@require_http_methods(["GET", "POST"])
def tenant_gdpr_data_export(request):
    """
    Self-service tenant portability pack (GDPR Art. 15 / 20) without initiating closure.
    """
    school, err = _require_school_admin(request)
    if err is not None:
        return err

    export_path = latest_export_zip_path(school)
    if request.method == "POST":
        action = (request.POST.get("action") or "generate").strip().lower()
        if action == "download":
            if not export_path:
                return render(
                    request,
                    "lifecycle/tenant_gdpr_data_export.html",
                    {
                        "school": school,
                        "has_export": False,
                        "error": "No export file yet — generate one first.",
                    },
                    status=404,
                )
            return FileResponse(
                open(export_path, "rb"),
                as_attachment=True,
                filename=f"{school.slug}-gdpr-portability.zip",
            )
        try:
            result = run_wind_down_export(school, full=True, actor=request.user)
        except Exception as exc:
            return render(
                request,
                "lifecycle/tenant_gdpr_data_export.html",
                {
                    "school": school,
                    "has_export": bool(export_path),
                    "error": str(exc),
                },
                status=500,
            )
        export_path = result.export_zip_path
        return render(
            request,
            "lifecycle/tenant_gdpr_data_export.html",
            {
                "school": school,
                "has_export": True,
                "export_zip_path": export_path,
                "student_export_count": result.student_export_count,
                "success": True,
            },
        )

    dsar_close_url = ""
    try:
        from django.urls import reverse

        dsar_close_url = reverse("lifecycle_dsar_export_and_close")
    except Exception:
        pass

    return render(
        request,
        "lifecycle/tenant_gdpr_data_export.html",
        {
            "school": school,
            "has_export": bool(export_path),
            "export_zip_path": export_path or "",
            "dsar_close_url": dsar_close_url,
            "data_rmc_offline_form": True,
        },
    )


@login_required
@require_http_methods(["GET"])
def api_tenant_gdpr_export_status(request):
    school, err = _require_school_admin(request)
    if err is not None:
        if isinstance(err, JsonResponse):
            return err
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    path = latest_export_zip_path(school)
    return JsonResponse({"ok": True, "has_export": bool(path)})
