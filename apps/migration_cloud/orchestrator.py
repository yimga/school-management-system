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
    bundle = MigrationBundle.objects.get(pk=bundle_id)  # tenant-isolation-allow: PK lookup by internal id from caller

    if bundle.status == BundleStatus.APPLIED and not dry_run:
        logger.info("migration_cloud.apply: bundle %s already APPLIED — no-op", bundle_id)
        return _empty_result(bundle, dry_run, BundleStatus.APPLIED)

    if bundle.status != BundleStatus.MAPPED:
        raise ValueError(
            f"Bundle {bundle_id} is in status {bundle.status}; must be MAPPED to apply."
        )

    bundle.mark_status(BundleStatus.APPLYING)
    bundle.refresh_from_db()
    _emit_progress(bundle_id=bundle_id, kind="stage_started", stage="APPLYING",
                   message=f"Apply started (dry_run={dry_run}, atomic={bundle.apply_atomic})")

    worker_count = workers or int(
        mc_defaults.get("migration_cloud.orchestrator.worker_count")
    )

    per_artifact_jobs = _build_jobs(bundle)
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

    atomic_mode = bool(getattr(bundle, "apply_atomic", False)) and not dry_run
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
    """Roll back every MigrationRun produced by this apply (best-effort)."""
    try:
        from apps.automation.models import MigrationRun
    except ImportError:
        return
    for o in outcomes:
        if not o.migration_run_id:
            continue
        try:
            run = MigrationRun.objects.get(pk=o.migration_run_id)  # tenant-isolation-allow: PK lookup by internal run id
            run.trigger_rollback(user=None)
        except Exception:  # noqa: BLE001
            logger.debug("orchestrator: rollback failed for run %s", o.migration_run_id, exc_info=True)


# --- Dependency-DAG wave partitioning ------------------------------------

# Ordered waves; jobs within a wave run in parallel, waves run serially so
# the next wave sees its parent rows already in the tenant schema.
_DEPENDENCY_WAVES: tuple[frozenset[str], ...] = (
    frozenset({"structure"}),                                       # wave 0: academic scaffold (SPLIT provisioning) — MUST precede students/enrollment/grades
    frozenset({"students", "staff", "sections", "academics"}),      # wave 1: independent roots (academics = Subject catalog, precedes grades)
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
    if "country" not in locale_hints:
        school = getattr(artifact.bundle, "school", None)
        country = getattr(school, "country_code", "") or ""
        if country:
            locale_hints["country"] = str(country).upper()

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


def _classify_quarantine_issue(err: str) -> str:
    """Bucket a lander error string into a ``MigrationQuarantineRecord.issue_class``."""
    e = (err or "").lower()
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

    domain_label = ((domain or "") or (artifact.path_within_bundle or ""))[:32]
    for idx, err in enumerate(result.errors[:200], start=1):  # cap runaway quarantine
        try:
            MigrationQuarantineRecord.objects.create(
                school=bundle.school,
                migration_run=run,
                domain=domain_label,
                row_index=idx,
                payload={"error": err, "artifact": artifact.path_within_bundle},
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
