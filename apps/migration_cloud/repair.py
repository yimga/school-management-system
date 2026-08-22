"""Safe, idempotent auto-repair for a stalled or failed Migration Cloud bundle.

An apply can finish in a state that needs another pass:

* ``FAILED`` — one or more artifacts errored mid-apply (a transient fault, or a
  lander bug since fixed, e.g. the Phase-0 quarantine-writer repair), so the
  whole bundle was flagged FAILED even though most rows landed.
* ``APPLIED`` with rows held for review / a visible-count shortfall — some rows
  were quarantined or a create did not persist, so the school is under-populated.

:func:`repair_bundle` re-applies the bundle **idempotently** — ``apply_bundle``
upserts by external id, so re-applying never duplicates already-landed rows;
previously-failed / held rows simply get another attempt — then re-verifies by
re-querying the tenant.

It is deliberately CONSERVATIVE. A blind retry is unsafe in several cases, and
:func:`repair_readiness` refuses every one of them rather than paper over it:

* NEVER a financial-guardrail failure. Re-applying must not silently bypass a
  control-total mismatch — the operator has to reconcile the numbers first.
  (Guardrail: never suppress ``FinancialMismatchError``.)
* NEVER finance artifacts under a non-atomic apply. A partial finance re-apply
  could double-count or leave money half-written, so finance repair requires
  ``apply_atomic`` (all-or-nothing).
* NEVER a ``RECONCILED`` bundle. Its source blobs are already purged (nothing to
  re-apply from) and it is confirmed good.
* NEVER a bundle mid-flight (``APPLYING``), cancelled (``ABORTED``), or not yet
  applied (pre-``MAPPED``) — those are not "broken applies".

This runs on the tenant's own bundle (IDOR-scoped by the calling view) and is
one explicit click, not a silent background fire: a live re-import writes to the
tenant DB, so the person owning the data initiates it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from django.utils import timezone

from .apply_progress_guard import reset_apply_progress
from .models import BundleStatus, FinancialMismatchError, MigrationBundle
from .progress import APPLY_RUN_EPOCH_KEY

logger = logging.getLogger(__name__)

# All finance-ish files (invoices / receipts / payments / fees) normalise to the
# single canonical domain slug ``finance`` in runmycampus_canonical.
_FINANCE_DOMAIN = "finance"


@dataclass
class RepairReadiness:
    """Whether a bundle can be safely re-applied, and why / why not."""

    repairable: bool
    reason: str
    blockers: list[str] = field(default_factory=list)
    has_finance: bool = False
    issue_count: int = 0
    status: str = ""


@dataclass
class RepairResult:
    """Outcome of a repair attempt."""

    ok: bool
    ran: bool
    message: str
    before_status: str = ""
    after_status: str = ""
    created: int = 0
    updated: int = 0
    quarantined: int = 0
    blockers: list[str] = field(default_factory=list)
    queued: bool = False
    outbox_id: str = ""
    auto_remediate: dict[str, Any] = field(default_factory=dict)


def _resolved_domains(bundle: MigrationBundle) -> set[str]:
    """Domains the bundle will actually apply (discovery result + tenant override)."""
    domains: set[str] = set()
    per_artifact_domain = (getattr(bundle, "discovery_summary", None) or {}).get(
        "per_artifact_domain"
    ) or {}
    for _path, entry in per_artifact_domain.items():
        if entry.get("domain"):
            domains.add(entry["domain"])
    if not getattr(bundle, "pk", None):
        return domains
    try:
        artifacts = bundle.artifacts.all()
    except Exception:  # noqa: BLE001 — unpersisted bundle / SimpleTestCase fakes
        logger.debug(
            "repair: artifact domain walk skipped for bundle %s",
            getattr(bundle, "pk", None),
            exc_info=True,
        )
        return domains
    for artifact in artifacts:
        entry = per_artifact_domain.get(artifact.path_within_bundle) or {}
        if entry.get("domain"):
            domains.add(entry["domain"])
        assigned = getattr(artifact, "assigned_domain", "") or ""
        if assigned:
            domains.add(assigned)
    return domains


def _has_finance(bundle: MigrationBundle) -> bool:
    return _FINANCE_DOMAIN in _resolved_domains(bundle)


def _recon_notes_are_current(bundle: MigrationBundle) -> bool:
    """True when stored recon notes describe *this* apply, not a previous one.

    ``apply_totals.applied_at`` is rewritten at the end of every live apply.
    ``reconciliation_summary.generated_at`` is rewritten only when reconcile
    actually ran. If apply finished later than recon, the notes are leftovers
    and must not keep a Repair card or a held-for-review badge.
    """
    totals = (getattr(bundle, "mapping_summary", None) or {}).get("apply_totals") or {}
    applied_at = str(totals.get("applied_at") or "")
    generated = str(
        (getattr(bundle, "reconciliation_summary", None) or {}).get("generated_at") or ""
    )
    if applied_at and generated:
        return generated >= applied_at
    return True


def _unresolved_issue_count(bundle: MigrationBundle) -> int:
    """Rows still needing attention: pending held rows + current visible-drift.

    Prefer live ``MigrationQuarantineRecord`` PENDING rows tied to this bundle
    so operator dismissals in the review queue immediately clear badges. Fall
    back to the last apply's ``quarantined`` total when no run-linked rows exist.
    """
    from .quarantine_resolution import pending_quarantine_count

    try:
        pending = pending_quarantine_count(bundle)
    except Exception:  # noqa: BLE001 — SimpleTestCase / offline callers use apply_totals
        logger.debug(
            "repair: live pending quarantine count unavailable for bundle %s",
            getattr(bundle, "pk", None),
            exc_info=True,
        )
        pending = 0
    if pending:
        drift_notes = []
        if _recon_notes_are_current(bundle):
            recon = getattr(bundle, "reconciliation_summary", None) or {}
            drift_notes = [n for n in (recon.get("notes") or []) if "visible" in str(n).lower()]
        return pending + len(drift_notes)

    apply_totals = (getattr(bundle, "mapping_summary", None) or {}).get("apply_totals") or {}
    quarantined = int(apply_totals.get("quarantined") or 0)
    if not _recon_notes_are_current(bundle):
        return quarantined
    recon = getattr(bundle, "reconciliation_summary", None) or {}
    drift_notes = [n for n in (recon.get("notes") or []) if "visible" in str(n).lower()]
    return quarantined + len(drift_notes)


def unresolved_issue_count(bundle: MigrationBundle) -> int:
    """Public alias used by the kickoff-page live attention composer."""
    return _unresolved_issue_count(bundle)


def _has_unresolved_issues(bundle: MigrationBundle) -> bool:
    return _unresolved_issue_count(bundle) > 0


def prior_apply_evidence(bundle: MigrationBundle) -> bool:
    """True when this bundle has already run at least one live apply."""
    totals = (getattr(bundle, "mapping_summary", None) or {}).get("apply_totals") or {}
    if str(totals.get("applied_at") or "").strip():
        return True
    return any(int(totals.get(k) or 0) for k in ("created", "updated", "quarantined"))


def _financial_guardrail_locked(bundle: MigrationBundle) -> bool:
    return bool((bundle.size_summary or {}).get("financial_guardrail_failed"))


def _not_repairable_reason(status: str) -> str:
    if status == BundleStatus.RECONCILED:
        return "This import is fully reconciled — there is nothing to repair."
    if status == BundleStatus.APPLIED:
        return "This import applied cleanly — there is nothing to repair."
    if status == BundleStatus.APPLYING:
        return "This import is still running. Wait for it to finish, then check again."
    if status == BundleStatus.ABORTED:
        return "This import was cancelled. Start a fresh upload to try again."
    return "This upload hasn't been imported yet — preview and import it first."


# A bundle wedges in APPLYING when the worker dies mid-apply (SIGKILL / OOM /
# deploy restart) before the orchestrator's catch-all can mark it FAILED, or when
# an error escaped the apply's pre-wave setup. Without a reclaim path
# repair_readiness refused APPLYING forever ("still running") and re-apply requires
# MAPPED, so the import was unrecoverable without DB surgery. Reclaim it only when
# NO apply is actually in flight AND it has been APPLYING past this threshold.
_APPLYING_STALE_SECONDS = 30 * 60  # generous — longer than a real large apply's quiet gaps


def _apply_in_flight(bundle: MigrationBundle) -> bool:
    """True if a durable apply job for this bundle is queued or running.

    The HeavyWorkOutbox apply row is the authoritative in-flight signal — it exists
    PENDING -> PROCESSING for the whole life of the background apply. Best-effort: if
    the outbox cannot be read we assume NOT in flight, so a genuinely wedged bundle
    stays reclaimable rather than being pinned "still running" forever.
    """
    try:
        from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

        return HeavyWorkOutbox.objects.filter(  # tenant-isolation-allow: bundle_id is the globally-unique shared MigrationBundle pk; the bundle is already tenant-scoped by the calling view
            bundle_id=bundle.pk,
            kind=HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE,
            status__in=(HeavyWorkOutbox.Status.PENDING, HeavyWorkOutbox.Status.PROCESSING),
        ).exists()
    except Exception:  # noqa: BLE001 — absence of the signal must not crash repair
        logger.debug("repair: could not read apply outbox for bundle %s", bundle.pk)
        return False


def applying_stale_by_time(bundle: MigrationBundle) -> bool:
    """A bundle stuck at APPLYING with no heartbeat past the stale threshold.

    Time-only — it does NOT consult the HeavyWorkOutbox in-flight signal. A LIVE
    apply heartbeats ``updated_at`` every wave/artifact (orchestrator
    ``_heartbeat_apply``), so a stale ``updated_at`` here means the apply's worker
    stopped writing. This is the single source of truth for "wedged apply"
    staleness; :func:`_applying_is_stale` layers the in-flight guard on top for the
    manual repair path, and ``orchestrator._apply_bundle_inner`` uses THIS one for
    the durable-retry self-heal (where the retry's own outbox row would otherwise
    read as in-flight and mask a genuinely dead prior apply).
    """
    if bundle.status != BundleStatus.APPLYING:
        return False
    return _seconds_since_apply_signal(bundle) > _APPLYING_STALE_SECONDS


def _seconds_since_apply_signal(bundle: MigrationBundle) -> float:
    """Age of the newest signal that only a LIVE apply can produce.

    ``updated_at`` alone is NOT trustworthy here: it is ``auto_now``, so *any*
    save to the bundle re-stamps it, including saves made by read-only viewers.
    A polled progress view that persisted its snapshot therefore kept re-arming
    the heartbeat of an apply whose worker was already dead, and the tenant was
    shown "Writing records into your school..." indefinitely.

    The progress-event stream is the honest signal: while a bundle is APPLYING
    only the orchestrator appends to it (stage_started, then a pulse per wave /
    artifact). Prefer the newest event and fall back to ``updated_at`` only when
    no event exists at all -- an apply always emits ``stage_started`` on entry,
    so the fallback is the empty-stream edge case, not the normal path.
    """
    now = timezone.now()
    try:
        from .models import MigrationProgressEvent

        latest = (
            MigrationProgressEvent.objects.filter(bundle_id=bundle.pk)  # tenant-isolation-allow: bundle_id is the globally-unique shared MigrationBundle pk; the bundle is already tenant-scoped by the caller
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first()
        )
    except Exception:  # noqa: BLE001 — never let a staleness probe break the page
        logger.debug("repair: could not read progress events for bundle %s", bundle.pk)
        latest = None
    if latest is not None:
        return (now - latest).total_seconds()
    updated = getattr(bundle, "updated_at", None)
    if updated is None:
        return float("inf")
    return (now - updated).total_seconds()


def _applying_is_stale(bundle: MigrationBundle) -> bool:
    """A bundle stuck at APPLYING with no in-flight apply job, past the threshold."""
    if _apply_in_flight(bundle):
        return False
    return applying_stale_by_time(bundle)


# A queued apply row this old has not been claimed by any drain, which means the
# queue is not moving for it (no worker consuming the broker, or the in-process
# drain never ran). Matches the threshold the review page uses to stop calling a
# queued import "working" — the tenant is told it is stuck, so the recovery path
# must agree with what they were told.
_QUEUED_APPLY_STUCK_SECONDS = 90  # magic-number-allow: queued-apply-wedged-threshold-seconds


def _apply_rows(bundle: MigrationBundle):
    """Open (PENDING / PROCESSING) apply outbox rows for this bundle, newest first."""
    from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

    if not getattr(bundle, "pk", None):
        return []
    try:
        return list(
            HeavyWorkOutbox.objects.filter(  # tenant-isolation-allow: bundle_id is the globally-unique shared MigrationBundle pk; the bundle is already tenant-scoped by the caller
                bundle_id=bundle.pk,
                kind=HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE,
                status__in=(
                    HeavyWorkOutbox.Status.PENDING,
                    HeavyWorkOutbox.Status.PROCESSING,
                ),
            ).order_by("-created_at")
        )
    except Exception:  # noqa: BLE001 — SimpleTestCase / offline callers use in-memory fakes
        logger.debug(
            "repair: apply outbox lookup unavailable for bundle %s",
            getattr(bundle, "pk", None),
            exc_info=True,
        )
        return []


def _row_is_wedged(bundle: MigrationBundle, row) -> bool:
    """True when this apply row cannot be making progress.

    PENDING past the threshold  → nothing ever claimed it.
    PROCESSING but the bundle's apply signal is stale → the worker that claimed it
    stopped heartbeating (killed mid-run), and the outbox reclaim window is far
    longer than a tenant can reasonably be asked to stare at a frozen bar.
    """
    from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

    now = timezone.now()
    if row.status == HeavyWorkOutbox.Status.PENDING:
        created = getattr(row, "created_at", None)
        if created is None:
            return False
        return (now - created).total_seconds() > _QUEUED_APPLY_STUCK_SECONDS
    return _seconds_since_apply_signal(bundle) > _APPLYING_STALE_SECONDS


def live_apply_in_flight(bundle: MigrationBundle) -> bool:
    """An apply that is genuinely moving — not merely an open outbox row.

    ``_apply_in_flight`` answers "is there an open row", which a wedged row also
    satisfies; that is what pinned a stranded repair as "still running" forever.
    """
    return any(not _row_is_wedged(bundle, row) for row in _apply_rows(bundle))


# How often one bundle may trigger a local drain nudge. The review page polls
# every ~2.5s per viewer, so without a cooldown a stuck import would spawn a drain
# thread on every poll from every open tab.
_NUDGE_COOLDOWN_SECONDS = 60  # magic-number-allow: stuck-apply-nudge-cooldown-seconds

# Tenant-facing wedge: shorter than orchestrator self-heal (30m) so Repair matches
# the Issue Remediator "stopped responding" card instead of spinning for half an hour.
_TENANT_WEDGE_HEARTBEAT_SECONDS = 180  # magic-number-allow: tenant-wedge-heartbeat-stuck-seconds


def tenant_apply_stuck(bundle: MigrationBundle) -> bool:
    """True when the tenant UI should treat this import as wedged / recoverable.

    Uses the same queued threshold as the progress poller and a shorter heartbeat
    window for PROCESSING/APPLYING so Repair is available when the remediator says
    the import stopped — not 30 minutes later.
    """
    from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

    if bundle.status in (BundleStatus.RECONCILED, BundleStatus.ABORTED):
        return False
    now = timezone.now()
    for row in _apply_rows(bundle):
        if row.status == HeavyWorkOutbox.Status.PENDING:
            created = getattr(row, "created_at", None)
            if created is not None and (now - created).total_seconds() > _QUEUED_APPLY_STUCK_SECONDS:
                return True
        elif row.status == HeavyWorkOutbox.Status.PROCESSING:
            if _seconds_since_apply_signal(bundle) > _TENANT_WEDGE_HEARTBEAT_SECONDS:
                return True
    if bundle.status == BundleStatus.APPLYING and not live_apply_in_flight(bundle):
        if _seconds_since_apply_signal(bundle) > _TENANT_WEDGE_HEARTBEAT_SECONDS:
            return True
    return False


def nudge_stuck_apply(bundle: MigrationBundle) -> bool:
    """Self-heal a queued apply that no drain has claimed. True if a nudge fired.

    Called from the tenant progress poller, which is the only heartbeat that is
    guaranteed to exist: it runs in the web process, needs no worker, and fires
    precisely while a human is watching the import that is stuck.

    The nudge drains IN-PROCESS on purpose. A row PENDING past
    :data:`_QUEUED_APPLY_STUCK_SECONDS` has already demonstrated that whatever was
    supposed to claim it is not claiming it — re-publishing to the same broker
    would be asking the mechanism that failed to try again. Idempotent: the drain
    claims rows with a conditional UPDATE, so a nudge that races a real worker
    loses the claim harmlessly.
    """
    from django.core.cache import cache

    rows = _apply_rows(bundle)
    if not rows or not any(_row_is_wedged(bundle, row) for row in rows):
        return False
    key = f"mc:nudge-apply:{bundle.pk}"
    try:
        if not cache.add(key, "1", _NUDGE_COOLDOWN_SECONDS):
            return False
    except Exception:  # noqa: BLE001 — a cache outage must not disable the self-heal
        logger.debug("repair: nudge cooldown unavailable for %s", bundle.pk, exc_info=True)
    try:
        from apps.platform_runtime.heavy_work_outbox import kick_heavy_work_drain

        kick_heavy_work_drain(force_local=True)
    except Exception:  # noqa: BLE001 — never break the poller on a self-heal attempt
        logger.warning("repair: local drain nudge failed for %s", bundle.pk, exc_info=True)
        return False
    logger.info(
        "migration_cloud.repair: nudged a local drain for stranded apply on bundle %s",
        bundle.pk,
    )
    return True


def supersede_wedged_apply(bundle: MigrationBundle) -> int:
    """Retire wedged apply rows and return how many were retired.

    The apply idempotency key is ``mc-apply:<id>:live:active`` and
    ``enqueue_heavy_work`` reuses any PENDING/PROCESSING row carrying it. So once a
    row wedges, every later enqueue is handed that same dead row and the caller is
    told "queued" while nothing was queued — pressing Repair again could never
    change anything. Retiring the row frees the key so the next enqueue creates
    real work.

    Safe by construction: only rows :func:`_row_is_wedged` accepts are touched, so
    a live apply is never cancelled out from under itself.
    """
    from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

    retired = 0
    for row in _apply_rows(bundle):
        if not _row_is_wedged(bundle, row):
            continue
        updated = HeavyWorkOutbox.objects.filter(  # tenant-isolation-allow: platform-heavy-work-outbox-supersede-by-pk
            pk=row.pk, status=row.status
        ).update(
            status=HeavyWorkOutbox.Status.FAILED,
            last_error=(
                "superseded: the apply was never picked up (or its worker stopped "
                "heartbeating) and a repair re-queued it"
            ),
            finished_at=timezone.now(),
        )
        if updated:
            retired += 1
            logger.warning(
                "migration_cloud.repair: superseded wedged apply row %s (%s) for bundle %s",
                row.pk,
                row.status,
                bundle.pk,
            )
    return retired


def repair_readiness(bundle: MigrationBundle) -> RepairReadiness:
    """Decide — conservatively — whether re-applying this bundle is safe."""
    status = bundle.status
    has_finance = _has_finance(bundle)

    # 1. A financial control-total failure must never be auto-bypassed.
    if _financial_guardrail_locked(bundle):
        return RepairReadiness(
            repairable=False,
            reason=(
                "This import stopped on a financial control-total check. Repair "
                "cannot bypass it — reconcile the expected money totals first, "
                "then re-import."
            ),
            blockers=["financial_guardrail_failed"],
            has_finance=True,
            status=status,
        )

    # 2. Only a failed apply, or an applied-with-open-issues one, is repairable.
    if status == BundleStatus.FAILED:
        reason = (
            "The last import failed part-way. Retrying is safe: records that "
            "already imported are updated in place, never duplicated, and the "
            "records that failed get another attempt."
        )
    elif status == BundleStatus.APPLIED and _has_unresolved_issues(bundle):
        reason = (
            "Some records were held for review or didn't fully land. Retrying "
            "re-attempts just those, without duplicating what already imported."
        )
    elif (
        status == BundleStatus.MAPPED
        and _has_unresolved_issues(bundle)
        and not live_apply_in_flight(bundle)
    ):
        # A repair that was queued and never drained. ``repair_bundle`` resets the
        # bundle to MAPPED *before* enqueuing, so a queue that never moves strands
        # it here — and MAPPED used to fall through to "this upload hasn't been
        # imported yet", which WITHDREW the only recovery control on the page while
        # the board still said "Queued". Nothing else could see it either: the
        # wedge probe only inspects APPLYING and the outbox reclaim only inspects
        # PROCESSING. Requiring unresolved issues keeps a genuinely fresh,
        # never-applied MAPPED upload on the honest "import it first" path.
        reason = (
            "The repair you started was never picked up by the importer. Retrying "
            "is safe: records that already imported are updated in place, never "
            "duplicated, and the rest get another attempt."
        )
    elif (
        status == BundleStatus.MAPPED
        and tenant_apply_stuck(bundle)
        and (prior_apply_evidence(bundle) or _has_unresolved_issues(bundle))
    ):
        # Operator reclaim or a crashed repair left the bundle at MAPPED while a
        # wedged outbox row still pins the UI at "Running". Retire the row (via
        # supersede_wedged_apply / --force-reclaim) then re-queue repair.
        reason = (
            "This import partially ran and the background job wedged. Retrying "
            "is safe: records that already imported are updated in place, never "
            "duplicated, and held rows can be cleared or re-attempted."
        )
    elif status == BundleStatus.APPLYING and (
        _applying_is_stale(bundle) or tenant_apply_stuck(bundle)
    ):
        # Reclaim a wedged apply — the worker was interrupted and no apply is in
        # flight. Same safety envelope as FAILED: the finance-atomic gate below
        # still applies, and apply_bundle upserts so landed rows are never dupes.
        reason = (
            "The last import stopped unexpectedly while applying — the worker was "
            "interrupted before it could finish. Retrying is safe: records that "
            "already imported are updated in place, never duplicated, and the rest "
            "get another attempt."
        )
    elif tenant_apply_stuck(bundle) and not live_apply_in_flight(bundle):
        reason = (
            "The importer never picked up this attempt (or it stopped without "
            "finishing). Retrying is safe: records that already imported are "
            "updated in place, never duplicated."
        )
    else:
        return RepairReadiness(
            repairable=False,
            reason=_not_repairable_reason(status),
            blockers=[f"status:{status}"],
            has_finance=has_finance,
            status=status,
        )

    # 3. Finance can only be retried all-or-nothing (atomic). A partial finance
    #    re-apply could double-count or half-write money.
    if has_finance and not bool(getattr(bundle, "apply_atomic", False)):
        return RepairReadiness(
            repairable=False,
            reason=(
                "This import includes finance data, which can only be safely "
                "retried in all-or-nothing mode. Ask your operator to enable "
                "atomic apply for this import, then repair."
            ),
            blockers=["finance_requires_atomic"],
            has_finance=True,
            issue_count=_unresolved_issue_count(bundle),
            status=status,
        )

    from .schema_binding import ensure_bundle_schema_name
    from .tenant_schema_readiness import (
        assess_tenant_schema_readiness,
        format_schema_drift_reason,
    )

    schema_name = ensure_bundle_schema_name(bundle)
    if schema_name:
        schema_ready = assess_tenant_schema_readiness(schema_name, attempt_repair=True)
        if not schema_ready.ready:
            return RepairReadiness(
                repairable=False,
                reason=format_schema_drift_reason(schema_ready),
                blockers=["tenant_schema_drift", *schema_ready.missing_labels[:5]],
                has_finance=has_finance,
                issue_count=_unresolved_issue_count(bundle),
                status=status,
            )

    return RepairReadiness(
        repairable=True,
        reason=reason,
        has_finance=has_finance,
        issue_count=_unresolved_issue_count(bundle),
        status=status,
    )


def _summary_message(result) -> str:
    return (
        f"Repair re-imported your data: {result.total_created} created, "
        f"{result.total_updated} updated, {result.total_quarantined} still held "
        "for review."
    )


def repair_bundle(*, bundle_id: int, off_http: bool = False) -> RepairResult:
    """Re-apply a repairable bundle idempotently, then re-verify.

    Returns a :class:`RepairResult`; never raises for the expected refusal /
    financial-abort paths (they are reported honestly with ``ok=False``). The
    bundle is only reset to ``MAPPED`` — the state ``apply_bundle`` requires — for
    bundles that :func:`repair_readiness` cleared.

    HTTP callers MUST pass ``off_http=True`` so the live re-apply lands on the
    durable HeavyWorkOutbox (never the request thread).
    """
    # tenant-isolation-allow: repair-bundle-pk-already-tenant-verified-by-calling-view
    # The sole caller (TenantMigrationRepairView.post) resolves the bundle through
    # _tenant_bundle_or_404 FIRST and passes that verified pk, so this re-fetch
    # cannot widen scope. Any NEW caller must do the same — pass a pk you have
    # already scoped to the acting tenant, never a raw user-supplied id.
    bundle = MigrationBundle.objects.get(pk=bundle_id)
    before = bundle.status
    readiness = repair_readiness(bundle)
    if not readiness.repairable:
        return RepairResult(
            ok=False,
            ran=False,
            message=readiness.reason,
            before_status=before,
            after_status=before,
            blockers=readiness.blockers,
        )

    logger.info(
        "migration_cloud.repair: re-applying bundle %s (was %s, %d open issue(s)) off_http=%s",
        bundle_id,
        before,
        readiness.issue_count,
        off_http,
    )
    try:
        from .auto_remediate import auto_remediate_before_repair

        auto_stats = auto_remediate_before_repair(bundle)
        logger.info(
            "migration_cloud.repair: auto-remediate bundle %s — %s",
            bundle_id,
            auto_stats,
        )
    except Exception:  # noqa: BLE001 — auto-remediate must not block repair
        auto_stats = {}
        logger.warning(
            "migration_cloud.repair: auto-remediate failed for bundle %s; continuing",
            bundle_id,
            exc_info=True,
        )
    # Reset to MAPPED so apply_bundle (which requires MAPPED) can re-run. Idempotent
    # upsert means landed rows are updated in place, never duplicated.
    #
    # The same write opens a NEW progress run. Without it the board replays the
    # previous apply: stage pct only ratchets up, so it showed the last run's 100%
    # for APPLYING (a frozen 75% overall) and reported the last run's created /
    # updated / held as though this repair had already produced them.
    now_iso = timezone.now().isoformat()
    bundle.mark_status(
        BundleStatus.MAPPED,
        summary_patch={
            "repair_requested_at": now_iso,
            APPLY_RUN_EPOCH_KEY: now_iso,
            "unified_progress_hwm": {"epoch": now_iso, "pct": 0.0},
        },
    )
    # A repair is a HUMAN deliberately asking for another attempt, so it re-arms the
    # forward-progress breaker. Without this, a bundle that tripped the breaker could
    # never be retried even after an operator resolved the held records that were
    # blocking it. Bounding automatic re-entry is the point; bounding people is not.
    reset_apply_progress(bundle)

    if off_http:
        from .celery_tasks import enqueue_apply

        # Free the apply idempotency key before enqueuing. Without this a wedged
        # PENDING/PROCESSING row is handed straight back by enqueue_heavy_work and
        # the tenant is told "queued" while nothing was queued — the reported
        # "Repair does nothing". Only rows proven wedged are retired, so a live
        # apply is never cancelled.
        superseded = supersede_wedged_apply(bundle)

        queued = enqueue_apply(
            bundle_id,
            dry_run=False,
            reconcile_after=True,
            force=True,
        )
        oid = str(
            getattr(queued, "outbox_id", None) or getattr(queued, "id", "") or ""
        )
        message = (
            "Repair is queued in the background. Refresh this page in a "
            "moment to see updated import results."
        )
        if superseded:
            message = (
                "The previous attempt had stopped without finishing, so it was "
                "cleared and a fresh repair is queued. Refresh this page in a "
                "moment to see updated import results."
            )
        try:
            from apps.platform_runtime.heavy_work_outbox import kick_heavy_work_drain

            # The tenant clicked Repair and is watching this page. Drain in-process
            # immediately — a configured-but-unconsumed broker accepts `.delay()`
            # yet never runs it, which otherwise leaves "Queued — waiting for the
            # importer…" frozen until the 90s poller nudge (or forever without one).
            kick_heavy_work_drain(force_local=True)
        except Exception:  # noqa: BLE001 — enqueue succeeded; drain kick is best-effort
            logger.warning(
                "migration_cloud.repair: local drain kick after enqueue failed for %s",
                bundle_id,
                exc_info=True,
            )
        return RepairResult(
            ok=True,
            ran=False,
            queued=True,
            outbox_id=oid,
            message=message,
            before_status=before,
            after_status=BundleStatus.MAPPED,
            auto_remediate=auto_stats,
        )

    from .orchestrator import apply_bundle

    try:
        result = apply_bundle(bundle_id=bundle_id, dry_run=False)
    except FinancialMismatchError:
        # apply_bundle already marked the bundle FAILED + set the guardrail flag.
        # Report honestly — this is NOT a suppression: the apply was aborted and
        # nothing beyond what already applied was written.
        bundle.refresh_from_db()
        return RepairResult(
            ok=False,
            ran=True,
            message=(
                "Repair stopped on the financial control-total check — the money "
                "totals don't match. Nothing was changed beyond what already "
                "applied. Reconcile the expected totals, then retry."
            ),
            before_status=before,
            after_status=bundle.status,
            blockers=["financial_guardrail_failed"],
        )
    except Exception as exc:  # noqa: BLE001 — surface, don't crash the request
        logger.warning("migration_cloud.repair: re-apply failed for %s: %s", bundle_id, exc)
        bundle.refresh_from_db()
        return RepairResult(
            ok=False,
            ran=True,
            message=(
                f"Repair re-import did not complete ({type(exc).__name__}). "
                "Nothing was duplicated — you can try again."
            ),
            before_status=before,
            after_status=bundle.status,
        )

    # Re-verify: re-query the tenant so source -> landed -> visible refreshes.
    # Best-effort — reconcile only advances to RECONCILED (and purges source
    # blobs) on perfect parity, so a still-imperfect repair stays APPLIED and
    # remains repairable.
    try:
        from .reconciliation import reconcile_bundle

        reconcile_bundle(bundle_id=bundle_id)
    except Exception:  # noqa: BLE001
        logger.debug("migration_cloud.repair: post-repair reconcile failed", exc_info=True)

    bundle.refresh_from_db()
    return RepairResult(
        ok=bundle.status in (BundleStatus.APPLIED, BundleStatus.RECONCILED),
        ran=True,
        message=_summary_message(result),
        before_status=before,
        after_status=bundle.status,
        created=result.total_created,
        updated=result.total_updated,
        quarantined=result.total_quarantined,
        auto_remediate=auto_stats,
    )
