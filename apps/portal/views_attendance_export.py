"""North Star SLICE 6 — student attendance CSV export (UI + download)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse

from apps.academics.services import get_active_year_and_term
from apps.schools.security_enforcer import enforce_tenant_security
from apps.schools.tenant_access import user_belongs_to_school
from .attendance_exports import (
    build_student_attendance_csv_response,
    build_student_attendance_export_queryset,
    get_classroom_options_for_export,
    get_student_options_for_export,
    parse_export_filters_from_get,
    user_can_access_student_attendance_export,
)


@login_required
@enforce_tenant_security(action="export", require_school=False)
def student_attendance_export(request: HttpRequest):
    if not user_can_access_student_attendance_export(request.user):
        return HttpResponseForbidden(
            "You do not have permission to access student attendance export."
        )
    school = getattr(request, "school", None)
    if not school:
        messages.warning(
            request,
            "Open this page from your school subdomain to export student attendance.",
        )
        return redirect("siteconfig:user_preferences")

    if not user_belongs_to_school(request.user, school):
        return HttpResponseForbidden("Not a member of this school.")

    year, _term = get_active_year_and_term()
    filters, err = parse_export_filters_from_get(request.GET)
    if err:
        messages.error(request, err)
    if filters is None:
        filters, _ = parse_export_filters_from_get({})

    compliance_url = None
    try:
        compliance_url = reverse("siteconfig:compliance_exports", urlconf="config.tenant_urls")
    except NoReverseMatch:
        pass

    return render(
        request,
        "portal/student_attendance_export.html",
        {
            "school": school,
            "classrooms": get_classroom_options_for_export(school, request.user, year),
            "students": get_student_options_for_export(school, request.user),
            "filters": filters,
            "filter_error": err,
            "take_attendance_url": reverse("portal:take_student_attendance"),
            "export_csv_url": reverse("portal:student_attendance_export_csv"),
            "compliance_exports_url": compliance_url,
            "evals_teacher_dashboard_url": reverse("evals:teacher_dashboard"),
        },
    )


@login_required
@enforce_tenant_security(action="export", require_school=False)
def student_attendance_export_csv(request: HttpRequest):
    if not user_can_access_student_attendance_export(request.user):
        return HttpResponseForbidden(
            "You do not have permission to export student attendance."
        )
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseBadRequest("School context required.")

    if not user_belongs_to_school(request.user, school):
        return HttpResponseForbidden("Not a member of this school.")

    filters, err = parse_export_filters_from_get(request.GET)
    if err or filters is None:
        return HttpResponseBadRequest(err or "Invalid filters.")

    qs, qerr = build_student_attendance_export_queryset(school, request.user, filters)
    if qerr:
        return HttpResponseBadRequest(qerr)

    return build_student_attendance_csv_response(qs, school, filters)
