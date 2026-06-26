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

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from apps.accounts.models import User
from apps.accounts.decorators import role_required
from apps.accounts.utils import get_user_role
from apps.academics.lms_services import (
    AssignmentClosedError,
    create_assignment,
    grade_submission,
    open_assignments_for_student,
    publish_assignment,
    submit_assignment,
    submission_map_for_student,
    submissions_for_assignment,
    teacher_assignments_for,
)
from apps.academics.models import Classroom, Subject
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


# --------------------------------------------------------------------------
# Teacher authoring + grading (the other half of the homework loop)
# --------------------------------------------------------------------------


def _teacher_guard(request: HttpRequest):
    """Return (school, teacher_profile) for a teacher, else an HttpResponse to return."""
    profile = getattr(request.user, "teacher_profile", None)
    if profile is None:
        messages.error(
            request, "No teacher profile found. Ask an admin to complete your profile."
        )
        return redirect("portal:teacher_dashboard_alias")
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseForbidden("No school context.")
    return school, profile


@role_required(User.Role.TEACHER)
@require_http_methods(["GET"])
def teacher_assignments(request: HttpRequest):
    """Teacher's own assignments with submission + graded counts."""
    guard = _teacher_guard(request)
    if not isinstance(guard, tuple):
        return guard
    school, teacher = guard
    assignments = list(teacher_assignments_for(school=school, teacher=teacher))
    return render(
        request,
        "portal/teacher_assignments.html",
        {
            "assignments": assignments,
            "page_title": "Assignments",
            "page_subtitle": "Create homework and grade what students submit.",
        },
    )


@role_required(User.Role.TEACHER)
@require_http_methods(["GET", "POST"])
def teacher_assignment_create(request: HttpRequest):
    """Create (and optionally publish) an assignment for one of the teacher's classes."""
    guard = _teacher_guard(request)
    if not isinstance(guard, tuple):
        return guard
    school, teacher = guard

    classrooms = list(
        Classroom.objects.filter(school=school).order_by("name").only("id", "name")
    )
    subjects = list(
        Subject.objects.filter(school=school).order_by("name").only("id", "name")
    )

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        classroom_id = request.POST.get("classroom")
        subject_id = request.POST.get("subject")
        instructions = (request.POST.get("instructions") or "").strip()
        due_raw = (request.POST.get("due_at") or "").strip()
        publish = request.POST.get("publish") == "1"

        classroom = next((c for c in classrooms if str(c.id) == classroom_id), None)
        subject = next((s for s in subjects if str(s.id) == subject_id), None)
        if not title or classroom is None or subject is None:
            messages.error(request, "Title, class, and subject are required.")
            return redirect("portal:teacher_assignment_create")

        due_at = None
        if due_raw:
            parsed = parse_datetime(due_raw)
            if parsed is not None and timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            due_at = parsed

        try:
            assignment = create_assignment(
                school=school,
                classroom=classroom,
                subject=subject,
                teacher=teacher,
                title=title,
                instructions=instructions,
                due_at=due_at,
                publish=publish,
            )
        except ValueError as exc:
            messages.error(request, str(exc).replace("_", " "))
            return redirect("portal:teacher_assignment_create")
        messages.success(
            request,
            f"{'Published' if publish else 'Saved draft'}: “{assignment.title}”.",
        )
        return redirect("portal:teacher_assignments")

    return render(
        request,
        "portal/teacher_assignment_create.html",
        {
            "classrooms": classrooms,
            "subjects": subjects,
            "page_title": "New assignment",
        },
    )


@role_required(User.Role.TEACHER)
@require_http_methods(["GET", "POST"])
def teacher_assignment_grade(request: HttpRequest, assignment_id: int):
    """List submissions for one of the teacher's assignments and grade them."""
    guard = _teacher_guard(request)
    if not isinstance(guard, tuple):
        return guard
    school, teacher = guard

    assignment = (
        LMSAssignment.objects.filter(pk=assignment_id, school=school, teacher=teacher)
        .select_related("subject", "classroom")
        .first()
    )
    if assignment is None:
        return HttpResponseForbidden("Assignment not available.")

    if request.method == "POST":
        if assignment.status == LMSAssignment.Status.DRAFT:
            publish_assignment(assignment=assignment)
            messages.success(request, f"Published “{assignment.title}”.")
            return redirect("portal:teacher_assignment_grade", assignment_id=assignment.id)
        submission_id = request.POST.get("submission_id")
        submission = (
            LMSSubmission.objects.filter(
                pk=submission_id, school=school, assignment=assignment
            ).first()
            if submission_id
            else None
        )
        if submission is None:
            messages.error(request, "Select a submission to grade.")
            return redirect("portal:teacher_assignment_grade", assignment_id=assignment.id)
        score_raw = (request.POST.get("score") or "").strip()
        feedback = (request.POST.get("feedback") or "").strip()
        score = None
        if score_raw:
            try:
                score = Decimal(score_raw)
            except (InvalidOperation, ValueError):
                messages.error(request, "Score must be a number.")
                return redirect(
                    "portal:teacher_assignment_grade", assignment_id=assignment.id
                )
        grade_submission(
            submission=submission, score=score, feedback=feedback, graded_by=request.user
        )
        messages.success(request, "Grade saved.")
        return redirect("portal:teacher_assignment_grade", assignment_id=assignment.id)

    submissions = list(submissions_for_assignment(school=school, assignment=assignment))
    return render(
        request,
        "portal/teacher_assignment_grade.html",
        {
            "assignment": assignment,
            "submissions": submissions,
            "page_title": f"Grade — {assignment.title}",
        },
    )
