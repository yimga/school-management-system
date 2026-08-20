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

from django.utils import timezone

from .models import BundleStatus, FinancialMismatchError, MigrationBundle

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


def _resolved_domains(bundle: MigrationBundle) -> set[str]:
    """Domains the bundle will actually apply (discovery result + tenant override)."""
    domains: set[str] = set()
    per_artifact_domain = (getattr(bundle, "discovery_summary", None) or {}).get(
        "per_artifact_domain"
    ) or {}
    for artifact in bundle.artifacts.all():
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
    """Rows still needing attention: current held rows + current visible-drift.

    Informational recon notes (scoped drill-down, incomplete verification copy)
    are not issues. Stale notes from a previous apply are ignored once a newer
    ``apply_totals.applied_at`` lands.
    """
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
    elif status == BundleStatus.APPLYING and _applying_is_stale(bundle):
        # Reclaim a wedged apply — the worker was interrupted and no apply is in
        # flight. Same safety envelope as FAILED: the finance-atomic gate below
        # still applies, and apply_bundle upserts so landed rows are never dupes.
        reason = (
            "The last import stopped unexpectedly while applying — the worker was "
            "interrupted before it could finish. Retrying is safe: records that "
            "already imported are updated in place, never duplicated, and the rest "
            "get another attempt."
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
    # Reset to MAPPED so apply_bundle (which requires MAPPED) can re-run. Idempotent
    # upsert means landed rows are updated in place, never duplicated.
    bundle.mark_status(
        BundleStatus.MAPPED,
        summary_patch={"repair_requested_at": timezone.now().isoformat()},
    )

    if off_http:
        from .celery_tasks import enqueue_apply

        queued = enqueue_apply(
            bundle_id,
            dry_run=False,
            reconcile_after=True,
        )
        oid = str(
            getattr(queued, "outbox_id", None) or getattr(queued, "id", "") or ""
        )
        return RepairResult(
            ok=True,
            ran=False,
            queued=True,
            outbox_id=oid,
            message=(
                "Repair is queued in the background. Refresh this page in a "
                "moment to see updated import results."
            ),
            before_status=before,
            after_status=BundleStatus.MAPPED,
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
    )
