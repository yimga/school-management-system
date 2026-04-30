"""
Point-in-time funnel + activation metrics for a single school (from MarketingFunnelEvent rows).
Multi-tenant rollups belong in analytics jobs; this supports operator proof and dashboards.
"""

from __future__ import annotations

from typing import Any


def get_school_funnel_metrics_snapshot(school_id) -> dict[str, Any]:
    """
    Counts and simple derived signals.

    ``activation_rate`` (alias of ``activation_indicator``) and ``conversion_rate``
    (1.0 when this school has ``onboarding_complete``) are 0.0–1.0 *per-school flags*, not
    population cohort rates. Use click_tracking for efficiency claims (insufficient_data gate).
    """
    from apps.schools.models import MarketingFunnelEvent

    base = MarketingFunnelEvent.objects.filter(school_id=school_id)
    types = (
        "onboarding_start",
        "onboarding_complete",
        "first_dashboard_view",
        "first_action",
        "first_result",
        "subscription_started",
        "payment_success",
        "payment_failed",
    )
    counts = {
        t: base.filter(event_type=t).count()
        for t in types
    }
    o_start = base.filter(event_type="onboarding_start").order_by("created_at").first()
    o_complete = base.filter(event_type="onboarding_complete").order_by("created_at").first()
    first_act = base.filter(event_type="first_action").order_by("created_at").first()
    first_dv = base.filter(event_type="first_dashboard_view").order_by("created_at").first()
    first_res = base.filter(event_type="first_result").order_by("created_at").first()
    ttfv_sec: float | None = None
    if o_start and first_res:
        ttfv_sec = (first_res.created_at - o_start.created_at).total_seconds()
    elif o_start and first_act:
        ttfv_sec = (first_act.created_at - o_start.created_at).total_seconds()
    ttdash_sec: float | None = None
    if o_start and first_dv:
        ttdash_sec = (first_dv.created_at - o_start.created_at).total_seconds()
    return {
        "school_id": str(school_id),
        "event_counts": counts,
        "time_to_first_value_seconds": ttfv_sec,
        "time_to_first_dashboard_seconds": ttdash_sec,
        "activation_indicator": 1.0 if first_act else 0.0,
        "activation_rate": 1.0 if first_act else 0.0,
        "result_indicator": 1.0 if first_res else 0.0,
        "revenue_signal_indicator": 1.0
        if (counts.get("payment_success", 0) > 0 or counts.get("subscription_started", 0) > 0)
        else 0.0,
        "conversion_rate": 1.0 if o_complete else 0.0,
    }
