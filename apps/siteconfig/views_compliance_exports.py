"""North Star SLICE 5 — compliance export operator UI and downloads (CSV only)."""

from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse

from apps.accounts.decorators import permission_required

from apps.accounts.security_audit import log_security_event
from apps.accounts.models import SecurityAuditLog
from apps.reports import compliance_exports as cx
from apps.reports.export_integrity import attach_export_integrity_headers
from apps.schools.security_enforcer import enforce_tenant_security


def _audit_export_download(request: HttpRequest, export_key: str, academic_year_id: int | None):
    """Best-effort audit trail for compliance CSV download."""
    school = getattr(request, "school", None)
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            action=AuditLog.Action.EXPORT,
            user=request.user if request.user.is_authenticated else None,
            model_name="ComplianceExport",
            object_id=str(
                f"{export_key}:{getattr(school, 'pk', '')}:{academic_year_id or ''}"
            )[:200],
            object_repr=f"compliance export {export_key}",
            app_label="reports",
            new_values={
                "export_key": export_key,
                "school_id": str(getattr(school, "pk", "") or ""),
                "academic_year_id": academic_year_id,
            },
        )
    except Exception:
        pass


@login_required
@permission_required("settings.manage", raise_exception=True)
@enforce_tenant_security(action="export", require_school=False)
def compliance_exports_view(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    if not school:
        messages.warning(
            request,
            "Open this page from your school subdomain to use compliance exports.",
        )
        return redirect("siteconfig:user_preferences")

    params: dict = {}
    if request.GET.get("academic_year_id"):
        try:
            params["academic_year_id"] = int(request.GET.get("academic_year_id"))
        except (TypeError, ValueError):
            pass

    families = cx.list_compliance_export_families(school)
    for row in families:
        key = row["export_key"]
        row["requirements"] = cx.get_compliance_export_requirements(key, school)
        row["missing_data"] = cx.get_compliance_export_missing_data(
            key, school, params
        )
        row["blocked"] = len(row["missing_data"]) > 0
        q = urlencode({"academic_year_id": params["academic_year_id"]} if params else {})
        try:
            base = reverse(
                "siteconfig:compliance_export_download",
                kwargs={"export_key": key},
            )
            row["download_path"] = f"{base}?{q}" if q else base
        except NoReverseMatch:
            row["download_path"] = "#"

    # Related control-plane links
    def _u(name: str) -> str | None:
        try:
            return reverse(name)
        except NoReverseMatch:
            return None

    admin_fallback = None
    if getattr(request.user, "is_superuser", False):
        try:
            admin_fallback = reverse("admin:app_list", kwargs={"app_label": "reports"})
        except NoReverseMatch:
            admin_fallback = None

    ctx = {
        "school": school,
        "families": families,
        "academic_year_qs_param": params.get("academic_year_id"),
        "student_attendance_export_url": _u("portal:student_attendance_export"),
        "report_templates_catalog_url": _u("siteconfig:report_templates_catalog_evidence"),
        "report_output_history_url": _u("siteconfig:report_output_history_evidence"),
        "academic_years_evidence_url": _u("siteconfig:academic_years_setup_evidence"),
        "departments_setup_url": _u("siteconfig:departments_setup_evidence"),
        "scheduled_reports_hub_url": _u("siteconfig:scheduled_reports_delivery_hub"),
        "metadata_operator_hub_url": _u("siteconfig:metadata_operator_hub"),
        "entity_catalog_url": _u("siteconfig:entity_catalog_overview"),
        "runtime_hub_url": _u("siteconfig:tenant_runtime_configuration_hub"),
        "admin_reports_app_url": admin_fallback,
    }
    return render(request, "siteconfig/compliance_exports.html", ctx)


@login_required
@permission_required("settings.manage", raise_exception=True)
@enforce_tenant_security(action="export", require_school=False)
def compliance_export_download_view(
    request: HttpRequest, export_key: str
) -> HttpResponse:
    school = getattr(request, "school", None)
    if not school:
        messages.error(request, "No tenant school on this request.")
        return redirect("siteconfig:user_preferences")

    params: dict = {}
    if request.GET.get("academic_year_id"):
        try:
            params["academic_year_id"] = int(request.GET.get("academic_year_id"))
        except (TypeError, ValueError):
            pass

    if not cx.get_compliance_export_family(export_key):
        messages.error(request, "Invalid export key.")
        return redirect("siteconfig:compliance_exports")

    result = cx.generate_regional_compliance_export(
        export_key, school, request.user, params=params
    )
    if not result.get("ok"):
        for m in result.get("missing") or [result.get("message") or "Blocked."]:
            messages.warning(request, m)
        return redirect("siteconfig:compliance_exports")

    _audit_export_download(
        request, export_key, result.get("academic_year_id")
    )

    body = result["content"]
    if isinstance(body, str):
        body_bytes = body.encode("utf-8")
    else:
        body_bytes = body

    try:
        log_security_event(
            request.user,
            SecurityAuditLog.EventType.DATA_EXPORT,
            request=request,
            school=school,
            initiator="self",
        )
    except Exception:
        pass

    resp = HttpResponse(
        body_bytes,
        content_type=result.get("content_type", "text/csv; charset=utf-8"),
    )
    filename = result.get("filename") or "export.csv"
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp["Cache-Control"] = "no-store"
    secret = getattr(settings, "SECRET_KEY", "") or ""
    if secret:
        attach_export_integrity_headers(
            resp,
            content=body_bytes,
            export_key=export_key,
            school_id=str(getattr(school, "pk", "")),
            secret=secret,
        )
    return resp
