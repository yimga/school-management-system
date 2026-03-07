"""
Phase 5 migration cloud: dry-run, run, scorecard, parity.
Used by accounts.migration_wizard; creates MigrationRun records in automation app.
"""
from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model

User = get_user_model()


def run_dry_run(school, migration_type: str, transformed_rows: list[dict], user=None, legacy_snapshot=None, **context) -> dict[str, Any]:
    """
    Validate and simulate a migration without writing. Returns scorecard dict:
    created, updated, error_count, errors (sample), duration_seconds, status, parity.
    Optionally creates a MigrationRun with dry_run=True for audit.
    legacy_snapshot: optional list of uploaded rows for read-only legacy view (stored on run).
    """
    create_audit = context.pop("create_audit", True)
    row_count = len(transformed_rows)
    snapshot = legacy_snapshot if isinstance(legacy_snapshot, list) else (transformed_rows[:500] if create_audit else [])

    if migration_type == "students":
        # Students: validate required fields and count valid rows; no DB lookup for "would create"
        required = {"first_name", "last_name"}
        errors = []
        valid_count = 0
        for idx, row in enumerate(transformed_rows, start=1):
            missing = [f for f in required if not (row.get(f) or "").strip()]
            if missing:
                errors.append(f"Row {idx}: missing required {missing}")
            else:
                valid_count += 1
        scorecard = {
            "created": valid_count,
            "updated": 0,
            "error_count": len(errors),
            "errors": errors[:30],
            "duration_seconds": 0,
            "status": "SUCCESS" if not errors else "PARTIAL",
        }
    elif migration_type == "grades":
        from apps.academics.services import get_active_year_and_term
        from apps.evals.importers import dry_run_grade_import

        active_year, _ = get_active_year_and_term()
        if not active_year:
            scorecard = {
                "created": 0,
                "updated": 0,
                "error_count": row_count,
                "errors": ["No active academic year set."],
                "duration_seconds": 0,
                "status": "FAILED",
            }
        else:
            scorecard = dry_run_grade_import(transformed_rows, active_year)
            scorecard["status"] = (
                "SUCCESS" if scorecard["error_count"] == 0
                else "PARTIAL" if scorecard["created"] or scorecard["updated"]
                else "FAILED"
            )
    else:
        scorecard = {
            "created": 0,
            "updated": 0,
            "error_count": row_count,
            "errors": [f"Unknown migration type: {migration_type}"],
            "duration_seconds": 0,
            "status": "FAILED",
        }

    scorecard["row_count"] = row_count
    scorecard["parity"] = compute_parity_from_scorecard(row_count, scorecard)

    if create_audit and school:
        from apps.automation.models import MigrationRun
        run = MigrationRun.objects.create(
            school=school,
            migration_type=migration_type,
            dry_run=True,
            row_count=row_count,
            created_count=scorecard.get("created", 0),
            updated_count=scorecard.get("updated", 0),
            error_count=scorecard.get("error_count", 0),
            status=scorecard.get("status", "PENDING"),
            triggered_by=user,
            execution_summary={
                "errors_sample": scorecard.get("errors", [])[:20],
                "parity": scorecard.get("parity"),
                "duration_seconds": scorecard.get("duration_seconds"),
            },
            legacy_snapshot={"rows": snapshot[:200]} if snapshot else {},
        )
        run.mark_completed(
            status=scorecard["status"],
            created_count=scorecard.get("created", 0),
            updated_count=scorecard.get("updated", 0),
            error_count=scorecard.get("error_count", 0),
            summary=run.execution_summary,
        )
        scorecard["migration_run_id"] = run.pk

    return scorecard


def run_migration_start(school, migration_type: str, row_count: int, user=None, legacy_snapshot=None):
    """Create a MigrationRun record for an actual import; caller performs the import then calls run_migration_finish.
    legacy_snapshot: optional dict e.g. {"rows": [...]} for read-only legacy view."""
    from apps.automation.models import MigrationRun
    snap = legacy_snapshot if isinstance(legacy_snapshot, dict) else {}
    if isinstance(legacy_snapshot, list):
        snap = {"rows": legacy_snapshot[:200]}
    return MigrationRun.objects.create(
        school=school,
        migration_type=migration_type,
        dry_run=False,
        row_count=row_count,
        status=MigrationRun.Status.PENDING,
        triggered_by=user,
        legacy_snapshot=snap,
    )


def run_migration_finish(run, result: dict[str, Any]) -> dict[str, Any]:
    """
    Update a MigrationRun with the outcome of the import. result: created, updated, error_count, errors (list), error_message (optional), duration_seconds (optional).
    Returns result dict with status, migration_run_id, parity added.
    """
    from apps.automation.models import MigrationRun

    status = (
        MigrationRun.Status.SUCCESS if result.get("error_count", 0) == 0
        else MigrationRun.Status.PARTIAL if (result.get("created") or result.get("updated")) else MigrationRun.Status.FAILED
    )
    summary = {
        "errors_sample": (result.get("errors") or [])[:20],
        "duration_seconds": result.get("duration_seconds"),
    }
    run.mark_completed(
        status=status,
        created_count=result.get("created", 0),
        updated_count=result.get("updated", 0),
        error_count=result.get("error_count", 0),
        error_message=result.get("error_message", ""),
        summary=summary,
    )
    if result.get("rollback_snapshot") and run.pk:
        run.rollback_snapshot = result["rollback_snapshot"]
        run.save(update_fields=["rollback_snapshot"])
    result["status"] = status
    result["migration_run_id"] = run.pk
    result["row_count"] = run.row_count
    result["parity"] = compute_parity_from_scorecard(run.row_count, result)
    return result


def compute_parity_from_scorecard(row_count: int, scorecard: dict) -> dict[str, Any]:
    """Parity checker: compare source row count to created + updated + error_count."""
    created = scorecard.get("created", 0)
    updated = scorecard.get("updated", 0)
    errors = scorecard.get("error_count", 0)
    total = created + updated + errors
    return {
        "source_rows": row_count,
        "total_processed": total,
        "match": total == row_count,
        "created": created,
        "updated": updated,
        "errors": errors,
    }


def compute_parity(migration_run) -> dict[str, Any]:
    """Given a MigrationRun, return parity info (source vs processed)."""
    row_count = migration_run.row_count
    total = migration_run.created_count + migration_run.updated_count + migration_run.error_count
    return {
        "source_rows": row_count,
        "total_processed": total,
        "match": total == row_count,
        "created": migration_run.created_count,
        "updated": migration_run.updated_count,
        "errors": migration_run.error_count,
    }
