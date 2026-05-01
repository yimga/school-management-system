"""
Operational insights — structured decisions (severity, explanation, action, audience, surfaces).

All computations use tenant-scoped ORM queries (no raw SQL).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

# Decision dashboard routing (Phase 4).
SURFACE_SCHOOL_HEALTH = "school_health"
SURFACE_REVENUE = "revenue"
SURFACE_ENGAGEMENT = "engagement"
SURFACE_RISK = "risk"
SURFACE_FOUNDER = "founder"


def filter_insights_by_surface(
    insights: list[dict[str, Any]], surface: str
) -> list[dict[str, Any]]:
    return [i for i in insights if surface in i.get("surfaces", [])]


def build_insights_for_school(school_id: str, *, user=None) -> list[dict[str, Any]]:
    """
    Return insight cards for a single school. Caller must enforce tenant scope.
    Each card includes ``surfaces`` for dashboard routing.
    """
    insights: list[dict[str, Any]] = []

    try:
        from apps.finance.models import Invoice

        overdue = (
            Invoice.objects.filter(school_id=school_id, status="OVERDUE")
            .aggregate(t=Sum("balance_amount"))
            .get("t")
            or 0
        )
        if overdue and float(overdue) > 0:
            insights.append(
                {
                    "id": "finance_overdue_balance",
                    "severity": "warning",
                    "title": "Overdue fee balance",
                    "explanation": "Outstanding invoices marked overdue need collection or settlement.",
                    "primary_action": {
                        "label": "Open finance invoices",
                        "path": "/finance/invoices/",
                    },
                    "audience": "finance_staff",
                    "surfaces": [SURFACE_REVENUE, SURFACE_RISK],
                }
            )

        by_class = (
            Invoice.objects.filter(school_id=school_id, status__in=("PARTIAL", "OVERDUE"))
            .values("student__classroom_id")
            .annotate(total=Sum("balance_amount"))
            .order_by("-total")[:5]
        )
        top = list(by_class)
        if top and top[0].get("total"):
            cid = top[0].get("student__classroom_id")
            insights.append(
                {
                    "id": "unpaid_balances_by_class",
                    "severity": "info",
                    "title": "Unpaid balances by class signal",
                    "explanation": (
                        f"Classroom id {cid} shows the largest unpaid invoice balance total "
                        "(concentration risk for collection)."
                    ),
                    "primary_action": {
                        "label": "Review class billing",
                        "path": "/finance/invoices/",
                    },
                    "audience": "bursar",
                    "surfaces": [SURFACE_REVENUE],
                }
            )
    except Exception:
        pass

    try:
        from apps.evals.models import Evaluation

        at_risk = Evaluation.objects.filter(
            school_id=school_id, final_score__lt=50, final_score__isnull=False
        ).count()
        if at_risk > 0:
            insights.append(
                {
                    "id": "students_academic_risk",
                    "severity": "danger",
                    "title": "Students at academic risk",
                    "explanation": f"{at_risk} evaluation rows have final score under 50.",
                    "primary_action": {
                        "label": "Open marks / evaluations",
                        "path": "/evals/",
                    },
                    "audience": "academic_staff",
                    "surfaces": [SURFACE_RISK],
                }
            )

        unpublished_teachers = (
            Evaluation.objects.filter(
                school_id=school_id, final_score__isnull=True
            )
            .values("teacher_id")
            .distinct()
            .count()
        )
        if unpublished_teachers > 0:
            insights.append(
                {
                    "id": "teachers_missing_final_marks",
                    "severity": "warning",
                    "title": "Teachers with unpublished marks",
                    "explanation": (
                        f"{unpublished_teachers} teacher(s) have at least one evaluation "
                        "row without a final score."
                    ),
                    "primary_action": {
                        "label": "Complete marking",
                        "path": "/evals/",
                    },
                    "audience": "academic_lead",
                    "surfaces": [SURFACE_RISK],
                }
            )
    except Exception:
        pass

    try:
        from apps.academics.models import Attendance

        today = timezone.localdate()
        absent_today = Attendance.objects.filter(
            school_id=school_id, date=today, status="absent"
        ).count()
        if absent_today > 25:
            insights.append(
                {
                    "id": "attendance_anomaly_absences",
                    "severity": "warning",
                    "title": "Attendance anomaly (absences)",
                    "explanation": f"{absent_today} absence records today — verify sessions and notices.",
                    "primary_action": {
                        "label": "Review attendance",
                        "path": "/portal/teacher/attendance/",
                    },
                    "audience": "attendance_team",
                    "surfaces": [SURFACE_ENGAGEMENT, SURFACE_RISK],
                }
            )
    except Exception:
        pass

    try:
        from apps.finance.models import Payment

        trend = (
            Payment.objects.filter(school_id=school_id, status="completed")
            .annotate(m=TruncMonth("paid_at"))
            .values("m")
            .annotate(total=Sum("amount"))
            .order_by("-m")[:3]
        )
        if trend:
            insights.append(
                {
                    "id": "revenue_trend_recent",
                    "severity": "info",
                    "title": "Revenue trend (payments)",
                    "explanation": "Rolling monthly completed payments (last buckets available).",
                    "primary_action": {
                        "label": "Finance dashboard",
                        "path": "/finance/",
                    },
                    "audience": "leadership",
                    "data": {"months": [dict(x) for x in trend]},
                    "surfaces": [SURFACE_REVENUE],
                }
            )

        cutoff = timezone.now() - timedelta(days=90)
        had_any = Payment.objects.filter(
            school_id=school_id, status="completed"
        ).exists()
        has_recent = Payment.objects.filter(
            school_id=school_id, status="completed", paid_at__gte=cutoff
        ).exists()
        if had_any and not has_recent:
            insights.append(
                {
                    "id": "churn_risk_payments",
                    "severity": "warning",
                    "title": "Churn risk (fee payments)",
                    "explanation": (
                        "No completed payment in the last 90 days despite prior payment history."
                    ),
                    "primary_action": {
                        "label": "Review billing and outreach",
                        "path": "/finance/",
                    },
                    "audience": "leadership",
                    "surfaces": [SURFACE_REVENUE, SURFACE_RISK],
                }
            )
    except Exception:
        pass

    try:
        from apps.schools.activation_gate import school_activation_gate_pending
        from apps.schools.models import School

        school = School.objects.filter(pk=school_id).first()
        if school and school_activation_gate_pending(school):
            insights.append(
                {
                    "id": "onboarding_activation_pending",
                    "severity": "warning",
                    "title": "Onboarding / activation pending",
                    "explanation": "Activation gate indicates a first operational milestone is not yet recorded.",
                    "primary_action": {
                        "label": "Complete first operational action",
                        "path": "/activation/first-action/",
                    },
                    "audience": "school_admin",
                    "surfaces": [SURFACE_SCHOOL_HEALTH],
                }
            )
    except Exception:
        pass

    try:
        from apps.marketplace.models import AppInstallation
        from apps.schools.models import School

        school = School.objects.filter(pk=school_id).only("created_at").first()
        if school and school.created_at:
            age = timezone.now() - school.created_at
            if age > timedelta(days=14):
                n_inst = AppInstallation.objects.filter(school_id=school_id).count()
                if n_inst < 2:
                    insights.append(
                        {
                            "id": "onboarding_low_marketplace_engagement",
                            "severity": "info",
                            "title": "School may need onboarding help (apps)",
                            "explanation": (
                                "Few marketplace installations for a tenant older than 14 days — "
                                "consider guided setup or catalog review."
                            ),
                            "primary_action": {
                                "label": "Open marketplace",
                                "path": "/marketplace/",
                            },
                            "audience": "success_team",
                            "surfaces": [SURFACE_SCHOOL_HEALTH],
                        }
                    )
    except Exception:
        pass

    return insights


def build_global_rollup_insights() -> list[dict[str, Any]]:
    """Founder / platform host rollup — coarse metrics only (ORM)."""
    insights: list[dict[str, Any]] = []
    try:
        from apps.schools.activation_gate import school_activation_gate_pending
        from apps.schools.models import MarketingFunnelEvent, School

        schools = School.objects.filter(is_active=True).count()
        insights.append(
            {
                "id": "global_active_schools",
                "severity": "info",
                "title": "Active schools",
                "explanation": f"{schools} active schools on platform.",
                "primary_action": {"label": "Control plane", "path": "/super/"},
                "audience": "founder",
                "surfaces": [SURFACE_FOUNDER],
            }
        )

        week_ago = timezone.now() - timedelta(days=7)
        signups = MarketingFunnelEvent.objects.filter(
            event_type="signup_completed", created_at__gte=week_ago
        ).count()
        insights.append(
            {
                "id": "global_signup_velocity",
                "severity": "info",
                "title": "Recent signups (7d)",
                "explanation": f"{signups} signup_completed funnel events in the last 7 days.",
                "primary_action": {"label": "Growth funnel", "path": "/super/"},
                "audience": "founder",
                "surfaces": [SURFACE_FOUNDER],
            }
        )

        pending_n = 0
        for s in School.objects.filter(is_active=True).only("pk", "settings")[:400]:
            try:
                if school_activation_gate_pending(s):
                    pending_n += 1
            except Exception:
                continue
        if pending_n:
            insights.append(
                {
                    "id": "global_activation_backlog_sample",
                    "severity": "warning",
                    "title": "Activation backlog (sampled)",
                    "explanation": (
                        f"{pending_n} of the first 400 active schools still show activation gate pending."
                    ),
                    "primary_action": {"label": "Review tenants", "path": "/super/"},
                    "audience": "founder",
                    "surfaces": [SURFACE_FOUNDER],
                }
            )
    except Exception:
        pass
    return insights
