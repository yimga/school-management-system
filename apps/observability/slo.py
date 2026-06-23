"""Service Level Objectives — SOT for what the platform promises.

SLOs encoded as code so they show up in code review, drift produces a
diff, and the operational dashboard reads from one place.

Each SLO has a target (e.g. 99.9% availability over 30 days, p95
latency < 800ms). The ``burn_rate`` helper computes how fast the error
budget is being consumed in the current window — values >= 1.0 mean
the budget will be exhausted before the window ends if the trend
continues; values >= 14.4 (Google's "fast burn") page immediately.

Reference: Google SRE Workbook ch. 5 (Alerting on SLOs).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SLOKind = Literal["availability", "latency_p95", "latency_p99", "freshness", "error_rate"]


@dataclass(frozen=True)
class SLODefinition:
    """Single SLO target. Immutable; treat as code, not config."""

    key: str
    label: str
    kind: SLOKind
    target: float
    window_days: int
    # For latency SLOs, the threshold the p95/p99 must beat (ms).
    threshold_ms: int | None = None
    # Human-readable owning team (search hint, not for code routing).
    owner: str = "platform"
    # Sentry transaction name(s) backing this SLO. The dashboard joins by
    # these when computing the burn rate.
    sentry_transactions: tuple[str, ...] = ()


# Canonical SLO set. **Add new SLOs here, not as one-off settings.**
#
# Targets are deliberately conservative; they reflect what we believe
# the platform should sustain in 2026 — not the cheapest goal that
# passes today's load test. Hit-rate calibration belongs in the
# dashboard, not here.
SLOS: tuple[SLODefinition, ...] = (
    SLODefinition(
        key="web.availability",
        label="Web availability (5xx-free request rate)",
        kind="availability",
        target=99.9,
        window_days=30,
        owner="platform",
        sentry_transactions=("http.server",),
    ),
    SLODefinition(
        key="attendance.submit",
        label="Attendance submit p95 latency",
        kind="latency_p95",
        target=95.0,
        threshold_ms=800,
        window_days=7,
        owner="academics",
        sentry_transactions=("attendance.submit",),
    ),
    SLODefinition(
        key="grade.entry",
        label="Grade entry p95 latency",
        kind="latency_p95",
        target=95.0,
        threshold_ms=900,
        window_days=7,
        owner="academics",
        sentry_transactions=("grade.entry",),
    ),
    SLODefinition(
        key="parent.dashboard",
        label="Parent dashboard render p95",
        kind="latency_p95",
        target=95.0,
        threshold_ms=1200,
        window_days=7,
        owner="portal",
        sentry_transactions=("parent.dashboard.render",),
    ),
    SLODefinition(
        key="migration.bundle_apply",
        label="Migration Cloud bundle apply success rate",
        kind="availability",
        target=99.0,
        window_days=30,
        owner="migration_cloud",
        sentry_transactions=("migration.bundle_apply",),
    ),
    SLODefinition(
        key="ai.gateway.latency",
        label="AI gateway p95 (ollama tier)",
        kind="latency_p95",
        target=95.0,
        threshold_ms=2500,
        window_days=7,
        owner="ai",
        sentry_transactions=("ai.gateway.invoke",),
    ),
    SLODefinition(
        key="webhook.delivery",
        label="Webhook delivery success rate",
        kind="availability",
        target=99.0,
        window_days=30,
        owner="integrations",
        sentry_transactions=("webhook.deliver",),
    ),
    SLODefinition(
        key="sync.conflict_pending",
        label="Sync conflict pending freshness",
        kind="freshness",
        target=99.0,
        window_days=7,
        owner="sync",
        sentry_transactions=("sync.delta_apply",),
    ),
    # === 2026-05-14 wave NS-4: extend to finance hotspots ===
    SLODefinition(
        key="finance.invoice_create",
        label="Invoice creation p95 latency",
        kind="latency_p95",
        target=95.0,
        threshold_ms=900,
        window_days=7,
        owner="finance",
        sentry_transactions=("finance.invoice.create",),
    ),
    SLODefinition(
        key="finance.payment_record",
        label="Payment record p95 latency (idempotency-aware)",
        kind="latency_p95",
        target=95.0,
        threshold_ms=1100,
        window_days=7,
        owner="finance",
        sentry_transactions=("finance.payment.record",),
    ),
    SLODefinition(
        key="auth.login",
        label="Login p95 latency",
        kind="latency_p95",
        target=95.0,
        threshold_ms=700,
        window_days=7,
        owner="identity",
        sentry_transactions=("auth.login",),
    ),
    SLODefinition(
        key="api.public_config",
        label="Public school-config API p95",
        kind="latency_p95",
        target=99.0,
        threshold_ms=350,
        window_days=7,
        owner="platform",
        sentry_transactions=("http.server",),
    ),
    # Wave B — G5: friction events should remain rare. If the validation-retry
    # signal spikes (>= 1% of authenticated sessions in a 24h window), success
    # team should be paged — it indicates a regressed form somewhere on the
    # platform. Tracked via the `FrictionEvent` rollup table.
    SLODefinition(
        key="ui.friction.validation_retry",
        label="UI form validation-retry rate (rare-event SLO)",
        kind="error_rate",
        target=99.0,  # < 1% of sessions experience a 3x validation retry
        window_days=1,
        owner="customer_success",
        sentry_transactions=(),
    ),
)


def slos_by_key() -> dict[str, SLODefinition]:
    return {s.key: s for s in SLOS}


def get_slo(key: str) -> SLODefinition | None:
    return slos_by_key().get(key)


def burn_rate(
    *,
    actual_error_rate: float,
    slo: SLODefinition,
    window_minutes: int,
) -> float:
    """Burn rate over ``window_minutes`` for one SLO.

    Burn rate = (actual_error_rate) / (1 - target/100). A value of 1.0
    means we'd exhaust the entire error budget exactly at the end of
    the SLO window if the rate continued.

    Google's multi-window alert thresholds (SRE Workbook Table 5-3):
      * 1h window, burn rate >= 14.4  → page (2% of monthly budget in 1h)
      * 6h window, burn rate >= 6     → page (5% of budget in 6h)
      * 1d window, burn rate >= 3     → ticket (10% of budget in 1d)
      * 3d window, burn rate >= 1     → ticket (10% of budget in 3d)

    Callers that need the alert classification should use
    :func:`burn_rate_severity` rather than re-implementing it.
    """
    error_budget = max(0.0, 1.0 - (slo.target / 100.0))
    if error_budget == 0:
        return float("inf") if actual_error_rate > 0 else 0.0
    return actual_error_rate / error_budget


def burn_rate_severity(*, burn: float, window_minutes: int) -> str:
    """Map a burn rate + window to alert severity.

    Returns one of: ``"page"``, ``"ticket"``, ``"watch"``, ``"ok"``.
    """
    hours = window_minutes / 60.0
    if hours <= 1 and burn >= 14.4:
        return "page"
    if hours <= 6 and burn >= 6.0:
        return "page"
    if hours <= 24 and burn >= 3.0:
        return "ticket"
    if hours <= 72 and burn >= 1.0:
        return "ticket"
    if burn >= 0.5:
        return "watch"
    return "ok"


def list_owners() -> set[str]:
    return {s.owner for s in SLOS}


def slo_commitments_for_display() -> list[dict]:
    """Public-facing SLO commitments for the status page (T1).

    Returns the platform's PROMISED objectives — targets only, derived from the
    registry, never live measurements. The status page shows what we commit to
    (AWS-/SLA-style trust), so it can never imply a current number it cannot
    honestly back. Each entry carries a human ``objective`` one-liner.
    """
    rows: list[dict] = []
    for s in SLOS:
        if s.kind in ("latency_p95", "latency_p99"):
            quant = "p99" if s.kind == "latency_p99" else "p95"
            objective = (
                f"{quant} under {s.threshold_ms} ms for {s.target}% of requests "
                f"({s.window_days}-day window)"
            )
        elif s.kind == "availability":
            objective = f"{s.target}% success over a {s.window_days}-day window"
        elif s.kind == "freshness":
            objective = f"Fresh within objective {s.target}% of the time ({s.window_days}d)"
        else:  # error_rate
            objective = (
                f"Under {round(100.0 - s.target, 2)}% affected over "
                f"a {s.window_days}-day window"
            )
        rows.append(
            {
                "key": s.key,
                "label": s.label,
                "kind": s.kind,
                "target_pct": s.target,
                "window_days": s.window_days,
                "threshold_ms": s.threshold_ms,
                "owner": s.owner,
                "objective": objective,
            }
        )
    return rows
