"""
Growth / conversion analytics — aggregates MarketingFunnelEvent + billing truth (no fabricated KPIs).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count, Min
from django.utils import timezone

# Canonical stage order for drop-off (optional stages allowed to be zero).
FUNNEL_STAGE_ORDER: tuple[str, ...] = (
    "visit",
    "discovery",
    "demo_started",
    "demo_attendance_completed",
    "demo_marks_completed",
    "demo_report_completed",
    "demo_cta_seen",
    "onboarding_start",
    "signup_started",
    "signup",
    "onboarding_complete",
    "signup_completed",
    "first_dashboard_view",
    "first_action",
    "first_result",
    "activation",
    "subscription_started",
)


def _lifecycle_distribution_sample(*, school_limit: int = 400) -> dict[str, int]:
    from apps.platform_runtime.tenant_lifecycle_state_machine import (
        ALL_LIFECYCLE_STATES,
        resolve_tenant_lifecycle_state,
    )
    from apps.schools.models import School

    counts = {s: 0 for s in ALL_LIFECYCLE_STATES}
    for school in School.objects.order_by("-id")[:school_limit]:
        st = resolve_tenant_lifecycle_state(school)["state"]
        if st in counts:
            counts[st] += 1
    return counts


def _time_to_value_fast_path_stats(window_qs, *, max_minutes: float = 10.0) -> dict[str, Any]:
    """Share of schools reaching first_result within max_minutes of earliest activation signal."""
    start_types = ("onboarding_start", "demo_started", "signup_completed")
    schools_first: dict[int, Any] = {}
    schools_result: dict[int, Any] = {}
    for row in (
        window_qs.filter(event_type__in=list(start_types) + ["first_result"])
        .filter(school_id__isnull=False)
        .values("school_id", "event_type", "created_at")
        .order_by("school_id", "created_at")
    ):
        sid = row["school_id"]
        et = row["event_type"]
        ts = row["created_at"]
        if et in start_types:
            if sid not in schools_first:
                schools_first[sid] = ts
        elif et == "first_result":
            if sid not in schools_result:
                schools_result[sid] = ts
    under = 0
    eligible = 0
    for sid, t0 in schools_first.items():
        t1 = schools_result.get(sid)
        if not t1 or t1 <= t0:
            continue
        eligible += 1
        minutes = (t1 - t0).total_seconds() / 60.0
        if minutes <= max_minutes:
            under += 1
    pct = round(100.0 * under / eligible, 2) if eligible else None
    return {
        "time_to_value_under_n_minutes": max_minutes,
        "time_to_value_fast_path_eligible": eligible,
        "time_to_value_fast_path_met": under,
        "time_to_value_fast_path_pct": pct,
    }


def build_growth_funnel_snapshot(*, days: int = 30) -> dict[str, Any]:
    """
    Counts, conversion rates, time-to-value, drop-offs, billing linkage, data-quality flags.
    """
    from apps.schools.models import MarketingFunnelEvent

    now = timezone.now()
    start = now - timedelta(days=days)

    total_qs = MarketingFunnelEvent.objects.all()
    window_qs = MarketingFunnelEvent.objects.filter(created_at__gte=start)

    def counts(qs):
        rows = qs.values("event_type").annotate(n=Count("id"))
        return {r["event_type"]: r["n"] for r in rows}

    all_counts = counts(total_qs)
    period_counts = counts(window_qs)

    visit = period_counts.get("visit", 0)
    subscription_started = period_counts.get("subscription_started", 0)
    signup_completed = period_counts.get("signup_completed", 0)

    # Conversion: visit → subscription (narrow definition); guard zeros.
    conversion_visit_to_sub_pct = (
        round(100.0 * subscription_started / visit, 2) if visit else None
    )
    conversion_signup_complete_to_sub_pct = (
        round(100.0 * subscription_started / signup_completed, 2)
        if signup_completed
        else None
    )

    # Activation rate from live schools (same as business_value; not funnel-only).
    activation_rate_pct = None
    try:
        from apps.platform_runtime.business_value import get_business_value_snapshot

        activation_rate_pct = get_business_value_snapshot().get("activation_rate_pct")
    except Exception:
        pass

    # Drop-off between adjacent stages (period window).
    dropoffs: list[dict[str, Any]] = []
    for i, stage in enumerate(FUNNEL_STAGE_ORDER[:-1]):
        nxt = FUNNEL_STAGE_ORDER[i + 1]
        a = period_counts.get(stage, 0)
        b = period_counts.get(nxt, 0)
        rate = round(100.0 * b / a, 2) if a else None
        dropoffs.append(
            {
                "from_stage": stage,
                "to_stage": nxt,
                "from_count": a,
                "to_count": b,
                "forward_rate_pct": rate,
            }
        )

    # Time to value: median minutes signup_completed → first_result (school-scoped, window-filtered events).
    tt_value_minutes = None
    tt_value_sample_size = 0
    school_signup = {}
    school_result = {}
    scoped = window_qs.filter(
        event_type__in=["signup_completed", "first_result"],
        school_id__isnull=False,
    ).values("school_id", "event_type").annotate(ts=Min("created_at"))
    for row in scoped:
        sid = row["school_id"]
        et = row["event_type"]
        ts = row["ts"]
        if et == "signup_completed":
            school_signup[sid] = ts
        elif et == "first_result":
            school_result[sid] = ts
    deltas = []
    for sid, t0 in school_signup.items():
        t1 = school_result.get(sid)
        if t1 and t1 > t0:
            deltas.append((t1 - t0).total_seconds() / 60.0)
    tt_value_sample_size = len(deltas)
    if deltas:
        deltas.sort()
        mid = len(deltas) // 2
        tt_value_minutes = round(deltas[mid], 2) if len(deltas) % 2 else round(
            (deltas[mid - 1] + deltas[mid]) / 2.0, 2
        )

    # Billing truth: paying subscriptions (not inferred from funnel alone).
    paying_schools = None
    try:
        from apps.billing.models import TenantSubscription

        paying_schools = TenantSubscription.objects.filter(
            status=TenantSubscription.Status.ACTIVE,
            billed_amount__gt=0,
        ).count()
    except Exception:
        paying_schools = None

    # Data quality: stages with zero volume in period (diagnostic, not "failure").
    missing_instrumentation = [
        s for s in FUNNEL_STAGE_ORDER if period_counts.get(s, 0) == 0
    ]
    insufficient_volume = visit < 10  # heuristic: no stable conversion claims

    # "Why not paying" narrative inputs (factual only).
    funnel_only_signups = period_counts.get("signup", 0)
    completed_verify = signup_completed
    saw_dashboard = period_counts.get("first_dashboard_view", 0)
    pay_gap_verify_to_sub = (
        completed_verify - subscription_started if completed_verify else None
    )

    growth_readiness = (
        "INSUFFICIENT_VOLUME"
        if insufficient_volume
        else (
            "INSTRUMENTATION_GAPS"
            if len(missing_instrumentation) > 4
            else "TRACKED"
        )
    )

    verdict = "NOT_READY" if insufficient_volume or visit == 0 else "READY"

    return {
        "period_days": days,
        "counts_all_time": all_counts,
        "counts_period": period_counts,
        "conversion_visit_to_subscription_pct": conversion_visit_to_sub_pct,
        "conversion_signup_completed_to_subscription_pct": conversion_signup_complete_to_sub_pct,
        "activation_rate_pct_live_db": activation_rate_pct,
        "time_to_value_median_minutes": tt_value_minutes,
        "time_to_value_sample_size": tt_value_sample_size,
        "dropoffs": dropoffs,
        "paying_schools_billed_gt_zero": paying_schools,
        "missing_event_types_in_period": missing_instrumentation,
        "insufficient_volume_for_claims": insufficient_volume,
        "why_not_paying_hints": {
            "signup_form_events_period": funnel_only_signups,
            "signup_completed_events_period": completed_verify,
            "first_dashboard_view_period": saw_dashboard,
            "subscription_started_events_period": subscription_started,
            "gap_verified_to_subscription_events": pay_gap_verify_to_sub,
        },
        "funnel_completeness_note": (
            "Stages are optional (e.g. demo_started); compare adjacent drop-offs, "
            "then billing.paying_schools for revenue truth."
        ),
        "growth_readiness": growth_readiness,
        "verdict": verdict,
        "lifecycle_distribution_sample": _lifecycle_distribution_sample(),
        "time_to_value_fast_path": _time_to_value_fast_path_stats(window_qs),
    }
