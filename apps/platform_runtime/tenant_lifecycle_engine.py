"""
Canonical tenant lifecycle phases for onboarding, retention, and scale operations.

Maps existing ``School`` / billing / onboarding / health signals into five product phases:
trial, onboarding, active, at_risk, churned — without duplicating control-plane
freeze/deactivate mechanics (see ``apps.schools.control_plane_lifecycle``).

Designed for batch evaluation (1000+ schools) using ORM aggregations and read-only
helpers; no per-tenant side effects in this module.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from django.utils import timezone

# ---------------------------------------------------------------------------
# Phase constants (public contract)
# ---------------------------------------------------------------------------
TRIAL = "trial"
ONBOARDING = "onboarding"
ACTIVE = "active"
AT_RISK = "at_risk"
CHURNED = "churned"

ALL_PHASES: tuple[str, ...] = (TRIAL, ONBOARDING, ACTIVE, AT_RISK, CHURNED)

# Directed edges: allowed logical transitions (operator/automation may enforce subset).
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    TRIAL: frozenset({ONBOARDING, ACTIVE, AT_RISK, CHURNED}),
    ONBOARDING: frozenset({TRIAL, ACTIVE, AT_RISK, CHURNED}),
    ACTIVE: frozenset({TRIAL, ONBOARDING, AT_RISK, CHURNED}),
    AT_RISK: frozenset({ACTIVE, ONBOARDING, TRIAL, CHURNED}),
    CHURNED: frozenset({TRIAL, ONBOARDING, ACTIVE}),
}


def validate_phase_transition(from_phase: str, to_phase: str) -> bool:
    """Return True if ``to_phase`` is in the allowed graph from ``from_phase``."""
    a = str(from_phase or "").strip().lower()
    b = str(to_phase or "").strip().lower()
    if a not in ALLOWED_TRANSITIONS or b not in ALL_PHASES:
        return False
    return b in ALLOWED_TRANSITIONS[a]


def _days_since(dt: Optional[Any]) -> Optional[float]:
    if dt is None:
        return None
    try:
        now = timezone.now()
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return max(0.0, (now - dt).total_seconds() / 86400.0)
    except (TypeError, ValueError):
        return None


def _login_frequency_score(school) -> int:
    """
    0–100 from ``School.last_activity`` (throttled tenant ping) and staff ``last_login``.
    """
    best_days: Optional[float] = None
    la = getattr(school, "last_activity", None)
    d = _days_since(la)
    if d is not None:
        best_days = d
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        # Latest login among users who belong to this school.
        qs = User.objects.filter(school_memberships__school_id=school.id).exclude(
            last_login__isnull=True
        )
        row = qs.order_by("-last_login").values_list("last_login", flat=True).first()
        if row:
            dl = _days_since(row)
            if dl is not None:
                best_days = dl if best_days is None else min(best_days, dl)
    except Exception:
        pass

    if best_days is None:
        return 0
    # Full score if activity within 7 days; decay toward 0 by ~45 days.
    if best_days <= 7:
        return 100
    if best_days >= 45:
        return max(0, int(100 * math.exp(-(best_days - 7) / 25)))
    return int(100 - (best_days - 7) * (100 / 38))


def _payment_activity_score(school, subscription) -> int:
    """0–100 from subscription / billing_type (no raw payment row required)."""
    from apps.billing.models import TenantSubscription

    bt = getattr(school, "billing_type", "") or ""
    try:
        free = getattr(school.BillingType, "FREE_TRIAL", "FREE_TRIAL")
    except Exception:
        free = "FREE_TRIAL"

    if bt == free:
        return 70

    if subscription is None:
        return 40

    st = getattr(subscription, "status", "") or ""
    if st == TenantSubscription.Status.ACTIVE:
        return 100
    if st == TenantSubscription.Status.TRIALING:
        return 75
    if st in {TenantSubscription.Status.PAST_DUE, TenantSubscription.Status.SUSPENDED}:
        return 25
    if st == TenantSubscription.Status.CANCELLED:
        return 10
    return 55


def _feature_usage_score(health: dict[str, Any]) -> int:
    """Derive 0–100 feature usage from existing customer_health depth signals."""
    students = int(health.get("student_count") or 0)
    teachers = int(health.get("teacher_count") or 0)
    reports = bool(health.get("has_report_schedules"))
    part = 0.0
    part += min(40.0, 40.0 * (1 - pow(0.995, min(students, 800))))
    part += min(35.0, 35.0 * (1 - pow(0.9, min(teachers, 50))))
    if reports:
        part += 25.0
    return int(max(0, min(100, round(part))))


def compute_health_dimensions(school) -> dict[str, Any]:
    """
    Four scoring pillars + composite (0–100 each where applicable).

    - feature_usage: depth of module adoption (students/teachers/reports).
    - login_frequency: recency of tenant/staff activity.
    - payment_activity: billing/subscription health.
    - completion_pct: onboarding checklist completion (same as onboarding engine).
    """
    from apps.platform_runtime.customer_health import calculate_school_health
    from apps.schools.control_plane_lifecycle import get_current_subscription

    health = calculate_school_health(school)
    sub = get_current_subscription(school)

    login_sc = _login_frequency_score(school) if school else 0
    pay_sc = _payment_activity_score(school, sub) if school else 0
    feat_sc = _feature_usage_score(health)
    completion = int(health.get("onboarding_percent") or 0)

    composite = int(
        round(
            completion * 0.35
            + feat_sc * 0.25
            + login_sc * 0.20
            + pay_sc * 0.20
        )
    )
    composite = max(0, min(100, composite))

    return {
        "feature_usage": feat_sc,
        "login_frequency": login_sc,
        "payment_activity": pay_sc,
        "completion_pct": completion,
        "composite_health": composite,
        "customer_health_status": health.get("status") or "",
        "customer_health_score": int(health.get("score") or 0),
    }


def resolve_lifecycle_phase(school) -> dict[str, Any]:
    """
    Resolve canonical lifecycle phase and explain signals.

    Precedence: churned → trial → onboarding → at_risk → active.
    """
    from apps.billing.models import TenantSubscription
    from apps.platform_runtime.customer_health import calculate_school_health
    from apps.platform_runtime.onboarding import get_school_onboarding_progress
    from apps.schools.control_plane_lifecycle import (
        get_current_subscription,
        get_lifecycle_snapshot,
    )

    if school is None:
        return {
            "phase": CHURNED,
            "reasons": ["no_school"],
            "operator_snapshot": {},
            "health_dimensions": {},
        }

    snap = get_lifecycle_snapshot(school)
    health = calculate_school_health(school)
    dims = compute_health_dimensions(school)
    prog = get_school_onboarding_progress(school)
    pct = int(prog.get("percent") or 0)
    sub = get_current_subscription(school)

    reasons: list[str] = []
    phase = ACTIVE

    if not getattr(school, "is_active", True):
        phase = CHURNED
        reasons.append("inactive_tenant")
    elif getattr(school, "is_frozen", False):
        phase = AT_RISK
        reasons.append("frozen")
    elif snap.get("state") in {"billing_exception"}:
        phase = AT_RISK
        reasons.append("billing_exception")
    elif snap.get("state") == "trialing" or (
        sub and getattr(sub, "status", "") == TenantSubscription.Status.TRIALING
    ):
        phase = TRIAL
        reasons.append("trial_or_trialing_subscription")
    elif pct < 85:
        phase = ONBOARDING
        reasons.append(f"onboarding_lt_85_pct_{pct}")
    elif health.get("status") in {"setup_needed", "at_risk"}:
        phase = AT_RISK
        reasons.append(f"health_{health.get('status')}")
    else:
        phase = ACTIVE
        reasons.append("healthy_operation")

    # Stale engagement: surface at_risk without masking incomplete onboarding checklist.
    if phase not in (CHURNED, ONBOARDING) and dims["login_frequency"] < 30:
        phase = AT_RISK
        reasons.append("stale_login_activity")

    return {
        "phase": phase,
        "reasons": reasons,
        "operator_snapshot": snap,
        "onboarding_percent": pct,
        "health_dimensions": dims,
        "health_summary": health,
    }


def get_inactivity_alert(school) -> Optional[dict[str, Any]]:
    """
    If tenant activity is stale, return alert payload for email/in-app; else None.

    Threshold: no ``last_activity`` and no staff login within 21 days → warning.
    """
    if school is None or not getattr(school, "is_active", False):
        return None

    dims = compute_health_dimensions(school)
    if dims["login_frequency"] >= 45:
        return None

    days: Optional[float] = None
    la = getattr(school, "last_activity", None)
    d = _days_since(la)
    if d is not None:
        days = d

    level = "warning" if (days is None or days > 21) else "info"
    return {
        "level": level,
        "school_id": school.id,
        "login_frequency_score": dims["login_frequency"],
        "days_since_last_activity": days,
        "message_key": "tenant_inactivity",
        "composite_health": dims["composite_health"],
    }


def get_retention_recommendations(school, *, limit: int = 6) -> list[dict[str, str]]:
    """Combine onboarding next steps with health-aware copy (URLs from onboarding rows)."""
    from apps.platform_runtime.customer_health import get_school_health_recommendations

    base = get_school_health_recommendations(school, limit=limit)
    phase_payload = resolve_lifecycle_phase(school)
    if phase_payload.get("phase") == AT_RISK and len(base) < limit:
        base.append(
            {
                "label": "Review subscription and usage",
                "url": "",
                "key": "lifecycle_at_risk",
            }
        )
    return base[:limit]


def get_success_automation_nudges(school, *, limit: int = 5) -> list[dict[str, str]]:
    """
    Automated nudges for in-product banners / digest (deterministic; AI can wrap strings).

    Phase-aware ordering; dedupe by key.
    """
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in get_retention_recommendations(school, limit=limit * 2):
        k = str(row.get("key") or row.get("label") or "")
        if k in seen:
            continue
        seen.add(k)
        out.append(row)
        if len(out) >= limit:
            break
    return out
