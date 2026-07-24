"""Rollback posture — preview + the REAL schema-scoped bundle revert.

``rollback_preview`` computes what a confirmed rollback WOULD revert (a dry-run
posture card, no writes). ``rollback_apply`` performs the actual revert by
delegating to ``MigrationRun.trigger_rollback`` for every apply run of the
import's linked bundle — the snapshot-driven, per-domain, school-scoped delete
registered in ``apps.automation.rollback_handlers``. The source platform is
never touched by either.
"""

from __future__ import annotations

from apps.migration_cloud.models_connectors import ImportRunStatus, MigrationImportRun
from apps.migration_cloud.services.connector_audit import record_connector_audit


ROLLBACK_CATEGORIES = {
    "safe_revert": "Imported records can be reverted with confirmation.",
    "manual_review": "Operator must review before any revert.",
    "not_reversible": "Records integrated with live workflows — manual cleanup only.",
    "external_unchanged": "Source platform was never modified.",
}


def rollback_preview(*, import_run: MigrationImportRun, actor) -> dict:
    """Dry-run rollback posture — does not delete tenant data.

    Reports honestly which of the import's created domains have a registered
    rollback handler (students / grades / finance / attendance / behavior /
    guardians / staff; enrollment has a handler but reports its in-place updates
    as non-restorable). Call :func:`rollback_apply` with ``confirm=True`` to
    perform the real, schema-scoped revert.
    """
    from apps.automation.rollback_handlers import registered_rollback_domains

    snapshot = import_run.rollback_snapshot_reference or ""
    created = import_run.created_counts or {}
    category = "safe_revert" if snapshot else "manual_review"
    if not created:
        category = "not_reversible"

    revertible = set(registered_rollback_domains())
    created_domains = list(created.keys())
    covered = [d for d in created_domains if d in revertible]
    uncovered = [d for d in created_domains if d not in revertible]

    preview = {
        "import_run_id": str(import_run.id),
        "category": category,
        "category_label": ROLLBACK_CATEGORIES[category],
        "created_counts": created,
        "updated_counts": import_run.updated_counts or {},
        "snapshot_reference": snapshot,
        "source_unchanged": True,
        "requires_confirmation": category in ("safe_revert", "manual_review"),
        # Honest revertability: derived from the live handler registry, not a
        # hardcoded claim. A bundle-linked import can actually revert `covered`.
        "domains_with_rollback_handler": sorted(revertible),
        "revertible_created_domains": covered,
        "unrevertible_created_domains": uncovered,
        "has_bundle": import_run.bundle_id is not None,
    }
    record_connector_audit(
        school=import_run.school,
        actor=actor,
        event_type="rollback_previewed",
        source_connection=import_run.source_connection,
        import_run=import_run,
        metadata={"category": category},
    )
    return preview


def rollback_apply(*, import_run: MigrationImportRun, actor, confirm: bool = False) -> dict:
    """Perform the REAL bundle rollback for a connector import run.

    Delegates to ``MigrationRun.trigger_rollback`` for every audit run of the
    import's linked bundle — the schema-scoped, snapshot-driven per-domain revert
    in ``apps.automation.rollback_handlers`` (students / grades + finance /
    attendance / behavior / guardians / staff; enrollment reports honestly that
    its in-place updates cannot be auto-restored). This is NOT a dry run:
    confirmed creates are deleted from the tenant schema. The source platform is
    never touched.

    Requires ``confirm=True`` (operator confirmation). Runs are found by
    ``execution_summary__bundle_id`` — the same linkage the reconciliation
    auto-rollback uses — and each ``trigger_rollback`` already scopes its delete
    to ``run.school``.
    """
    if not confirm:
        return {
            "ok": False,
            "applied": False,
            "message": "Rollback requires operator confirmation (confirm=True).",
        }

    bundle = getattr(import_run, "bundle", None)
    if bundle is None:
        return {
            "ok": False,
            "applied": False,
            "message": (
                "Import run has no linked bundle; there are no apply runs to revert. "
                "Nothing was changed."
            ),
        }

    try:
        from apps.automation.models import MigrationRun
    except ImportError:
        return {"ok": False, "applied": False, "message": "Rollback engine unavailable."}

    runs = list(
        MigrationRun.objects.filter(  # tenant-isolation-allow: scoped via bundle.pk (bundle.school)
            execution_summary__bundle_id=bundle.pk,
        )
    )

    results: list[dict] = []
    reverted_total = 0
    any_failed = False
    for run in runs:
        if not run.can_rollback:
            continue
        _rollback_run, result = run.trigger_rollback(user=actor)
        results.append({
            "run_id": run.pk,
            "migration_type": run.migration_type,
            "success": bool(result.get("success")),
            "reverted_count": int(result.get("reverted_count") or 0),
            "message": result.get("message", ""),
        })
        reverted_total += int(result.get("reverted_count") or 0)
        if not result.get("success"):
            any_failed = True

    applied_any = bool(results)
    if applied_any:
        import_run.status = (
            ImportRunStatus.PARTIAL if any_failed else ImportRunStatus.ROLLED_BACK
        )
        import_run.save(update_fields=["status"])

    record_connector_audit(
        school=import_run.school,
        actor=actor,
        event_type="rollback_applied",
        source_connection=import_run.source_connection,
        import_run=import_run,
        metadata={
            "runs_attempted": len(results),
            "reverted_total": reverted_total,
            "any_failed": any_failed,
        },
    )
    return {
        "ok": applied_any and not any_failed,
        "applied": applied_any,
        "reverted_total": reverted_total,
        "runs": results,
        "message": (
            f"Reverted {reverted_total} record(s) across {len(results)} run(s)."
            if applied_any
            else "No revertible apply runs found for this bundle; nothing was changed."
        ),
    }


def rollback_posture_card(import_run: MigrationImportRun) -> dict:
    preview = {
        "status": import_run.status,
        "rollback_snapshot_reference": import_run.rollback_snapshot_reference,
        "created_counts": import_run.created_counts,
        "source_unchanged": True,
    }
    if import_run.status == "completed" and import_run.rollback_snapshot_reference:
        preview["category"] = "safe_revert"
    elif import_run.status == "partial":
        preview["category"] = "manual_review"
    else:
        preview["category"] = "not_reversible"
    preview["category_label"] = ROLLBACK_CATEGORIES.get(preview["category"], "")
    return preview
