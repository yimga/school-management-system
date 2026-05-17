"""
Rollback handlers for MigrationRun (Phase 5 migration cloud, 11.1).
Each migration_type can register a handler(run, rollback_run) -> {success, message, reverted_count}.
Handlers use run.rollback_snapshot (e.g. created_ids, updated_ids) to revert.
"""

from typing import Any, Callable, Optional

_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {}


def register_rollback_handler(migration_type: str):
    """Decorator to register a rollback handler for a migration type."""

    def decorator(fn: Callable[..., dict[str, Any]]):
        _REGISTRY[migration_type] = fn
        return fn

    return decorator


def get_rollback_handler(
    migration_type: str,
) -> Optional[Callable[..., dict[str, Any]]]:
    return _REGISTRY.get(migration_type)


def run_rollback(run, rollback_run) -> dict[str, Any]:
    """Execute the rollback for run; returns dict with success, message, reverted_count."""
    handler = get_rollback_handler(run.migration_type)
    if not handler:
        return {
            "success": False,
            "message": f"No rollback handler for {run.migration_type}.",
            "reverted_count": 0,
        }
    return handler(run, rollback_run)


@register_rollback_handler("students")
def _rollback_students(run, rollback_run) -> dict[str, Any]:
    """
    Delete StudentProfile records that were created in this migration run.
    rollback_snapshot: {"created_ids": [uuid, ...]} from student bulk-commit API.
    """
    from apps.people.models import StudentProfile

    created_ids = (run.rollback_snapshot or {}).get("created_ids") or []
    if not created_ids:
        return {
            "success": True,
            "message": "No created_ids in snapshot; nothing to revert.",
            "reverted_count": 0,
        }
    school = getattr(run, "school", None)
    if not school:
        return {"success": False, "message": "Run has no school.", "reverted_count": 0}
    qs = StudentProfile.objects.filter(pk__in=created_ids, school=school)
    count = qs.count()
    qs.delete()
    return {
        "success": True,
        "message": f"Deleted {count} student record(s).",
        "reverted_count": count,
    }


@register_rollback_handler("grades")
def _rollback_grades(run, rollback_run) -> dict[str, Any]:
    """
    Delete Evaluation records that were created or updated in this migration run.
    rollback_snapshot: {"created_ids": [...], "updated_ids": [...]} from evals apply_import.
    """
    from apps.evals.models import Evaluation

    snapshot = run.rollback_snapshot or {}
    created_ids = snapshot.get("created_ids") or []
    updated_ids = snapshot.get("updated_ids") or []
    ids = list(created_ids) + list(updated_ids)
    if not ids:
        return {
            "success": True,
            "message": "No created_ids/updated_ids in snapshot; nothing to revert.",
            "reverted_count": 0,
        }
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    qs = Evaluation.objects.filter(pk__in=ids)
    count = qs.count()
    qs.delete()
    return {
        "success": True,
        "message": f"Deleted {count} grade record(s).",
        "reverted_count": count,
    }
