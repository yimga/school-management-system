"""Tenant-facing DSAR self-serve: 'Export and close' flow.

URL: /portal/configure/offboarding/export-and-close/
- GET → confirmation page describing what will happen
- POST → marks school soft-deleted, kicks off export task, returns
  download instructions

Permissions: tenant must be authenticated AND user.is_staff (a school
admin). The legacy /school/studio/offboarding/ flow lives elsewhere;
this is a "one-button" DSAR-compliant simplification.

Closes the audit gap: no DSAR self-serve previously existed; school
admins had to email ops to start an export.
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .services_offboarding import grace_expires_at, mark_deleted

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


# Function-based view because the dispatch decorator chain is simpler
# for staff_or_admin gating + tenant resolution.
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
            {"error": "No tenant context resolved — try logging in from your school's subdomain."},
            status=400,
        )

    if request.method == "GET":
        return render(
            request,
            "lifecycle/dsar_export_and_close.html",
            {"school": school, "grace_expires_at": grace_expires_at(school)},
        )

    # POST: require explicit confirmation
    confirm = (request.POST.get("confirm") or "").strip()
    if confirm.lower() != school.slug.lower():
        return render(
            request,
            "lifecycle/dsar_export_and_close.html",
            {
                "school": school,
                "grace_expires_at": grace_expires_at(school),
                "error": f"Please type the school slug '{school.slug}' to confirm.",
            },
            status=400,
        )
    reason = (request.POST.get("reason") or "")[:200]
    mark_deleted(school, actor=request.user, reason=reason or "Tenant-initiated DSAR export+close")
    # Best-effort: trigger export job (delegated to existing offboarding
    # pipeline). Wrap in try so the soft-delete state is preserved even
    # if the export task can't be enqueued in dev.
    try:
        from apps.schools.tenant_offboarding import run_wind_down_export

        export_result = run_wind_down_export(school)
        export_path = getattr(export_result, "archive_path", None) or getattr(
            export_result, "manifest_path", None
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lifecycle.dsar.export_enqueue_failed school_id=%s err=%s",
            school.id,
            type(exc).__name__,
        )
        export_path = None

    return render(
        request,
        "lifecycle/dsar_export_and_close.html",
        {
            "school": school,
            "grace_expires_at": grace_expires_at(school),
            "phase": "submitted",
            "export_path_present": bool(export_path),
        },
    )
