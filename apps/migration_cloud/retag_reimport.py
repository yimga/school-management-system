"""Retag misclassified artifacts and re-import an already-applied bundle.

Tenant review used to update ``assigned_domain`` and call ``_advance()`` only.
On ``APPLIED`` / ``RECONCILED`` bundles ``advance_bundle`` is a no-op and
``apply_bundle`` refuses to write — so a telephone directory tagged
``custom_fields`` stayed as generic blobs even after the operator picked
**Teachers / Staff**. This module is the shared operator path (UI + CLI).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.utils import timezone

from apps.migration_cloud.models import BundleStatus, FinancialMismatchError, MigrationBundle
from apps.migration_cloud.repair import RepairResult, repair_bundle, repair_readiness


@dataclass
class RetagReimportResult:
    ok: bool
    catalog_changed: int = 0
    inference_refreshed: bool = False
    repair: RepairResult | None = None
    message: str = ""
    blockers: list[str] = field(default_factory=list)


def bundle_needs_reimport_after_retag(bundle: MigrationBundle) -> bool:
    """True when the bundle already applied but tags/data paths still disagree."""
    if bundle.status not in (BundleStatus.APPLIED, BundleStatus.RECONCILED):
        return False
    try:
        from apps.migration_cloud.catalog_preflight import assess_bundle_catalog_routing

        report = assess_bundle_catalog_routing(bundle)
    except (ImportError, AttributeError, TypeError, ValueError):
        report = {"artifacts": []}
    for finding in report.get("artifacts") or []:
        if not isinstance(finding, dict):
            continue
        assigned = str(finding.get("assigned_domain") or "").strip()
        recommended = str(finding.get("recommended_domain") or "").strip()
        severity = str(finding.get("severity") or "ok")
        if (
            recommended
            and recommended != assigned
            and severity in ("advisory", "critical")
        ):
            return True

    applied_domains = (bundle.discovery_summary or {}).get("per_artifact_domain") or {}
    for art in bundle.artifacts.filter(quarantined=False):
        current = (art.assigned_domain or "").strip()
        path_key = art.path_within_bundle or art.filename or ""
        entry = applied_domains.get(path_key) or applied_domains.get(art.filename or "") or {}
        applied = ""
        if isinstance(entry, dict):
            applied = str(entry.get("domain") or "").strip()
        elif entry:
            applied = str(entry).strip()
        if current and applied and current != applied:
            return True
        if current == "staff" and applied == "custom_fields":
            return True
    return False


def apply_catalog_retags(bundle: MigrationBundle) -> int:
    from apps.migration_cloud.catalog_preflight import apply_catalog_recommendations
    from apps.migration_cloud.domain_overrides import sync_operator_assigned_domains

    changed = apply_catalog_recommendations(bundle)
    sync_operator_assigned_domains(bundle, rewind_status=False)
    return changed


def refresh_inference(bundle: MigrationBundle) -> dict[str, Any]:
    from apps.migration_cloud.pipeline import refresh_bundle_inference

    return refresh_bundle_inference(bundle_id=bundle.pk, use_accelerator=True)


def force_reimport_applied_bundle(
    bundle: MigrationBundle,
    *,
    off_http: bool = True,
) -> RepairResult:
    """Reset to MAPPED and re-apply — for cleanly-applied bundles repair refuses."""
    from apps.migration_cloud.apply_progress_guard import reset_apply_progress
    from apps.migration_cloud.progress import APPLY_RUN_EPOCH_KEY
    from apps.migration_cloud.repair import (
        _financial_guardrail_locked,
        _has_finance,
        supersede_wedged_apply,
    )

    if _financial_guardrail_locked(bundle):
        return RepairResult(
            ok=False,
            ran=False,
            message=(
                "Re-import stopped: financial control-total lock is active. "
                "Reconcile totals first."
            ),
            before_status=bundle.status,
            after_status=bundle.status,
            blockers=["financial_guardrail_failed"],
        )
    if _has_finance(bundle) and not bool(getattr(bundle, "apply_atomic", False)):
        return RepairResult(
            ok=False,
            ran=False,
            message="Finance artifacts require atomic apply before re-import.",
            before_status=bundle.status,
            after_status=bundle.status,
            blockers=["finance_requires_atomic"],
        )

    before = bundle.status
    now_iso = timezone.now().isoformat()
    bundle.mark_status(
        BundleStatus.MAPPED,
        summary_patch={
            "operator_retag_reapply_at": now_iso,
            APPLY_RUN_EPOCH_KEY: now_iso,
            "unified_progress_hwm": {"epoch": now_iso, "pct": 0.0},
        },
    )
    reset_apply_progress(bundle)

    if off_http:
        from apps.migration_cloud.celery_tasks import enqueue_apply

        supersede_wedged_apply(bundle)
        queued = enqueue_apply(
            bundle.pk,
            dry_run=False,
            reconcile_after=True,
            force=True,
        )
        oid = str(getattr(queued, "outbox_id", None) or getattr(queued, "id", "") or "")
        return RepairResult(
            ok=True,
            ran=False,
            queued=True,
            outbox_id=oid,
            message=(
                "Re-import queued with corrected record types. "
                "Refresh this page in a moment for updated counts."
            ),
            before_status=before,
            after_status=BundleStatus.MAPPED,
        )

    from apps.migration_cloud.orchestrator import apply_bundle

    try:
        result = apply_bundle(bundle_id=bundle.pk, dry_run=False)
    except FinancialMismatchError:
        bundle.refresh_from_db()
        return RepairResult(
            ok=False,
            ran=True,
            message=(
                "Re-import stopped on the financial control-total check — "
                "reconcile totals before retrying."
            ),
            before_status=before,
            after_status=bundle.status,
            blockers=["financial_guardrail_failed"],
        )
    bundle.refresh_from_db()
    repair_result = RepairResult(
        ok=bundle.status in (BundleStatus.APPLIED, BundleStatus.RECONCILED),
        ran=True,
        message=(
            f"Re-imported with corrected record types: {result.total_created} created, "
            f"{result.total_updated} updated, {result.total_quarantined} held."
        ),
        before_status=before,
        after_status=bundle.status,
        created=result.total_created,
        updated=result.total_updated,
        quarantined=result.total_quarantined,
    )
    if repair_result.ok and getattr(bundle, "school", None) is not None:
        try:
            from django.db import DatabaseError

            from apps.migration_cloud.post_import_graph_closure import (
                run_post_import_graph_closure,
            )

            run_post_import_graph_closure(bundle.school, bundle=bundle, dry_run=False)
            repair_result.message += " Import graph closure ran automatically."
        except (ImportError, DatabaseError, TypeError, ValueError):
            pass
    return repair_result


def retag_and_reimport_bundle(
    bundle: MigrationBundle,
    *,
    apply_catalog: bool = True,
    off_http: bool = True,
) -> RetagReimportResult:
    """Apply catalog retags, refresh inference, then repair or force re-import."""
    catalog_changed = apply_catalog_retags(bundle) if apply_catalog else 0
    refresh_inference(bundle)
    bundle.refresh_from_db()

    readiness = repair_readiness(bundle)
    if readiness.repairable:
        repair = repair_bundle(bundle_id=bundle.pk, off_http=off_http)
        return RetagReimportResult(
            ok=repair.ok,
            catalog_changed=catalog_changed,
            inference_refreshed=True,
            repair=repair,
            message=repair.message,
            blockers=list(repair.blockers or []),
        )

    if bundle.status in (BundleStatus.APPLIED, BundleStatus.RECONCILED) or catalog_changed:
        repair = force_reimport_applied_bundle(bundle, off_http=off_http)
        return RetagReimportResult(
            ok=repair.ok,
            catalog_changed=catalog_changed,
            inference_refreshed=True,
            repair=repair,
            message=repair.message,
            blockers=list(repair.blockers or []),
        )

    return RetagReimportResult(
        ok=False,
        catalog_changed=catalog_changed,
        inference_refreshed=True,
        message=readiness.reason,
        blockers=list(readiness.blockers or []),
    )
