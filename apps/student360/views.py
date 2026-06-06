"""
Student 360 full-page view (Section 26.1 / 15.1).
Permission-gated; tabbed UI: Summary, Academic, Finance, Attendance, Timeline.
Immutable transcript: freeze action and cross-year archive view.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.compliance.decorators import audit_pii_view

from .services import (
    get_student_360_summary,
    get_student_timeline_feed,
    get_immutable_transcripts_for_student,
    create_immutable_transcript,
)


def _student_360_academic(student):
    """Recent enrollments and evaluations for 360 Academic tab."""
    enrollments = []
    evaluations = []
    try:
        from django.apps import apps

        if apps.is_installed("academics"):
            from apps.academics.models import ClassEnrollment

            enrollments = list(
                ClassEnrollment.objects.filter(student=student).select_related(
                    "classroom", "academic_year"
                )[:20]
            )
        if apps.is_installed("evals"):
            Evaluation = apps.get_model("evals", "Evaluation")
            # tenant-isolation-allow: `student` is school-scoped by caller; FK already binds tenant (reviewed 2026-05-14)
            evaluations = list(
                Evaluation.objects.filter(student=student).select_related(
                    "term", "academic_year"
                )[:20]
            )
    except (
        ImportError,
        LookupError,
        AttributeError,
        TypeError,
        ValueError,
        DatabaseError,
    ):
        pass
    return {"enrollments": enrollments, "evaluations": evaluations}


def _student_360_finance(student):
    """Recent invoices for 360 Finance tab."""
    invoices = []
    try:
        from django.apps import apps

        if apps.is_installed("finance"):
            Invoice = apps.get_model("finance", "Invoice")
            # tenant-isolation-allow: `student` is school-scoped by caller; FK already binds tenant (reviewed 2026-05-14)
            invoices = list(
                Invoice.objects.filter(student=student).order_by("-created_at")[:20]
            )
    except (
        ImportError,
        LookupError,
        AttributeError,
        TypeError,
        ValueError,
        DatabaseError,
    ):
        pass
    return {"invoices": invoices}


@login_required
@audit_pii_view(model_name="StudentProfile", object_id_kwarg="student_id", sensitivity="HIGH", reason="Student 360 full profile view")
def student_360_page(request, student_id):
    """
    Full Student 360 page: tabbed Summary, Academic, Finance, Attendance, Timeline.
    Requires view permission on the student.
    """
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("School context required.")
    from apps.people.models import StudentProfile

    student = get_object_or_404(
        StudentProfile.objects.prefetch_related("tags"),
        pk=student_id,
        school=school,
        is_active=True,
    )
    user = request.user
    if not user.is_staff:
        from apps.accounts.permissions import can_view_student_data

        if not can_view_student_data(user, student_id):
            return HttpResponseForbidden(
                "You do not have permission to view this student."
            )
    role = (getattr(user, "role", "") or "").upper()
    can_see_private_tags = user.is_staff or role in (
        "ADMIN",
        "IT_ADMIN",
        "LEADERSHIP",
    )
    information_tags = [
        tag
        for tag in student.tags.filter(is_active=True).order_by("name")
        if not tag.is_private or can_see_private_tags
    ]
    summary = get_student_360_summary(
        school.id,
        student_id,
        include_timeline_count=True,
        include_export_available=True,
    )
    timeline = get_student_timeline_feed(school.id, student_id, limit=50)
    academic = _student_360_academic(student)
    finance = _student_360_finance(student)
    from apps.portal.views_passport import _staff_may_view_student

    return render(
        request,
        "student360/student_360_page.html",
        {
            "student": student,
            "summary": summary,
            "timeline": timeline,
            "academic": academic,
            "finance": finance,
            "show_passport_vault_links": _staff_may_view_student(request, student),
            "information_tags": information_tags,
            "can_see_private_tags": can_see_private_tags,
        },
    )


@login_required
@audit_pii_view(model_name="StudentProfile", object_id_kwarg="student_id", sensitivity="HIGH", reason="Student 360 full-PII export pack")
def student_360_export(request, student_id):
    """Permission-gated export pack (JSON) for Student 360."""
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("School context required.")
    from apps.people.models import StudentProfile

    _student = get_object_or_404(
        StudentProfile, pk=student_id, school=school, is_active=True
    )
    user = request.user
    if not user.is_staff:
        from apps.accounts.permissions import can_view_student_data

        if not can_view_student_data(user, student_id):
            return HttpResponseForbidden(
                "You do not have permission to export this student."
            )
    from .services import export_student_pack
    import json
    from django.http import HttpResponse

    data = export_student_pack(school.id, student_id, format="json")
    if not data:
        return HttpResponseForbidden("Export not available.")
    response = HttpResponse(
        json.dumps(data, indent=2, default=str), content_type="application/json"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="student_360_export_{student_id}.json"'
    )
    return response


@login_required
@audit_pii_view(model_name="ImmutableTranscript", object_id_kwarg="student_id", sensitivity="HIGH", reason="Transcript archive list view")
def transcript_archive(request, student_id):
    """
    Cross-year archive view: list immutable transcripts for this student (Section 15.1).
    Permission: same as student 360 view (view student data).

    Pass 9.B closeout: AuditLog.Action.VIEW emitted on 2xx GETs (FERPA read-access).
    """
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("School context required.")
    from apps.people.models import StudentProfile

    # v4.01 — the archive exists to serve withdrawn/graduated students, who are
    # exactly the ones with is_active=False. Scope by school (tenant) only.
    student = get_object_or_404(
        StudentProfile, pk=student_id, school=school
    )
    user = request.user
    if not user.is_staff:
        from apps.accounts.permissions import can_view_student_data

        if not can_view_student_data(user, student_id):
            return HttpResponseForbidden(
                "You do not have permission to view this student."
            )
    archives = get_immutable_transcripts_for_student(student)
    from apps.academics.models import AcademicYear

    academic_years = list(
        AcademicYear.objects.filter(school=school).order_by("-start_date")[:20]
    )
    return render(
        request,
        "student360/transcript_archive.html",
        {
            "student": student,
            "archives": archives,
            "academic_years": academic_years,
        },
    )


@login_required
def transcript_archive_year(request, student_id, year_id):
    """Single academic year immutable transcript (read-only) for archive."""
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("School context required.")
    from apps.people.models import StudentProfile
    from .models import ImmutableTranscript

    # v4.01 — single-year archive must reach withdrawn/graduated students too.
    student = get_object_or_404(
        StudentProfile, pk=student_id, school=school
    )
    user = request.user
    if not user.is_staff:
        from apps.accounts.permissions import can_view_student_data

        if not can_view_student_data(user, student_id):
            return HttpResponseForbidden(
                "You do not have permission to view this student."
            )
    transcript = get_object_or_404(
        ImmutableTranscript,
        student=student,
        academic_year_id=year_id,
    )
    return render(
        request,
        "student360/transcript_archive_year.html",
        {
            "student": student,
            "transcript": transcript,
            "snapshot": transcript.snapshot,
        },
    )


@login_required
def transcript_freeze(request, student_id):
    """
    Freeze current transcript for the selected academic year (create/update ImmutableTranscript).
    POST only; requires view + change permission on student (or staff).
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required.")
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("School context required.")
    from apps.people.models import StudentProfile

    # v4.01 — a transcript freeze happens at graduation/withdrawal, so the
    # student is often NO LONGER is_active. Scope by school (tenant) only.
    student = get_object_or_404(
        StudentProfile, pk=student_id, school=school
    )
    user = request.user
    if not user.is_staff:
        # v4.01 AUTHZ — freezing an immutable transcript is a WRITE to the
        # student's academic record. Gate on edit permission, not the READ-only
        # can_view_student_data (which let a PARENT/STUDENT freeze a transcript).
        from apps.accounts.permissions import can_edit_student_grades

        if not can_edit_student_grades(user, student_id):
            return HttpResponseForbidden(
                "You do not have permission to update this student's transcript."
            )
    year_id = request.POST.get("academic_year_id")
    if not year_id:
        messages.error(request, "Please select an academic year.")
        return redirect("portal:student_360_page", student_id=student_id)
    from apps.academics.models import AcademicYear

    academic_year = AcademicYear.objects.filter(pk=year_id, school=school).first()
    if not academic_year:
        messages.error(request, "Invalid academic year.")
        return redirect("portal:student_360_page", student_id=student_id)
    obj = create_immutable_transcript(student, academic_year, created_by=user)
    if obj:
        messages.success(
            request, f"Transcript for {academic_year.name} frozen successfully."
        )
    else:
        messages.error(
            request,
            "Could not freeze transcript; check that report data is available for this year.",
        )
    return redirect("portal:transcript_archive", student_id=student_id)
