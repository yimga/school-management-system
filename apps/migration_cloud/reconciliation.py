"""Phase U8 — reconciliation: the trust layer.

After ``orchestrator.apply_bundle`` lands rows in the tenant schema, the
operator (and eventually the tenant admin) needs to see *with their own
eyes* that the migration was faithful:

    * record-count parity per domain (source vs target)
    * per-field fill-rate scorecards (e.g. 98% of students have an email)
    * stratified random sample N rows for side-by-side comparison
    * idempotency check (re-running same bundle = zero duplicates)
    * quarantine drill-down (operator can ack errors + re-run a subset)

Output lives on ``MigrationBundle.reconciliation_summary`` (JSONField)
so the wizard renders without re-computing. Stable, deterministic,
re-runnable without side-effects.

Lifecycle: APPLIED → RECONCILED (or stays APPLIED if a critical check fails).
"""

from __future__ import annotations

import logging
import random
from dataclasses import asdict, dataclass, field
from typing import Any

from django.utils import timezone
from django.db import DatabaseError

from .models import BundleStatus, MigrationArtifact, MigrationBundle

logger = logging.getLogger(__name__)


@dataclass
class DomainParity:
    domain: str
    source_count: int
    target_created: int
    target_updated: int
    quarantined: int
    parity_pct: float
    # Rows ACTUALLY visible in the tenant school (re-queried post-apply). ``None``
    # when the domain has no confirmed model mapping (honest "not verified").
    target_visible_count: int | None = None
    fill_rate_by_field: dict[str, float] = field(default_factory=dict)
    # C-5 honesty: ``fill_rate_by_field`` is computed from the SOURCE file's
    # profiler null-rates, NOT from values that landed in the tenant. This label
    # names that basis so the wizard never reads it as "landed completeness".
    fill_rate_basis: str = "source_completeness"
    sample_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReconciliationReport:
    bundle_id: int
    generated_at: str
    overall_parity_pct: float
    per_domain: list[DomainParity] = field(default_factory=list)
    idempotency_check: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # PASS 2 verdict (verification.verify_bundle_checksums.as_dict()). Carries
    # the per-record SHA-256 source-vs-landed comparison, its closing bucket
    # tally, and every divergence by name. Empty dict when the pass did not run.
    checksum_verification: dict[str, Any] = field(default_factory=dict)


def reconcile_bundle(
    *,
    bundle_id: int,
    sample_size: int = 10,
    cohort: dict[str, Any] | None = None,
) -> ReconciliationReport:
    """Compute the reconciliation report for an APPLIED bundle.

    Idempotent: re-running produces identical numbers (modulo the random
    sample, which is seeded by the bundle's idempotency_key for stability).

    ``cohort`` (optional) restricts the report to a subset of the bundle.
    Shape::

        {
            "grade_level": "7" | ["6", "7"],
            "date_range": ["2025-09-01", "2025-09-30"],
            "student_external_ids": ["PS-1029", "PS-1042"],
            "domains": ["attendance", "grades"]
        }

    Any combination of keys is allowed. Filters compose with AND.
    """
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    bundle = MigrationBundle.objects.get(pk=bundle_id)
    if bundle.status not in (BundleStatus.APPLIED, BundleStatus.RECONCILED):
        raise ValueError(
            f"Bundle {bundle_id} is in status {bundle.status}; must be APPLIED to reconcile."
        )

    cohort = cohort or {}
    # A cohort restricts this pass to a SUBSET (a drill-down / inspection), so its
    # parity + drift notes only cover that subset. Closing the bundle out
    # (APPLIED→RECONCILED) or purging the encrypted source blobs on a partial
    # verification would destroy the proof AND the source for every domain this
    # pass never re-queried. A scoped reconcile is therefore strictly READ-ONLY:
    # it reports, but never transitions status, purges blobs, or auto-rolls-back.
    # Only a full-bundle (un-scoped) reconcile may seal + purge.
    scoped_readonly = bool(cohort)

    apply_totals = (bundle.mapping_summary or {}).get("apply_totals") or {}
    per_artifact_domain = (
        (bundle.discovery_summary or {}).get("per_artifact_domain") or {}
    )
    per_artifact_mappings = (bundle.mapping_summary or {}).get("per_artifact") or {}

    # Group artifacts by domain so reconciliation aggregates correctly.
    by_domain: dict[str, list[MigrationArtifact]] = {}
    cohort_domains = _normalise_cohort_list(cohort.get("domains"))
    for artifact in bundle.artifacts.all():
        domain = (per_artifact_domain.get(artifact.path_within_bundle) or {}).get(
            "domain", "custom_fields"
        )
        if cohort_domains and domain not in cohort_domains:
            continue
        by_domain.setdefault(domain, []).append(artifact)

    seed = _seed_for_bundle(bundle.idempotency_key)
    rng = random.Random(seed)

    parities: list[DomainParity] = []
    total_source = 0
    total_landed = 0

    # Pull MigrationRun stats per domain from the audit trail (self-reported).
    domain_run_stats = _domain_run_stats(bundle)

    # Re-query the tenant to count rows ACTUALLY visible per domain. The
    # self-reported run stats above cannot detect a rolled-back / wrong-school /
    # filtered-on-save apply — this is the real "did it land and is it in the
    # school" proof. A verification FAILURE (``None``) is distinct from a
    # legitimately-EMPTY result (``{}`` — no domain has a confident model
    # mapping): a failure must BLOCK the APPLIED → RECONCILED transition so the
    # bundle can never purge its encrypted source blobs on self-reported counts
    # alone. See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (C-6).
    visible_result = _safe_verify_visible(bundle)
    verification_failed = visible_result is None
    visible_by_domain = visible_result or {}
    visible_drift_notes: list[str] = []
    # Domains we CAN re-query (mapped in verification._DOMAIN_MODELS). Lets us tell a
    # domain whose visible-count is legitimately absent because it is unverifiable
    # (alumni / payroll / compliance — DFV-only, honest "not verified") apart from one
    # whose per-domain count ERRORED — verify_landed_counts swallows per-domain
    # failures, so an errored domain is silently absent. The latter reported creates
    # but we have NO proof they landed, so it must block the seal + purge.
    try:
        from .verification import domains_with_verification

        _verifiable_domains = domains_with_verification()
    except Exception:  # noqa: BLE001 — never let the spec lookup break reconcile
        _verifiable_domains = set()

    for domain, artifacts in sorted(by_domain.items()):
        source_count = sum(a.row_count or 0 for a in artifacts)
        run_stats = domain_run_stats.get(domain, {})
        target_created = run_stats.get("created", 0)
        target_updated = run_stats.get("updated", 0)
        quarantined = run_stats.get("errors", 0)
        landed = target_created + target_updated
        parity_pct = (landed / source_count * 100.0) if source_count else 100.0

        visible = visible_by_domain.get(domain)
        # Newly-created rows MUST be present in the school; if fewer rows are
        # visible than were reported created, the apply did not persist (rollback
        # / wrong scope) — surface it and keep the bundle out of RECONCILED.
        if visible is not None and target_created > 0 and visible < target_created:
            visible_drift_notes.append(
                f"{domain}: landers reported {target_created} created but only "
                f"{visible} row(s) are visible in the school — verify the apply persisted."
            )
        elif (
            visible is None
            and target_created > 0
            and not verification_failed
            and domain in _verifiable_domains
        ):
            # This domain IS re-queryable and reported creates, but its visible-count
            # is missing — the per-domain re-query errored (and was swallowed). Without
            # proof the rows landed, keep the bundle APPLIED so it can never purge on
            # self-reported counts. (A whole-verification failure is handled below.)
            visible_drift_notes.append(
                f"{domain}: landers reported {target_created} created but the "
                "visible-count re-query could not be completed — cannot confirm the "
                "rows landed; not sealing."
            )

        fill_rate = _fill_rate_for_domain(artifacts, per_artifact_mappings)
        samples = _stratified_sample(
            artifacts,
            per_artifact_mappings,
            sample_size=sample_size,
            rng=rng,
            cohort=cohort,
        )

        parities.append(DomainParity(
            domain=domain,
            source_count=source_count,
            target_created=target_created,
            target_updated=target_updated,
            quarantined=quarantined,
            parity_pct=round(parity_pct, 2),
            target_visible_count=visible,
            fill_rate_by_field=fill_rate,
            sample_rows=samples,
        ))
        total_source += source_count
        total_landed += landed

    overall = (total_landed / total_source * 100.0) if total_source else 100.0

    idempotency = _idempotency_check(bundle, apply_totals)

    notes: list[str] = []
    parity_threshold = 99.0
    if overall < parity_threshold:
        notes.append(
            f"Overall parity {overall:.2f}% is below the {parity_threshold}% threshold; "
            "operator review required before marking RECONCILED."
        )
    # A visible-count shortfall (creates that did not persist) is a hard signal —
    # keep the bundle APPLIED (not RECONCILED) so it is reviewed / repaired.
    notes.extend(visible_drift_notes)
    # A verification FAILURE (the visible-count check raised) must also block
    # RECONCILED: without proof the rows landed, advancing would purge the
    # encrypted source blobs on self-reported numbers alone. This note both
    # blocks the transition (the RECONCILED gate is ``if not notes``) and tells
    # the operator verification did not run.
    if verification_failed:
        notes.append(
            "Post-apply verification could not be completed (visible-count check "
            "failed) — the bundle stays APPLIED and the encrypted source blobs are "
            "retained until the landed rows are confirmed."
        )
    # PASS 2 — the cryptographic proof. Everything above counted rows; this
    # re-reads each SOURCE record from the encrypted artifact and each LANDED row
    # from the tenant database, independently, and compares them by SHA-256. Only
    # BLOCKING findings go into ``notes`` (a non-empty ``notes`` is what holds the
    # bundle at APPLIED); the full closing tally always lands in the summary below,
    # so a clean pass is still on the record rather than merely implied.
    checksum_summary: dict[str, Any] = {}
    if scoped_readonly:
        # A scoped drill-down never seals, so it never pays for the re-read.
        checksum_summary = {"ran": False, "reason": "scoped_readonly_reconcile"}
    elif not _checksum_pass_enabled():
        checksum_summary = {"ran": False, "reason": "disabled_by_setting"}
    else:
        checksum_report = _safe_verify_checksums(bundle)
        if checksum_report is None:
            checksum_summary = {"ran": False, "reason": "verifier_error"}
            notes.append(
                "Post-apply checksum verification (Pass 2) could not be completed "
                "— the bundle stays APPLIED and the encrypted source blobs are "
                "retained until source-vs-landed integrity is proven."
            )
        else:
            checksum_summary = checksum_report.as_dict()
            checksum_summary["ran"] = True
            notes.extend(_checksum_blocking_notes(checksum_report))
    if scoped_readonly:
        notes.append(
            "Scoped drill-down reconcile — read-only. The bundle was NOT closed "
            "out and the encrypted source blobs were retained; only a full-bundle "
            "reconcile may seal it."
        )

    report = ReconciliationReport(
        bundle_id=bundle.pk,
        generated_at=timezone.now().isoformat(),
        overall_parity_pct=round(overall, 2),
        per_domain=parities,
        idempotency_check=idempotency,
        notes=notes,
        checksum_verification=checksum_summary,
    )

    bundle.reconciliation_summary = _report_to_dict(report)
    bundle.save(update_fields=["reconciliation_summary", "updated_at"])

    # Auto-rollback gate (Tier 2 #13). Operators opt in by setting
    # `parity_drift_rollback_pct > 0` on the bundle.
    drift_threshold = float(getattr(bundle, "parity_drift_rollback_pct", 0.0) or 0.0)
    if (
        not scoped_readonly
        and drift_threshold > 0
        and overall < drift_threshold
        and bundle.status == BundleStatus.APPLIED
    ):
        _auto_rollback_bundle(bundle=bundle, observed_pct=overall, threshold=drift_threshold)
        notes.append(
            f"Auto-rollback triggered: overall parity {overall:.2f}% < threshold {drift_threshold:.2f}%."
        )
        report.notes = notes
        bundle.reconciliation_summary = _report_to_dict(report)
        bundle.save(update_fields=["reconciliation_summary", "updated_at"])
        return report

    if not scoped_readonly and not notes and bundle.status == BundleStatus.APPLIED:
        from .models_cutover import cutover_signoff_pending_for_bundle

        if cutover_signoff_pending_for_bundle(bundle):
            notes.append(
                "Cutover sign-off pending — reconcile sealed until the operator "
                "records domain sign-off on the cutover runbook."
            )
            report.notes = notes
            bundle.reconciliation_summary = _report_to_dict(report)
            bundle.save(update_fields=["reconciliation_summary", "updated_at"])
            return report
        bundle.mark_status(BundleStatus.RECONCILED)
        # Partner lifecycle event (G-5): nothing emitted bundle.reconciled before —
        # partners had no signal the migration was verified + sealed. Best-effort.
        try:
            from .services.lifecycle_events import (
                EVENT_BUNDLE_RECONCILED,
                emit_bundle_lifecycle_event,
            )
            emit_bundle_lifecycle_event(
                bundle, EVENT_BUNDLE_RECONCILED,
                {"overall_parity_pct": getattr(report, "overall_parity_pct", None)},
            )
        except Exception:  # noqa: BLE001 — event emission never blocks reconcile
            pass
        # Phase U5 content store (gap #2): the migration has landed +
        # reconciled, so the captured source PII is no longer needed. Drop the
        # encrypted blobs now (artifact METADATA is retained for the audit
        # trail). Best-effort — retention cleanup never blocks reconcile.
        try:
            from .artifact_blob_store import delete_blobs_for_bundle
            delete_blobs_for_bundle(bundle)
        except Exception:  # noqa: BLE001
            logger.debug(
                "migration_cloud.reconcile: source-blob cleanup skipped", exc_info=True
            )
        _mark_onboarding_migration_completed(bundle)

    return report


def run_post_apply_verification(*, bundle_id: int) -> None:
    """Best-effort visible-count verification immediately after a live apply.

    The tenant Review & Import pipeline's "Verify in school" bead and the
    per-domain verification table both depend on ``reconciliation_summary``,
    which is written only by :func:`reconcile_bundle`. Repair already called
    this path; normal applies did not — so verify never reached the finish line.

    Never raises: a reconcile failure must not undo a successful apply.
    """
    try:
        from .progress import emit

        emit(
            bundle_id=bundle_id,
            kind="stage_started",
            stage="VERIFYING",
            message="Verifying imported records are visible in your school…",
        )
        try:
            from .auto_remediate import auto_remediate_after_apply
            from .models import MigrationBundle

            bundle = MigrationBundle.objects.filter(pk=bundle_id).first()
            if bundle is not None:
                auto_remediate_after_apply(bundle)
        except Exception:  # noqa: BLE001
            logger.debug(
                "migration_cloud: post-apply auto-remediate skipped for bundle %s",
                bundle_id,
                exc_info=True,
            )
        reconcile_bundle(bundle_id=bundle_id)
        emit(
            bundle_id=bundle_id,
            kind="stage_finished",
            stage="VERIFYING",
            message="School verification finished.",
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "migration_cloud: post-apply verification failed for bundle %s",
            bundle_id,
            exc_info=True,
        )
        try:
            from .progress import emit

            emit(
                bundle_id=bundle_id,
                kind="error",
                stage="VERIFYING",
                message=(
                    "Could not complete school verification — "
                    "review counts manually or use Repair."
                ),
            )
        except Exception:  # noqa: BLE001
            logger.debug(
                "migration_cloud: VERIFYING error event failed for bundle %s",
                bundle_id,
                exc_info=True,
            )


def _mark_onboarding_migration_completed(bundle) -> None:
    """Write back the public-onboarding migration status so build_school_readiness
    resolves the "Data migrated" phase after a real reconcile.

    The migrate phase reads ``School.settings["rmc_public_onboarding"]["migration"]
    ["status"]`` — which the pipeline never wrote back, so a school that opted into
    a vendor migration saw that phase pending forever even after RECONCILE. Marks
    it completed. Best-effort; never blocks reconcile.
    """
    try:
        school = getattr(bundle, "school", None)
        if school is None:
            return
        blob = dict(getattr(school, "settings", None) or {})
        ob = dict(blob.get("rmc_public_onboarding") or {})
        mig = dict(ob.get("migration") or {})
        if mig.get("status") == "completed":
            return
        mig["status"] = "completed"
        ob["migration"] = mig
        blob["rmc_public_onboarding"] = ob
        school.settings = blob
        school.save(update_fields=["settings"])
    except Exception:  # noqa: BLE001 — status write-back never blocks reconcile
        logger.debug(
            "migration_cloud.reconcile: onboarding status write-back skipped",
            exc_info=True,
        )


def _auto_rollback_bundle(*, bundle: MigrationBundle, observed_pct: float, threshold: float) -> None:
    """Roll back every MigrationRun belonging to this bundle and flag the bundle FAILED."""
    try:
        from apps.automation.models import MigrationRun
    except ImportError:
        return
    runs = MigrationRun.objects.filter(execution_summary__bundle_id=bundle.pk)  # tenant-isolation-allow: scoped via bundle.pk (bundle.school)
    rollback_count = 0
    for run in runs:
        try:
            run.trigger_rollback(user=None)
            rollback_count += 1
        except Exception:  # noqa: BLE001
            logger.warning("reconcile auto-rollback: run %s failed", run.pk, exc_info=True)
    bundle.mark_status(
        BundleStatus.FAILED,
        summary_patch={
            "auto_rollback": {
                "observed_parity_pct": observed_pct,
                "threshold_pct": threshold,
                "runs_rolled_back": rollback_count,
                "at": timezone.now().isoformat(),
            },
        },
    )


# --- Helpers -----------------------------------------------------------

def _seed_for_bundle(idempotency_key: str) -> int:
    """Stable sample seed derived from the bundle's idempotency_key."""
    return sum(ord(c) for c in idempotency_key) if idempotency_key else 1


def _domain_run_stats(bundle: MigrationBundle) -> dict[str, dict[str, int]]:
    """Aggregate MigrationRun counts per domain for this bundle.

    Counts ONLY the latest live (non-dry-run) run per artifact. Every apply attempt
    creates a fresh MigrationRun per (domain, artifact), so a re-apply — repair, or a
    rollback + reapply — leaves the prior attempt's run behind. Blindly summing
    created_count across all of them double-counts: reconciliation then sees more
    "created" than are visible in the school, raises a phantom drift note, and wedges
    the bundle at APPLIED forever (it can never seal RECONCILED) (#6). Dry-run preview
    runs report would-create counts that never landed, so they are excluded too.

    Keyed by artifact_id (present since audit runs were introduced); a legacy run
    without it falls back to migration_type (``domain:path`` — still per-artifact), so
    two files in one domain are never collapsed. Ascending-pk iteration means the last
    write per key wins = the latest attempt.
    """
    try:
        from apps.automation.models import MigrationRun
    except ImportError:
        return {}

    latest_run_by_artifact: dict[Any, Any] = {}
    runs = (
        MigrationRun.objects.filter(  # tenant-isolation-allow: scoped via bundle.pk (bundle.school)
            execution_summary__bundle_id=bundle.pk,
        )
        .exclude(dry_run=True)
        .order_by("pk")
    )
    for run in runs:
        summary = run.execution_summary or {}
        artifact_key = summary.get("artifact_id")
        if artifact_key is None:
            artifact_key = run.migration_type  # legacy fallback: domain:path
        latest_run_by_artifact[artifact_key] = run

    stats: dict[str, dict[str, int]] = {}
    for run in latest_run_by_artifact.values():
        summary = run.execution_summary or {}
        domain = (summary.get("domain") or "").strip() or "custom_fields"
        bucket = stats.setdefault(domain, {"created": 0, "updated": 0, "errors": 0})
        bucket["created"] += run.created_count or 0
        bucket["updated"] += run.updated_count or 0
        bucket["errors"] += run.error_count or 0
    return stats


def _safe_verify_visible(bundle: MigrationBundle) -> dict[str, int] | None:
    """Re-query the tenant for visible row-counts per domain; never raises.

    Delegates to :func:`apps.migration_cloud.verification.verify_landed_counts`
    (the post-apply "did it land + is it in the school" proof).

    Returns a ``{domain: count}`` map on success — possibly EMPTY when no domain
    has a confident model mapping (the honest "not verified" case that may still
    proceed). Returns ``None`` when verification itself FAILED (raised) — a
    distinct signal the caller uses to BLOCK RECONCILED, so a bundle never
    advances (and purges its source blobs) on self-reported counts alone.
    """
    try:
        from .verification import verify_landed_counts

        return verify_landed_counts(bundle)
    except Exception:  # noqa: BLE001
        logger.warning("reconcile: visible-count verification failed", exc_info=True)
        return None


def _fill_rate_for_domain(
    artifacts: list[MigrationArtifact],
    per_artifact_mappings: dict[str, list[dict[str, Any]]],
) -> dict[str, float]:
    """Per canonical field, fraction of SOURCE rows with a non-empty value.

    C-5 honesty: this is derived from the profiler's source-side ``null_rate`` ×
    ``row_count`` — it measures source-file completeness, NOT how many values
    actually landed in the tenant. The caller labels it ``fill_rate_basis =
    "source_completeness"`` so it is never read as landed completeness. The real
    post-apply proof is ``verification.verify_landed_counts`` (visible counts).
    """
    field_counts: dict[str, tuple[int, int]] = {}  # field -> (non_empty, total)
    for artifact in artifacts:
        cols_by_name = {
            c.get("name"): c for c in (artifact.profile or {}).get("columns") or []
        }
        for mapping in per_artifact_mappings.get(artifact.path_within_bundle, []):
            canonical = mapping.get("canonical_field", "")
            if not canonical or canonical.startswith("custom_fields."):
                continue
            col = cols_by_name.get(mapping.get("source_column"))
            if not col:
                continue
            null_rate = float(col.get("null_rate", 0.0))
            total = artifact.row_count or 0
            non_empty = int(total * (1.0 - null_rate))
            prev_non, prev_total = field_counts.get(canonical, (0, 0))
            field_counts[canonical] = (prev_non + non_empty, prev_total + total)
    return {
        f: round((n / t) * 100.0, 2) if t else 0.0
        for f, (n, t) in field_counts.items()
    }


def _normalise_cohort_list(value: Any) -> set[str]:
    """Accept either a single value or a list/tuple; return a normalised set."""
    if value in (None, ""):
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(v).strip() for v in value if str(v).strip()}
    return {str(value).strip()}


def _row_passes_cohort(row: dict[str, Any], cohort: dict[str, Any]) -> bool:
    """Check a single canonical row against cohort filters.

    Filters compose with AND. Unknown fields skip the filter.
    """
    if not cohort:
        return True

    grades = _normalise_cohort_list(cohort.get("grade_level"))
    if grades:
        grade = str(row.get("grade_level") or "").strip()
        if grade and grade not in grades:
            return False

    ids = _normalise_cohort_list(cohort.get("student_external_ids"))
    if ids:
        sid = str(row.get("student_external_id") or row.get("external_id") or "").strip()
        if sid and sid not in ids:
            return False

    dr = cohort.get("date_range") or cohort.get("dates")
    if isinstance(dr, (list, tuple)) and len(dr) == 2:
        start, end = (str(dr[0] or ""), str(dr[1] or ""))
        date_val = str(row.get("date") or row.get("due_date") or row.get("enrolled_at") or "")
        if date_val and ((start and date_val < start) or (end and date_val > end)):
            return False
    return True


def _stratified_sample(
    artifacts: list[MigrationArtifact],
    per_artifact_mappings: dict[str, list[dict[str, Any]]],
    *,
    sample_size: int,
    rng: random.Random,
    cohort: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return N sample rows showing source columns + canonical mapping side-by-side.

    Deterministic given the bundle's idempotency_key (caller seeds the RNG).
    """
    samples: list[dict[str, Any]] = []
    per_artifact_quota = max(1, sample_size // max(len(artifacts), 1))
    for artifact in artifacts:
        cols = (artifact.profile or {}).get("columns") or []
        mappings = per_artifact_mappings.get(artifact.path_within_bundle, [])
        mapping_by_source = {m["source_column"]: m for m in mappings}

        # Build candidate source-row dicts from per-column sample arrays.
        max_rows = min(per_artifact_quota * 2, max(
            (len(c.get("samples") or []) for c in cols), default=0
        ))
        if max_rows == 0:
            continue
        picks = rng.sample(range(max_rows), min(per_artifact_quota, max_rows))
        for idx in sorted(picks):
            source_row: dict[str, Any] = {}
            canonical_row: dict[str, Any] = {}
            for c in cols:
                name = c.get("name", "")
                samples_list = c.get("samples") or []
                value = samples_list[idx] if idx < len(samples_list) else None
                source_row[name] = value
                m = mapping_by_source.get(name)
                if m:
                    canonical_row[m["canonical_field"]] = value
            if cohort and not _row_passes_cohort(canonical_row, cohort):
                continue
            samples.append({
                "artifact": artifact.path_within_bundle,
                "source": source_row,
                "canonical": canonical_row,
            })
            if len(samples) >= sample_size:
                return samples
    return samples


def _idempotency_check(bundle: MigrationBundle, apply_totals: dict[str, Any]) -> dict[str, Any]:
    """Idempotency posture — advisory, NOT a performed check.

    C-5 honesty: this report does NOT re-apply the bundle, so it cannot assert
    that a re-run produced zero new creates. It surfaces the real applied totals
    and is explicit that verifying idempotency requires an actual second
    (dry-run) apply — dropping the previous "the contract guarantees this" claim.
    """
    return {
        "key": bundle.idempotency_key,
        "applied_at": apply_totals.get("applied_at"),
        "applied_created": int(apply_totals.get("created") or 0),
        "applied_updated": int(apply_totals.get("updated") or 0),
        "verified": False,
        "basis": "advisory",
        "guidance": (
            "Advisory only — this report does NOT re-apply the bundle. Re-running "
            "the same idempotency_key is EXPECTED to produce zero new creates (only "
            "updates) because landers upsert by external_id, but that is not verified "
            "here. To actually verify, trigger a second dry-run apply and confirm "
            "created == 0."
        ),
    }


def _report_to_dict(report: ReconciliationReport) -> dict[str, Any]:
    """Lossy-but-useful conversion for JSONField storage."""
    return {
        "bundle_id": report.bundle_id,
        "generated_at": report.generated_at,
        "overall_parity_pct": report.overall_parity_pct,
        "per_domain": [asdict(d) for d in report.per_domain],
        "idempotency_check": report.idempotency_check,
        "notes": report.notes,
        "checksum_verification": report.checksum_verification,
    }


def _checksum_pass_enabled() -> bool:
    """Whether reconcile runs PASS 2 (the cryptographic source-vs-landed compare).

    Defaults ON. Turning it off means a bundle may seal — and purge its encrypted
    source blobs — on ROW COUNTS alone, which cannot see a truncated field, a
    mis-mapped column, or a coerced value. The reconciliation summary records
    ``{"ran": False, "reason": "disabled_by_setting"}`` so the omission is visible on
    the bundle rather than silent.
    """
    from django.conf import settings

    return bool(getattr(settings, "RMC_MIGRATION_CHECKSUM_VERIFY_ENABLED", True))


def _safe_verify_checksums(bundle: MigrationBundle):
    """Run PASS 2 for ``bundle``; never raises.

    Delegates to :func:`apps.migration_cloud.verification.verify_bundle_checksums`.
    Returns the report, or ``None`` when the verifier itself failed — a distinct
    signal the caller turns into a BLOCKING note, so a verifier that could not run is
    never mistaken for one that ran clean.
    """
    try:
        from .verification import verify_bundle_checksums

        return verify_bundle_checksums(bundle)
    except (ImportError, OSError, ValueError, TypeError, LookupError, ArithmeticError, DatabaseError):  # a verifier that could not run is REPORTED, never mistaken for clean
        logger.warning("reconcile: checksum (pass 2) verification failed", exc_info=True)
        return None


def _checksum_blocking_notes(report: Any) -> list[str]:
    """Notes for PASS 2 findings that must hold the bundle at APPLIED.

    Only BLOCKING findings belong here: a non-empty ``notes`` list is the seal gate,
    so an informational line would wedge every healthy bundle. The full outcome —
    including a clean one — is written to ``reconciliation_summary.checksum_
    verification`` regardless.

    Every note carries its domain's WHOLE bucket tally, because a partial breakdown is
    worse than none: a refusal, a row nobody could identify, and a genuinely absent row
    would otherwise wear the same shape. Divergences are ENUMERATED by identity and
    field, not merely counted — a count tells an operator that something is wrong and
    nothing about which record to look at.
    """
    notes: list[str] = []
    for d in report.per_domain:
        # Every bucket, every time. A breakdown that omits one lets a refusal, a
        # row nobody could identify and a genuinely absent row wear the same shape.
        tally = (
            f"{d.source_records} source record(s) = {d.matched} matched"
            f" + {d.divergent} divergent + {d.missing_in_destination} missing"
            f" + {d.unidentified} unidentified"
            f" + {d.unresolved_identity} unresolved-identity"
            f" + {d.ambiguous_destination} ambiguous-destination"
            f" + {d.skipped_over_cap} over-cap"
        )
        depth = getattr(d, "depth", "value")
        if not d.tally_closes:
            notes.append(
                f"{d.domain}: checksum verification did not account for every source "
                f"record ({tally}; bucketed {d.bucketed}). The pass disagreed with "
                "itself, so its result cannot be trusted — not sealing."
            )
            continue
        if d.divergent or d.missing_in_destination:
            detail = "; ".join(_describe_divergence(x) for x in d.divergences[:10])
            more = ""
            recorded = len(d.divergences)
            total = d.divergent + d.missing_in_destination
            if recorded > 10:
                more = f" (+{recorded - 10} more recorded on the bundle)"
            elif total > recorded:
                more = f" (+{total - recorded} more not individually recorded)"
            notes.append(
                f"{d.domain} ({depth}): SHA-256 comparison of the source artifact "
                f"against the landed rows found divergence — {tally}. Diverging "
                f"records: {detail}{more}. The migration is NOT verified; the bundle "
                "stays APPLIED and its encrypted source is retained for repair."
            )
        elif d.source_records > 0 and d.matched == 0:
            notes.append(
                f"{d.domain}: not one source record could be matched to a landed row "
                f"({tally}). An applied bundle whose rows were all dismissed leaves "
                "exactly this shape — zero divergences over zero comparisons is not a "
                "clean import, so the bundle is not sealed."
            )
    return notes


def _describe_divergence(div: Any) -> str:
    """One diverging record, named, with the fields that actually differ."""
    if getattr(div, "kind", "") == "missing_in_destination":
        return f"{div.identity!r} is not in the destination"
    fields = getattr(div, "field_diffs", None) or {}
    if not fields:
        return f"{div.identity!r} digest mismatch"
    shown = ", ".join(
        f"{name}: source {values[0]!r} vs landed {values[1]!r}"
        for name, values in list(fields.items())[:4]
    )
    return f"{div.identity!r} ({shown})"
