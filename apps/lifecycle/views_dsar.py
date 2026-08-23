"""Tenant-facing DSAR self-serve: export + offboarding request (operator approval).

URL: /portal/configure/offboarding/export-and-close/
- GET → confirmation page describing export + request flow
- POST → submits offboarding request (operator-only) or legacy self-close when enabled

Permissions: tenant-lifecycle access for THIS school (membership + settings.manage
/ owner / admin-like role), as used by the export-only sibling view.
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.schools.tenant_access import user_belongs_to_school
from apps.schools.tenant_offboarding_policy import operator_only_offboarding

from .services_offboarding import grace_expires_at
from .tenant_school_resolve import (
    can_access_tenant_lifecycle,
    lifecycle_access_denied_response,
    resolve_request_school,
)

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def dsar_export_and_close(request):
    school = resolve_request_school(request)
    if school is None:
        return render(
            request,
            "lifecycle/dsar_export_and_close.html",
            {
                "error": "No tenant context resolved — try logging in from your school's subdomain."
            },
            status=400,
        )

    # ``is_staff`` is the PLATFORM operator-team flag; nothing in signup or
    # provisioning ever sets it on a school owner, so gating on it 403'd every
    # real tenant admin on their own GDPR close page. Gate on tenant-lifecycle
    # access instead — the same check the export-only sibling already uses.
    if not can_access_tenant_lifecycle(request, school):
        return lifecycle_access_denied_response(request)
    # Closing a tenant is destructive and irreversible, so — unlike the
    # export-only sibling — the actor must also BELONG to this school.
    # can_access_tenant_lifecycle() admits any platform operator through
    # tenant_operator_hub_eligible(), which never looks at membership.
    if not user_belongs_to_school(request.user, school):
        return lifecycle_access_denied_response(request)

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
