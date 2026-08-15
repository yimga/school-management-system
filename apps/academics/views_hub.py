"""Tenant-scoped Academics command center."""

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.accounts.decorators import require_permission
from apps.schools.mixins import require_school

from .models import AcademicYear, Classroom, CourseSyllabus, Subject, SubjectAssignment, Term


def _tenant_url(name: str) -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return ""


@login_required
@require_school
@require_permission("settings.manage", "grades.manage")
def academics_hub(request):
    """Show authoritative academic setup and operational entry points for one school."""
    school = request.school
    model_counts = {
        "academic_years": 0,
        "terms": 0,
        "classes": 0,
        "subjects": 0,
        "assignments": 0,
        "syllabi": 0,
    }
    try:
        # tenant-isolation-allow: every query is explicitly scoped to request.school
        model_counts = {
            "academic_years": AcademicYear.objects.filter(school=school).count(),
            "terms": Term.objects.filter(academic_year__school=school).count(),
            "classes": Classroom.objects.filter(school=school).count(),
            "subjects": Subject.objects.filter(school=school).count(),
            "assignments": SubjectAssignment.objects.filter(school=school).count(),
            "syllabi": CourseSyllabus.objects.filter(subject_assignment__school=school).count(),
        }
    except DatabaseError:
        pass

    actions = [
        ("Academic years & terms", "Create the calendar that powers timetables, grading and reporting.", "siteconfig:academic_years_setup_evidence", "academic_years"),
        ("Classes & subjects", "Review the teaching structure and the subjects available to this school.", "accounts:backend_classroom_list", "classes"),
        ("Teaching assignments", "Connect teachers, classes and subjects with tenant-scoped records.", "accounts:backend_subject_list", "assignments"),
        ("Timetable", "Generate, review conflicts and publish a real school timetable.", "accounts:ops_timetabling", "terms"),
        ("Attendance", "Open the operational attendance capture workflow.", "portal:teacher_attendance", "classes"),
        ("Grading rules", "Configure the rules used by assessment and report surfaces.", "siteconfig:grading_settings", "subjects"),
        ("Course syllabi", "Review syllabus coverage and the approval queue.", "academics:syllabus_approval_queue", "syllabi"),
    ]
    cards = [
        {"title": title, "description": description, "url": _tenant_url(route_name), "count": model_counts[count_key]}
        for title, description, route_name, count_key in actions
    ]
    from apps.academics.academic_calendar import calendar_confirmation_state

    return render(
        request,
        "academics/hub.html",
        {
            "school": school,
            "model_counts": model_counts,
            "academic_actions": cards,
            "calendar_advisory": calendar_confirmation_state(school),
        },
    )
