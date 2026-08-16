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


def _rollback_message(reverted_total: int, run_count: int, not_reverted: list[dict]) -> str:
    """An honest one-line summary: what was reverted, and what was left in place."""
    if not run_count and not not_reverted:
        return "No revertible apply runs found for this bundle; nothing was changed."
    parts = [f"Reverted {reverted_total} record(s) across {run_count} run(s)."]
    if not_reverted:
        domains = ", ".join(sorted({str(d.get("migration_type") or "?") for d in not_reverted}))
        parts.append(
            f"{len(not_reverted)} domain run(s) could NOT be auto-reverted ({domains}) and were "
            "left in place — this was not a clean-slate purge; review the details and prune "
            "those manually."
        )
    return " ".join(parts)


def rollback_bundle(*, bundle, actor, confirm: bool = False) -> dict:
    """Revert every apply run of a ``MigrationBundle`` — child-first, school-scoped.

    The single source of truth for a full-bundle rollback, used by BOTH the tenant
    upload flow and the operator console. Each apply run is delegated to
    ``MigrationRun.trigger_rollback`` (the snapshot-driven, per-domain, school-scoped
    revert in ``apps.automation.rollback_handlers``) in REVERSE apply order
    (``-started_at``) so a child domain (grades) is reverted before the parent it
    references (students) and a PROTECT FK never blocks the delete.

    Reports HONESTLY. Beyond ``reverted_total`` + per-run ``runs``, it returns
    ``not_reverted`` — the apply runs whose rows were LEFT IN PLACE: a domain whose
    handler reports it is non-automatic (shared academic scaffold; an in-place update
    that was not snapshotted), a PROTECT-blocked delete, or a landed run that kept no
    rollback snapshot. ``ok`` is True only when the revert was genuinely complete
    (something applied, nothing failed, nothing left behind) — a caller must NEVER
    present the result as a clean-slate purge when ``not_reverted`` is non-empty.
    ``confirm=True`` is required to delete anything; the source platform is never
    touched.
    """
    empty = {"ok": False, "applied": False, "reverted_total": 0, "runs": [], "not_reverted": []}
    if not confirm:
        return {**empty, "message": "Rollback requires confirmation (confirm=True)."}
    if bundle is None:
        return {
            **empty,
            "message": (
                "No linked bundle; there are no apply runs to revert. Nothing was changed."
            ),
        }
    try:
        from apps.automation.models import MigrationRun
    except ImportError:
        return {**empty, "message": "Rollback engine unavailable."}

    runs = list(
        MigrationRun.objects.filter(  # tenant-isolation-allow: bundle.pk is the globally-unique shared MigrationBundle pk; the bundle is already tenant-scoped by the calling view, and each trigger_rollback scopes its delete to run.school
            execution_summary__bundle_id=bundle.pk,
        ).order_by("-started_at")  # child-first: reverse of the apply (wave) order
    )

    results: list[dict] = []
    not_reverted: list[dict] = []
    reverted_total = 0
    any_failed = False
    for run in runs:
        if not run.can_rollback:
            # A landed (SUCCESS/PARTIAL), non-revert, not-already-reverted run that kept
            # NO snapshot created rows we cannot auto-revert — surface it honestly.
            # Dry runs, rollback runs, already-reverted runs, and failed runs that
            # landed nothing are correctly silent.
            landed = run.status in (MigrationRun.Status.SUCCESS, MigrationRun.Status.PARTIAL)
            is_revert = run.migration_type == "rollback" or bool(run.dry_run)
            already = run.rolled_back_by_run_id is not None
            if landed and not is_revert and not already and not run.rollback_snapshot:
                not_reverted.append({
                    "migration_type": run.migration_type,
                    "reason": "this run kept no rollback snapshot, so its rows can't be auto-reverted.",
                })
            continue
        _rollback_run, result = run.trigger_rollback(user=actor)
        success = bool(result.get("success"))
        reverted = int(result.get("reverted_count") or 0)
        results.append({
            "run_id": run.pk,
            "migration_type": run.migration_type,
            "success": success,
            "reverted_count": reverted,
            "message": result.get("message", ""),
        })
        reverted_total += reverted
        if not success:
            any_failed = True
            not_reverted.append({
                "migration_type": run.migration_type,
                "reason": result.get("message") or "could not be reverted.",
            })

    applied_any = bool(results)
    return {
        "ok": applied_any and not any_failed and not not_reverted,
        "applied": applied_any,
        "reverted_total": reverted_total,
        "runs": results,
        "not_reverted": not_reverted,
        "message": _rollback_message(reverted_total, len(results), not_reverted),
    }


def rollback_apply(*, import_run: MigrationImportRun, actor, confirm: bool = False) -> dict:
    """Perform the REAL bundle rollback for a connector import run.

    Thin wrapper over :func:`rollback_bundle` (the shared, child-first, honest
    revert) that resolves the import run's linked bundle, then records the connector
    audit event and updates the import-run status. Requires ``confirm=True``. The
    source platform is never touched.
    """
    if not confirm:
        return {
            "ok": False, "applied": False, "reverted_total": 0, "runs": [], "not_reverted": [],
            "message": "Rollback requires operator confirmation (confirm=True).",
        }

    bundle = getattr(import_run, "bundle", None)
    if bundle is None:
        return {
            "ok": False, "applied": False, "reverted_total": 0, "runs": [], "not_reverted": [],
            "message": (
                "Import run has no linked bundle; there are no apply runs to revert. "
                "Nothing was changed."
            ),
        }

    result = rollback_bundle(bundle=bundle, actor=actor, confirm=True)

    if result.get("applied"):
        import_run.status = (
            ImportRunStatus.ROLLED_BACK if result.get("ok") else ImportRunStatus.PARTIAL
        )
        import_run.save(update_fields=["status"])

    record_connector_audit(
        school=import_run.school,
        actor=actor,
        event_type="rollback_applied",
        source_connection=import_run.source_connection,
        import_run=import_run,
        metadata={
            "runs_attempted": len(result.get("runs", [])),
            "reverted_total": result.get("reverted_total", 0),
            "not_reverted": len(result.get("not_reverted", [])),
            "any_failed": result.get("applied", False) and not result.get("ok", False),
        },
    )
    return result


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
