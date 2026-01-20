from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Iterable, List
import re

from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import SubjectAssignment
from apps.academics.services import get_active_year_and_term
from apps.analytics.models import GradingDeadline
from apps.evals.models import Evaluation
from apps.evals.services import completion_for_assignment
from apps.finance.models import Invoice, PaymentReminder
from apps.people.models import StudentProfile
from apps.payroll.models import LeaveRequest, Payslip, PayrollEmployee
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
        "analytics": _analytics_insights(students, year, term),
        "referral": _referral_overview(students),
    }


def _referral_overview(students: list[StudentProfile]):
    if not students:
        return {
            "code": None,
            "total_codes": 0,
            "completeness_avg": 0,
            "note": "Referral codes appear after student onboarding.",
        }

    codes = [s.referral_code for s in students if s.referral_code]
    code = codes[0] if codes else None
    completeness_vals = [s.parent_completeness for s in students if hasattr(s, "parent_completeness")]
    completeness_avg = int(round(sum(completeness_vals) / len(completeness_vals))) if completeness_vals else 0
    return {
        "code": code,
        "total_codes": len(codes),
        "completeness_avg": completeness_avg,
        "note": "Share your referral code during onboarding to unlock bonuses.",
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


_PHONE_CLEANER = re.compile(r"[^\d]")


def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = _PHONE_CLEANER.sub("", phone)
    return digits if digits else None


def _communication_center():
    site = SiteSettings.get_solo()
    items = []
    links: list[dict[str, str]] = []

    if site.company_phone:
        items.append(
            {"type": "phone", "label": "Call customer service", "value": site.company_phone}
        )
        phone_digits = _normalize_phone(site.company_phone)
        if phone_digits:
            links.append(
                {
                    "label": "Call customer service",
                    "url": f"tel:+{phone_digits}",
                    "icon": "bi-telephone",
                }
            )

    if site.company_email:
        items.append({"type": "email", "label": "Email support", "value": site.company_email})
        links.append(
            {
                "label": "Email customer service",
                "url": f"mailto:{site.company_email}",
                "icon": "bi-envelope",
            }
        )

    whatsapp = (
        Integration.objects.filter(enabled=True, name__icontains="whatsapp")
        .order_by("updated_at")
        .first()
    )
    if whatsapp:
        wa_number = whatsapp.config.get("phone") or whatsapp.config.get("whatsapp_number")
        wa_digits = _normalize_phone(wa_number)
        if wa_number:
            items.append({"type": "whatsapp", "label": whatsapp.name, "value": wa_number})
        if wa_digits:
            links.insert(
                0,
                {
                    "label": f"Chat on {whatsapp.name}",
                    "url": f"https://wa.me/{wa_digits}",
                    "icon": "bi-whatsapp",
                    "target": "_blank",
                },
            )

    other_integrations = (
        Integration.objects.filter(enabled=True)
        .exclude(pk=whatsapp.pk if whatsapp else None)
        .order_by("-updated_at")
    )
    for integration in other_integrations:
        config_url = integration.config.get("url")
        if not config_url:
            continue
        links.append(
            {
                "label": integration.name,
                "url": config_url,
                "icon": "bi-box-arrow-up-right",
                "target": "_blank",
            }
        )

    primary_action = links[0] if links else None
    return {
        "items": items,
        "links": links,
        "primary_action": primary_action,
        "cta": primary_action["label"] if primary_action else "Connect with us",
        "note": "We also send reminders via SMS/email; update preferences in portal settings.",
    }


def _analytics_insights(students, year, term):
    if not students or not year or not term:
        return {
            "highlights": [],
            "lowlights": [],
            "label": "Analytics populate as teachers publish evaluations.",
        }

    evals = Evaluation.objects.filter(
        student__in=students,
        academic_year=year,
        term=term,
    ).select_related("subject_assignment__subject")

    subject_totals: dict[str, dict[str, float]] = {}
    for e in evals:
        subj = e.subject_assignment.subject.name if e.subject_assignment_id else "General"
        subject_totals.setdefault(subj, {"total": 0.0, "count": 0})
        subject_totals[subj]["total"] += float(e.total_score or 0.0)
        subject_totals[subj]["count"] += 1

    averages = []
    for subject, data in subject_totals.items():
        if data["count"] == 0:
            continue
        averages.append({"subject": subject, "average": round(data["total"] / data["count"], 2)})

    averages.sort(key=lambda x: x["average"], reverse=True)

    return {
        "highlights": averages[:3],
        "lowlights": averages[-3:],
        "label": "Top/bottom subjects based on published evaluations.",
    }


def _assignment_completion_spotlight(assignments, term) -> List[dict]:
    spotlight = []
    for assignment in assignments:
        sa = assignment.subject_assignment
        stats = completion_for_assignment(sa, term)
        spotlight.append({
            "label": f"{sa.subject.name} \u2013 {sa.classroom.name}",
            "pct": stats.completion_pct,
            "pending": stats.pending,
            "total": stats.total,
            "url": reverse("evals:teacher_marks_entry") + f"?subject_assignment_id={sa.id}",
        })
    spotlight.sort(key=lambda x: x["pct"])
    return spotlight[:4]


def _teacher_finance_block(teacher):
    if not getattr(teacher, "allow_finance_panel", False):
        return {}

    payroll_profile = PayrollEmployee.objects.filter(user=teacher.user).first()
    if not payroll_profile:
        return {"label": "No payroll profile yet."}

    latest_payslip = payroll_profile.payslips.select_related("payroll_run").first()
    pending_leaves = payroll_profile.leave_requests.filter(status=LeaveRequest.Status.PENDING).count()

    return {
        "net_pay": latest_payslip.net_pay if latest_payslip else None,
        "status": latest_payslip.status if latest_payslip else "N/A",
        "period": f"{latest_payslip.payroll_run.period_start} \u2192 {latest_payslip.payroll_run.period_end}"
        if latest_payslip else "",
        "next_pay": getattr(teacher, "next_pay_date", None),
        "notes": getattr(teacher, "paystub_notes", ""),
        "pending_leaves": pending_leaves,
    }


def teacher_dashboard_widget_data(assignments, progress, year, term, teacher=None):
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
        {"label": "Enter marks", "url": reverse("evals:teacher_marks_entry")},
        {"label": "View marks", "url": reverse("evals:teacher_marks_list")},
        {"label": "My assignments", "url": reverse("evals:teacher_dashboard")},
    ]

    completion = {
        "overall_pct": completion_pct,
        "filled": filled,
        "total": total_slots,
        "pending": missing,
        "spotlight": _assignment_completion_spotlight(assignments, term),
    }

    attendance = _attendance_snapshot([a.subject_assignment.classroom for a in assignments], year, term) if assignments else None

    return {
        "completion_pct": completion_pct,
        "completion": completion,
        "missing": missing,
        "assignments_count": len(assignments),
        "links": links,
        "upcoming": upcoming,
        "tasks": {
          "pending_evaluations": missing,
          "description": "Missing marks show what still needs entry.",
        },
        "communication": _communication_center(),
        "finance": _teacher_finance_block(teacher) if teacher else {},
        "attendance": attendance,
    }
