"""Phase U5 — apply step orchestrator.

Walks every artifact in a MAPPED bundle, streams rows through their
column mappings + transformers, and lands them via the registered
per-domain lander under the tenant schema. Records one
``apps.automation.MigrationRun`` per (domain, artifact) for audit +
rollback.

Lifecycle: MAPPED → APPLYING → APPLIED (or FAILED on hard error).

Invariants:
    * **Tenant scoping.** All persistence runs inside
      ``django_tenants.utils.schema_context(bundle.schema_name)`` so writes
      land in the right tenant schema. Bundle metadata + MigrationRun audit
      stays in the public schema.
    * **Idempotency.** Re-running an APPLIED bundle is a no-op
      (lifecycle guard); operators rollback explicitly via
      ``MigrationRun.trigger_rollback()`` if they need to redo.
    * **No data loss.** Rows that fail transformation or upsert land in
      ``apps.automation.MigrationQuarantineRecord`` with the source row +
      error attached, viewable in the wizard.
    * **AI gateway is never called from here.** All AI happens earlier
      (mapper, classifier). Apply is deterministic.

Public surface:
    apply_bundle(bundle_id, *, dry_run=False, workers=None) → ApplyResult
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from django.utils import timezone

from django.db import transaction

from apps.migration_cloud import defaults as mc_defaults

from .guardrails import enforce_financial_guardrail
from .landers import LanderError, LanderResult, get_lander
from .models import (
    BundleStatus,
    FinancialMismatchError,
    MigrationArtifact,
    MigrationBundle,
)
from .progress import emit as _emit_progress, refresh_snapshot
from .services.lifecycle_events import (
    EVENT_BUNDLE_APPLIED,
    EVENT_BUNDLE_FAILED,
    emit_bundle_lifecycle_event,
)
from .transformers import TransformerContext, TransformerError, get_transformer

logger = logging.getLogger(__name__)


@dataclass
class ArtifactApplyOutcome:
    artifact_id: int
    path_within_bundle: str
    domain: str
    migration_run_id: int | None
    result: LanderResult = field(default_factory=LanderResult)
    status: str = "PENDING"
    error: str = ""


@dataclass
class ApplyResult:
    bundle_id: int
    dry_run: bool
    per_artifact: list[ArtifactApplyOutcome]
    total_created: int = 0
    total_updated: int = 0
    total_quarantined: int = 0
    status: str = ""


def apply_bundle(
    *,
    bundle_id: int,
    dry_run: bool = False,
    workers: int | None = None,
) -> ApplyResult:
    """Apply a MAPPED bundle to its tenant.

    Sentry custom transaction `migration.bundle_apply` backs the
    homonymous SLO in `apps/observability/slo.py`.
    """
    from apps.observability.tracing import (
        finish_transaction, set_transaction_status, start_named_transaction,
    )
    from apps.platform_runtime.workflow_tracker import ensure_workflow_run

    _txn = start_named_transaction("migration.bundle_apply", bundle_id=bundle_id)
    try:
        # Track the apply as a WorkflowRun so a wedged apply is VISIBLE to the stuck
        # / abandoned watchdogs. The outbox drain (production path) and repair call
        # this function directly — bypassing the @track_workflow-decorated Celery
        # task — so without this wrap no run exists and every watchdog is blind. The
        # orchestrator already pulses "prepare"/"apply_waves"/"finalize" against
        # active_workflow_run(); this gives those pulses a run to land on.
        with ensure_workflow_run(
            "migration_bundle_apply",
            steps=("prepare", "apply_waves", "finalize"),
            expected_duration_seconds=1800,  # magic-number-allow: workflow-expected-duration-seconds (matches celery_tasks.apply_bundle_task)
            payload={"bundle_id": bundle_id, "dry_run": bool(dry_run)},
        ):
            return _apply_bundle_inner(bundle_id=bundle_id, dry_run=dry_run, workers=workers)
    except Exception:
        set_transaction_status(_txn, "internal_error")
        raise
    finally:
        finish_transaction(_txn)


def _apply_bundle_inner(
    *,
    bundle_id: int,
    dry_run: bool = False,
    workers: int | None = None,
) -> ApplyResult:
    # Claim the bundle atomically under a row lock: read status, re-check, and
    # flip MAPPED->APPLYING inside one transaction so two concurrent applies
    # (HeavyWorkOutbox double-dispatch, or a manual apply racing the outbox)
    # cannot both observe MAPPED and both run every lander -> parallel user
    # provisioning double-creates guardians/staff. select_for_update is a no-op
    # on SQLite (tests) and locks the row on Postgres (prod); the second apply
    # blocks until this commits, then sees APPLYING and refuses below.
    # A dry run is a PREVIEW: it must never mutate the durable lifecycle status.
    # Flipping the real bundle to APPLYING for a dry run made repair.py / the
    # tenant progress card see a live import in flight, and a dry-run worker crash
    # left the bundle wedged at APPLYING — so keep it at MAPPED; the dry-run
    # results land in size_summary["last_dry_run"] at the end.
    from .schema_binding import ensure_bundle_schema_name

    with transaction.atomic():
        bundle = MigrationBundle.objects.select_for_update().get(pk=bundle_id)  # tenant-isolation-allow: PK lookup by internal id from caller

        if bundle.status == BundleStatus.APPLIED and not dry_run:
            logger.info("migration_cloud.apply: bundle %s already APPLIED — no-op", bundle_id)
            return _empty_result(bundle, dry_run, BundleStatus.APPLIED)

        if bundle.status != BundleStatus.MAPPED:
            raise ValueError(
                f"Bundle {bundle_id} is in status {bundle.status}; must be MAPPED to apply."
            )

        effective_schema = ensure_bundle_schema_name(bundle)
        if bundle.school_id and not effective_schema:
            raise ValueError(
                f"Bundle {bundle_id} is bound to school_id={bundle.school_id} but has no "
                "tenant schema_name — refuse apply so rows are not written off-tenant. "
                "Re-bind the school or repair Client.schema_name, then retry."
            )

        if not dry_run:
            bundle.mark_status(BundleStatus.APPLYING)
    bundle.refresh_from_db()
    _emit_progress(bundle_id=bundle_id, kind="stage_started", stage="APPLYING",
                   message=f"Apply started (dry_run={dry_run}, atomic={bundle.apply_atomic})")

    worker_count = workers or int(
        mc_defaults.get("migration_cloud.orchestrator.worker_count")
    )

    per_artifact_jobs = _build_jobs(bundle)

    # Honesty gate (defense in depth with profiler.profile_bundle): a real apply
    # of a bundle that HAS artifacts but zero WORKABLE jobs (every file quarantined
    # or an archive shell) would otherwise stamp a *green* APPLIED with all-zero
    # totals — the operator believes rows landed when none did. Mark FAILED
    # (repairable) so "APPLIED" always means real rows were considered. A genuinely
    # empty bundle (no artifacts at all) keeps its prior no-op behaviour.
    if not dry_run and not per_artifact_jobs and bundle.artifacts.exists():
        logger.warning(
            "orchestrator: bundle %s reached apply with no workable artifacts "
            "(all quarantined) — marking FAILED instead of a 0-row APPLIED",
            bundle_id,
        )
        bundle.mark_status(
            BundleStatus.FAILED,
            summary_patch={
                "no_workable_artifacts": True,
                "error": "No workable artifacts to apply — every file was quarantined.",
            },
        )
        _emit_progress(bundle_id=bundle_id, kind="warning", stage="APPLYING",
                       message="Apply aborted — no workable artifacts (all quarantined).")
        try:
            emit_bundle_lifecycle_event(
                bundle, EVENT_BUNDLE_FAILED,
                {"reason": "no_workable_artifacts"},
            )
        except Exception:  # noqa: BLE001 — event emission never blocks
            pass
        return _empty_result(bundle, dry_run, BundleStatus.FAILED)

    try:
        from apps.platform_runtime.workflow_tracker import active_workflow_run, pulse_workflow_step

        pulse_workflow_step(
            active_workflow_run(),
            "prepare",
            payload={
                "bundle_id": bundle_id,
                "dry_run": dry_run,
                "artifacts": len(per_artifact_jobs),
            },
        )
    except Exception:
        pass
    outcomes: list[ArtifactApplyOutcome] = []
    failed = False

    # FK dependency DAG: students + staff + sections must land before
    # enrollment / attendance / grades / guardians / behavior / finance
    # so child rows can resolve their parent FKs. custom_fields runs last
    # since it references the entity that owns the dynamic value.
    waves = _partition_jobs_by_dependency(per_artifact_jobs)

    def _run_waves() -> None:
        for wave_index, wave_jobs in enumerate(waves):
            if not wave_jobs:
                continue
            _emit_progress(
                bundle_id=bundle_id, kind="artifact_progress", stage="APPLYING",
                message=f"Wave {wave_index} starting ({len(wave_jobs)} artifact(s))",
                detail={"wave": wave_index, "artifacts": len(wave_jobs)},
            )
            try:
                from apps.platform_runtime.workflow_tracker import (
                    active_workflow_run,
                    pulse_workflow_step,
                )

                pulse_workflow_step(
                    active_workflow_run(),
                    "apply_waves",
                    payload={"wave": wave_index, "artifacts": len(wave_jobs)},
                )
            except Exception:
                pass
            if worker_count <= 1 or len(wave_jobs) <= 1:
                for job in wave_jobs:
                    outcomes.append(_apply_artifact(bundle, job, dry_run=dry_run))
            else:
                with ThreadPoolExecutor(max_workers=worker_count) as pool:
                    futures = {
                        pool.submit(_apply_artifact, bundle, job, dry_run=dry_run): job
                        for job in wave_jobs
                    }
                    for future in as_completed(futures):
                        outcomes.append(future.result())

    # Finance MUST be all-or-nothing. In non-atomic mode finance rows commit
    # (autocommit) BEFORE the financial guardrail runs; a control-total mismatch
    # then marks the bundle FAILED and calls _rollback_all_runs — but finance has
    # no rollback handler, so the mismatched ledger stays committed while the
    # operator believes nothing landed. Forcing atomic makes the guardrail's abort
    # real: transaction.atomic() DB-rolls-back every finance write on
    # FinancialMismatchError. Mirrors repair.repair_readiness's finance-requires-
    # atomic gate. See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (BLOCKER 3).
    finance_present = any(job.domain == "finance" for job in per_artifact_jobs)
    atomic_mode = (bool(getattr(bundle, "apply_atomic", False)) or finance_present) and not dry_run
    if atomic_mode:
        # Worker threads open their own DB connections and would NOT join the
        # outer transaction.atomic(), silently breaking all-or-nothing. Force
        # single-threaded so the atomic block actually wraps every write.
        worker_count = 1
    try:
        if atomic_mode:
            with transaction.atomic():
                _run_waves()
                _maybe_check_financial_guardrail(bundle, outcomes)
        else:
            _run_waves()
            if not dry_run:
                _maybe_check_financial_guardrail(bundle, outcomes)
    except FinancialMismatchError as exc:
        logger.warning("orchestrator: financial guardrail aborted apply: %s", exc)
        _emit_progress(bundle_id=bundle_id, kind="warning", stage="APPLYING",
                       message=f"Financial guardrail failure — apply aborted: {exc}")
        bundle.mark_status(
            BundleStatus.FAILED,
            summary_patch={"financial_guardrail_failed": True, "error": str(exc)},
        )
        if not atomic_mode:
            _rollback_all_runs(outcomes)
        # Partner lifecycle event (G-5): fires on BOTH the API and UI paths.
        emit_bundle_lifecycle_event(
            bundle, EVENT_BUNDLE_FAILED,
            {"reason": "financial_guardrail", "error": str(exc)},
        )
        raise
    except Exception as exc:  # noqa: BLE001 — ANY apply failure must mark FAILED, never wedge at APPLYING
        # The bundle was set to APPLYING at the top of this function. Letting an
        # unexpected error (a lander crash, a DB error, an OOM) propagate from here
        # would leave it APPLYING forever: re-apply requires MAPPED and repair refused
        # APPLYING as "still running", so the import became unrecoverable without DB
        # surgery. Mark it FAILED — which repair_readiness treats as repairable — as a
        # best-effort, then re-raise the original error so the caller / outbox still
        # sees the failure. (A worker SIGKILL never reaches this handler; repair.py
        # reclaims that stale-APPLYING case by timeout.)
        logger.exception("orchestrator: apply failed for bundle %s — marking FAILED", bundle_id)
        # A dry-run crash must NOT corrupt the durable status. The bundle was left
        # at MAPPED (the APPLYING flip above is gated on ``not dry_run``), so a
        # preview that blows up simply re-raises to the caller and the operator can
        # retry the preview — the real bundle is untouched.
        if not dry_run:
            try:
                bundle.mark_status(
                    BundleStatus.FAILED,
                    summary_patch={"error": f"{type(exc).__name__}: {exc}"},
                )
            except Exception:  # noqa: BLE001 — marking FAILED must not mask the original error
                logger.exception("orchestrator: could not mark bundle %s FAILED", bundle_id)
        try:
            _emit_progress(bundle_id=bundle_id, kind="error", stage="APPLYING",
                           message=f"Apply failed — {type(exc).__name__}")
            if not atomic_mode:
                _rollback_all_runs(outcomes)
            if not dry_run:
                emit_bundle_lifecycle_event(
                    bundle, EVENT_BUNDLE_FAILED,
                    {"reason": "apply_exception", "error": str(exc)},
                )
        except Exception:  # noqa: BLE001 — best-effort cleanup, never mask the original error
            logger.exception("orchestrator: post-failure cleanup errored for bundle %s", bundle_id)
        raise

    totals = _summarize_outcomes(outcomes)
    bundle.mapping_summary = {
        **(bundle.mapping_summary or {}),
        "apply_totals": {
            "created": totals["created"],
            "updated": totals["updated"],
            "quarantined": totals["quarantined"],
            "errors": totals["errors"],
            "dry_run": dry_run,
            "applied_at": timezone.now().isoformat(),
        },
    }
    bundle.save(update_fields=["mapping_summary", "updated_at"])

    failed = any(o.status == "FAILED" for o in outcomes)
    new_status = BundleStatus.FAILED if failed else BundleStatus.APPLIED
    if dry_run:
        # Dry-run never advances past MAPPED — operator still needs to apply.
        bundle.mark_status(BundleStatus.MAPPED, summary_patch={"last_dry_run": totals})
    else:
        bundle.mark_status(new_status, summary_patch={"apply_totals": totals})
        # Partner lifecycle event (G-5): emitted here at the SERVICE layer so a
        # migration run from the connector/customer UI fires the same webhook an
        # API-driven apply does (the REST viewset no longer emits — avoids double).
        emit_bundle_lifecycle_event(
            bundle,
            EVENT_BUNDLE_APPLIED if new_status == BundleStatus.APPLIED else EVENT_BUNDLE_FAILED,
            {
                "created": totals.get("created", 0),
                "updated": totals.get("updated", 0),
                "quarantined": totals.get("quarantined", 0),
                "status": str(new_status),
            },
        )

    _emit_progress(
        bundle_id=bundle.pk, kind="stage_finished", stage="APPLYING",
        message=f"Apply finished: {totals.get('created')} created, "
                f"{totals.get('updated')} updated, {totals.get('quarantined')} quarantined",
        detail={"totals": totals},
    )
    refresh_snapshot(bundle=bundle)

    try:
        from apps.platform_runtime.workflow_tracker import active_workflow_run, pulse_workflow_step

        pulse_workflow_step(
            active_workflow_run(),
            "finalize",
            payload={"status": new_status, "created": totals.get("created", 0)},
        )
    except Exception:
        pass

    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEventType
        from apps.migration_cloud.services.bundle_lifecycle_audit import safe_bundle_audit

        safe_bundle_audit(
            bundle,
            MigrationCloudAuditEventType.BUNDLE_APPLIED.value,
            payload_summary={
                "bundle_id": str(bundle.pk),
                "dry_run": bool(dry_run),
                "status": str(new_status if not dry_run else BundleStatus.MAPPED),
                "created": int(totals.get("created", 0)),
                "updated": int(totals.get("updated", 0)),
                "quarantined": int(totals.get("quarantined", 0)),
                # Field-level rollup: per domain, the counts + the NAMES of fields
                # overwritten on existing records (names as list values; raw
                # values never leave the tenant schema).
                "domains": _field_level_apply_summary(outcomes),
            },
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "migration_cloud.orchestrator: apply audit failed bundle_id=%s",
            bundle_id,
            exc_info=True,
        )

    return ApplyResult(
        bundle_id=bundle.pk,
        dry_run=dry_run,
        per_artifact=outcomes,
        total_created=totals["created"],
        total_updated=totals["updated"],
        total_quarantined=totals["quarantined"],
        status=new_status if not dry_run else BundleStatus.MAPPED,
    )


def _maybe_check_financial_guardrail(
    bundle: MigrationBundle, outcomes: list["ArtifactApplyOutcome"],
) -> None:
    """Run the financial guardrail if any finance domain landed and expected_totals is set."""
    if not bundle.expected_totals:
        return
    finance_landed = any(
        o.domain == "finance" and o.status in ("SUCCESS", "PARTIAL") for o in outcomes
    )
    students_landed = any(
        o.domain == "students" and o.status in ("SUCCESS", "PARTIAL") for o in outcomes
    )
    # Only enforce when something happened in a domain the guardrail observes.
    if not (finance_landed or students_landed):
        return
    bundle.refresh_from_db()
    report = enforce_financial_guardrail(bundle=bundle)
    bundle.mapping_summary = {
        **(bundle.mapping_summary or {}),
        "financial_guardrail": report.to_dict(),
    }
    bundle.save(update_fields=["mapping_summary", "updated_at"])


def _rollback_all_runs(outcomes: list["ArtifactApplyOutcome"]) -> None:
    """Roll back every MigrationRun produced by this apply, CHILD-FIRST.

    Runs are rolled back most-recent-first (``order_by("-started_at")``) — the
    REVERSE of the dependency-wave order they applied in. This is load-bearing:
    later-wave rows PROTECT earlier-wave rows (``Evaluation.student`` /
    ``Evaluation.teacher`` are ``on_delete=PROTECT``), so deleting a wave-1
    student BEFORE its wave-3 grades raises ``IntegrityError`` — that student's
    rollback is marked FAILED and swallowed while the grades roll back
    afterwards, leaving the student/teacher ORPHANED and live though the bundle
    reads FAILED. Iterating ``outcomes`` in append (wave) order did exactly this.
    Rolling back child rows first (grades before students) is the only safe
    order; ``connector_rollback`` / ``reconciliation`` auto-rollback get it
    implicitly via ``MigrationRun.Meta.ordering`` — here it is explicit.
    """
    try:
        from apps.automation.models import MigrationRun
    except ImportError:
        return
    run_ids = [o.migration_run_id for o in outcomes if o.migration_run_id]
    if not run_ids:
        return
    # tenant-isolation-allow: PK-set lookup by internal run ids from this apply
    runs = list(MigrationRun.objects.filter(pk__in=run_ids).order_by("-started_at"))
    for run in runs:
        try:
            run.trigger_rollback(user=None)
        except Exception:  # noqa: BLE001
            logger.debug(
                "orchestrator: rollback failed for run %s", run.pk, exc_info=True,
            )


# --- Dependency-DAG wave partitioning ------------------------------------

# Ordered waves; jobs within a wave run in parallel, waves run serially so
# the next wave sees its parent rows already in the tenant schema.
_DEPENDENCY_WAVES: tuple[frozenset[str], ...] = (
    frozenset({"structure", "academic_sessions", "specialties"}),   # wave 0: academic scaffold (SPLIT provisioning + OneRoster years/terms + trade/stream catalog) — MUST precede students/enrollment/grades
    frozenset({"students", "staff", "sections", "academics", "alumni"}),  # wave 1: independent roots (academics = Subject catalog, precedes grades; alumni upserts StudentProfile so guardians/finance/grades can resolve alumni students)
    frozenset({"enrollment", "guardians", "schedule"}),             # wave 2: depend on wave 1
    frozenset({"attendance", "grades", "behavior", "finance", "transcripts",  # wave 3: depend on wave 2
               "health", "library", "transport", "hostel", "cafeteria",
               "athletics_teams"}),                                 # athletics_teams precedes its roster/fixtures
    frozenset({"custom_fields"}),                                   # wave 4: catch-all (athletics_memberships/fixtures, *_assignments) — after their parents
)


def _partition_jobs_by_dependency(jobs: list["_ArtifactJob"]) -> list[list["_ArtifactJob"]]:
    """Bucket jobs into FK-safe waves so child rows can resolve their parents.

    Any domain not in ``_DEPENDENCY_WAVES`` lands in the final catch-all
    wave alongside custom_fields, so adding a new domain is non-breaking.
    """
    waves: list[list["_ArtifactJob"]] = [[] for _ in _DEPENDENCY_WAVES]
    catch_all_idx = len(_DEPENDENCY_WAVES) - 1
    for job in jobs:
        placed = False
        for i, wave_domains in enumerate(_DEPENDENCY_WAVES):
            if job.domain in wave_domains:
                waves[i].append(job)
                placed = True
                break
        if not placed:
            waves[catch_all_idx].append(job)
    return waves


# --- Job model + builder ------------------------------------------------

@dataclass
class _ArtifactJob:
    artifact: MigrationArtifact
    domain: str
    mappings: list[dict[str, Any]]


def _build_jobs(bundle: MigrationBundle) -> list[_ArtifactJob]:
    mapping_summary = bundle.mapping_summary or {}
    per_artifact_mappings = mapping_summary.get("per_artifact") or {}
    per_artifact_domain = (
        (bundle.discovery_summary or {}).get("per_artifact_domain") or {}
    )

    jobs: list[_ArtifactJob] = []
    for artifact in bundle.artifacts.filter(quarantined=False):
        # Skip parent archive shells — they hold no rows.
        if artifact.detected_format == "archive":
            continue
        mappings = per_artifact_mappings.get(artifact.path_within_bundle) or []
        domain_entry = per_artifact_domain.get(artifact.path_within_bundle) or {}
        # Tenant/operator per-file override on the artifact row wins over discovery.
        assigned = (getattr(artifact, "assigned_domain", None) or "").strip()
        domain = assigned or domain_entry.get("domain", "custom_fields")
        if not mappings:
            # If U4 never ran for this artifact, default everything to custom_fields
            # unless the tenant explicitly assigned a domain (still land via that
            # lander with empty mappings → lander quarantines bad rows).
            if not assigned:
                domain = "custom_fields"
        jobs.append(_ArtifactJob(artifact=artifact, domain=domain, mappings=mappings))
    return jobs


# --- Per-artifact apply -------------------------------------------------

def _apply_artifact(
    bundle: MigrationBundle,
    job: _ArtifactJob,
    *,
    dry_run: bool,
) -> ArtifactApplyOutcome:
    outcome = ArtifactApplyOutcome(
        artifact_id=job.artifact.pk,
        path_within_bundle=job.artifact.path_within_bundle,
        domain=job.domain,
        migration_run_id=None,
    )

    run = _create_audit_run(bundle, job, dry_run=dry_run)
    outcome.migration_run_id = getattr(run, "pk", None)

    lander = get_lander(job.domain) or get_lander("custom_fields")
    if lander is None:
        outcome.status = "FAILED"
        outcome.error = f"No lander registered for domain {job.domain!r} (or custom_fields fallback)"
        _finalize_audit_run(run, outcome, status="FAILED")
        return outcome

    try:
        rows_iter = _iter_canonical_rows(job)
        result = _run_lander_under_schema(
            lander=lander,
            rows_iter=rows_iter,
            bundle=bundle,
            artifact=job.artifact,
            dry_run=dry_run,
        )
    except LanderError as exc:
        outcome.status = "FAILED"
        outcome.error = str(exc)
        _finalize_audit_run(run, outcome, status="FAILED")
        return outcome
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "migration_cloud.apply: unexpected error applying artifact %s",
            job.artifact.pk,
        )
        outcome.status = "FAILED"
        outcome.error = f"{type(exc).__name__}: {exc}"
        _finalize_audit_run(run, outcome, status="FAILED")
        return outcome

    outcome.result = result
    outcome.status = "PARTIAL" if result.quarantined else "SUCCESS"
    _finalize_audit_run(run, outcome, status=outcome.status)
    _quarantine_errors(
        bundle=bundle, run=run, artifact=job.artifact, domain=job.domain, result=result
    )
    return outcome


# --- Row iteration + transformer application ----------------------------

def _iter_canonical_rows(job: _ArtifactJob) -> Iterator[dict[str, Any]]:
    """Stream the artifact's bytes, apply mappings + transformers, yield canonical rows.

    When the parent bundle has ``diff_mode='since'`` set with ``diff_since``,
    rows older than the threshold are filtered out before reaching the lander.
    """
    artifact = job.artifact
    mapping_index = {m["source_column"]: m for m in job.mappings}
    locale_hints = dict(artifact.locale_hints or {})
    diff_threshold = None
    if getattr(artifact.bundle, "diff_mode", "full") == "since":
        diff_threshold = getattr(artifact.bundle, "diff_since", None)

    # Surface the tenant's country to every transformer so country-aware
    # transformers (grading_scale_to_canonical, name_split_locale,
    # attendance_code_rewrite) can resolve scale / dialect / name-order
    # without needing per-mapping options.
    school = getattr(artifact.bundle, "school", None)
    country = str(getattr(school, "country_code", "") or "").upper()
    if country:
        locale_hints.setdefault("country", country)
        # Seed locale + date format from the tenant's country profile so the date
        # transformer disambiguates DD/MM vs MM/DD. The profiler's own per-column
        # date_format vote (evidence from the data) is already in locale_hints and
        # WINS — we only FILL when it produced none, so an all-days-<=12 US export
        # is not misread as EU. See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (B-5).
        locale_hints.setdefault("locale", country)
        if "date_format" not in locale_hints:
            try:
                from .country_profiles import resolved_country_profile
                prof = resolved_country_profile(country)
                if prof is not None and getattr(prof, "date_format", ""):
                    locale_hints["date_format"] = prof.date_format
            except Exception:  # noqa: BLE001 — hint seeding is best-effort
                pass

    # Phase U5 content store (gap #2): if the source bytes were captured at
    # ingest, stream them from the encrypted blob — this is what lets archive
    # members + remote / OAuth-folder pulls apply real rows instead of nothing.
    from .artifact_blob_store import open_artifact_blob_stream

    blob_stream, blob_encoding = open_artifact_blob_stream(artifact)
    if blob_stream is not None:
        try:
            raw_bytes = blob_stream.read()
        finally:
            try:
                blob_stream.close()
            except Exception:  # noqa: BLE001
                pass
        fmt = artifact.detected_format
        if fmt in ("csv", "tsv", "unknown", "json", "jsonl"):
            text = raw_bytes.decode(blob_encoding or "utf-8", errors="replace")
            if fmt == "json":
                raw_iter = _iter_json_rows_text(text, mapping_index, locale_hints)
            elif fmt == "jsonl":
                raw_iter = _iter_jsonl_rows_stream(io.StringIO(text), mapping_index, locale_hints)
            else:
                raw_iter = _iter_csv_rows_stream(io.StringIO(text), mapping_index, locale_hints)
        elif fmt in ("xlsx", "xls"):
            # Binary spreadsheet: read from bytes, NOT the decoded text (which
            # would be garbage). openpyxl/xlrd degrade to no rows if absent.
            raw_iter = _iter_spreadsheet_rows_bytes(raw_bytes, fmt, mapping_index, locale_hints)
        elif fmt == "pdf":
            # PDF: extract + tabularise via the shared extractor, then read the
            # resulting TSV. Digital PDFs land rows; scanned-without-OCR → none.
            raw_iter = _iter_pdf_rows_bytes(raw_bytes, mapping_index, locale_hints)
        else:
            return iter(())
        if diff_threshold is not None:
            from .diff_mode import row_passes_diff_filter
            raw_iter = (row for row in raw_iter if row_passes_diff_filter(row=row, threshold=diff_threshold))
        return raw_iter

    bundle_uri = artifact.bundle.intake_source_uri or ""
    path = Path(bundle_uri) if bundle_uri else None
    if path is None or not path.exists() or artifact.path_within_bundle != path.name:
        # No blob + not the single top-level local file: nothing readable here
        # (should be rare now the content store captures at ingest). Yield
        # nothing rather than error.
        return iter(())

    encoding = artifact.encoding or "utf-8"

    if artifact.detected_format in ("csv", "tsv", "unknown"):
        raw_iter = _iter_csv_rows(path, encoding, mapping_index, locale_hints)
    elif artifact.detected_format == "json":
        raw_iter = _iter_json_rows(path, encoding, mapping_index, locale_hints)
    elif artifact.detected_format == "jsonl":
        raw_iter = _iter_jsonl_rows(path, encoding, mapping_index, locale_hints)
    elif artifact.detected_format in ("xlsx", "xls"):
        raw_iter = _iter_spreadsheet_rows_bytes(
            path.read_bytes(), artifact.detected_format, mapping_index, locale_hints
        )
    elif artifact.detected_format == "pdf":
        raw_iter = _iter_pdf_rows_bytes(path.read_bytes(), mapping_index, locale_hints)
    else:
        return iter(())
    if diff_threshold is not None:
        from .diff_mode import row_passes_diff_filter
        raw_iter = (row for row in raw_iter if row_passes_diff_filter(row=row, threshold=diff_threshold))
    return raw_iter


def _iter_csv_rows(
    path: Path,
    encoding: str,
    mapping_index: dict[str, dict[str, Any]],
    locale_hints: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding=encoding, errors="replace", newline="") as fh:
        # ``yield from`` keeps the generator frame — and thus the open file —
        # alive until the caller has consumed every row.
        yield from _iter_csv_rows_stream(fh, mapping_index, locale_hints)


def _strip_leading_comment_lines(fh: Any) -> Iterator[str]:
    """Yield lines from ``fh``, dropping ONLY leading blank + ``#``-comment lines.

    The RunMyCampus canonical template ships a leading
    ``# runmycampus-canonical-template: ...`` marker line. Without dropping it,
    ``csv.DictReader`` takes that comment as the sole fieldname and every real
    row misroutes to quarantine on apply — so a school that downloaded a
    template, filled it in and re-uploaded it lost its data at import (the
    profiler was fixed but this apply-path reader was not). Only LEADING lines
    are dropped; once real content starts, every row is yielded unchanged, so a
    data value that begins with ``#`` is never lost and quoted newlines still
    reassemble (csv pulls more lines from this iterator inside a quote).
    """
    header_seen = False
    for line in fh:
        if not header_seen:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            header_seen = True
        yield line


def _iter_csv_rows_stream(
    fh: Any,
    mapping_index: dict[str, dict[str, Any]],
    locale_hints: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Core CSV row iterator over any seekable text stream (file OR blob-backed StringIO)."""
    sample = fh.read(4096)  # magic-number-allow: file-read-chunk-bytes
    fh.seek(0)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(_strip_leading_comment_lines(fh), dialect=dialect)
    for raw_row in reader:
        yield _transform_row(raw_row, mapping_index, locale_hints)


def _iter_json_rows(
    path: Path,
    encoding: str,
    mapping_index: dict[str, dict[str, Any]],
    locale_hints: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    text = path.read_text(encoding=encoding, errors="replace")
    yield from _iter_json_rows_text(text, mapping_index, locale_hints)


def _iter_json_rows_text(
    text: str,
    mapping_index: dict[str, dict[str, Any]],
    locale_hints: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Core JSON row iterator over already-decoded text (file OR blob-backed)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return
    for raw_row in data:
        if isinstance(raw_row, dict):
            yield _transform_row(raw_row, mapping_index, locale_hints)


def _iter_jsonl_rows(
    path: Path,
    encoding: str,
    mapping_index: dict[str, dict[str, Any]],
    locale_hints: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding=encoding, errors="replace") as fh:
        yield from _iter_jsonl_rows_stream(fh, mapping_index, locale_hints)


def _iter_jsonl_rows_stream(
    fh: Any,
    mapping_index: dict[str, dict[str, Any]],
    locale_hints: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Core JSONL row iterator over any line-iterable text stream (file OR blob-backed StringIO)."""
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            raw_row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw_row, dict):
            yield _transform_row(raw_row, mapping_index, locale_hints)


def _stringify_cell(cell: Any) -> str:
    """Coerce a spreadsheet cell to the string shape downstream expects.

    CSV rows arrive as strings; transformers assume strings. Integers stored
    as floats by the reader (``36.0``) are rendered as ``"36"`` to match what
    the same value would look like in a CSV export.
    """
    if cell is None:
        return ""
    if isinstance(cell, str):
        return cell
    if isinstance(cell, float) and cell.is_integer():
        return str(int(cell))
    return str(cell)


def _xlsx_rows(raw_bytes: bytes) -> tuple[list[Any], Iterator[Any]]:
    """Return ``(header_row, data_row_iterator)`` for an in-memory XLSX.

    ``([], iter(()))`` when openpyxl is unavailable or the file is unreadable,
    so apply degrades to zero rows instead of raising. The workbook is held
    open until the data iterator is exhausted (read-only, streaming).
    """
    try:
        from openpyxl import load_workbook  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return [], iter(())
    try:
        wb = load_workbook(filename=io.BytesIO(raw_bytes), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        return [], iter(())
    ws = wb[wb.sheetnames[0]] if wb.sheetnames else None
    if ws is None:
        _close_quietly(wb)
        return [], iter(())
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        _close_quietly(wb)
        return [], iter(())

    def _gen() -> Iterator[Any]:
        try:
            for row in rows_iter:
                yield row
        finally:
            _close_quietly(wb)

    return list(header_row), _gen()


def _xls_rows(raw_bytes: bytes) -> tuple[list[Any], Iterator[Any]]:
    """Return ``(header_row, data_row_iterator)`` for a legacy in-memory XLS.

    ``([], iter(()))`` when xlrd is unavailable or the file is unreadable.
    """
    try:
        import xlrd  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return [], iter(())
    try:
        wb = xlrd.open_workbook(file_contents=raw_bytes)
    except Exception:  # noqa: BLE001
        return [], iter(())
    if wb.nsheets == 0:
        return [], iter(())
    sh = wb.sheet_by_index(0)
    if sh.nrows == 0:
        return [], iter(())
    header_row = [sh.cell_value(0, c) for c in range(sh.ncols)]

    def _gen() -> Iterator[Any]:
        for r in range(1, sh.nrows):
            yield [sh.cell_value(r, c) for c in range(sh.ncols)]

    return header_row, _gen()


def _close_quietly(wb: Any) -> None:
    try:
        wb.close()
    except Exception:  # noqa: BLE001
        pass


def _iter_spreadsheet_rows_bytes(
    raw_bytes: bytes,
    fmt: str,
    mapping_index: dict[str, dict[str, Any]],
    locale_hints: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Yield canonical rows from an in-memory XLSX/XLS workbook.

    First worksheet, first row = headers. All cells are stringified so the
    downstream transformers see the same shape they get from CSV. This is the
    apply-time counterpart to the profiler's ``_read_xlsx`` / ``_read_xls`` —
    without it, an Excel upload classifies but lands zero rows.
    """
    header_row, data_rows = _xls_rows(raw_bytes) if fmt == "xls" else _xlsx_rows(raw_bytes)
    if not header_row:
        return
    headers = [str(h).strip() if h is not None else "" for h in header_row]
    for row in data_rows:
        raw_row: dict[str, Any] = {}
        for h, cell in zip(headers, row):
            if not h:
                continue  # unnamed column — nothing to map onto
            raw_row[h] = _stringify_cell(cell)
        if not any(str(v).strip() for v in raw_row.values()):
            continue  # skip fully-blank trailing rows
        yield _transform_row(raw_row, mapping_index, locale_hints)


def _iter_pdf_rows_bytes(
    raw_bytes: bytes,
    mapping_index: dict[str, dict[str, Any]],
    locale_hints: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Yield canonical rows from a PDF's extracted + tabularised text.

    Digitally-generated PDFs (pdfplumber) yield rows; scanned PDFs with no OCR
    binaries yield nothing (the review surface explains why). Reuses the CSV
    row iterator over the TSV the shared extractor produces, so a PDF lands
    exactly like the equivalent CSV would.
    """
    from .pdf_extract import extract_pdf_tsv

    tsv = extract_pdf_tsv(raw_bytes)
    if not tsv.strip():
        return
    yield from _iter_csv_rows_stream(io.StringIO(tsv), mapping_index, locale_hints)


# Value-hygiene for messy exports (pandas / spreadsheet dumps). A pandas
# ``to_csv`` writes NaN as the literal ``nan`` and None as ``None``; a numeric
# id read as a float is written ``241904748.0``. Stored verbatim these become a
# student's parent named "None", an admission number "nan", or an id that no
# longer round-trips. Normalised centrally so EVERY reader (CSV/XLSX/JSON) and
# EVERY domain gets the same clean value.
_NULL_LITERALS: frozenset[str] = frozenset(
    {"nan", "none", "null", "n/a", "#n/a", "nil", "(null)", "\\n", "\\N"}
)
_INT_FLOAT_RE = re.compile(r"^-?\d+\.0+$")


def _normalize_source_value(value: Any) -> Any:
    """Fold export sentinels to a real null and repair spreadsheet float-ids.

    ``nan``/``None``/``null``/``N/A`` → ``""`` (a genuine empty, not a literal
    string); an integer-valued float string (``"241904748.0"``) → its integer
    form so a text id round-trips exactly. Genuine decimals (``"36.5"``) and
    non-string values are returned untouched.
    """
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return value
    if s.lower() in _NULL_LITERALS:
        return ""
    if _INT_FLOAT_RE.match(s):
        return s.split(".", 1)[0]
    return value


def _transform_row(
    raw_row: dict[str, Any],
    mapping_index: dict[str, dict[str, Any]],
    locale_hints: dict[str, Any],
) -> dict[str, Any]:
    """Apply column mappings + transformers; return canonical-keyed dict."""
    canonical: dict[str, Any] = {}
    for source_col, raw_value in raw_row.items():
        raw_value = _normalize_source_value(raw_value)
        mapping = mapping_index.get(source_col)
        if mapping is None and isinstance(source_col, str):
            # The PROFILER strips surrounding whitespace from headers (so the
            # mapping's source_column is "TEACHER UNIQUE ID"), but the apply-path
            # csv.DictReader keys the row by the RAW header (" TEACHER UNIQUE ID"
            # with the leading space real African/TVET exports carry). Without
            # this whitespace-tolerant retry the padded column never joins its
            # mapping, lands in _unmapped, and a required id (staff_external_id)
            # is silently lost — quarantining every row. BOM is deliberately NOT
            # stripped here: the profiler keeps it ("﻿NAME"), so the exact
            # match above already covers it and both sides stay consistent.
            stripped = source_col.strip()
            if stripped != source_col:
                mapping = mapping_index.get(stripped)
        if mapping is None:
            # Unmapped column — drop into custom_fields key for the lander to pick up.
            canonical[f"_unmapped.{source_col}"] = raw_value
            continue

        canonical_field = mapping.get("canonical_field", "")
        if canonical_field.startswith("custom_fields."):
            canonical[canonical_field] = raw_value
            continue

        transformer_name = mapping.get("transformer")
        if not transformer_name:
            canonical[canonical_field] = raw_value
            continue

        transformer = get_transformer(transformer_name)
        if transformer is None:
            canonical[canonical_field] = raw_value
            continue

        ctx = TransformerContext(
            canonical_field=canonical_field,
            hints=locale_hints,
            options=mapping.get("transformer_options") or {},
        )
        try:
            canonical[canonical_field] = transformer.transform(raw_value, ctx)
        except TransformerError as exc:
            # Per-row transformer failure: store raw + flag for quarantine via
            # a sentinel error key the lander recognises.
            canonical[canonical_field] = raw_value
            canonical.setdefault("_transformer_errors", []).append(
                f"{canonical_field}: {exc!s}"
            )
    return canonical


# --- Tenant-schema wrapper ---------------------------------------------

def _run_lander_under_schema(
    *,
    lander,
    rows_iter,
    bundle: MigrationBundle,
    artifact: MigrationArtifact,
    dry_run: bool,
) -> LanderResult:
    """Wrap the lander call in ``schema_context(bundle.schema_name)`` for tenant scoping."""
    from .landers.base import LanderContext  # local to keep import surface clean

    ctx = LanderContext(
        school=bundle.school,
        schema_name=bundle.schema_name,
        bundle_id=bundle.pk,
        artifact_id=artifact.pk,
        dry_run=dry_run,
    )

    if not bundle.schema_name:
        # Public-schema apply (e.g. signup-time staged bundle without tenant yet).
        return lander.land(canonical_rows=rows_iter, ctx=ctx)

    try:
        from django_tenants.utils import schema_context
    except ImportError:
        return lander.land(canonical_rows=rows_iter, ctx=ctx)

    from django.db import connection

    if not hasattr(connection, "set_schema"):
        # Non-tenant DB backend (single-schema sqlite dev/test lane): there is
        # no schema to switch, and entering schema_context raises
        # AttributeError ('DatabaseWrapper' has no 'tenant') — which failed
        # every artifact instead of applying it.
        return lander.land(canonical_rows=rows_iter, ctx=ctx)

    with schema_context(bundle.schema_name):
        return lander.land(canonical_rows=rows_iter, ctx=ctx)


# --- Audit + quarantine -------------------------------------------------

def _create_audit_run(bundle: MigrationBundle, job: _ArtifactJob, *, dry_run: bool):
    """Create one ``apps.automation.MigrationRun`` per (domain, artifact)."""
    try:
        from apps.automation.models import MigrationRun
    except ImportError:
        return None

    return MigrationRun.objects.create(
        school=bundle.school,
        migration_type=f"{job.domain}:{job.artifact.path_within_bundle}"[:64],
        dry_run=dry_run,
        status=MigrationRun.Status.PENDING,
        triggered_by=bundle.triggered_by,
        execution_summary={
            "bundle_id": bundle.pk,
            "artifact_id": job.artifact.pk,
            "domain": job.domain,
            "mapping_count": len(job.mappings),
        },
    )


def _json_safe(value: Any) -> Any:
    """Make lander audit payloads JSONField-safe (no model instances)."""
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return str(value)[:500]


def _finalize_audit_run(run, outcome: ArtifactApplyOutcome, *, status: str) -> None:
    if run is None:
        return
    try:
        from apps.automation.models import MigrationRun
    except ImportError:
        return

    status_map = {
        "SUCCESS": MigrationRun.Status.SUCCESS,
        "PARTIAL": MigrationRun.Status.PARTIAL,
        "FAILED": MigrationRun.Status.FAILED,
    }
    run.mark_completed(
        status=status_map.get(status, MigrationRun.Status.FAILED),
        created_count=outcome.result.created,
        updated_count=outcome.result.updated,
        error_count=outcome.result.quarantined,
        error_message=outcome.error[:2000] if outcome.error else "",
        summary={
            **(run.execution_summary or {}),
            "created_ids": outcome.result.created_ids[:200],  # cap for size
            "updated_ids_with_old_values": _json_safe(
                outcome.result.updated_ids_with_old_values[:200]
            ),
            "errors_sample": outcome.result.errors[:20],
        },
    )
    # Rollback snapshot: minimal enough to revert.
    run.rollback_snapshot = {
        "created_ids": outcome.result.created_ids,
        "updated_ids_with_old_values": outcome.result.updated_ids_with_old_values,
        "domain": outcome.domain,
        "artifact_id": outcome.artifact_id,
    }
    run.save(update_fields=["rollback_snapshot"])


def _classify_quarantine_issue(err: str) -> str:
    """Bucket a lander error string into a ``MigrationQuarantineRecord.issue_class``."""
    e = (err or "").lower()
    # D-3: a source-deletion HOLD is not a failure — it is a tobedeleted structural
    # row we deliberately did not import as active. Classify it distinctly so the
    # operator review surface can separate "held: source deleted" from real errors.
    if "held for review" in e or ("marked this" in e and "deleted" in e):
        return "source_deletion"
    if "duplicate" in e or "unique" in e or "already exists" in e:
        return "duplicate"
    if "invalid" in e or "not found" in e or "unresolved" in e or "no such" in e:
        return "invalid_ref"
    if "missing" in e or "required" in e or "not provided" in e:
        return "missing_required"
    return "lander_error"


def _quarantine_errors(
    *,
    bundle: MigrationBundle,
    run,
    artifact: MigrationArtifact,
    domain: str,
    result: LanderResult,
) -> None:
    """Persist per-row failures to ``apps.automation.MigrationQuarantineRecord``.

    Landers surface per-row problems as strings in ``result.errors`` (they do not
    carry the source-row payload back), so each error is stored with its position
    in the error list as ``row_index`` plus a classified ``issue_class`` — enough
    to make "held for review" rows durable and inspectable instead of silently
    dropped. Never blocks apply.

    NOTE: the previous implementation wrote ``row_snapshot=``/``reason=`` — fields
    that do not exist on the model — so every ``create()`` raised ``TypeError``
    swallowed by the guard below, and quarantine rows were NEVER persisted (silent
    data loss). This writes the real model fields.
    """
    if not result.errors:
        return
    try:
        from apps.automation.models import MigrationQuarantineRecord
    except ImportError:
        return

    # C-4: when a lander recorded the offending source row (via
    # _helpers.record_row_error), thread it into the quarantine record so the
    # operator sees WHAT failed, keyed by the exact error string. Landers that
    # only append error strings keep the string-only payload — no regression.
    row_by_error: dict[str, Any] = {}
    for er in (getattr(result, "error_rows", None) or []):
        if isinstance(er, dict) and "error" in er:
            row_by_error[str(er.get("error"))] = er.get("row")

    domain_label = ((domain or "") or (artifact.path_within_bundle or ""))[:32]
    for idx, err in enumerate(result.errors[:200], start=1):  # cap runaway quarantine
        payload = {"error": err, "artifact": artifact.path_within_bundle}
        source_row = row_by_error.get(str(err))
        if source_row is not None:
            payload["source_row"] = source_row
        try:
            # Savepoint: this runs INSIDE the forced-atomic finance apply, and the
            # swallow below would otherwise leave a failed create's needs_rollback set
            # on the whole transaction — poisoning every subsequent write. The
            # savepoint keeps the swallow clean (same rule as landers._helpers).
            with transaction.atomic():
                MigrationQuarantineRecord.objects.create(
                    school=bundle.school,
                    migration_run=run,
                    domain=domain_label,
                    row_index=idx,
                    payload=payload,
                    issue_class=_classify_quarantine_issue(err),
                    status=MigrationQuarantineRecord.Status.PENDING,
                )
        except Exception:  # noqa: BLE001 — quarantine writes never block apply
            logger.warning(
                "migration_cloud.apply: quarantine write skipped for domain=%s row=%s",
                domain_label,
                idx,
                exc_info=True,
            )


# --- Helpers ----------------------------------------------------------

def _summarize_outcomes(outcomes: list[ArtifactApplyOutcome]) -> dict[str, Any]:
    totals = {
        "created": sum(o.result.created for o in outcomes),
        "updated": sum(o.result.updated for o in outcomes),
        "quarantined": sum(o.result.quarantined for o in outcomes),
        "errors": sum(len(o.result.errors) for o in outcomes),
        "artifacts_failed": sum(1 for o in outcomes if o.status == "FAILED"),
    }
    return totals


_APPLY_AUDIT_FIELD_CAP = 60  # magic-number-allow: apply-audit-field-name-list-cap


def _field_level_apply_summary(
    outcomes: list[ArtifactApplyOutcome],
) -> list[dict[str, Any]]:
    """Per-domain, field-level rollup for the ``bundle.applied`` audit event.

    Extends the coarse bundle totals with, per domain: the created / updated /
    quarantined counts AND the NAMES of the fields overwritten on existing
    records (the ``old`` keys of each update). This is the security-relevant
    surface — which existing fields a re-apply mutated — recorded tamper-evidently
    without any raw values.

    Field NAMES ride as list VALUES (never dict keys) so ``_sanitize_payload``,
    which rejects sensitive-keyword dict KEYS, never trips on a legitimate field
    name like ``email`` / ``date_of_birth``; the raw values stay in the tenant
    schema and never reach the append-only chain.
    """
    by_domain: dict[str, dict[str, Any]] = {}
    for o in outcomes:
        info = by_domain.setdefault(
            o.domain,
            {"created": 0, "updated": 0, "quarantined": 0, "_fields": set()},
        )
        r = o.result
        info["created"] += int(getattr(r, "created", 0) or 0)
        info["updated"] += int(getattr(r, "updated", 0) or 0)
        info["quarantined"] += int(getattr(r, "quarantined", 0) or 0)
        for entry in getattr(r, "updated_ids_with_old_values", None) or []:
            old = (entry or {}).get("old") or {}
            if isinstance(old, dict):
                info["_fields"].update(str(k) for k in old.keys())

    summary: list[dict[str, Any]] = []
    for domain in sorted(by_domain):
        info = by_domain[domain]
        fields = sorted(info["_fields"])
        summary.append(
            {
                "domain": domain,
                "created": info["created"],
                "updated": info["updated"],
                "quarantined": info["quarantined"],
                "updated_fields": fields[:_APPLY_AUDIT_FIELD_CAP],
                "updated_fields_truncated": len(fields) > _APPLY_AUDIT_FIELD_CAP,
            }
        )
    return summary


def _empty_result(bundle: MigrationBundle, dry_run: bool, status: str) -> ApplyResult:
    return ApplyResult(
        bundle_id=bundle.pk,
        dry_run=dry_run,
        per_artifact=[],
        total_created=0,
        total_updated=0,
        total_quarantined=0,
        status=status,
    )
