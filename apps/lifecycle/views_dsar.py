"""Tenant-facing DSAR self-serve: export + offboarding request (operator approval).

URL: /portal/configure/offboarding/export-and-close/
- GET → confirmation page describing export + request flow
- POST → submits offboarding request (operator-only) or legacy self-close when enabled

Permissions: tenant must be authenticated AND user.is_staff (school admin).
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.schools.tenant_offboarding_policy import operator_only_offboarding

from .services_offboarding import grace_expires_at

logger = logging.getLogger(__name__)


def _resolve_school(request):
    school = (
        getattr(request, "school", None)
        or getattr(request, "tenant_school", None)
        or getattr(request, "tenant", None)
    )
    if school and hasattr(school, "id"):
        return school
    return None


@login_required
@require_http_methods(["GET", "POST"])
def dsar_export_and_close(request):
    if not (request.user.is_staff or getattr(request.user, "is_superuser", False)):
        return HttpResponseForbidden("Only school staff/admin may initiate offboarding.")
    school = _resolve_school(request)
    if school is None:
        return render(
            request,
            "lifecycle/dsar_export_and_close.html",
            {
                "error": "No tenant context resolved — try logging in from your school's subdomain."
            },
            status=400,
        )

    operator_only = operator_only_offboarding()

    if request.method == "GET":
        return render(
            request,
            "lifecycle/dsar_export_and_close.html",
            {
                "school": school,
                "grace_expires_at": grace_expires_at(school),
                "operator_only": operator_only,
            },
        )

    confirm = (request.POST.get("confirm") or "").strip()
    if confirm.lower() != school.slug.lower():
        return render(
            request,
            "lifecycle/dsar_export_and_close.html",
            {
                "school": school,
                "grace_expires_at": grace_expires_at(school),
                "operator_only": operator_only,
                "error": f"Please type the school slug '{school.slug}' to confirm.",
            },
            status=400,
        )

    export_path = None
    try:
        from apps.schools.tenant_offboarding import run_wind_down_export

        export_result = run_wind_down_export(school, full=True, actor=request.user)
        export_path = getattr(export_result, "archive_path", None) or getattr(
            export_result, "manifest_path", None
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lifecycle.dsar.export_enqueue_failed school_id=%s err=%s",
            school.id,
            type(exc).__name__,
        )

    if operator_only:
        try:
            from apps.schools.tenant_offboarding import request_tenant_offboarding

            request_tenant_offboarding(
                school,
                actor=request.user,
                acknowledge=True,
            )
        except ValueError as exc:
            return render(
                request,
                "lifecycle/dsar_export_and_close.html",
                {
                    "school": school,
                    "grace_expires_at": grace_expires_at(school),
                    "operator_only": operator_only,
                    "error": str(exc),
                },
                status=400,
            )
        phase = "request_submitted"
    else:
        reason = (request.POST.get("reason") or "")[:200]
        from .services_offboarding import mark_deleted

        mark_deleted(
            school,
            actor=request.user,
            reason=reason or "Tenant-initiated DSAR export+close",
        )
        phase = "submitted"

    return render(
        request,
        "lifecycle/dsar_export_and_close.html",
        {
            "school": school,
            "grace_expires_at": grace_expires_at(school),
            "operator_only": operator_only,
            "phase": phase,
            "export_path_present": bool(export_path),
        },
    )
