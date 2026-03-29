from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import json
import logging

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import DatabaseError
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Specialty,
    Term,
    Subject,
    SubjectAssignment,
)
from apps.academics.services import get_active_year_and_term
from apps.evals.models import Evaluation
from apps.people.models import TeacherProfile
from apps.siteconfig.cache_utils import tenant_cache_key
from apps.finance.models import Notification
from apps.accounts.utils import get_dashboard_context
from apps.platform_runtime.helpers import (
    get_effective_flags,
    get_effective_site_settings,
)


usage_logger = logging.getLogger("analytics.usage")

# Typed exceptions for analytics usage logging (§2.4 broad-except policy)
_ANALYTICS_USAGE_LOG_ERRORS = (AttributeError, TypeError, KeyError, ValueError)

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


def _parse_int(
    value: str | None,
    default: int,
    min_val: int | None = None,
    max_val: int | None = None,
) -> int:
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


@staff_member_required(login_url=settings.LOGIN_URL)
def dashboard(request: HttpRequest):
    # Part B.5: Optional response cache. Enable via Feature Control (enable_analytics_dashboard_cache) or analytics_dashboard_cache_seconds > 0.
    site = get_effective_site_settings(request=request)
    flags = get_effective_flags(request)
    cache_ttl = 0
    if flags.get("enable_analytics_dashboard_cache"):
        try:
            cache_ttl = int(flags.get("analytics_dashboard_cache_seconds") or 60)
        except (TypeError, ValueError):
            cache_ttl = 60
    else:
        try:
            cache_ttl = int(flags.get("analytics_dashboard_cache_seconds") or 0)
        except (TypeError, ValueError):
            pass
    cache_key = None
    if cache_ttl > 0:
        from django.core.cache import cache

        cache_key = tenant_cache_key(
            "analytics_dash:"
            + (request.get_full_path().replace("/", "_") or "default"),
            request,
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return HttpResponse(cached, content_type="text/html; charset=utf-8")

    active_year, active_term = get_active_year_and_term()
    if not active_year or not active_term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    year_id = request.GET.get("year") or str(active_year.id)
    term_id = request.GET.get("term") or str(active_term.id)

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id, academic_year=year_obj)

    classroom_id = request.GET.get("classroom")
    specialty_id = request.GET.get("specialty")
    classroom_obj = (
        Classroom.objects.filter(id=classroom_id).first() if classroom_id else None
    )
    specialty_obj = (
        Specialty.objects.filter(id=specialty_id).first() if specialty_id else None
    )

    top_n = _parse_int(
        request.GET.get("top_n"),
        int(site.top_students_default_limit),
        min_val=1,
        max_val=100,
    )
    pass_mark = _parse_decimal(request.GET.get("pass_mark"), site.pass_mark)
    weak_threshold = _parse_decimal(
        request.GET.get("weak_threshold"), site.weak_subject_threshold
    )
    improve_delta = _parse_decimal(
        request.GET.get("improve_delta"), site.improvement_delta_threshold
    )
    use_promotion_rule = (
        request.GET.get("use_promotion_rule") == "1"
        if "use_promotion_rule" in request.GET
        else site.use_promotion_rule_for_pass
    )
    deadline_mode = (
        request.GET.get("deadline_mode") or site.deadline_mode or DEADLINE_MODE_TERM_END
    )

    terms = list(Term.objects.filter(academic_year=year_obj).order_by("start_date"))
    improve_from_id = request.GET.get("improve_from") or (
        str(terms[0].id) if terms else ""
    )
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

    dashboard_context = get_dashboard_context(request.user, "analytics")
    dashboard_settings = dashboard_context.get("dashboard_settings", {})
    allow_custom_layout = dashboard_context.get("allow_custom_layout", False)
    dashboard_layout_url = dashboard_context.get("dashboard_layout_url", "")
    widget_meta_json = dashboard_context.get("widget_meta_json", "")
    available_sidebar_items = [
        {
            "id": "analytics-home",
            "label": "Analytics Home",
            "url": reverse("analytics:dashboard"),
            "icon": "bi-bar-chart-line",
        },
        {
            "id": "analytics-master",
            "label": "Master Sheet",
            "url": reverse("analytics:master_sheet"),
            "icon": "bi-file-earmark-spreadsheet",
        },
        {
            "id": "analytics-deadlines",
            "label": "Grading Deadlines",
            "url": reverse("analytics:deadlines"),
            "icon": "bi-calendar-check",
        },
        {
            "id": "finance-notifications",
            "label": "Finance Notifications",
            "url": reverse("finance:notifications"),
            "icon": "bi-bell",
        },
    ]
    finance_requests_qs = Notification.objects.filter(
        recipient=request.user,
        title__icontains="finance access request",
        is_read=False,
    ).order_by("-created_at")
    finance_request_link = reverse("requests:dashboard")

    # Chart data: weak subjects (horizontal bar)
    weak_for_chart = weak_subject_rows[:10]
    chart_weak_subjects = {
        "type": "bar",
        "data": {
            "labels": [str(row.subject) for row in weak_for_chart],
            "datasets": [
                {
                    "label": "Average",
                    "data": [float(row.average) for row in weak_for_chart],
                    "backgroundColor": "rgba(255, 193, 7, 0.7)",
                    "borderColor": "#ffc107",
                    "borderWidth": 1,
                }
            ],
        },
        "options": {
            "indexAxis": "y",
            "scales": {
                "x": {"max": 100, "beginAtZero": True},
            },
        },
    }

    # Chart data: specialty pass rates (donut). Cap for dashboard (see docs/DASHBOARD_DATA_CAPPING_POLICY.md)
    from apps.dashboard.context import DASHBOARD_CHART_TOP_N

    specialty_for_chart = specialty_rows[:DASHBOARD_CHART_TOP_N]
    chart_specialty_donut = {
        "type": "doughnut",
        "data": {
            "labels": [str(row.specialty) for row in specialty_for_chart],
            "datasets": [
                {
                    "data": [row.passed for row in specialty_for_chart],
                    "backgroundColor": [
                        "rgba(13, 110, 253, 0.8)",
                        "rgba(25, 135, 84, 0.8)",
                        "rgba(255, 193, 7, 0.8)",
                        "rgba(220, 53, 69, 0.8)",
                        "rgba(111, 66, 193, 0.8)",
                        "rgba(13, 202, 240, 0.8)",
                        "rgba(13, 110, 253, 0.8)",
                        "rgba(25, 135, 84, 0.8)",
                        "rgba(255, 193, 7, 0.8)",
                        "rgba(220, 53, 69, 0.8)",
                        "rgba(111, 66, 193, 0.8)",
                        "rgba(13, 202, 240, 0.8)",
                    ][: len(specialty_for_chart)],
                }
            ],
        },
    }

    phase7_de = {
        "eyebrow": "Analytics home",
        "headline_label": "Top-N window",
        "headline_value": top_n,
        "headline_meta": f"{term_obj.label} · {year_obj.name}",
        "metrics": [
            {
                "label": "Weak subjects",
                "value": len(weak_subject_rows),
                "meta": "Below threshold",
                "status": "warn" if weak_subject_rows else "ok",
            },
            {
                "label": "Teacher compliance rows",
                "value": len(teacher_rows),
                "meta": "On deadlines",
                "status": "ok",
            },
            {
                "label": "Students improving",
                "value": len(improvement_rows),
                "meta": "Term-over-term",
                "status": "ok",
            },
        ],
        "urgent_queue": (
            [
                {
                    "title": f"{len(weak_subject_rows)} weak subject signal(s)",
                    "url": (request.path or "") + "#analytics-weak-anchor",
                    "hint": "Prioritize interventions this term.",
                }
            ]
            if weak_subject_rows
            else [
                {
                    "title": "No weak-subject fire drill",
                    "url": "",
                    "hint": "Tune filters or thresholds as needed.",
                }
            ]
        ),
        "next_actions": [
            {"label": "Master sheet", "url": reverse("analytics:master_sheet")},
            {"label": "Grading deadlines", "url": reverse("analytics:deadlines")},
            {"label": "Executive view", "url": reverse("analytics:executive_dashboard")},
        ],
        "activity": [
            {
                "title": "Dashboard context",
                "meta": f"Year {year_obj.name}, term {term_obj.label}",
            }
        ],
    }

    context = {
        "year": year_obj,
        "term": term_obj,
        "phase7_de": phase7_de,
        "chart_weak_subjects_json": json.dumps(chart_weak_subjects),
        "chart_specialty_donut_json": json.dumps(chart_specialty_donut),
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
    context.update(
        {
            "allow_custom_layout": allow_custom_layout,
            "dashboard_settings": dashboard_settings,
            "dashboard_layout_url": dashboard_layout_url,
            "available_sidebar_items": available_sidebar_items,
            "widget_meta_json": widget_meta_json,
            "finance_requests_count": finance_requests_qs.count(),
            "finance_request_notifications": finance_requests_qs[:5],
            "finance_request_link": finance_request_link,
        }
    )
    # Lightweight analytics usage logging (for future tuning of defaults and performance)
    try:
        usage_logger.info(
            "analytics_dashboard_view",
            extra={
                "user_id": getattr(request.user, "id", None),
                "user_role": getattr(request.user, "role", None),
                "year_id": year_obj.id,
                "term_id": term_obj.id,
                "classroom_id": getattr(classroom_obj, "id", None),
                "specialty_id": getattr(specialty_obj, "id", None),
                "top_n": top_n,
                "pass_mark": float(pass_mark),
                "weak_threshold": float(weak_threshold),
                "improve_delta": float(improve_delta),
                "use_promotion_rule": bool(use_promotion_rule),
                "deadline_mode": deadline_mode,
            },
        )
    except _ANALYTICS_USAGE_LOG_ERRORS:
        # Never block the request if usage logging fails
        pass
    response = render(request, "analytics/dashboard.html", context)
    if cache_ttl > 0 and cache_key and response.status_code == 200:
        from django.core.cache import cache

        cache.set(cache_key, response.content, cache_ttl)
    return response


@staff_member_required(login_url=settings.LOGIN_URL)
def master_sheet(request: HttpRequest):
    active_year, active_term = get_active_year_and_term()
    if not active_year or not active_term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    year_id = request.GET.get("year") or str(active_year.id)
    term_id = request.GET.get("term")

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = (
        Term.objects.filter(id=term_id, academic_year=year_obj).first()
        if term_id
        else None
    )

    classroom_id = request.GET.get("classroom")
    specialty_id = request.GET.get("specialty")
    subject_id = request.GET.get("subject")
    teacher_id = request.GET.get("teacher")

    classroom_obj = (
        Classroom.objects.filter(id=classroom_id).first() if classroom_id else None
    )
    specialty_obj = (
        Specialty.objects.filter(id=specialty_id).first() if specialty_id else None
    )
    subject_obj = Subject.objects.filter(id=subject_id).first() if subject_id else None
    teacher_obj = (
        TeacherProfile.objects.filter(id=teacher_id).first() if teacher_id else None
    )

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

    evals = evals.order_by(
        "student__last_name", "student__first_name", "subject_assignment__subject__name"
    )

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="master-grading-sheet.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
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
            ]
        )
        for e in evals:
            writer.writerow(
                [
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
                ]
            )
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
        "teachers": TeacherProfile.objects.select_related("user").order_by(
            "user__last_name"
        ),
        "selected_classroom": classroom_obj,
        "selected_specialty": specialty_obj,
        "selected_subject": subject_obj,
        "selected_teacher": teacher_obj,
        "evals": evals,
        "export_query": export_params.urlencode(),
    }
    return render(request, "analytics/master_sheet.html", context)


@staff_member_required(login_url=settings.LOGIN_URL)
def grading_deadlines(request: HttpRequest):
    """
    Grading deadlines management.
    Uses SubjectAssignment.grading_deadline_at; deadlines can be set per assignment in admin.
    """
    active_year, active_term = get_active_year_and_term()
    if not active_year or not active_term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    year_obj = get_object_or_404(
        AcademicYear, id=request.GET.get("year") or str(active_year.id)
    )
    term_obj = get_object_or_404(
        Term, id=request.GET.get("term") or str(active_term.id), academic_year=year_obj
    )

    deadlines_qs = (
        SubjectAssignment.objects.filter(
            academic_year=year_obj,
            term=term_obj,
            grading_deadline_at__isnull=False,
        )
        .select_related("classroom", "specialty", "subject")
        .order_by("grading_deadline_at")
    )
    deadlines = [
        {
            "subject_assignment": sa,
            "deadline_at": sa.grading_deadline_at,
            "classroom": sa.classroom.name,
            "subject": sa.subject.name,
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


def _can_access_strategic_report(user):
    """Proprietor, Leadership, Admin, or strategic.report permission."""
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = (getattr(user, "role", "") or "").upper()
    if role in ("PROPRIETOR", "LEADERSHIP", "ADMIN"):
        return True
    return getattr(user, "has_feature_permission", lambda _: False)("strategic.report")


@login_required
def strategic_report(request: HttpRequest):
    """Strategic reporting and school roadmap. RBAC: PROPRIETOR, LEADERSHIP, ADMIN, or strategic.report."""
    if not _can_access_strategic_report(request.user):
        return HttpResponseForbidden(
            "You do not have permission to view strategic reporting."
        )
    from apps.people.models import StudentProfile

    school = getattr(request, "school", None)
    active_year, _ = get_active_year_and_term()
    student_qs = StudentProfile.objects.filter(is_active=True)
    teacher_qs = TeacherProfile.objects.filter(is_active=True)
    if school is not None:
        student_qs = student_qs.filter(school=school)
        teacher_qs = teacher_qs.filter(school=school)
    total_students = student_qs.count()
    total_teachers = teacher_qs.count()
    dashboard_context = get_dashboard_context(request.user, "analytics")
    context = {
        "total_students": total_students,
        "total_teachers": total_teachers,
        "active_year": active_year,
        "dashboard_context": dashboard_context,
    }
    return render(request, "analytics/strategic_report.html", context)


@login_required
def forecaster_api(request: HttpRequest):
    """
    Phase Welcome (optional): Academic Forecaster API — anonymized indicators, at-risk hint, principal forecast.
    Returns JSON for request.school; 403 if no school. No PII.
    """
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("School context required.")
    from apps.analytics.forecaster import (
        get_anonymized_indicators,
        at_risk_hint,
        principal_forecast_teachers,
    )

    ratio = _parse_int(request.GET.get("ratio"), 25, min_val=5, max_val=100)
    return JsonResponse(
        {
            "indicators": get_anonymized_indicators(school),
            "at_risk": at_risk_hint(school),
            "principal_forecast": principal_forecast_teachers(
                school, target_ratio=float(ratio)
            ),
        }
    )


@login_required
def at_risk_dashboard(request: HttpRequest):
    """
    At-Risk dashboard: heat map grid (Red/Amber/Green), trend, "Why" column.
    Uses RiskFactor (nightly-computed) and InterventionLog.
    """
    from apps.schools.mixins import get_current_school
    from apps.analytics.models import InterventionLog, RiskFactor, StudentAtRiskSignal

    school = get_current_school(request)
    if not school:
        return HttpResponseForbidden("School context required.")
    role = (getattr(request.user, "role", "") or "").upper()
    if (
        role not in ("ADMIN", "LEADERSHIP", "PRINCIPAL", "TEACHER", "HOD", "DEAN")
        and not request.user.is_staff
    ):
        return HttpResponseForbidden("Not allowed.")

    # Latest risk score per student (dedupe by student_id, keep most recent)
    raw = list(
        RiskFactor.objects.filter(school=school)
        .select_related("student")
        .order_by("-computed_at")[:300]
    )
    by_student = {}
    for r in raw:
        if r.student_id not in by_student:
            by_student[r.student_id] = r
    factors = list(by_student.values())

    interventions = list(
        InterventionLog.objects.filter(
            school=school, status=InterventionLog.Status.ONGOING
        ).select_related("student")[:50]
    )
    ews_signals = list(
        StudentAtRiskSignal.objects.filter(school=school)
        .exclude(status=StudentAtRiskSignal.Status.RESOLVED)
        .exclude(status=StudentAtRiskSignal.Status.DISMISSED)
        .select_related("student_user")[:40]
    )
    return render(
        request,
        "analytics/at_risk_dashboard.html",
        {
            "risk_factors": factors,
            "interventions": interventions,
            "ews_signals": ews_signals,
            "school": school,
        },
    )


def _at_risk_roles_ok(user) -> bool:
    role = (getattr(user, "role", "") or "").upper()
    return (
        role in ("ADMIN", "LEADERSHIP", "PRINCIPAL", "TEACHER", "HOD", "DEAN")
        or user.is_staff
    )


def _flash(request, kind: str, msg: str) -> None:
    """Flash message when MessageMiddleware present (tests / API may omit it)."""
    try:
        if kind == "success":
            messages.success(request, msg)
        else:
            messages.error(request, msg)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        pass


@login_required
@require_POST
def at_risk_intervention_action(request: HttpRequest):
    """
    BR-06: Start / resolve / dismiss intervention from at-risk dashboard (POST).
    """
    from apps.schools.mixins import get_current_school
    from apps.analytics.models import InterventionLog, RiskFactor
    from apps.people.models import StudentProfile

    school = get_current_school(request)
    if not school or not _at_risk_roles_ok(request.user):
        return HttpResponseForbidden("Not allowed.")
    action = (request.POST.get("action") or "").strip().lower()
    if action == "start":
        sid = request.POST.get("student_id")
        if not sid:
            _flash(request, "error", "Missing student.")
            return HttpResponse(
                status=302, headers={"Location": reverse("analytics:at_risk_dashboard")}
            )
        student = get_object_or_404(
            StudentProfile.objects.filter(school=school), pk=sid
        )
        reason = (
            request.POST.get("trigger_reason") or ""
        ).strip() or "At-risk dashboard"
        act = (request.POST.get("action_taken") or "").strip() or "Review scheduled"
        rf = (
            RiskFactor.objects.filter(school=school, student=student)
            .order_by("-computed_at")
            .first()
        )
        if rf:
            reason = f"{reason} (score {rf.score}, {rf.band})"
        log = InterventionLog.objects.create(
            school=school,
            student=student,
            trigger_reason=reason[:255],
            action_taken=act[:100],
            status=InterventionLog.Status.ONGOING,
        )
        try:
            from apps.platform_runtime.events import emit_platform_event

            emit_platform_event(
                "ews_intervention_started",
                {
                    "intervention_id": str(log.id),
                    "student_id": str(student.id),
                    "school_id": str(school.id),
                },
                tenant_id=str(school.id),
                school_id=school.id,
            )
        except (OSError, TypeError, ValueError, DatabaseError):
            pass
        if getattr(student, "user_id", None):
            from apps.analytics.models import StudentAtRiskSignal

            StudentAtRiskSignal.objects.filter(
                school=school, student_user_id=student.user_id
            ).update(status=StudentAtRiskSignal.Status.IN_INTERVENTION)
        _flash(request, "success", "Intervention logged.")
    elif action == "resolve":
        lid = request.POST.get("intervention_id")
        log = get_object_or_404(InterventionLog, pk=lid, school=school)
        log.status = InterventionLog.Status.RESOLVED
        log.resolved_at = timezone.now()
        log.save(update_fields=["status", "resolved_at"])
        su = getattr(log.student, "user_id", None)
        if su:
            from apps.analytics.models import StudentAtRiskSignal

            StudentAtRiskSignal.objects.filter(
                school=school, student_user_id=su
            ).update(status=StudentAtRiskSignal.Status.RESOLVED)
        _flash(request, "success", "Marked resolved.")
    elif action == "dismiss":
        lid = request.POST.get("intervention_id")
        log = get_object_or_404(InterventionLog, pk=lid, school=school)
        log.status = InterventionLog.Status.DISMISSED
        log.dismissed_at = timezone.now()
        log.dismissed_by = request.user
        log.save(update_fields=["status", "dismissed_at", "dismissed_by"])
        su = getattr(log.student, "user_id", None)
        if su:
            from apps.analytics.models import StudentAtRiskSignal

            StudentAtRiskSignal.objects.filter(
                school=school, student_user_id=su
            ).update(status=StudentAtRiskSignal.Status.DISMISSED)
        _flash(request, "success", "Dismissed.")
    else:
        _flash(request, "error", "Unknown action.")
    return redirect("analytics:at_risk_dashboard")


@login_required
def executive_dashboard(request: HttpRequest):
    """
    Unified Executive Dashboard: Finance + HR + student outcomes (ROI view).
    Stub: links to existing dashboards and key metrics.
    """
    from apps.schools.mixins import get_current_school

    school = get_current_school(request)
    if not school:
        return HttpResponseForbidden("School context required.")
    role = (getattr(request.user, "role", "") or "").upper()
    if (
        role not in ("ADMIN", "LEADERSHIP", "PRINCIPAL", "PROPRIETOR")
        and not request.user.is_staff
    ):
        return HttpResponseForbidden("Not allowed.")
    return render(request, "analytics/executive_dashboard.html", {"school": school})
