"""Portal student-facing LMS homework loop — list + detail/submit.

Closes the loop the student dashboard already half-wired: it surfaces "homework due
this week, not yet submitted" from ``academics.LMSSubmission`` but links to a dead
fallback because no submit surface existed. These views are that surface.

Both the online POST here and the offline-then-synced replay converge on ONE store via
``academics.lms_services.submit_assignment`` (the offline form carries
``data-rmc-offline-form="homework_submission"`` so a low-connectivity submit queues and
applies through ``platform_runtime.offline_queue._apply_lms_submission``).
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.models import User
from apps.accounts.utils import get_user_role
from apps.academics.lms_services import (
    AssignmentClosedError,
    open_assignments_for_student,
    submit_assignment,
    submission_map_for_student,
)
from apps.academics.models_lms import LMSAssignment, LMSSubmission
from apps.people.models import StudentProfile
from apps.siteconfig.config_service import get_effective_site_settings


_STUDENT_LOOKUP_ERRORS = (AttributeError, DatabaseError, TypeError, ValueError)


def _resolve_student(request: HttpRequest):
    """The active StudentProfile for the requesting user, or None."""
    try:
        # tenant-isolation-allow: scoped-via-request-user-own-profile-reviewed-2026-06-25
        return (
            StudentProfile.objects.filter(user=request.user, is_active=True)
            .select_related("classroom")
            .first()
        )
    except _STUDENT_LOOKUP_ERRORS:
        return None


def _student_guard(request: HttpRequest):
    """Return (school, profile) when the caller is a student with the portal enabled,
    else an HttpResponse to return immediately."""
    if get_user_role(request.user) != User.Role.STUDENT:
        return redirect("portal:parent_dashboard")
    site = get_effective_site_settings(request=request)
    if not getattr(site, "enable_student_portal", True):
        return HttpResponseForbidden("Student portal is disabled.")
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseForbidden("No school context.")
    profile = _resolve_student(request)
    if profile is None:
        return HttpResponseForbidden("No student profile.")
    return school, profile


@login_required
@require_http_methods(["GET"])
def student_assignments(request: HttpRequest):
    """List the student's open assignments with per-item submission status."""
    guard = _student_guard(request)
    if not isinstance(guard, tuple):
        return guard
    school, profile = guard

    assignments = list(open_assignments_for_student(school=school, student=profile))
    smap = submission_map_for_student(
        school=school,
        student=profile,
        assignment_ids=[a.id for a in assignments],
    )
    now = timezone.now()
    rows = []
    for a in assignments:
        sub = smap.get(a.id)
        submitted = bool(sub and sub.status in (
            LMSSubmission.Status.SUBMITTED,
            LMSSubmission.Status.LATE,
            LMSSubmission.Status.GRADED,
            LMSSubmission.Status.RETURNED,
        ))
        rows.append(
            {
                "assignment": a,
                "submission": sub,
                "submitted": submitted,
                "status": sub.status if sub else LMSSubmission.Status.NOT_SUBMITTED,
                "overdue": bool(a.due_at and a.due_at < now and not submitted),
            }
        )
    return render(
        request,
        "portal/student_assignments.html",
        {
            "rows": rows,
            "profile": profile,
            "page_title": "Homework",
            "page_subtitle": "Assignments for your class. Submissions work offline.",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def student_assignment_submit(request: HttpRequest, assignment_id: int):
    """GET: assignment detail + submission form. POST: record the student's submission."""
    guard = _student_guard(request)
    if not isinstance(guard, tuple):
        return guard
    school, profile = guard

    # Tenant- and classroom-scoped: a student only reaches their own class's work.
    assignment = (
        LMSAssignment.objects.filter(
            pk=assignment_id, school=school, classroom_id=profile.classroom_id
        )
        .select_related("subject")
        .first()
    )
    if assignment is None:
        return HttpResponseForbidden("Assignment not available.")

    existing = (
        LMSSubmission.objects.filter(
            school=school, assignment=assignment, student=profile
        ).first()
    )

    if request.method == "POST":
        content = (request.POST.get("content") or "").strip()
        attachment = request.FILES.get("attachment")
        if not content and not attachment and not (existing and existing.content):
            messages.error(request, "Add your answer or an attachment before submitting.")
            return redirect("portal:student_assignment_submit", assignment_id=assignment.id)
        try:
            submit_assignment(
                assignment=assignment,
                student=profile,
                content=content,
                attachment=attachment,
                force=True,  # online: an explicit re-submit replaces the draft/prior text
            )
        except AssignmentClosedError:
            messages.error(request, "This assignment is no longer open for submissions.")
            return redirect("portal:student_assignments")
        messages.success(request, f"Submitted “{assignment.title}”.")
        return redirect("portal:student_assignments")

    return render(
        request,
        "portal/student_assignment_detail.html",
        {
            "assignment": assignment,
            "submission": existing,
            "profile": profile,
            "is_open": assignment.is_open_for_submissions,
            "page_title": assignment.title,
        },
    )
