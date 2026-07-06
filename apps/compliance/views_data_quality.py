"""Data Quality Center — tenant-scoped completeness + reachability checks."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import render

from apps.compliance.auth_utils import is_admin_or_staff
from apps.compliance.data_quality import data_quality_checks, summarize


@login_required
def data_quality_center(request: HttpRequest) -> HttpResponse:
    """Render the tenant's Data Quality Center.

    Surfaces every issue returned by the registered checks in
    `apps.compliance.data_quality.DATA_QUALITY_CHECKS`. Grouped by severity
    (blocker → warning → info), Apple Mail-style.
    """
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseForbidden(
            "Data Quality Center is only available from a tenant school context."
        )

    # RBAC-completion (2026-07) TIGHTENING: previously any authenticated user in
    # a tenant context could read this. Restrict to admin/staff/leadership,
    # `compliance.manage` (both via is_admin_or_staff), or read-tier
    # `compliance.view` holders. Guarded so a DB hiccup fails closed.
    user = request.user
    allowed = is_admin_or_staff(user)
    if not allowed:
        try:
            allowed = bool(user.has_feature_permission("compliance.view"))
        except Exception:
            allowed = False
    if not allowed:
        return HttpResponseForbidden(
            "You do not have permission to view the Data Quality Center."
        )

    issues = data_quality_checks(school=school)
    counts = summarize(issues)

    # Stable sort: blocker > warning > info; ties by title.
    severity_order = {"blocker": 0, "warning": 1, "info": 2}
    issues_sorted = sorted(
        issues,
        key=lambda i: (severity_order.get(i.get("severity"), 99), i.get("title") or ""),
    )

    blockers = [i for i in issues_sorted if i.get("severity") == "blocker"]
    warnings = [i for i in issues_sorted if i.get("severity") == "warning"]
    infos = [i for i in issues_sorted if i.get("severity") == "info"]

    return render(
        request,
        "compliance/data_quality_center.html",
        {
            "school": school,
            "issues": issues_sorted,
            "blockers": blockers,
            "warnings": warnings,
            "infos": infos,
            "counts": counts,
        },
    )
