"""
Phase 5 migration cloud: dry-run, run, scorecard, parity.
Used by accounts.migration_wizard; creates MigrationRun records in automation app.
Phase B: schema inference for "Other" / generic profiles.
Phase C: pre-migration validation with categorized issues (duplicates, missing_required, invalid_refs).
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from django.contrib.auth import get_user_model

User = get_user_model()

# Phase C: issue categories
VALIDATION_CATEGORIES = ("duplicates", "missing_required", "invalid_refs")


def _normalize_for_match(s: str) -> str:
    """Lowercase, collapse spaces/underscores/dashes to single underscore."""
    if not s:
        return ""
    t = re.sub(r"[\s_\-]+", "_", str(s).strip().lower())
    return t.strip("_")


def infer_schema_mapping(
    headers: list[str], target_fields: list[str]
) -> dict[str, str]:
    """
    Phase B: Infer suggested mapping from source column names to target fields.
    Uses normalized name similarity (e.g. FirstName -> first_name, student_id -> admission_number for students).
    Returns dict: source_header -> target_field (only when exactly one match).
    """
    if not headers or not target_fields:
        return {}
    target_set = {_normalize_for_match(f): f for f in target_fields}
    # Common aliases for student/grade imports (when target_fields include these)
    alias_map = {
        "student_number": "admission_number",
        "student_id": "admission_number",
        "firstname": "first_name",
        "lastname": "last_name",
        "fname": "first_name",
        "lname": "last_name",
        "student_code": "student_code",
        "course_id": "subject_assignment_id",
        "section_id": "subject_assignment_id",
        "term": "term_id",
    }
    result = {}
    for header in headers:
        norm = _normalize_for_match(header)
        if not norm:
            continue
        # Exact match to target
        if norm in target_set:
            result[header] = target_set[norm]
            continue
        # Alias
        if norm in alias_map and alias_map[norm] in target_fields:
            result[header] = alias_map[norm]
            continue
        # Partial: target "first_name" matches header "firstname" (already via alias), or "first_name"
        for t_norm, t_field in target_set.items():
            if norm == t_norm or norm.replace("_", "") == t_norm.replace("_", ""):
                result[header] = t_field
                break
    return result


def run_pre_migration_validation(
    migration_type: str,
    transformed_rows: list[dict],
    school=None,
) -> dict[str, list[dict]]:
    """
    Phase C: Pre-migration validation with categorized issues.
    Returns validation_issues: {
        "duplicates": [{"row_indices": [1, 5], "key": "admission_number", "value": "X", "message": "..."}],
        "missing_required": [{"row": 1, "fields": ["first_name"], "message": "..."}],
        "invalid_refs": [{"row": 2, "ref_field": "student_code", "value": "Y", "message": "Student not found"}],
    }
    """
    issues = {cat: [] for cat in VALIDATION_CATEGORIES}

    if migration_type == "students":
        required = {"first_name", "last_name"}
        first_keys = (
            set((transformed_rows[0] or {}).keys()) if transformed_rows else set()
        )
        key_field = (
            "admission_number" if "admission_number" in first_keys else "student_code"
        )
        key_to_rows: dict[str, list[int]] = defaultdict(list)
        for idx, row in enumerate(transformed_rows, start=1):
            r = row or {}
            key_val = str(r.get(key_field) or "").strip()
            if key_val:
                key_to_rows[key_val].append(idx)
            missing = [f for f in required if not (r.get(f) or "").strip()]
            if missing:
                issues["missing_required"].append(
                    {
                        "row": idx,
                        "fields": missing,
                        "message": f"Row {idx}: missing required {missing}",
                    }
                )
        for key_val, indices in key_to_rows.items():
            if len(indices) > 1:
                issues["duplicates"].append(
                    {
                        "row_indices": indices,
                        "key": key_field,
                        "value": key_val,
                        "message": f"Duplicate {key_field} '{key_val}' in rows {indices}",
                    }
                )

    elif migration_type == "grades" and school:
        from apps.academics.models import SubjectAssignment
        from apps.people.models import StudentProfile
        from apps.academics.services import get_active_year_and_term

        active_year, _ = get_active_year_and_term()
        if not active_year:
            for idx in range(1, len(transformed_rows) + 1):
                issues["invalid_refs"].append(
                    {
                        "row": idx,
                        "ref_field": "academic_year",
                        "value": "",
                        "message": "No active academic year set.",
                    }
                )
            return issues
        # Resolve valid student_codes and subject_assignment ids for this school/year
        student_codes = set(
            StudentProfile.objects.filter(school=school).values_list(
                "student_code", flat=True
            )
        )
        student_codes = {str(s).strip().upper() for s in student_codes if s}
        sa_ids = set(
            SubjectAssignment.objects.filter(academic_year=active_year).values_list(
                "id", flat=True
            )
        )
        key_to_rows: dict[tuple, list[int]] = defaultdict(list)
        for idx, row in enumerate(transformed_rows, start=1):
            r = row or {}
            sc = str(r.get("student_code", "")).strip().upper()
            try:
                sa_id = int(r.get("subject_assignment_id") or 0)
            except (TypeError, ValueError):
                sa_id = 0
            term_id = r.get("term_id")
            # duplicate key: (student_code, subject_assignment_id, term_id)
            tup = (sc, sa_id, term_id)
            key_to_rows[tup].append(idx)
            if sc and sc not in student_codes:
                issues["invalid_refs"].append(
                    {
                        "row": idx,
                        "ref_field": "student_code",
                        "value": sc,
                        "message": f"Row {idx}: student_code '{sc}' not found in school",
                    }
                )
            if sa_id and sa_id not in sa_ids:
                issues["invalid_refs"].append(
                    {
                        "row": idx,
                        "ref_field": "subject_assignment_id",
                        "value": sa_id,
                        "message": f"Row {idx}: subject_assignment_id {sa_id} not found for active year",
                    }
                )
            required_grade = ["student_code", "subject_assignment_id", "term_id"]
            missing = [
                f
                for f in required_grade
                if not (r.get(f) is not None and str(r.get(f)).strip() != "")
            ]
            if missing:
                issues["missing_required"].append(
                    {
                        "row": idx,
                        "fields": missing,
                        "message": f"Row {idx}: missing required {missing}",
                    }
                )
        for tup, indices in key_to_rows.items():
            if len(indices) > 1:
                issues["duplicates"].append(
                    {
                        "row_indices": indices,
                        "key": "student_code, subject_assignment_id, term_id",
                        "value": str(tup),
                        "message": f"Duplicate grade key in rows {indices}",
                    }
                )
    elif migration_type == "grades":
        # no school: only duplicates and missing_required
        key_to_rows = defaultdict(list)
        for idx, row in enumerate(transformed_rows, start=1):
            r = row or {}
            sc = str(r.get("student_code", "")).strip()
            try:
                sa_id = int(r.get("subject_assignment_id") or 0)
            except (TypeError, ValueError):
                sa_id = 0
            term_id = r.get("term_id")
            key_to_rows[(sc, sa_id, term_id)].append(idx)
            required_grade = ["student_code", "subject_assignment_id", "term_id"]
            missing = [
                f
                for f in required_grade
                if not (r.get(f) is not None and str(r.get(f)).strip() != "")
            ]
            if missing:
                issues["missing_required"].append(
                    {
                        "row": idx,
                        "fields": missing,
                        "message": f"Row {idx}: missing required {missing}",
                    }
                )
        for tup, indices in key_to_rows.items():
            if len(indices) > 1:
                issues["duplicates"].append(
                    {
                        "row_indices": indices,
                        "key": "student_code, subject_assignment_id, term_id",
                        "value": str(tup),
                        "message": f"Duplicate grade key in rows {indices}",
                    }
                )

    return issues


def run_dry_run(
    school,
    migration_type: str,
    transformed_rows: list[dict],
    user=None,
    legacy_snapshot=None,
    **context,
) -> dict[str, Any]:
    """
    Validate and simulate a migration without writing. Returns scorecard dict:
    created, updated, error_count, errors (sample), duration_seconds, status, parity.
    Optionally creates a MigrationRun with dry_run=True for audit.
    legacy_snapshot: optional list of uploaded rows for read-only legacy view (stored on run).
    """
    create_audit = context.pop("create_audit", True)
    row_count = len(transformed_rows)
    snapshot = (
        legacy_snapshot
        if isinstance(legacy_snapshot, list)
        else (transformed_rows[:500] if create_audit else [])
    )

    # Phase C: run pre-migration validation and attach categorized issues
    validation_issues = run_pre_migration_validation(
        migration_type, transformed_rows, school=school
    )

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
                "SUCCESS"
                if scorecard["error_count"] == 0
                else "PARTIAL"
                if scorecard["created"] or scorecard["updated"]
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
    scorecard["validation_issues"] = validation_issues

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
                "validation_issues": validation_issues,
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


def run_migration_start(
    school, migration_type: str, row_count: int, user=None, legacy_snapshot=None
):
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
        MigrationRun.Status.SUCCESS
        if result.get("error_count", 0) == 0
        else MigrationRun.Status.PARTIAL
        if (result.get("created") or result.get("updated"))
        else MigrationRun.Status.FAILED
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
    # §0.1.5 exception queue: runs with errors need operator review
    run.refresh_from_db()
    ex = MigrationRun.ExceptionAck
    need_open = run.error_count > 0 or run.status in (
        MigrationRun.Status.PARTIAL,
        MigrationRun.Status.FAILED,
    )
    new_ex = ex.OPEN if need_open else ex.NA
    if run.exception_ack_status != new_ex:
        run.exception_ack_status = new_ex
        run.save(update_fields=["exception_ack_status"])
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
    total = (
        migration_run.created_count
        + migration_run.updated_count
        + migration_run.error_count
    )
    return {
        "source_rows": row_count,
        "total_processed": total,
        "match": total == row_count,
        "created": migration_run.created_count,
        "updated": migration_run.updated_count,
        "errors": migration_run.error_count,
    }
