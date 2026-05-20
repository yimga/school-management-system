"""Rollback posture — preview and categorized revert guidance."""

from __future__ import annotations

from apps.migration_cloud.models_connectors import MigrationImportRun
from apps.migration_cloud.services.connector_audit import record_connector_audit


ROLLBACK_CATEGORIES = {
    "safe_revert": "Imported records can be reverted with confirmation.",
    "manual_review": "Operator must review before any revert.",
    "not_reversible": "Records integrated with live workflows — manual cleanup only.",
    "external_unchanged": "Source platform was never modified.",
}


def rollback_preview(*, import_run: MigrationImportRun, actor) -> dict:
    """Dry-run rollback posture — does not delete tenant data."""
    snapshot = import_run.rollback_snapshot_reference or ""
    created = import_run.created_counts or {}
    category = "safe_revert" if snapshot else "manual_review"
    if not created:
        category = "not_reversible"

    preview = {
        "import_run_id": str(import_run.id),
        "category": category,
        "category_label": ROLLBACK_CATEGORIES[category],
        "created_counts": created,
        "updated_counts": import_run.updated_counts or {},
        "snapshot_reference": snapshot,
        "source_unchanged": True,
        "requires_confirmation": category in ("safe_revert", "manual_review"),
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
