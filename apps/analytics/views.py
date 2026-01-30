from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Specialty, Term, Subject, SubjectAssignment
from apps.academics.services import get_active_year_and_term
from apps.evals.models import Evaluation
from apps.people.models import TeacherProfile
from apps.siteconfig.models import SiteSettings
from apps.finance.models import Notification
from apps.siteconfig.models_dashboard import get_dashboard_widget_metadata


from .services import (
    DEADLINE_MODE_CUSTOM,
    DEADLINE_MODE_PUBLISH,
    DEADLINE_MODE_TERM_END,
    annual_rankings,
    specialty_pass_rates,
    student_improvements,
    subject_weaknesses,
    teacher_compliance,
    term_rankings,
)


def _parse_int(value: str | None, default: int, min_val: int | None = None, max_val: int | None = None) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    if min_val is not None:
        parsed = max(min_val, parsed)
    if max_val is not None:
        parsed = min(max_val, parsed)
    return parsed


def _parse_decimal(value: str | None, default: Decimal) -> Decimal:
    if value is None:
        return Decimal(str(default))
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(default))


@staff_member_required
def dashboard(request: HttpRequest):
    site = SiteSettings.get_solo()
    active_year, active_term = get_active_year_and_term()
    if not active_year or not active_term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    year_id = request.GET.get("year") or str(active_year.id)
    term_id = request.GET.get("term") or str(active_term.id)

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id, academic_year=year_obj)

    classroom_id = request.GET.get("classroom")
    specialty_id = request.GET.get("specialty")
    classroom_obj = Classroom.objects.filter(id=classroom_id).first() if classroom_id else None
    specialty_obj = Specialty.objects.filter(id=specialty_id).first() if specialty_id else None

    top_n = _parse_int(
        request.GET.get("top_n"),
        int(site.top_students_default_limit),
        min_val=1,
        max_val=100,
    )
    pass_mark = _parse_decimal(request.GET.get("pass_mark"), site.pass_mark)
    weak_threshold = _parse_decimal(request.GET.get("weak_threshold"), site.weak_subject_threshold)
    improve_delta = _parse_decimal(request.GET.get("improve_delta"), site.improvement_delta_threshold)
    use_promotion_rule = (
        request.GET.get("use_promotion_rule") == "1"
        if "use_promotion_rule" in request.GET
        else site.use_promotion_rule_for_pass
    )
    deadline_mode = request.GET.get("deadline_mode") or site.deadline_mode or DEADLINE_MODE_TERM_END

    terms = list(Term.objects.filter(academic_year=year_obj).order_by("start_date"))
    improve_from_id = request.GET.get("improve_from") or (str(terms[0].id) if terms else "")
    improve_to_id = request.GET.get("improve_to") or str(term_obj.id)

    from_term = Term.objects.filter(id=improve_from_id, academic_year=year_obj).first()
    to_term = Term.objects.filter(id=improve_to_id, academic_year=year_obj).first()

    class_rankings = term_rankings(term_obj, classroom_obj) if classroom_obj else []
    top_class_students = [
        {"rank": idx + 1, "student": row[0], "average": row[1]}
        for idx, row in enumerate(class_rankings[:top_n])
    ]
    top_school_students = [
        {"rank": idx + 1, "student": row[0], "average": row[1]}
        for idx, row in enumerate(term_rankings(term_obj)[:top_n])
    ]

    annual_class = annual_rankings(year_obj, terms, classroom_obj)
    annual_school = annual_rankings(year_obj, terms)
    top_annual_class = [
        {"rank": idx + 1, "student": row[0], "average": row[1]}
        for idx, row in enumerate(annual_class[:top_n])
    ]
    top_annual_school = [
        {"rank": idx + 1, "student": row[0], "average": row[1]}
        for idx, row in enumerate(annual_school[:top_n])
    ]

    weak_subject_rows = subject_weaknesses(
        academic_year=year_obj,
        term=term_obj,
        classroom=classroom_obj,
        specialty=specialty_obj,
        threshold=weak_threshold,
    )
    improvement_rows = []
    if from_term and to_term and from_term.id != to_term.id:
        improvement_rows = student_improvements(
            academic_year=year_obj,
            from_term=from_term,
            to_term=to_term,
            classroom=classroom_obj,
            min_delta=improve_delta,
        )

    teacher_rows = teacher_compliance(
        academic_year=year_obj,
        term=term_obj,
        deadline_mode=deadline_mode,
    )

    pass_period = request.GET.get("pass_period") or "term"
    pass_term = None if pass_period == "annual" else term_obj
    specialty_rows = specialty_pass_rates(
        academic_year=year_obj,
        term=pass_term,
        pass_mark=pass_mark,
        use_promotion_rule=use_promotion_rule,
    )

    from apps.accounts.utils import get_dashboard_context
    dashboard_ctx = get_dashboard_context(request.user, "analytics")
    dashboard_settings = dashboard_ctx["dashboard_settings"]
    allow_custom_layout = dashboard_ctx["allow_custom_layout"]
    dashboard_layout_url = dashboard_ctx["dashboard_layout_url"]
    widget_meta_json = dashboard_ctx["widget_meta_json"]
    available_sidebar_items = [
        {"id": "analytics-home", "label": "Analytics Home", "url": reverse("analytics:dashboard"), "icon": "bi-bar-chart-line"},
        {"id": "analytics-master", "label": "Master Sheet", "url": reverse("analytics:master_sheet"), "icon": "bi-file-earmark-spreadsheet"},
        {"id": "analytics-deadlines", "label": "Grading Deadlines", "url": reverse("analytics:deadlines"), "icon": "bi-calendar-check"},
        {"id": "finance-notifications", "label": "Finance Notifications", "url": reverse("finance:notifications"), "icon": "bi-bell"},
    ]
    finance_requests_qs = Notification.objects.filter(
        recipient=request.user,
        title__icontains="finance access request",
        is_read=False,
    ).order_by("-created_at")
    finance_request_link = reverse("requests:dashboard")

    context = {
        "year": year_obj,
        "term": term_obj,
        "years": AcademicYear.objects.order_by("-start_date"),
        "terms": terms,
        "classrooms": Classroom.objects.filter(academic_year=year_obj).order_by("name"),
        "specialties": Specialty.objects.order_by("name"),
        "selected_classroom": classroom_obj,
        "selected_specialty": specialty_obj,
        "top_n": top_n,
        "pass_mark": pass_mark,
        "weak_threshold": weak_threshold,
        "improve_delta": improve_delta,
        "use_promotion_rule": use_promotion_rule,
        "deadline_mode": deadline_mode,
        "deadline_modes": [
            (DEADLINE_MODE_TERM_END, "Term end"),
            (DEADLINE_MODE_CUSTOM, "Custom deadline"),
            (DEADLINE_MODE_PUBLISH, "Publish date"),
        ],
        "pass_period": pass_period,
        "class_rankings": class_rankings,
        "top_class_students": top_class_students,
        "top_school_students": top_school_students,
        "top_annual_class": top_annual_class,
        "top_annual_school": top_annual_school,
        "weak_subjects": weak_subject_rows,
        "improvements": improvement_rows,
        "teacher_stats": teacher_rows,
        "specialty_rates": specialty_rows,
        "improve_from": from_term,
        "improve_to": to_term,
    }
    context.update({
        "allow_custom_layout": allow_custom_layout,
        "dashboard_settings": dashboard_settings,
        "dashboard_layout_url": dashboard_layout_url,
        "available_sidebar_items": available_sidebar_items,
        "widget_meta_json": widget_meta_json,
        "finance_requests_count": finance_requests_qs.count(),
        "finance_request_notifications": finance_requests_qs[:5],
        "finance_request_link": finance_request_link,
    })
    return render(request, "analytics/dashboard.html", context)


@staff_member_required
def master_sheet(request: HttpRequest):
    active_year, active_term = get_active_year_and_term()
    if not active_year or not active_term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    year_id = request.GET.get("year") or str(active_year.id)
    term_id = request.GET.get("term")

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = Term.objects.filter(id=term_id, academic_year=year_obj).first() if term_id else None

    classroom_id = request.GET.get("classroom")
    specialty_id = request.GET.get("specialty")
    subject_id = request.GET.get("subject")
    teacher_id = request.GET.get("teacher")

    classroom_obj = Classroom.objects.filter(id=classroom_id).first() if classroom_id else None
    specialty_obj = Specialty.objects.filter(id=specialty_id).first() if specialty_id else None
    subject_obj = Subject.objects.filter(id=subject_id).first() if subject_id else None
    teacher_obj = TeacherProfile.objects.filter(id=teacher_id).first() if teacher_id else None

    evals = Evaluation.objects.filter(academic_year=year_obj).select_related(
        "student",
        "teacher__user",
        "subject_assignment__classroom",
        "subject_assignment__specialty",
        "subject_assignment__subject",
        "term",
    )

    if term_obj:
        evals = evals.filter(term=term_obj)
    if classroom_obj:
        evals = evals.filter(subject_assignment__classroom=classroom_obj)
    if specialty_obj:
        evals = evals.filter(subject_assignment__specialty=specialty_obj)
    if subject_obj:
        evals = evals.filter(subject_assignment__subject=subject_obj)
    if teacher_obj:
        evals = evals.filter(teacher=teacher_obj)

    evals = evals.order_by("student__last_name", "student__first_name", "subject_assignment__subject__name")

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="master-grading-sheet.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Student Code",
            "Student Name",
            "Classroom",
            "Specialty",
            "Subject",
            "Teacher",
            "Term",
            "Seq 1",
            "Seq 2",
            "Exam",
            "Mock",
            "Practical",
            "Total",
            "Updated At",
        ])
        for e in evals:
            writer.writerow([
                e.student.student_code,
                f"{e.student.last_name} {e.student.first_name}",
                e.subject_assignment.classroom.name,
                e.subject_assignment.specialty.name,
                e.subject_assignment.subject.name,
                e.teacher.user.get_full_name() or e.teacher.user.username,
                e.term.label,
                e.seq1_score or "",
                e.seq2_score or "",
                e.exam_score or "",
                e.mock_score or "",
                e.practical_score or "",
                f"{e.total_score:.2f}",
                timezone.localtime(e.updated_at).strftime("%Y-%m-%d %H:%M"),
            ])
        return response

    export_params = request.GET.copy()
    export_params["export"] = "csv"

    context = {
        "year": year_obj,
        "term": term_obj,
        "years": AcademicYear.objects.order_by("-start_date"),
        "terms": Term.objects.filter(academic_year=year_obj).order_by("start_date"),
        "classrooms": Classroom.objects.filter(academic_year=year_obj).order_by("name"),
        "specialties": Specialty.objects.order_by("name"),
        "subjects": Subject.objects.order_by("name"),
        "teachers": TeacherProfile.objects.select_related("user").order_by("user__last_name"),
        "selected_classroom": classroom_obj,
        "selected_specialty": specialty_obj,
        "selected_subject": subject_obj,
        "selected_teacher": teacher_obj,
        "evals": evals,
        "export_query": export_params.urlencode(),
    }
    return render(request, "analytics/master_sheet.html", context)


@staff_member_required
def grading_deadlines(request: HttpRequest):
    """
    Grading deadlines management using SubjectAssignment.deadline_at.
    """
    active_year, active_term = get_active_year_and_term()
    if not active_year or not active_term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    year_obj = get_object_or_404(AcademicYear, id=request.GET.get("year") or str(active_year.id))
    term_obj = get_object_or_404(Term, id=request.GET.get("term") or str(active_term.id), academic_year=year_obj)

    deadlines_qs = (
        SubjectAssignment.objects.filter(
            academic_year=year_obj,
            term=term_obj,
            deadline_at__isnull=False,
        )
        .select_related("classroom", "subject", "specialty")
        .order_by("deadline_at")
    )
    deadlines = [
        {
            "id": sa.id,
            "assignment": sa,
            "deadline_at": sa.deadline_at,
            "classroom": sa.classroom.name,
            "subject": sa.subject.name,
            "specialty": getattr(sa.specialty, "name", "") or "",
        }
        for sa in deadlines_qs
    ]

    context = {
        "year": year_obj,
        "term": term_obj,
        "years": AcademicYear.objects.order_by("-start_date"),
        "terms": Term.objects.filter(academic_year=year_obj).order_by("start_date"),
        "classrooms": Classroom.objects.filter(academic_year=year_obj).order_by("name"),
        "deadlines": deadlines,
    }
    return render(request, "analytics/deadlines.html", context)
