"""
Founder-facing business value metrics for North Star evidence.
"""

from __future__ import annotations

from apps.schools.models import School


def get_business_value_snapshot() -> dict[str, int]:
    """
    Lightweight conversion/onboarding/monetization signals from live models.
    Returns zeros when optional billing models are unavailable.
    """
    total_schools = School.objects.count()
    approved_schools = School.objects.filter(is_approved=True).count()
    active_schools = School.objects.filter(is_active=True).count()

    onboarding_in_progress = School.objects.filter(is_active=True, is_approved=False).count()

    billing_watchlist = 0
    paid_subscriptions = 0
    try:
        from apps.billing.models import TenantSubscription

        billing_watchlist = TenantSubscription.objects.filter(
            status__in=[
                TenantSubscription.Status.PAST_DUE,
                TenantSubscription.Status.SUSPENDED,
            ]
        ).count()
        paid_subscriptions = TenantSubscription.objects.filter(
            status=TenantSubscription.Status.ACTIVE
        ).count()
    except Exception:
        billing_watchlist = 0
        paid_subscriptions = 0

    revenue_share_draft = 0
    try:
        from apps.billing.models import RevenueSharePayout

        revenue_share_draft = RevenueSharePayout.objects.filter(
            status=RevenueSharePayout.Status.DRAFT
        ).count()
    except Exception:
        revenue_share_draft = 0

    activation_rate_pct = int((approved_schools / total_schools) * 100) if total_schools else 0
    paid_penetration_pct = int((paid_subscriptions / active_schools) * 100) if active_schools else 0

    return {
        "schools_total": total_schools,
        "schools_approved": approved_schools,
        "schools_active": active_schools,
        "onboarding_in_progress": onboarding_in_progress,
        "activation_rate_pct": activation_rate_pct,
        "paid_subscriptions": paid_subscriptions,
        "paid_penetration_pct": paid_penetration_pct,
        "billing_watchlist": billing_watchlist,
        "revenue_share_draft": revenue_share_draft,
    }

