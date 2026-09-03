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


# Phase 9: distinctive header tokens per SIS export (heuristic source detection).
_SOURCE_HEADER_SIGNATURES: dict[str, frozenset[str]] = {
    "powerschool": frozenset(
        {"dcid", "lastfirst", "schoolid", "enroll_status"}
    ),
    "infinite_campus": frozenset(
        {"studentstateidentifier", "calid", "state_student_number"}
    ),
    "veracross": frozenset({"person_pk", "household_fk", "person_id"}),
    "blackbaud": frozenset({"constituent_id", "legacy_id", "system_id"}),
}


def detect_source_system_from_headers(headers: list[str] | None) -> dict[str, Any]:
    """
    Infer likely SIS / export source from CSV column names (non-destructive hint).
    Returns: suggested_system, score (0–1), matched_signals, candidates (ranked).
    """
    if not headers:
        return {
            "suggested_system": "other",
            "score": 0.0,
            "matched_signals": [],
            "candidates": [],
        }
    norms = [_normalize_for_match(h) for h in headers if h and str(h).strip()]
    norm_set = set(norms)

    def _token_hits(sig: frozenset[str]) -> list[str]:
        matched: list[str] = []
        for raw in sig:
            tn = _normalize_for_match(raw)
            if tn in norm_set:
                matched.append(raw)
                continue
            for n in norms:
                if len(tn) >= 5 and tn in n:
                    matched.append(raw)
                    break
                if len(n) >= 5 and n in tn:
                    matched.append(raw)
                    break
        return sorted(set(matched))

    scores: dict[str, tuple[float, list[str]]] = {}
    for system, sig in _SOURCE_HEADER_SIGNATURES.items():
        hits = _token_hits(sig)
        frac = len(hits) / max(len(sig), 1)
        scores[system] = (frac, hits)

    ranked = sorted(scores.items(), key=lambda x: (-x[1][0], x[0]))
    best_system, (best_frac, best_hits) = ranked[0]
    second_frac = ranked[1][1][0] if len(ranked) > 1 else 0.0

    if best_frac < 0.34:
        suggested = "other"
        conf = round(best_frac, 3)
    elif best_frac - second_frac < 0.01 and second_frac >= 0.34:
        suggested = "other"
        conf = round(best_frac * 0.75, 3)
    else:
        suggested = best_system
        conf = min(1.0, round(best_frac + 0.1 * len(best_hits), 3))

    return {
        "suggested_system": suggested,
        "score": conf,
        "matched_signals": best_hits,
        "candidates": [
            {"system": name, "score": round(sc, 3), "matched": hits}
            for name, (sc, hits) in ranked
            if sc > 0
        ][:4],
    }


def compute_migration_confidence(
    row_count: int,
    scorecard: dict[str, Any],
    validation_issues: dict[str, list[Any]],
) -> dict[str, Any]:
    """
    Phase 9: single scorecard band for operators (not a legal guarantee).
    Combines row-level errors with categorized validation issue counts.
    """
    if row_count <= 0:
        return {"band": "unknown", "score": 0.0, "hint": "No rows uploaded."}
    err = int(scorecard.get("error_count") or 0)
    vi_total = sum(len(validation_issues.get(cat, []) or []) for cat in VALIDATION_CATEGORIES)
    penalty = (err + vi_total) / float(row_count)
    score = max(0.0, min(1.0, 1.0 - penalty))
    if score >= 0.85 and err == 0 and vi_total == 0:
        band = "high"
        hint = "Dry run clean — review parity, then commit or export audit from run history."
    elif score >= 0.55:
        band = "medium"
        hint = "Some rows or validation issues need review before production import."
    else:
        band = "low"
        hint = "Fix validation issues or adjust mapping; avoid full commit until score improves."
    return {
        "band": band,
        "score": round(score, 3),
        "hint": hint,
        "error_rows": err,
        "validation_issue_rows": vi_total,
    }


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

        active_year, _ = get_active_year_and_term(school=school)
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
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
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

        active_year, _ = get_active_year_and_term(school=school)
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
    scorecard["confidence"] = compute_migration_confidence(
        row_count, scorecard, validation_issues
    )

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


# ---------------------------------------------------------------------------
# Real playbook import appliers (students + grades).
#
# ``automation.playbook_executor._run_one_step`` imports these two names inside a
# ``try/except ImportError`` so a deploy without them degrades to PARTIAL rather
# than crashing. For a LONG time they did not exist, so every real playbook
# student/grade step silently reported ``*_service_unavailable``. They are now
# real, routing through the SAME apply paths the interactive surfaces use:
#   * students -> apps.customersuccess.bulk_csv_student_import.apply_bulk_csv
#   * grades   -> apps.evals.importers.apply_grade_import_job
# The executor's guard stays as a defensive fallback for any deploy that ships an
# older migration_services.py.
# ---------------------------------------------------------------------------

# Canonical bulk-CSV columns the student importer recognises.
_STUDENT_CSV_HEADERS = (
    "external_id",
    "first_name",
    "last_name",
    "middle_name",
    "date_of_birth",
    "email",
    "grade_level",
    "guardian_email",
    "guardian_name",
    "guardian_phone",
)

# Playbook / SIS row aliases -> canonical column, matched on normalised keys
# (``_normalize_for_match`` lower-cases and collapses spaces/dashes to "_").
_STUDENT_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    # external_id is the per-student idempotency anchor. Prefer an explicit
    # external_id, then the school's own identifiers.
    "external_id": (
        "external_id",
        "student_code",
        "admission_number",
        "student_number",
        "student_id",
        "matricule",
    ),
    "first_name": ("first_name", "firstname", "fname", "given_name"),
    "last_name": ("last_name", "lastname", "lname", "surname", "family_name"),
    "middle_name": ("middle_name", "middlename"),
    "date_of_birth": ("date_of_birth", "dob", "birthdate", "birth_date"),
    "email": ("email", "email_address"),
    "grade_level": ("grade_level", "grade", "class", "class_level"),
    "guardian_email": ("guardian_email", "parent_email"),
    "guardian_name": ("guardian_name", "parent_name"),
    "guardian_phone": ("guardian_phone", "parent_phone"),
}

# Bound how much error detail we hand back to the executor's stored summary.
_IMPORT_RESULT_ERROR_CAP = 100  # magic-number-allow: import-error-report-cap


def _first_present_value(normalized_row: dict, aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        value = normalized_row.get(alias)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _student_rows_to_canonical_csv(rows: list[dict]) -> str:
    """Adapt playbook/SIS row-dicts to the canonical bulk-CSV the wizard parses.

    Round-tripping through the real CSV text means ``parse_and_validate_csv``
    applies exactly the same validation (external_id format, required
    first/last name, email shape, ISO date, in-batch duplicate detection) the
    onboarding wizard relies on — no second, drifting validator.
    """
    import csv as _csv
    import io as _io

    buffer = _io.StringIO()
    writer = _csv.DictWriter(buffer, fieldnames=list(_STUDENT_CSV_HEADERS))
    writer.writeheader()
    for row in rows:
        source = row if isinstance(row, dict) else {}
        normalized = {
            _normalize_for_match(k): v for k, v in source.items() if k
        }
        writer.writerow(
            {
                column: _first_present_value(normalized, aliases)
                for column, aliases in _STUDENT_FIELD_ALIASES.items()
            }
        )
    return buffer.getvalue()


def run_student_import(school, rows, user=None) -> dict[str, Any]:
    """Persist migration-playbook student rows via the bulk-CSV import kernel.

    Adapts row-dicts to the canonical columns, runs the wizard's own
    parse+validate, then applies via
    ``apps.customersuccess.bulk_csv_student_import.apply_bulk_csv``. That kernel
    is idempotent: it synthesises a tenant-scoped ``student_code``
    (``S<school_id>-<external_id>``) and skips rows whose code already exists, so
    re-running a playbook step never duplicates students. Validation is
    all-or-nothing (one bad row rejects the batch) — the returned ``errors`` name
    the exact rows so the operator can fix the sheet and re-run.

    Returns the executor's expected shape: ``created`` / ``updated`` /
    ``errors`` (list) plus ``skipped`` (idempotent re-run hits) for the audit
    summary. ``updated`` is always 0 — the kernel creates or skips, it does not
    mutate an existing student's fields.
    """
    from apps.customersuccess.bulk_csv_student_import import (
        apply_bulk_csv,
        parse_and_validate_csv,
    )

    rows = list(rows or [])
    if not school or not getattr(school, "pk", None):
        return {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": ["no_school_context"],
        }
    if not rows:
        return {"created": 0, "updated": 0, "skipped": 0, "errors": []}

    validated = parse_and_validate_csv(_student_rows_to_canonical_csv(rows))
    if not validated.is_valid:
        errors = [
            f"Row {e.lineno}: {e.field} — {e.reason}" for e in validated.errors
        ] + [
            f"duplicate identifier '{dup}' in the uploaded rows"
            for dup in validated.duplicate_external_ids
        ]
        return {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": errors[:_IMPORT_RESULT_ERROR_CAP],
        }

    applied = apply_bulk_csv(school_id=school.pk, validated=validated)
    errors = [
        f"{e.get('external_id', '?')}: {e.get('reason', '')}".strip()
        for e in applied.errors
    ]
    return {
        "created": applied.created,
        "updated": 0,
        "skipped": applied.skipped,
        "errors": errors[:_IMPORT_RESULT_ERROR_CAP],
    }


def run_grade_import(school, rows, user=None) -> dict[str, Any]:
    """Persist migration-playbook grade rows via the shared grade-apply service.

    Resolves the school's active academic year (falling back to its most recent)
    and that year's first term, then delegates to
    ``apps.evals.importers.apply_grade_import_job`` — the SAME service the
    teacher-facing upload view uses — so the playbook step records an auditable
    ``GradeImportJob`` and dedupes exactly like an interactive import
    (``update_or_create`` on ``academic_year, term, subject_assignment,
    student``). Year resolution is pinned to ``school`` so a playbook run can
    never write another tenant's grades.
    """
    from apps.academics.models import AcademicYear, Term
    from apps.evals.importers import apply_grade_import_job

    rows = list(rows or [])
    if not school or not getattr(school, "pk", None):
        return {"created": 0, "updated": 0, "errors": ["no_school_context"]}
    if not rows:
        return {"created": 0, "updated": 0, "errors": []}

    year = (
        AcademicYear.objects.filter(school=school, is_active=True)
        .order_by("-start_date")
        .first()
        or AcademicYear.objects.filter(school=school).order_by("-start_date").first()
    )
    if not year:
        return {"created": 0, "updated": 0, "errors": ["no_academic_year_for_school"]}
    # tenant-isolation-allow: term-scoped-via-school-resolved-academic-year
    term = (
        Term.objects.filter(academic_year=year).order_by("position", "id").first()
    )
    if not term:
        return {"created": 0, "updated": 0, "errors": ["no_term_for_academic_year"]}

    result = apply_grade_import_job(
        academic_year=year, term=term, csv_rows=rows, uploaded_by=user
    )
    errors = result.get("errors") or []
    return {
        "created": result.get("created", 0),
        "updated": result.get("updated", 0),
        "errors": errors[:_IMPORT_RESULT_ERROR_CAP],
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
