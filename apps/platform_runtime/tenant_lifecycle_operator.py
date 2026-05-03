"""
Operator-facing lifecycle rows: labels, severity, evidence, primary actions.

Uses ``MarketingFunnelEvent``, ``get_school_funnel_metrics_snapshot``, and
``resolve_tenant_lifecycle_state`` only — no fabricated cohort metrics.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from django.db.models import Count
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.platform_runtime.models import TenantRetentionPlaybookAction
from apps.platform_runtime.tenant_lifecycle_state_machine import (
    ALL_LIFECYCLE_STATES,
    STATE_ACTIVATED,
    STATE_AT_RISK,
    STATE_CHURNED,
    STATE_DEMO,
    STATE_EXPANSION_READY,
    STATE_ONBOARDING,
    STATE_PAYING,
    STATE_RECOVERED,
    STATE_SIGNUP_STARTED,
    resolve_tenant_lifecycle_state,
)

ViewerScope = Literal["platform", "tenant"]

_STATE_LABELS: dict[str, str] = {
    STATE_DEMO: "Demo",
    STATE_SIGNUP_STARTED: "Signup started",
    STATE_ONBOARDING: "Onboarding",
    STATE_ACTIVATED: "Activated",
    STATE_PAYING: "Paying",
    STATE_AT_RISK: "At risk",
    STATE_EXPANSION_READY: "Expansion-ready",
    STATE_CHURNED: "Churned",
    STATE_RECOVERED: "Recovered",
}

_STATE_SEVERITY: dict[str, str] = {
    STATE_DEMO: "info",
    STATE_SIGNUP_STARTED: "info",
    STATE_ONBOARDING: "info",
    STATE_ACTIVATED: "info",
    STATE_PAYING: "info",
    STATE_AT_RISK: "warning",
    STATE_EXPANSION_READY: "info",
    STATE_CHURNED: "critical",
    STATE_RECOVERED: "info",
}


def _safe_reverse(viewname: str) -> str:
    try:
        return reverse(viewname)
    except NoReverseMatch:
        return ""


def resolve_primary_action_url(
    state_key: str,
    *,
    viewer_scope: ViewerScope,
    school_id: Optional[int],
) -> str:
    """Deterministic primary navigation for dashboard cards (never raw SQL)."""
    if viewer_scope == "platform":
        if state_key == STATE_AT_RISK:
            u = _safe_reverse("super:billing_dashboard")
            return u or _safe_reverse("super:tenant_health")
        if state_key == STATE_PAYING:
            return _safe_reverse("super:billing_dashboard") or _safe_reverse(
                "super:schools_list"
            )
        if state_key == STATE_EXPANSION_READY:
            return _safe_reverse("super:schools_list")
        if state_key == STATE_CHURNED:
            return _safe_reverse("super:schools_list")
        return _safe_reverse("super:schools_list")

    # tenant scope
    if state_key == STATE_DEMO:
        return _safe_reverse("signup_school") or _safe_reverse("marketing_landing")
    if state_key in (STATE_SIGNUP_STARTED, STATE_ONBOARDING):
        return _safe_reverse("onboard_wizard") or _safe_reverse("setup_studio")
    if state_key == STATE_ACTIVATED:
        return _safe_reverse("accounts:redirect") or "/"
    if state_key == STATE_PAYING:
        return _safe_reverse("finance:dashboard") or _safe_reverse("accounts:redirect")
    if state_key == STATE_AT_RISK:
        return (
            _safe_reverse("finance:payments")
            or _safe_reverse("finance:dashboard")
            or _safe_reverse("accounts:redirect")
        )
    if state_key == STATE_EXPANSION_READY:
        u = _safe_reverse("analytics:governed_query_builder")
        return u or _safe_reverse("finance:reports") or _safe_reverse("accounts:redirect")
    if state_key == STATE_CHURNED:
        return _safe_reverse("accounts:redirect") or "/"
    if state_key == STATE_RECOVERED:
        return _safe_reverse("accounts:redirect") or "/"
    return _safe_reverse("accounts:redirect") or "/"


def _funnel_evidence(school_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
    from apps.schools.models import MarketingFunnelEvent

    rows = []
    for ev in MarketingFunnelEvent.objects.filter(school_id=school_id).order_by(
        "-created_at"
    )[:limit]:
        rows.append(
            {
                "event_type": ev.event_type,
                "created_at": ev.created_at.isoformat(),
            }
        )
    return rows


def build_lifecycle_operator_row(
    school,
    *,
    viewer_scope: ViewerScope,
    computed_at=None,
) -> dict[str, Any]:
    """One tenant row/card for dashboards (school must be non-null)."""
    from apps.schools.funnel_metrics import get_school_funnel_metrics_snapshot

    computed_at = computed_at or timezone.now()
    sid = getattr(school, "pk", None)
    raw = resolve_tenant_lifecycle_state(school)
    state_key = str(raw.get("state") or "")
    reasons = list(raw.get("reasons") or [])
    reason = "; ".join(reasons) if reasons else state_key

    funnel = get_school_funnel_metrics_snapshot(sid) if sid else {}
    evidence: dict[str, Any] = {
        "funnel_snapshot": funnel,
        "recent_funnel_events": _funnel_evidence(sid) if sid else [],
        "lifecycle_hints": raw.get("event_hints") or {},
    }

    primary = resolve_primary_action_url(
        state_key,
        viewer_scope=viewer_scope,
        school_id=sid,
    )

    return {
        "school_id": sid,
        "school_name": getattr(school, "name", "") or "",
        "school_slug": getattr(school, "slug", "") or "",
        "state_key": state_key,
        "label": _STATE_LABELS.get(state_key, state_key.title()),
        "reason": reason,
        "evidence": evidence,
        "primary_action_url": primary,
        "severity": _STATE_SEVERITY.get(state_key, "info"),
        "computed_at": computed_at.isoformat(),
    }


def lifecycle_state_distribution(rows: list[dict[str, Any]]) -> dict[str, int]:
    out = {s: 0 for s in ALL_LIFECYCLE_STATES}
    for r in rows:
        sk = str(r.get("state_key") or "")
        if sk in out:
            out[sk] += 1
    return out


def compute_portfolio_activation_metrics(
    *,
    min_sample: int = 10,
    school_ids: Optional[list[int]] = None,
) -> dict[str, Any]:
    """
    Cohort-style rollups over schools that appear in funnel events.

    Returns ``insufficient_data`` when denominators fall below ``min_sample``.
    """
    from apps.schools.models import MarketingFunnelEvent

    base = MarketingFunnelEvent.objects.filter(school_id__isnull=False)
    if school_ids is not None:
        base = base.filter(school_id__in=list(school_ids))

    def _distinct(ev: str) -> set[int]:
        return set(
            base.filter(event_type=ev).values_list("school_id", flat=True).distinct()
        )

    started = _distinct("onboarding_start")
    completed = _distinct("onboarding_complete")
    activated = _distinct("first_action") | _distinct("first_result")
    paying_like = _distinct("subscription_started") | _distinct("payment_success")

    def _median_ttfa_seconds() -> float | None:
        """Median time onboarding_start → first_action for schools with both."""
        deltas: list[float] = []
        for sid in started & _distinct("first_action"):
            o0 = (
                MarketingFunnelEvent.objects.filter(
                    school_id=sid, event_type="onboarding_start"
                )
                .order_by("created_at")
                .values_list("created_at", flat=True)
                .first()
            )
            a0 = (
                MarketingFunnelEvent.objects.filter(
                    school_id=sid, event_type="first_action"
                )
                .order_by("created_at")
                .values_list("created_at", flat=True)
                .first()
            )
            if o0 and a0:
                deltas.append((a0 - o0).total_seconds())
        if not deltas:
            return None
        deltas.sort()
        mid = len(deltas) // 2
        if len(deltas) % 2:
            return round(deltas[mid], 3)
        return round((deltas[mid - 1] + deltas[mid]) / 2.0, 3)

    n_started = len(started)
    insufficient = n_started < min_sample
    activation_rate: float | None = None
    conversion_rate: float | None = None
    paid_penetration: float | None = None
    dropoff_stage: str | None = None

    if not insufficient:
        activation_rate = round(len(activated & started) / n_started, 4)
        conversion_rate = round(len(completed & started) / n_started, 4)
        paying_in_started = len(paying_like & started)
        paid_penetration = round(paying_in_started / n_started, 4)

        stages = [
            ("onboarding_start", n_started),
            ("onboarding_complete", len(completed & started)),
            ("first_action", len((_distinct("first_action") & started))),
            ("subscription_started", len((_distinct("subscription_started") & started))),
        ]
        max_drop = -1.0
        worst = None
        prev_n = stages[0][1]
        for name, n in stages[1:]:
            if prev_n <= 0:
                break
            drop = (prev_n - n) / prev_n
            if drop > max_drop:
                max_drop = drop
                worst = name
            prev_n = n
        dropoff_stage = worst

    median_ttfa = _median_ttfa_seconds()
    ttfa_insufficient = median_ttfa is None or len(started & _distinct("first_action")) < min_sample

    return {
        "min_sample": min_sample,
        "schools_with_onboarding_start": n_started,
        "insufficient_data": insufficient,
        "activation_rate": activation_rate,
        "conversion_rate": conversion_rate,
        "paid_penetration": paid_penetration,
        "dropoff_stage": dropoff_stage,
        "median_time_to_first_action_seconds": median_ttfa,
        "time_to_first_value_insufficient_data": ttfa_insufficient,
    }


def build_lifecycle_dashboard_context(
    schools: list,
    *,
    viewer_scope: ViewerScope,
) -> dict[str, Any]:
    """Template context for ``tenant_lifecycle_dashboard``."""
    now = timezone.now()
    rows = [
        build_lifecycle_operator_row(s, viewer_scope=viewer_scope, computed_at=now)
        for s in schools
    ]
    ids = [getattr(s, "pk", None) for s in schools if getattr(s, "pk", None)]
    id_list = [i for i in ids if i]
    open_counts: dict[int, int] = {}
    if id_list:
        open_qs = (
            TenantRetentionPlaybookAction.objects.filter(
                school_id__in=id_list,
                status=TenantRetentionPlaybookAction.Status.OPEN,
            )
            .values("school_id")
            .annotate(n=Count("id"))
        )
        open_counts = {r["school_id"]: r["n"] for r in open_qs}
    for row in rows:
        sid = row.get("school_id")
        row["open_retention_actions"] = open_counts.get(sid, 0) if sid else 0

    metrics = compute_portfolio_activation_metrics(
        min_sample=10,
        school_ids=ids if viewer_scope == "tenant" else None,
    )
    dist = lifecycle_state_distribution(rows)
    at_risk_rows = [r for r in rows if r.get("state_key") == STATE_AT_RISK]
    expansion_rows = [r for r in rows if r.get("state_key") == STATE_EXPANSION_READY]

    return {
        "viewer_scope": viewer_scope,
        "rows": rows,
        "distribution": dist,
        "metrics": metrics,
        "at_risk_rows": at_risk_rows,
        "expansion_ready_rows": expansion_rows,
        "page_marker": "rmc-tenant-lifecycle-dashboard",
    }
