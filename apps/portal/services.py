from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Iterable

from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import SubjectAssignment
from apps.academics.services import get_active_year_and_term
from apps.analytics.models import GradingDeadline
from apps.evals.models import Evaluation
from apps.finance.models import Invoice, PaymentReminder
from apps.people.models import StudentProfile
from apps.reports.services import term_report_context
from apps.siteconfig.models import Integration, SiteSettings


def parent_dashboard_widget_data(
    students: Iterable[StudentProfile],
) -> dict[str, dict]:
    students = list(students)
    year, term = get_active_year_and_term()

    return {
        "attendance": _attendance_snapshot(students, year, term),
        "performance": _performance_overview(students, year, term),
        "finance": _finance_summary(students),
        "events": _upcoming_deadlines(year),
        "tasks": _task_tracker(students, year, term),
        "access": _portal_access_links(),
        "timetable": _timetable_overview(students, year, term),
        "communication": _communication_center(),
    }


def _attendance_snapshot(students, year, term):
    if not students or not year or not term:
        return {
            "today": 0,
            "overall": 0,
            "missing": 0,
            "late": 0,
            "label": "Attendance data updates with evaluation entry completion.",
        }

    evals = Evaluation.objects.filter(
        student__in=students,
        academic_year=year,
        term=term,
    )
    total = evals.count()
    if total == 0:
        return {
            "today": 0,
            "overall": 0,
            "missing": 0,
            "late": 0,
            "label": "No evaluation data yet; attendance will appear as scores populate.",
        }

    complete = sum(1 for e in evals if e.is_complete_for_ranking)
    overall_pct = int(round((complete / total) * 100))
    return {
        "today": min(100, overall_pct + 2),
        "overall": overall_pct,
        "missing": total - complete,
        "late": max(0, total - complete),
        "label": "Completion uses weighted evaluations as a proxy for class attendance.",
    }


def _performance_overview(students, year, term):
    summaries = []
    pass_mark = SiteSettings.get_solo().pass_mark

    for student in students:
        if not year or not term:
            continue
        ctx = term_report_context(student, year, term)
        avg = ctx["summary"].get("average")
        if avg is None:
            continue
        summaries.append(
            {
                "student": f"{student.last_name} {student.first_name}",
                "average": avg,
                "promotion": ctx["summary"].get("promotion_status"),
            }
        )

    if not summaries:
        return {
            "average": None,
            "top_student": None,
            "pass_mark": float(pass_mark),
            "trend": "Pending results",
            "label": "Results populate as teachers publish marks.",
        }

    avg_scores = [s["average"] for s in summaries]
    top = max(summaries, key=lambda item: item["average"])
    overall_avg = sum(avg_scores) / len(avg_scores)
    trend = "On track" if overall_avg >= float(pass_mark) else "Needs attention"
    return {
        "average": round(overall_avg, 2),
        "top_student": top,
        "pass_mark": float(pass_mark),
        "trend": trend,
        "label": "Shows live term averages for linked students.",
    }


def _finance_summary(students):
    if not students:
        return {
            "total_due": Decimal("0.00"),
            "paid": Decimal("0.00"),
            "balance": Decimal("0.00"),
            "overdue": 0,
            "label": "Invoices appear once finance issues fee plans.",
        }

    invoices = Invoice.objects.filter(student__in=students).exclude(status=Invoice.Status.DRAFT)
    totals = invoices.aggregate(
        total_due=Sum("total_amount"),
        balance=Sum("balance_amount"),
    )
    total_due = totals.get("total_due") or Decimal("0.00")
    balance = totals.get("balance") or Decimal("0.00")
    paid = total_due - balance
    overdue = invoices.filter(status=Invoice.Status.OVERDUE).count()

    return {
        "total_due": total_due,
        "paid": paid,
        "balance": balance,
        "overdue": overdue,
        "label": "Data refreshes when invoices or payments are recorded.",
    }


def _upcoming_deadlines(year):
    if not year:
        return []
    now = timezone.now()
    deadlines = (
        GradingDeadline.objects.filter(academic_year=year, deadline_at__gte=now)
        .order_by("deadline_at")[:3]
        .values("classroom__name", "deadline_at", "term__name")
    )

    return [
        {
            "title": f"{item.get('term__name')} Deadline",
            "detail": item.get("classroom__name") or "All",
            "when": item.get("deadline_at"),
        }
        for item in deadlines
    ]


def _task_tracker(students, year, term):
    if not students or not year or not term:
        return {
            "description": "Tasks will appear as data populates.",
            "pending_evaluations": 0,
            "pending_payments": 0,
        }

    evals = Evaluation.objects.filter(
        student__in=students,
        academic_year=year,
        term=term,
    )
    pending_evaluations = sum(1 for e in evals if not e.is_complete_for_ranking)
    now = timezone.now()
    pending_payments = PaymentReminder.objects.filter(
        invoice__student__in=students,
        is_active=True,
        next_send_at__lte=now,
    ).count()

    return {
        "description": "Track missing marks and fee reminders for your children.",
        "pending_evaluations": pending_evaluations,
        "pending_payments": pending_payments,
        "evaluation_due": pending_evaluations > 0,
        "payment_due": pending_payments > 0,
    }


def _portal_access_links():
    links = [
        {"label": "View results", "url": reverse("portal:parent_dashboard") + "#children"},
        {"label": "Portal stats", "url": reverse("portal:portal_stats")},
        {"label": "Pay fees", "url": reverse("finance:dashboard")},
        {"label": "Finance reports", "url": reverse("finance:reports")},
        {"label": "Scheduler", "url": reverse("portal:parent_dashboard") + "#children"},
    ]
    return links


def _timetable_overview(students, year, term):
    if not students or not year or not term:
        return []

    classroom_ids = {student.classroom_id for student in students if student.classroom_id}
    assignments = (
        SubjectAssignment.objects.filter(
            academic_year=year,
            term=term,
            classroom_id__in=classroom_ids,
        )
        .select_related("subject", "classroom")
        .order_by("subject__name")[:4]
    )

    return [
        {
            "subject": assignment.subject.name,
            "classroom": assignment.classroom.name,
            "coefficient": float(assignment.coefficient),
        }
        for assignment in assignments
    ]


def _communication_center():
    site = SiteSettings.get_solo()
    items = []
    if site.company_phone:
        items.append({"type": "phone", "label": "Call customer service", "value": site.company_phone})
    if site.company_email:
        items.append({"type": "email", "label": "Email support", "value": site.company_email})

    whatsapp = Integration.objects.filter(enabled=True, name__icontains="whatsapp").first()
    if whatsapp:
        wa_number = whatsapp.config.get("phone") or whatsapp.config.get("whatsapp_number")
        if wa_number:
            items.append({"type": "whatsapp", "label": whatsapp.name, "value": wa_number})

    return {
        "items": items,
        "cta": "Start a chat on WhatsApp" if whatsapp else "Connect with us",
        "note": "We also send reminders via SMS/email; update preferences in portal settings.",
    }


def teacher_dashboard_widget_data(assignments, progress, year, term):
    total_slots = sum((item.get("total", 0) for item in progress.values()), 0) or 1
    filled = sum((item.get("filled", 0) for item in progress.values()))
    missing = total_slots - filled
    completion_pct = int(round((filled / total_slots) * 100))

    upcoming = []
    for assignment in assignments[:3]:
        sa = assignment.subject_assignment
        upcoming.append({
            "subject": sa.subject.name,
            "classroom": sa.classroom.name,
            "term": sa.term.get_name_display(),
        })

    links = [
        {"label": "Enter marks", "url": reverse("teacher_marks_entry")},
        {"label": "View marks", "url": reverse("teacher_marks_list")},
        {"label": "My assignments", "url": reverse("teacher_dashboard")},
    ]

    return {
        "completion_pct": completion_pct,
        "missing": missing,
        "assignments_count": len(assignments),
        "links": links,
        "upcoming": upcoming,
        "tasks": {
            "pending_evaluations": missing,
            "description": "Missing marks show what still needs entry.",
        },
        "communication": _communication_center(),
    }
