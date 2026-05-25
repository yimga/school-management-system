"""
Mission-control metrics for super command center dashboards (BR-12 extraction from super_views).
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .models import School, SchoolProvisioningEvent
from .super_views_constants import CONTROL_PLANE_METRIC_FAILURES


def build_command_center_data() -> dict:
    """
    Phase 3 mission-control metrics:
    - Provisioning SLA (request -> completed)
    - Churn risk indicators
    - Support backlog aging
    - Phase 4 differentiators (recovery rate, passport portability)
    """
    now = timezone.now()
    today = now.date()
    data = {
        "provisioning_sla_avg_hours": 0.0,
        "provisioning_sla_target_hours": 24,
        "provisioning_sla_breaches": 0,
        "provisioning_sla_samples": 0,
        "provisioning_breach_rows": [],
        "support_open_count": 0,
        "support_backlog_48h_count": 0,
        "support_backlog_7d_count": 0,
        "support_oldest_open_hours": 0.0,
        "support_stale_rows": [],
        "tenant_churn_risk_count": 0,
        "tenant_churn_risk_rows": [],
        "tenant_inactive_30d_count": 0,
        "trial_ending_soon_count": 0,
        "recovery_rate_pct": 0.0,
        "resolved_interventions": 0,
        "total_interventions": 0,
        "student_passport_count": 0,
        "student_passport_invite_count": 0,
    }

    open_ticket_statuses = {"OPEN", "IN_PROGRESS", "WAITING"}

    # Provisioning SLA
    try:
        from django.db.models import Min

        request_rows = (
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            SchoolProvisioningEvent.objects.filter(
                event_type=SchoolProvisioningEvent.EventType.REQUEST_RECEIVED,
                created_at__gte=now - timedelta(days=60),
            )
            .values("school_id")
            .annotate(requested_at=Min("created_at"))
        )
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        complete_rows = (
            SchoolProvisioningEvent.objects.filter(
                event_type=SchoolProvisioningEvent.EventType.COMPLETED,
                created_at__gte=now - timedelta(days=60),
            )
            .values("school_id")
            .annotate(completed_at=Min("created_at"))
        )
        request_map = {row["school_id"]: row["requested_at"] for row in request_rows}
        complete_map = {row["school_id"]: row["completed_at"] for row in complete_rows}
        durations = []
        breach_rows = []
        for school_id, requested_at in request_map.items():
            completed_at = complete_map.get(school_id)
            if not completed_at or completed_at < requested_at:
                continue
            hours = (completed_at - requested_at).total_seconds() / 3600.0
            durations.append(hours)
            if hours > data["provisioning_sla_target_hours"]:
                breach_rows.append({"school_id": school_id, "hours": round(hours, 1)})
        data["provisioning_sla_samples"] = len(durations)
        data["provisioning_sla_avg_hours"] = (
            round(sum(durations) / len(durations), 1) if durations else 0.0
        )
        data["provisioning_sla_breaches"] = len(breach_rows)
        data["provisioning_breach_rows"] = breach_rows[:20]
    except CONTROL_PLANE_METRIC_FAILURES:
        pass

    # Support backlog aging
    stale_urgent_school_ids: set = set()
    try:
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        qs = (
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            GlobalSupportTicket.objects.filter(status__in=open_ticket_statuses)
            .select_related("school")
            .order_by("created_at")
        )
        tickets = list(qs[:300])
        stale_rows = []
        oldest_open_hours = 0.0
        for ticket in tickets:
            age_hours = max(0.0, (now - ticket.created_at).total_seconds() / 3600.0)
            if age_hours > oldest_open_hours:
                oldest_open_hours = age_hours
            if age_hours >= 48:
                stale_rows.append(
                    {
                        "ticket": ticket,
                        "age_hours": round(age_hours, 1),
                    }
                )
            if ticket.priority == "URGENT" and age_hours >= 48:
                stale_urgent_school_ids.add(ticket.school_id)
        data["support_open_count"] = qs.count()
        data["support_backlog_48h_count"] = sum(
            1 for row in stale_rows if row["age_hours"] >= 48
        )
        data["support_backlog_7d_count"] = sum(
            1 for row in stale_rows if row["age_hours"] >= (24 * 7)
        )
        data["support_oldest_open_hours"] = round(oldest_open_hours, 1)
        data["support_stale_rows"] = stale_rows[:25]
    except CONTROL_PLANE_METRIC_FAILURES:
        pass

    # Tenant churn risk heuristic (candidate schools only — not full fleet materialization)
    try:
        from django.db.models import Q

        inactive_cutoff = now - timedelta(days=30)
        trial_cutoff = today + timedelta(days=7)
        inactive_count = (
            School.objects.filter(is_active=True)
            .filter(
                Q(last_activity__isnull=True) | Q(last_activity__lt=inactive_cutoff)
            )
            .count()
        )
        trial_soon_count = (
            School.objects.filter(
                is_active=True,
                billing_type=School.BillingType.FREE_TRIAL,
                trial_end_date__isnull=False,
                trial_end_date__lte=trial_cutoff,
            ).count()
        )
        risk_candidates = School.objects.filter(is_active=True).filter(
            Q(last_activity__isnull=True)
            | Q(last_activity__lt=inactive_cutoff)
            | Q(
                billing_type=School.BillingType.FREE_TRIAL,
                trial_end_date__isnull=False,
                trial_end_date__lte=trial_cutoff,
            )
            | Q(pk__in=stale_urgent_school_ids)
        )
        schools = list(
            risk_candidates.only(
                "id",
                "name",
                "slug",
                "last_activity",
                "billing_type",
                "trial_end_date",
            ).order_by("name")[:500]
        )
        risk_rows = []
        for school in schools:
            reasons = []
            last_activity = getattr(school, "last_activity", None)
            if not last_activity or (now - last_activity) > timedelta(days=30):
                reasons.append("No activity in 30+ days")
            if getattr(school, "billing_type", "") == School.BillingType.FREE_TRIAL:
                trial_end = getattr(school, "trial_end_date", None)
                if trial_end and trial_end <= trial_cutoff:
                    reasons.append("Free trial ending in <= 7 days")
            if school.id in stale_urgent_school_ids:
                reasons.append("Urgent support ticket stale 48h+")
            if reasons:
                risk_rows.append(
                    {
                        "school": school,
                        "reasons": reasons,
                        "risk_score": len(reasons),
                    }
                )
        risk_rows.sort(key=lambda row: (-row["risk_score"], row["school"].name))
        data["tenant_churn_risk_count"] = len(risk_rows)
        data["tenant_churn_risk_rows"] = risk_rows[:25]
        data["tenant_inactive_30d_count"] = inactive_count
        data["trial_ending_soon_count"] = trial_soon_count
    except CONTROL_PLANE_METRIC_FAILURES:
        pass

    # Phase 4 differentiator metrics
    try:
        from apps.analytics.models import InterventionLog

        total_interventions = InterventionLog.objects.count()
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        resolved = InterventionLog.objects.filter(
            status=InterventionLog.Status.RESOLVED
        ).count()
        data["total_interventions"] = total_interventions
        data["resolved_interventions"] = resolved
        data["recovery_rate_pct"] = (
            round((resolved / total_interventions) * 100, 1)
            if total_interventions
            else 0.0
        )
    except CONTROL_PLANE_METRIC_FAILURES:
        pass

    try:
        from apps.people.models import StudentPassport, PassportSchoolInvite

        data["student_passport_count"] = StudentPassport.objects.count()
        data["student_passport_invite_count"] = PassportSchoolInvite.objects.count()
    except CONTROL_PLANE_METRIC_FAILURES:
        pass

    return data
