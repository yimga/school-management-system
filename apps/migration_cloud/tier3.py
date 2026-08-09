"""Tier 3 long-tail features for the Migration Cloud.

Module-per-feature is overkill for these — each is a small, focused piece
of logic that the wizard / management command surfaces invoke directly:

    #15 ``merge_bundles``          — multi-bundle merge view
    #16 ``generate_handoff_doc``   — auto-generated migration receipt
    #17 ``lockout_legacy_source``  — flip legacy to read-only at T+0
    #18 ``estimate_token_spend``   — cost predictor for AI mapping
    #19 ``suggest_profiles_for``   — cross-tenant MigrationProfile recall
    #20 ``export_tenant_to_canonical`` — reverse migration / export-out
    #21 ``stage_rollout_plan``     — multi-stage rollouts (grade 12 pilot etc.)
    #22 ``ocr_confidence_warning`` — borderline OCR confidence flag
    #23 ``sla_tier_targets``       — SLA tier enforcement / targets
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from typing import Any, Iterable

from django.utils import timezone

from .models import (
    BundleStatus,
    MigrationArtifact,
    MigrationBundle,
)

logger = logging.getLogger(__name__)


# --- #15 multi-bundle merge ------------------------------------------------

def merge_bundles(
    *,
    bundles: list[MigrationBundle],
    label: str = "",
    idempotency_key: str | None = None,
) -> MigrationBundle:
    """Create a parent bundle that owns the artifacts of N child bundles.

    Useful for "Sept cutover" = students.csv Monday + grades.zip Wednesday +
    photos.tar Friday rolled up. Children are left in place (no data move)
    but the parent's artifact list points at the same MigrationArtifact rows
    so reconciliation / apply runs cross-bundle.
    """
    if not bundles:
        raise ValueError("merge_bundles requires at least one source bundle.")
    base = bundles[0]
    parent = MigrationBundle.objects.create(
        school=base.school,
        schema_name=base.schema_name,
        label=label or f"Merged ({len(bundles)} bundles)",
        intake_method=base.intake_method,
        idempotency_key=idempotency_key or f"merged-{timezone.now().timestamp()}",
        sla_tier=base.sla_tier,
        status=BundleStatus.MAPPED,
        triggered_by=base.triggered_by,
    )
    # The merged parent gets NEW artifact rows with a rewritten
    # ``path_within_bundle`` (``{child.pk}::<path>``). The captured source bytes
    # live in a per-artifact OneToOne blob keyed to the ORIGINAL pk, and the
    # rewritten path also defeats the single-top-level-local-file fallback — so
    # without copying the blob a merged apply lands ZERO rows for every artifact.
    from .artifact_blob_store import clone_artifact_blob

    merged_per_artifact: dict[str, list] = {}
    merged_domains: dict[str, dict] = {}
    for child in bundles:
        for artifact in child.artifacts.all():
            merged_artifact = MigrationArtifact.objects.create(
                bundle=parent,
                parent_archive=None,
                path_within_bundle=f"{child.pk}::{artifact.path_within_bundle}",
                filename=artifact.filename,
                mime_type=artifact.mime_type,
                detected_format=artifact.detected_format,
                byte_size=artifact.byte_size,
                sha256=artifact.sha256,
                encoding=artifact.encoding,
                row_count=artifact.row_count,
                column_count=artifact.column_count,
                locale_hints=dict(artifact.locale_hints or {}),
                profile=dict(artifact.profile or {}),
                inferred_source=artifact.inferred_source,
                inferred_domain=list(artifact.inferred_domain or []),
            )
            clone_artifact_blob(artifact, merged_artifact)
        for path, mappings in (child.mapping_summary or {}).get("per_artifact", {}).items():
            merged_per_artifact[f"{child.pk}::{path}"] = mappings
        for path, dom in (child.discovery_summary or {}).get("per_artifact_domain", {}).items():
            merged_domains[f"{child.pk}::{path}"] = dom
    parent.mapping_summary = {"per_artifact": merged_per_artifact, "merged_from": [b.pk for b in bundles]}
    parent.discovery_summary = {"per_artifact_domain": merged_domains, "merged_from": [b.pk for b in bundles]}
    parent.save(update_fields=["mapping_summary", "discovery_summary", "updated_at"])
    return parent


# --- #16 handoff document --------------------------------------------------

def generate_handoff_doc(*, bundle: MigrationBundle) -> dict[str, Any]:
    """Produce a FERPA-friendly summary an operator can email to the school's IT lead.

    Returns a dict (the view renders it to HTML/PDF). Contains the bundle
    lifecycle, totals, reconciliation parity, financial-guardrail status,
    and any pending operator-review items.
    """
    apply_totals = (bundle.mapping_summary or {}).get("apply_totals") or {}
    recon = bundle.reconciliation_summary or {}
    guardrail = (bundle.mapping_summary or {}).get("financial_guardrail") or {}
    conflicts_pending = bundle.conflicts.filter(resolution="PENDING").count()
    assets_stored = bundle.assets.filter(status="STORED").count()
    assets_failed = bundle.assets.filter(status="FAILED").count()
    return {
        "title": f"Migration Receipt — {bundle.label or bundle.idempotency_key}",
        "school_name": getattr(bundle.school, "name", "") if bundle.school else "",
        "generated_at": timezone.now().isoformat(),
        "bundle_id": bundle.pk,
        "status": bundle.status,
        "source": (bundle.discovery_summary or {}).get("source", {}).get("chosen", "unknown"),
        "artifacts": bundle.artifact_count,
        "totals": {
            "created": apply_totals.get("created", 0),
            "updated": apply_totals.get("updated", 0),
            "quarantined": apply_totals.get("quarantined", 0),
        },
        "reconciliation": {
            "overall_parity_pct": recon.get("overall_parity_pct"),
            "per_domain_count": len(recon.get("per_domain") or []),
        },
        "financial_guardrail": {
            "enforced": bool(guardrail),
            "ok": guardrail.get("ok"),
            "checks": len(guardrail.get("checks") or []),
        },
        "assets": {"stored": assets_stored, "failed": assets_failed},
        "open_action_items": {"conflicts_pending": conflicts_pending},
        "ferpa_notice": (
            "This document summarises a school data migration. It does NOT contain "
            "student-level personal information. Detailed records are available to "
            "authorised school officials via the platform under access controls."
        ),
    }


# --- #17 legacy lockout ----------------------------------------------------

def lockout_legacy_source(*, bundle: MigrationBundle, instructions: str = "") -> dict[str, Any]:
    """Produce a checklist + write to the bundle's progress log so the operator
    can confirm the legacy system has been flipped to read-only at T+0.

    We don't actually call into the legacy system (it's out-of-band) — we
    record the operator's confirmation so the audit log shows "lockout
    requested at <ts>" and the reconciliation report can quote it.
    """
    from .progress import emit
    emit(
        bundle_id=bundle.pk,
        kind="info",
        stage="LOCKOUT",
        message="Legacy source lockout requested",
        detail={"instructions": instructions[:500]},
    )
    summary = dict(bundle.size_summary or {})
    summary["legacy_lockout"] = {
        "requested_at": timezone.now().isoformat(),
        "instructions": instructions[:500],
    }
    bundle.size_summary = summary
    bundle.save(update_fields=["size_summary", "updated_at"])
    return summary["legacy_lockout"]


# --- #18 cost predictor ----------------------------------------------------

@dataclass
class CostEstimate:
    artifact_count: int
    column_count_total: int
    estimated_ai_calls: int
    estimated_tokens: int
    estimated_usd: float


def _cost_params() -> tuple[int, float]:
    from apps.migration_cloud import defaults as _mc_defaults
    try:
        tokens = int(_mc_defaults.get("migration_cloud.cost.avg_tokens_per_call"))
    except Exception:  # noqa: BLE001
        tokens = 800
    try:
        usd = float(_mc_defaults.get("migration_cloud.cost.usd_per_1k_tokens"))
    except Exception:  # noqa: BLE001
        usd = 0.002
    return tokens, usd


_AVG_TOKENS_PER_CALL = 800
_USD_PER_1K_TOKENS = 0.002


def estimate_token_spend(*, bundle: MigrationBundle) -> CostEstimate:
    """Estimate AI token spend before running expensive bundle mapping.

    Heuristic: every column without a high-confidence deterministic mapping
    triggers ~1 AI call at ~800 tokens. Vendor prices vary; we use a
    conservative $0.002/1k tokens default that can be overridden.
    """
    artifact_count = bundle.artifact_count
    columns_total = 0
    ai_calls = 0
    per_artifact = (bundle.mapping_summary or {}).get("per_artifact") or {}
    for artifact in bundle.artifacts.all():
        cols = (artifact.profile or {}).get("columns") or []
        columns_total += len(cols)
        mappings = per_artifact.get(artifact.path_within_bundle) or []
        deterministic = sum(
            1 for m in mappings
            if str(m.get("method") or "") in ("alias", "embedding", "accelerator", "operator_command")
            and float(m.get("confidence") or 0.0) >= 0.85
        )
        ai_calls += max(0, len(cols) - deterministic)
    avg_tokens, usd_per_1k = _cost_params()
    tokens = ai_calls * avg_tokens
    usd = round(tokens / 1000 * usd_per_1k, 4)
    return CostEstimate(
        artifact_count=artifact_count,
        column_count_total=columns_total,
        estimated_ai_calls=ai_calls,
        estimated_tokens=tokens,
        estimated_usd=usd,
    )


# --- #19 cross-tenant profile recall ---------------------------------------

def suggest_profiles_for(*, source_system: str, domain: str = "", limit: int = 5) -> list[dict[str, Any]]:
    """Return MigrationProfile rows other tenants saved for the same source.

    Surfaces profiles by ``source_system`` (and optionally ``domain``) so a
    new tenant can pick a curated PowerSchool / Blackbaud / etc. mapping
    instead of starting from scratch.
    """
    try:
        from apps.automation.models import MigrationProfile
    except Exception:  # noqa: BLE001
        return []
    qs = MigrationProfile.objects.filter(is_active=True)
    if source_system:
        qs = qs.filter(source_system__iexact=source_system)
    if domain:
        qs = qs.filter(domain__iexact=domain)
    return [
        {
            "slug": p.slug,
            "name": p.name,
            "description": p.description,
            "source_system": p.source_system,
            "domain": p.domain,
            "saved_from_bundle_id": (p.config or {}).get("saved_from_bundle_id"),
        }
        for p in qs.order_by("-id")[:limit]
    ]


# --- #20 reverse migration / export-out ------------------------------------

def export_tenant_to_canonical(*, school: Any, domains: Iterable[str] | None = None) -> dict[str, str]:
    """Export tenant data back to canonical CSVs (no-lock-in promise).

    Returns ``{domain: csv_text}``. The view layer streams these as a zip.
    Iterates the per-domain tenant model and emits canonical columns.
    """
    out: dict[str, str] = {}
    domains = set(domains or ("students", "guardians", "finance"))
    try:
        from apps.people.models import StudentProfile
    except Exception:  # noqa: BLE001
        StudentProfile = None
    if StudentProfile is not None and "students" in domains:
        out["students"] = _csv_dump(StudentProfile.objects.filter(school=school) if "school" in {f.name for f in StudentProfile._meta.get_fields()} else StudentProfile.objects.all(),  # tenant-isolation-allow: branch above scopes via school=school

                                     ["external_id", "first_name", "last_name", "email", "phone",
                                      "date_of_birth", "grade_level", "enrollment_status"])
    try:
        from apps.people.models import StudentGuardian
    except Exception:  # noqa: BLE001
        StudentGuardian = None
    if StudentGuardian is not None and "guardians" in domains:
        # Transfer design §8 defect 2: "guardians" was in the default domain
        # set above but had no branch — silently omitted from every export.
        guardian_fields = [
            "guardian_external_id", "first_name", "last_name", "email",
            "phone", "relationship", "student_external_id",
        ]
        guardian_rows = []
        guardian_qs = StudentGuardian.objects.filter(
            student__school=school
        ).select_related("student", "guardian_user")
        for g in guardian_qs.iterator():
            guardian_user = getattr(g, "guardian_user", None)
            student = getattr(g, "student", None)
            guardian_rows.append({
                "guardian_external_id": f"g-{g.pk}",
                "first_name": getattr(guardian_user, "first_name", "") or "",
                "last_name": getattr(guardian_user, "last_name", "") or "",
                "email": g.email or getattr(guardian_user, "email", "") or "",
                "phone": g.phone,
                "relationship": g.relationship,
                "student_external_id": (
                    getattr(student, "admission_number", "")
                    or getattr(student, "student_code", "")
                    or ""
                ),
            })
        out["guardians"] = _csv_dump_rows(guardian_rows, guardian_fields)
    try:
        from apps.finance.models import Invoice
    except Exception:  # noqa: BLE001
        Invoice = None
    if Invoice is not None and "finance" in domains:
        qs = Invoice.objects.all()  # tenant-isolation-allow: invoked via export_tenant_to_canonical(school=...), Invoice scoped via tenant schema
        out["finance"] = _csv_dump(qs, ["reference", "amount", "currency", "due_date", "issue_date", "description"])
    return out


def _csv_dump(qs, fields: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(fields)
    for obj in qs.iterator():
        writer.writerow([_csv_safe(getattr(obj, f, "")) for f in fields])
    return buf.getvalue()


def _csv_dump_rows(rows: list[dict], fields: list[str]) -> str:
    """CSV from computed dict rows (for domains needing FK traversal)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(fields)
    for row in rows:
        writer.writerow([_csv_safe(row.get(f, "")) for f in fields])
    return buf.getvalue()


def _str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


# Leading characters a spreadsheet treats as the start of a formula.
_CSV_FORMULA_TRIGGERS = ("=", "@", "\t", "\r")


def _csv_safe(v: Any) -> str:
    """Neutralize CSV formula injection on the "no lock-in" tenant export.

    A tenant value like ``=cmd|'/c calc'!A1`` (which itself may have arrived via a
    prior migration into a name / description) would execute when the export CSV
    is opened in Excel / Google Sheets. Prefix a leading formula trigger with a
    single quote so the cell renders as text. A leading ``+`` / ``-`` is only
    neutralized when it is NOT a plain number, so negative amounts and signed
    values still round-trip.
    """
    s = _str(v)
    if not s:
        return s
    first = s[0]
    if first in _CSV_FORMULA_TRIGGERS:
        return "'" + s
    if first in ("+", "-"):
        rest = s[1:].replace(",", "").replace(".", "", 1)
        if not rest.isdigit():
            return "'" + s
    return s


# --- #21 multi-stage rollouts ---------------------------------------------

def stage_rollout_plan(*, bundle: MigrationBundle, stages: list[dict[str, Any]]) -> dict[str, Any]:
    """Record a phased rollout plan on the bundle (grade 12 pilot → grade 9-12 → all).

    Each stage = ``{"label": "grade 12 pilot", "filter": {"grade_level": "12"}}``.
    The orchestrator's cohort hook reads this and limits rows per stage; the
    operator advances stages explicitly.
    """
    summary = dict(bundle.size_summary or {})
    summary["rollout_plan"] = {
        "stages": stages,
        "current_stage": 0,
        "created_at": timezone.now().isoformat(),
    }
    bundle.size_summary = summary
    bundle.save(update_fields=["size_summary", "updated_at"])
    return summary["rollout_plan"]


def advance_rollout_stage(*, bundle: MigrationBundle) -> dict[str, Any]:
    plan = (bundle.size_summary or {}).get("rollout_plan") or {}
    if not plan.get("stages"):
        raise ValueError("no rollout plan on this bundle")
    plan["current_stage"] = min(plan["current_stage"] + 1, len(plan["stages"]) - 1)
    summary = dict(bundle.size_summary or {})
    summary["rollout_plan"] = plan
    bundle.size_summary = summary
    bundle.save(update_fields=["size_summary", "updated_at"])
    return plan


# --- #22 OCR confidence warning -------------------------------------------

def ocr_confidence_warning(*, ocr_chars: int, vendor_confidence: float | None) -> str | None:
    """Borderline OCR returns garbage; warn the operator at edges."""
    from apps.migration_cloud import defaults as _mc_defaults
    try:
        min_chars = int(_mc_defaults.get("migration_cloud.ocr.min_chars_for_decision"))
    except Exception:  # noqa: BLE001
        min_chars = 40
    try:
        low_threshold = float(_mc_defaults.get("migration_cloud.ocr.low_confidence_threshold"))
    except Exception:  # noqa: BLE001
        low_threshold = 0.5
    if ocr_chars < min_chars:
        return f"OCR extracted only {ocr_chars} characters — likely too few to identify the vendor reliably. Try a higher-resolution screenshot."
    if vendor_confidence is not None and 0.0 < vendor_confidence < low_threshold:
        return f"Vendor confidence ({vendor_confidence:.0%}) is low — the OCR text was readable but the result is uncertain. Treat this as a hint, not a decision."
    return None


# --- #23 SLA tier targets / enforcement -----------------------------------

_SLA_TARGETS_FALLBACK = {
    "small": {"target_minutes": 60, "escalate_minutes": 120},
    "mid": {"target_minutes": 240, "escalate_minutes": 480},
    "large": {"target_minutes": 720, "escalate_minutes": 1440},
    "state": {"target_minutes": 4320, "escalate_minutes": 7200},
}


def sla_tier_targets(*, bundle: MigrationBundle) -> dict[str, Any]:
    """Return the SLA targets for a bundle + whether it's running over."""
    from apps.migration_cloud import defaults as _mc_defaults
    tier = bundle.sla_tier or "small"
    try:
        all_targets = _mc_defaults.get("migration_cloud.sla.targets")
        targets = all_targets.get(tier) or _SLA_TARGETS_FALLBACK.get(tier, _SLA_TARGETS_FALLBACK["small"])
    except Exception:  # noqa: BLE001
        targets = _SLA_TARGETS_FALLBACK.get(tier, _SLA_TARGETS_FALLBACK["small"])
    started = bundle.started_at
    completed = bundle.completed_at
    now = timezone.now()
    elapsed_min = None
    if started:
        end = completed or now
        elapsed_min = int((end - started).total_seconds() / 60)
    over_target = elapsed_min is not None and elapsed_min > targets["target_minutes"]
    over_escalate = elapsed_min is not None and elapsed_min > targets["escalate_minutes"]
    return {
        "tier": tier,
        "targets": targets,
        "elapsed_minutes": elapsed_min,
        "over_target": over_target,
        "escalate": over_escalate,
    }
