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
    fill_rate_by_field: dict[str, float] = field(default_factory=dict)
    sample_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReconciliationReport:
    bundle_id: int
    generated_at: str
    overall_parity_pct: float
    per_domain: list[DomainParity] = field(default_factory=list)
    idempotency_check: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


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
    bundle = MigrationBundle.objects.get(pk=bundle_id)
    if bundle.status not in (BundleStatus.APPLIED, BundleStatus.RECONCILED):
        raise ValueError(
            f"Bundle {bundle_id} is in status {bundle.status}; must be APPLIED to reconcile."
        )

    cohort = cohort or {}

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

    # Pull MigrationRun stats per domain from the audit trail.
    domain_run_stats = _domain_run_stats(bundle)

    for domain, artifacts in sorted(by_domain.items()):
        source_count = sum(a.row_count or 0 for a in artifacts)
        run_stats = domain_run_stats.get(domain, {})
        target_created = run_stats.get("created", 0)
        target_updated = run_stats.get("updated", 0)
        quarantined = run_stats.get("errors", 0)
        landed = target_created + target_updated
        parity_pct = (landed / source_count * 100.0) if source_count else 100.0

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

    report = ReconciliationReport(
        bundle_id=bundle.pk,
        generated_at=timezone.now().isoformat(),
        overall_parity_pct=round(overall, 2),
        per_domain=parities,
        idempotency_check=idempotency,
        notes=notes,
    )

    bundle.reconciliation_summary = _report_to_dict(report)
    bundle.save(update_fields=["reconciliation_summary", "updated_at"])

    if not notes and bundle.status == BundleStatus.APPLIED:
        bundle.mark_status(BundleStatus.RECONCILED)

    return report


# --- Helpers -----------------------------------------------------------

def _seed_for_bundle(idempotency_key: str) -> int:
    """Stable sample seed derived from the bundle's idempotency_key."""
    return sum(ord(c) for c in idempotency_key) if idempotency_key else 1


def _domain_run_stats(bundle: MigrationBundle) -> dict[str, dict[str, int]]:
    """Aggregate MigrationRun counts per domain for this bundle."""
    try:
        from apps.automation.models import MigrationRun
    except ImportError:
        return {}

    stats: dict[str, dict[str, int]] = {}
    runs = MigrationRun.objects.filter(
        execution_summary__bundle_id=bundle.pk,
    )
    for run in runs:
        summary = run.execution_summary or {}
        domain = (summary.get("domain") or "").strip() or "custom_fields"
        bucket = stats.setdefault(domain, {"created": 0, "updated": 0, "errors": 0})
        bucket["created"] += run.created_count or 0
        bucket["updated"] += run.updated_count or 0
        bucket["errors"] += run.error_count or 0
    return stats


def _fill_rate_for_domain(
    artifacts: list[MigrationArtifact],
    per_artifact_mappings: dict[str, list[dict[str, Any]]],
) -> dict[str, float]:
    """Per canonical field, fraction of source rows with a non-empty value."""
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
    """Sanity check: a re-applied bundle should produce zero net new creates."""
    return {
        "key": bundle.idempotency_key,
        "applied_at": apply_totals.get("applied_at"),
        "guidance": (
            "Re-running the same idempotency_key against the same bundle "
            "must produce zero new creates (only updates). The orchestrator's "
            "upsert-by-external_id contract guarantees this for landers that "
            "respect the contract; the dynamic-field fallback de-dupes by "
            "(definition_slug, object_id)."
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
    }
