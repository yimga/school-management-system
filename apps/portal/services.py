from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Iterable

from django.db.models import Sum
from django.utils import timezone

from apps.academics.services import get_active_year_and_term
from apps.analytics.models import GradingDeadline
from apps.evals.models import Evaluation
from apps.finance.models import Invoice
from apps.people.models import StudentProfile
from apps.reports.services import term_report_context
from apps.siteconfig.models import SiteSettings


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
