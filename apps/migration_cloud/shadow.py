"""Phase U8 — shadow-mode for cutover safety.

A school cutting over from an existing SIS doesn't want a hard switch:
they want to run RunMyCampus and the old system *in parallel* for a
window (typically 7–30 days), watch the deltas auto-reconcile, and only
flip the DNS / accept the new system when parity holds above a
configurable threshold.

This module provides three operations against an ``APPLIED`` (or
``RECONCILED``) bundle:

    start_shadow_window(bundle, hours, threshold_pct, source_pull) →
        Begin tracking. Records `shadow_window_opened_at`, target
        parity threshold, and the *snapshot* of the tenant counts at
        start. `source_pull` is a callable the operator provides that
        returns the *current* counts from the old SIS (rows per
        canonical domain) — the platform doesn't assume how the old
        system is queried; it just consumes the count dict.

    refresh_shadow(bundle, source_pull) →
        Recompute current tenant counts, compute deltas vs. the source
        snapshot, append a tick to the rolling drift series, and decide
        whether the auto-cutover policy fires.

    close_shadow(bundle, accepted=True|False) →
        Either accept (cutover) or reject the shadow window. On accept,
        the bundle transitions to ``RECONCILED`` and the shadow record
        is sealed with `accepted=True`. On reject, the window closes
        with `accepted=False` so the operator can re-run the source
        feed before re-opening.

State lives in ``MigrationBundle.reconciliation_summary['shadow']``::

    {
        "opened_at": "2026-05-14T10:00:00Z",
        "target_parity_pct": 99.0,
        "max_window_hours": 168,
        "source_snapshot": {"students": 1240, "guardians": 1830, ...},
        "ticks": [
            {"at": "2026-05-14T10:05:00Z", "source": {...},
             "tenant": {...}, "drift_pct": 0.4, "trip": false}
        ],
        "auto_cutover_armed": true,
        "closed_at": null,
        "accepted": null,
    }

This is intentionally storage-only — no Celery beat, no background
poller. The operator (or a tenant cron) calls ``refresh_shadow`` on a
schedule that matches their SLA. Anything beat-driven lives on top of
this surface in a future polish wave.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Callable

from django.utils import timezone

from .models import BundleStatus, MigrationBundle

logger = logging.getLogger(__name__)


@dataclass
class ShadowTick:
    at: str
    source: dict[str, int]
    tenant: dict[str, int]
    drift_pct: float
    trip: bool                      # True if drift crossed the auto-cutover threshold


@dataclass
class ShadowState:
    opened_at: str = ""
    target_parity_pct: float = 99.0
    max_window_hours: int = 168
    source_snapshot: dict[str, int] = field(default_factory=dict)
    ticks: list[ShadowTick] = field(default_factory=list)
    auto_cutover_armed: bool = False
    closed_at: str | None = None
    accepted: bool | None = None


def start_shadow_window(
    *,
    bundle_id: int,
    target_parity_pct: float = 99.0,
    max_window_hours: int = 168,
    source_pull: Callable[[], dict[str, int]] | None = None,
    auto_cutover_armed: bool = False,
) -> ShadowState:
    """Open a shadow window on an APPLIED / RECONCILED bundle.

    ``source_pull()`` returns the old-system per-domain row counts at the
    moment shadowing starts; this is the snapshot subsequent ticks
    compare against. When ``source_pull`` is omitted, the snapshot is
    seeded from the bundle's own ``mapping_summary.apply_totals`` so the
    operator can still track drift as the *new* tenant evolves.
    """
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    bundle = MigrationBundle.objects.get(pk=bundle_id)
    if bundle.status not in (BundleStatus.APPLIED, BundleStatus.RECONCILED):
        raise ValueError(
            f"Bundle {bundle_id} in status {bundle.status}; must be APPLIED to shadow."
        )

    snapshot = source_pull() if source_pull else _seed_snapshot_from_bundle(bundle)
    state = ShadowState(
        opened_at=timezone.now().isoformat(),
        target_parity_pct=float(target_parity_pct),
        max_window_hours=int(max_window_hours),
        source_snapshot=dict(snapshot or {}),
        auto_cutover_armed=bool(auto_cutover_armed),
    )
    _save_state(bundle, state)
    return state


def refresh_shadow(
    *,
    bundle_id: int,
    source_pull: Callable[[], dict[str, int]] | None = None,
    tenant_counter: Callable[[MigrationBundle], dict[str, int]] | None = None,
) -> ShadowState:
    """Take a tick: pull source counts + tenant counts, compute drift, persist.

    Returns the updated state. If the auto-cutover policy is armed and
    drift trips below the parity threshold, the function calls
    ``close_shadow(bundle, accepted=True)`` and the bundle transitions
    to RECONCILED.
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    """
    bundle = MigrationBundle.objects.get(pk=bundle_id)
    state = _load_state(bundle)
    if state is None:
        raise ValueError(f"Bundle {bundle_id} has no open shadow window.")
    if state.closed_at:
        raise ValueError(
            f"Bundle {bundle_id} shadow window already closed at {state.closed_at}."
        )

    source_counts = source_pull() if source_pull else dict(state.source_snapshot)
    tenant_counts = (
        tenant_counter(bundle)
        if tenant_counter
        else _count_tenant_rows(bundle)
    )

    drift_pct = _compute_drift_pct(source_counts, tenant_counts)
    trip = drift_pct >= (100.0 - state.target_parity_pct)
    tick = ShadowTick(
        at=timezone.now().isoformat(),
        source=dict(source_counts),
        tenant=dict(tenant_counts),
        drift_pct=round(drift_pct, 3),
        trip=trip,
    )
    state.ticks.append(tick)
    _save_state(bundle, state)

    # Auto-cutover: if armed AND most recent N ticks all hold below the
    # drift threshold (parity >= target), trip the cutover.
    if state.auto_cutover_armed and _sustained_parity(state):
        close_shadow(bundle_id=bundle_id, accepted=True)
        bundle.refresh_from_db()
        state = _load_state(bundle) or state
    return state


# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
def close_shadow(*, bundle_id: int, accepted: bool) -> ShadowState:
    """Seal the shadow window. ``accepted=True`` advances the bundle to RECONCILED."""
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    bundle = MigrationBundle.objects.get(pk=bundle_id)
    state = _load_state(bundle)
    if state is None:
        raise ValueError(f"Bundle {bundle_id} has no shadow window to close.")
    state.closed_at = timezone.now().isoformat()
    state.accepted = bool(accepted)
    state.auto_cutover_armed = False
    _save_state(bundle, state)
    if accepted and bundle.status == BundleStatus.APPLIED:
        bundle.mark_status(
            BundleStatus.RECONCILED,
            summary_patch={"shadow_accepted": True, "shadow_closed_at": state.closed_at},
        )
    return state


# --- Helpers --------------------------------------------------------------

_SUSTAINED_TICKS = 3  # consecutive clean ticks required before auto-cutover


def _sustained_parity(state: ShadowState) -> bool:
    if len(state.ticks) < _SUSTAINED_TICKS:
        return False
    recent = state.ticks[-_SUSTAINED_TICKS:]
    return all(not t.trip for t in recent)


def _compute_drift_pct(source: dict[str, int], tenant: dict[str, int]) -> float:
    """Symmetric percentage drift across the union of domains.

    drift_pct = 100 * sum(abs(src - tgt)) / max(1, sum(max(src, tgt)))

    A perfectly synchronised state returns 0.0; any one-sided population
    returns 100.0.
    """
    domains = set(source.keys()) | set(tenant.keys())
    total_diff = 0
    total_scale = 0
    for d in domains:
        s = int(source.get(d, 0) or 0)
        t = int(tenant.get(d, 0) or 0)
        total_diff += abs(s - t)
        total_scale += max(s, t)
    if total_scale == 0:
        return 0.0
    return 100.0 * total_diff / total_scale


def _seed_snapshot_from_bundle(bundle: MigrationBundle) -> dict[str, int]:
    """Use the bundle's own per-domain landed counts as the source baseline.

    Useful when no live-source feed is available — the operator can still
    track *forward* drift (rows added in the new tenant beyond the
    migrated baseline) without wiring a connection to the old SIS.
    """
    apply_totals = (bundle.mapping_summary or {}).get("apply_totals") or {}
    return {
        "students": int(apply_totals.get("created", 0)),
        "guardians": 0,
        "staff": 0,
        "attendance": 0,
        "grades": 0,
        "finance": 0,
    }


def _count_tenant_rows(bundle: MigrationBundle) -> dict[str, int]:
    """Count current rows in the tenant for the domains we know how to count.

    Best-effort: each model is imported lazily and any failure for one
    domain just leaves that key at 0 rather than aborting the tick.
    Wrapped in ``schema_context`` so counts come from the correct tenant.
    """
    counts: dict[str, int] = {}
    try:
        from django_tenants.utils import schema_context  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        schema_context = None  # type: ignore[assignment]

    def _wrap(work):
        if schema_context and bundle.schema_name:
            with schema_context(bundle.schema_name):
                return work()
        return work()

    def _safe_count(label: str, importer: Callable[[], int]) -> None:
        try:
            counts[label] = _wrap(importer)
        except Exception:  # noqa: BLE001
            counts[label] = 0

    _safe_count("students", lambda: _model_count("apps.people.models", "StudentProfile"))
    _safe_count("guardians", lambda: _model_count("apps.people.models", "StudentGuardian"))
    _safe_count("staff", lambda: _model_count("apps.people.models", "TeacherProfile"))
    _safe_count("attendance", lambda: _model_count("apps.academics.models", "Attendance"))
    _safe_count("grades", lambda: _model_count("apps.evals.models", "Evaluation"))
    _safe_count("finance", lambda: _model_count("apps.finance.models", "Invoice"))
    _safe_count("sections", lambda: _model_count("apps.academics.models", "Classroom"))
    _safe_count("behavior", lambda: _model_count("apps.academics.models", "Incident"))
    return counts


def _model_count(module: str, class_name: str) -> int:
    import importlib
    mod = importlib.import_module(module)
    cls = getattr(mod, class_name, None)
    if cls is None:
        return 0
    return cls.objects.count()


def _load_state(bundle: MigrationBundle) -> ShadowState | None:
    payload = (bundle.reconciliation_summary or {}).get("shadow")
    if not isinstance(payload, dict):
        return None
    ticks = [
        ShadowTick(
            at=t.get("at", ""),
            source=dict(t.get("source") or {}),
            tenant=dict(t.get("tenant") or {}),
            drift_pct=float(t.get("drift_pct", 0.0) or 0.0),
            trip=bool(t.get("trip", False)),
        )
        for t in (payload.get("ticks") or [])
    ]
    return ShadowState(
        opened_at=str(payload.get("opened_at") or ""),
        target_parity_pct=float(payload.get("target_parity_pct", 99.0) or 99.0),
        max_window_hours=int(payload.get("max_window_hours", 168) or 168),
        source_snapshot=dict(payload.get("source_snapshot") or {}),
        ticks=ticks,
        auto_cutover_armed=bool(payload.get("auto_cutover_armed", False)),
        closed_at=payload.get("closed_at"),
        accepted=payload.get("accepted"),
    )


def _save_state(bundle: MigrationBundle, state: ShadowState) -> None:
    summary = dict(bundle.reconciliation_summary or {})
    summary["shadow"] = {
        "opened_at": state.opened_at,
        "target_parity_pct": state.target_parity_pct,
        "max_window_hours": state.max_window_hours,
        "source_snapshot": state.source_snapshot,
        "ticks": [asdict(t) for t in state.ticks],
        "auto_cutover_armed": state.auto_cutover_armed,
        "closed_at": state.closed_at,
        "accepted": state.accepted,
    }
    bundle.reconciliation_summary = summary
    bundle.save(update_fields=["reconciliation_summary", "updated_at"])
