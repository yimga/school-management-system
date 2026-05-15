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
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from django.utils import timezone

from apps.migration_cloud import defaults as mc_defaults

from .landers import LanderError, LanderResult, get_lander
from .models import BundleStatus, MigrationArtifact, MigrationBundle
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

    _txn = start_named_transaction("migration.bundle_apply", bundle_id=bundle_id)
    try:
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
    bundle = MigrationBundle.objects.get(pk=bundle_id)

    if bundle.status == BundleStatus.APPLIED and not dry_run:
        logger.info("migration_cloud.apply: bundle %s already APPLIED — no-op", bundle_id)
        return _empty_result(bundle, dry_run, BundleStatus.APPLIED)

    if bundle.status != BundleStatus.MAPPED:
        raise ValueError(
            f"Bundle {bundle_id} is in status {bundle.status}; must be MAPPED to apply."
        )

    bundle.mark_status(BundleStatus.APPLYING)
    bundle.refresh_from_db()

    worker_count = workers or int(
        mc_defaults.get("migration_cloud.orchestrator.worker_count")
    )

    per_artifact_jobs = _build_jobs(bundle)
    outcomes: list[ArtifactApplyOutcome] = []
    failed = False

    # FK dependency DAG: students + staff + sections must land before
    # enrollment / attendance / grades / guardians / behavior / finance
    # so child rows can resolve their parent FKs. custom_fields runs last
    # since it references the entity that owns the dynamic value.
    waves = _partition_jobs_by_dependency(per_artifact_jobs)

    for wave_index, wave_jobs in enumerate(waves):
        if not wave_jobs:
            continue
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

    return ApplyResult(
        bundle_id=bundle.pk,
        dry_run=dry_run,
        per_artifact=outcomes,
        total_created=totals["created"],
        total_updated=totals["updated"],
        total_quarantined=totals["quarantined"],
        status=new_status if not dry_run else BundleStatus.MAPPED,
    )


# --- Dependency-DAG wave partitioning ------------------------------------

# Ordered waves; jobs within a wave run in parallel, waves run serially so
# the next wave sees its parent rows already in the tenant schema.
_DEPENDENCY_WAVES: tuple[frozenset[str], ...] = (
    frozenset({"students", "staff", "sections"}),                   # wave 0: independent roots
    frozenset({"enrollment", "guardians", "schedule"}),             # wave 1: depend on wave 0
    frozenset({"attendance", "grades", "behavior", "finance", "transcripts",  # wave 2: depend on wave 1
               "health", "library", "transport", "hostel", "cafeteria"}),
    frozenset({"custom_fields"}),                                   # wave 3: catch-all last
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
        domain = domain_entry.get("domain", "custom_fields")
        if not mappings:
            # If U4 never ran for this artifact, default everything to custom_fields.
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
    _quarantine_errors(bundle=bundle, run=run, artifact=job.artifact, result=result)
    return outcome


# --- Row iteration + transformer application ----------------------------

def _iter_canonical_rows(job: _ArtifactJob) -> Iterator[dict[str, Any]]:
    """Stream the artifact's bytes, apply mappings + transformers, yield canonical rows."""
    artifact = job.artifact
    mapping_index = {m["source_column"]: m for m in job.mappings}
    locale_hints = dict(artifact.locale_hints or {})

    # Surface the tenant's country to every transformer so country-aware
    # transformers (grading_scale_to_canonical, name_split_locale,
    # attendance_code_rewrite) can resolve scale / dialect / name-order
    # without needing per-mapping options.
    if "country" not in locale_hints:
        school = getattr(artifact.bundle, "school", None)
        country = getattr(school, "country_code", "") or ""
        if country:
            locale_hints["country"] = str(country).upper()

    bundle_uri = artifact.bundle.intake_source_uri or ""
    path = Path(bundle_uri) if bundle_uri else None
    if path is None or not path.exists() or artifact.path_within_bundle != path.name:
        # Defer for archive members + remote bytes; Phase U5+ content store
        # will expose a per-artifact reader. Yield nothing rather than error.
        return iter(())

    encoding = artifact.encoding or "utf-8"

    if artifact.detected_format in ("csv", "tsv", "unknown"):
        return _iter_csv_rows(path, encoding, mapping_index, locale_hints)
    if artifact.detected_format == "json":
        return _iter_json_rows(path, encoding, mapping_index, locale_hints)
    if artifact.detected_format == "jsonl":
        return _iter_jsonl_rows(path, encoding, mapping_index, locale_hints)
    return iter(())


def _iter_csv_rows(
    path: Path,
    encoding: str,
    mapping_index: dict[str, dict[str, Any]],
    locale_hints: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding=encoding, errors="replace", newline="") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        for raw_row in reader:
            yield _transform_row(raw_row, mapping_index, locale_hints)


def _iter_json_rows(
    path: Path,
    encoding: str,
    mapping_index: dict[str, dict[str, Any]],
    locale_hints: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    text = path.read_text(encoding=encoding, errors="replace")
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


def _transform_row(
    raw_row: dict[str, Any],
    mapping_index: dict[str, dict[str, Any]],
    locale_hints: dict[str, Any],
) -> dict[str, Any]:
    """Apply column mappings + transformers; return canonical-keyed dict."""
    canonical: dict[str, Any] = {}
    for source_col, raw_value in raw_row.items():
        mapping = mapping_index.get(source_col)
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
            "updated_ids_with_old_values": outcome.result.updated_ids_with_old_values[:200],
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


def _quarantine_errors(
    *,
    bundle: MigrationBundle,
    run,
    artifact: MigrationArtifact,
    result: LanderResult,
) -> None:
    """Write per-row failures to ``apps.automation.MigrationQuarantineRecord``."""
    if not result.errors:
        return
    try:
        from apps.automation.models import MigrationQuarantineRecord
    except ImportError:
        return

    for err in result.errors[:200]:  # cap to avoid runaway quarantine
        try:
            MigrationQuarantineRecord.objects.create(
                school=bundle.school,
                migration_run=run,
                domain=run.migration_type[:64] if run else artifact.path_within_bundle[:64],
                row_snapshot={"error": err},
                reason=err[:500],
            )
        except Exception:  # noqa: BLE001 — quarantine writes never block apply
            logger.debug(
                "migration_cloud.apply: quarantine write skipped", exc_info=True
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
