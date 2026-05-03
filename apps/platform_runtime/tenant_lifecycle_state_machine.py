"""
Product lifecycle states (demo → growth) derived from funnel events + billing + health.

Event-driven: states are resolved from ``MarketingFunnelEvent`` rows, subscription
status, and ``tenant_lifecycle_engine.resolve_lifecycle_phase`` — no ad-hoc URL heuristics.
"""

from __future__ import annotations

from typing import Any, Optional

from django.conf import settings
from django.utils import timezone

from apps.platform_runtime.tenant_lifecycle_engine import AT_RISK, resolve_lifecycle_phase


def _churn_payment_failed_days() -> int:
    return int(getattr(settings, "TENANT_LIFECYCLE_CHURN_PAYMENT_FAILED_DAYS", 30))


def _churn_inactivity_days() -> int:
    return int(getattr(settings, "TENANT_LIFECYCLE_CHURN_INACTIVITY_DAYS", 90))

# ---------------------------------------------------------------------------
# Canonical product states (public contract, mission alignment)
# ---------------------------------------------------------------------------
STATE_DEMO = "demo"
STATE_SIGNUP_STARTED = "signup_started"
STATE_ONBOARDING = "onboarding"
STATE_ACTIVATED = "activated"
STATE_PAYING = "paying"
STATE_AT_RISK = "at_risk"
STATE_EXPANSION_READY = "expansion_ready"
STATE_CHURNED = "churned"
STATE_RECOVERED = "recovered"

ALL_LIFECYCLE_STATES: tuple[str, ...] = (
    STATE_DEMO,
    STATE_SIGNUP_STARTED,
    STATE_ONBOARDING,
    STATE_ACTIVATED,
    STATE_PAYING,
    STATE_AT_RISK,
    STATE_EXPANSION_READY,
    STATE_CHURNED,
    STATE_RECOVERED,
)


def _school_has_event(school_id: Optional[int], event_type: str) -> bool:
    if not school_id:
        return False
    from apps.schools.models import MarketingFunnelEvent

    return MarketingFunnelEvent.objects.filter(
        school_id=school_id, event_type=event_type
    ).exists()


def _latest_event_ts(school_id: Optional[int], event_type: str):
    if not school_id:
        return None
    from apps.schools.models import MarketingFunnelEvent

    row = (
        MarketingFunnelEvent.objects.filter(school_id=school_id, event_type=event_type)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    return row


def resolve_tenant_lifecycle_state(school) -> dict[str, Any]:
    """
    Return primary lifecycle label + reasons + funnel hints.

    Precedence: churned → recovered → unresolved payment_failed (billing-relevant)
    → paying / expansion_ready → engine at_risk → activated → signup_started → onboarding → demo → default activated.
    """
    from apps.billing.models import TenantSubscription
    from apps.platform_runtime.customer_health import calculate_school_health
    from apps.platform_runtime.onboarding import get_school_onboarding_progress
    from apps.schools.control_plane_lifecycle import get_current_subscription

    empty = {
        "state": STATE_ACTIVATED,
        "reasons": ["no_school"],
        "flags": {},
        "event_hints": {},
    }
    if school is None:
        return empty

    sid = getattr(school, "pk", None)
    reasons: list[str] = []
    flags: dict[str, bool] = {}
    event_hints: dict[str, bool] = {
        "has_demo_started": _school_has_event(sid, "demo_started"),
        "has_signup_started": _school_has_event(sid, "signup_started")
        or _school_has_event(sid, "signup"),
        "has_signup_completed": _school_has_event(sid, "signup_completed"),
        "has_onboarding_start": _school_has_event(sid, "onboarding_start"),
        "has_onboarding_complete": _school_has_event(sid, "onboarding_complete"),
        "has_first_dashboard": _school_has_event(sid, "first_dashboard_view"),
        "has_first_action": _school_has_event(sid, "first_action"),
        "has_subscription_started": _school_has_event(sid, "subscription_started"),
        "has_payment_success": _school_has_event(sid, "payment_success"),
        "has_tenant_recovered": _school_has_event(sid, "tenant_recovered"),
    }

    if not getattr(school, "is_active", True):
        return {
            "state": STATE_CHURNED,
            "reasons": ["school_inactive"],
            "flags": flags,
            "event_hints": event_hints,
        }

    if event_hints["has_tenant_recovered"]:
        reasons.append("tenant_recovered_event")
        return {
            "state": STATE_RECOVERED,
            "reasons": reasons,
            "flags": flags,
            "event_hints": event_hints,
        }

    now = timezone.now()
    sub = get_current_subscription(school)
    st_sub = str(getattr(sub, "status", "") or "")
    billing_relevant = bool(sub) or event_hints["has_subscription_started"]
    pf_ts = _latest_event_ts(sid, "payment_failed")
    ps_ts = _latest_event_ts(sid, "payment_success")

    is_paying = st_sub == TenantSubscription.Status.ACTIVE and (
        float(getattr(sub, "billed_amount", 0) or 0) > 0
        or event_hints["has_payment_success"]
    )

    churn_pay_days = _churn_payment_failed_days()
    churn_idle_days = _churn_inactivity_days()
    la = getattr(school, "last_activity", None)

    if (
        getattr(school, "is_active", True)
        and la is not None
        and not is_paying
        and (now - la).days >= churn_idle_days
        and (
            event_hints["has_payment_success"]
            or event_hints["has_subscription_started"]
        )
    ):
        reasons.append("dormant_monetized_tenant")
        return {
            "state": STATE_CHURNED,
            "reasons": reasons,
            "flags": flags,
            "event_hints": event_hints,
        }

    if (
        billing_relevant
        and pf_ts is not None
        and ps_ts is not None
        and ps_ts > pf_ts
        and (ps_ts - pf_ts).days >= churn_pay_days
    ):
        reasons.append("billing_recovered_after_prolonged_failure")
        return {
            "state": STATE_RECOVERED,
            "reasons": reasons,
            "flags": flags,
            "event_hints": event_hints,
        }

    if billing_relevant and pf_ts is not None and (
        ps_ts is None or pf_ts > ps_ts
    ):
        if (now - pf_ts).days >= churn_pay_days:
            reasons.append("prolonged_payment_failure")
            return {
                "state": STATE_CHURNED,
                "reasons": reasons,
                "flags": flags,
                "event_hints": event_hints,
            }
        reasons.append("latest_payment_event_failed")
        return {
            "state": STATE_AT_RISK,
            "reasons": reasons,
            "flags": flags,
            "event_hints": event_hints,
        }

    if is_paying:
        health = calculate_school_health(school)
        students = int(health.get("student_count") or 0)
        teachers = int(health.get("teacher_count") or 0)
        score = int(health.get("score") or 0)
        reports = bool(health.get("has_report_schedules"))
        module_breadth = reports or teachers >= 4
        if (
            students >= 20
            and score >= 77
            and event_hints["has_first_action"]
            and module_breadth
        ):
            reasons.append("expansion_depth")
            return {
                "state": STATE_EXPANSION_READY,
                "reasons": reasons,
                "flags": flags,
                "event_hints": event_hints,
            }
        reasons.append("subscription_active_paid")
        return {
            "state": STATE_PAYING,
            "reasons": reasons,
            "flags": flags,
            "event_hints": event_hints,
        }

    phase_payload = resolve_lifecycle_phase(school)
    if phase_payload.get("phase") == AT_RISK:
        reasons.append("engine_at_risk")
        return {
            "state": STATE_AT_RISK,
            "reasons": reasons,
            "flags": flags,
            "event_hints": event_hints,
        }

    if (
        event_hints["has_signup_completed"]
        or event_hints["has_first_dashboard"]
        or event_hints["has_first_action"]
        or _school_has_event(sid, "first_result")
    ):
        reasons.append("live_tenant")
        return {
            "state": STATE_ACTIVATED,
            "reasons": reasons,
            "flags": flags,
            "event_hints": event_hints,
        }

    if (
        event_hints["has_signup_started"] or _school_has_event(sid, "signup")
    ) and not event_hints["has_signup_completed"]:
        reasons.append("signup_in_progress")
        return {
            "state": STATE_SIGNUP_STARTED,
            "reasons": reasons,
            "flags": flags,
            "event_hints": event_hints,
        }

    prog = get_school_onboarding_progress(school)
    pct = int(prog.get("percent") or 0)
    onboarding_incomplete = (
        event_hints["has_onboarding_start"]
        and not event_hints["has_onboarding_complete"]
    ) or (
        pct < 85
        and (
            event_hints["has_signup_completed"]
            or event_hints["has_first_dashboard"]
        )
    )
    if onboarding_incomplete:
        reasons.append("onboarding_incomplete")
        return {
            "state": STATE_ONBOARDING,
            "reasons": reasons,
            "flags": flags,
            "event_hints": event_hints,
        }

    if event_hints["has_demo_started"] and not event_hints["has_signup_completed"]:
        reasons.append("demo_without_conversion")
        return {
            "state": STATE_DEMO,
            "reasons": reasons,
            "flags": flags,
            "event_hints": event_hints,
        }

    reasons.append("default_active")
    return {
        "state": STATE_ACTIVATED,
        "reasons": reasons,
        "flags": flags,
        "event_hints": event_hints,
    }


def validate_lifecycle_transition(
    from_state: str, to_state: str, *, reason: str = ""
) -> bool:
    """
    Directed graph sanity check for automation (not enforced at ORM layer).

    Allows forward progress and recovery paths; blocks absurd jumps unless recovered.
    """
    a = str(from_state or "").strip().lower()
    b = str(to_state or "").strip().lower()
    if a not in ALL_LIFECYCLE_STATES or b not in ALL_LIFECYCLE_STATES:
        return False
    if a == b:
        return True
    allowed: dict[str, frozenset[str]] = {
        STATE_DEMO: frozenset(
            {
                STATE_SIGNUP_STARTED,
                STATE_ONBOARDING,
                STATE_ACTIVATED,
                STATE_CHURNED,
            }
        ),
        STATE_SIGNUP_STARTED: frozenset(
            {STATE_ONBOARDING, STATE_ACTIVATED, STATE_CHURNED}
        ),
        STATE_ONBOARDING: frozenset(
            {STATE_ACTIVATED, STATE_PAYING, STATE_AT_RISK, STATE_CHURNED}
        ),
        STATE_ACTIVATED: frozenset(
            {
                STATE_PAYING,
                STATE_AT_RISK,
                STATE_EXPANSION_READY,
                STATE_CHURNED,
                STATE_ONBOARDING,
            }
        ),
        STATE_PAYING: frozenset(
            {STATE_AT_RISK, STATE_EXPANSION_READY, STATE_CHURNED, STATE_RECOVERED}
        ),
        STATE_AT_RISK: frozenset(
            {STATE_ACTIVATED, STATE_PAYING, STATE_CHURNED, STATE_RECOVERED}
        ),
        STATE_EXPANSION_READY: frozenset({STATE_AT_RISK, STATE_PAYING, STATE_CHURNED}),
        STATE_CHURNED: frozenset({STATE_RECOVERED, STATE_SIGNUP_STARTED}),
        STATE_RECOVERED: frozenset(
            {STATE_ACTIVATED, STATE_PAYING, STATE_ONBOARDING, STATE_AT_RISK}
        ),
    }
    return b in allowed.get(a, frozenset())
