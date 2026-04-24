"""
Migration playbook executor: run multiple migration profiles in sequence.
Each step creates a MigrationRun (migration_type = profile.slug); when steps_payload
is provided, each step is executed via the existing migration services.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from apps.automation.models import (
    AutomationExecutionLog,
    MigrationPlaybook,
    MigrationProfile,
    MigrationRun,
)
from apps.automation.playbook_override_reason import normalize_playbook_override_reason


def _normalize_tenant_schema_name(raw) -> str:
    """
    Normalize the active tenant schema name for audit logs.
    Must be safe for storage and filtering: string-only, stripped, max 63 chars.
    """
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if not s:
        return ""
    return s[:63]


def _record_playbook_execution_log(
    *,
    playbook: MigrationPlaybook,
    school,
    user,
    dry_run: bool,
    runs: list[MigrationRun],
    status: str,
    message: str | None = None,
    extra_execution_summary: dict[str, Any] | None = None,
) -> AutomationExecutionLog:
    """One AutomationExecutionLog per execute_playbook call (audit; no automatic step retries)."""
    from django.db import connection

    if status == "SUCCESS":
        exec_status = AutomationExecutionLog.Status.SUCCESS
    elif status == "PARTIAL":
        exec_status = AutomationExecutionLog.Status.PARTIAL
    else:
        exec_status = AutomationExecutionLog.Status.FAILED
    failed_steps = sum(1 for r in runs if r.status == MigrationRun.Status.FAILED)
    partial_steps = sum(1 for r in runs if r.status == MigrationRun.Status.PARTIAL)
    summary = {
        "playbook_id": playbook.pk,
        "playbook_slug": playbook.slug,
        "school_id": str(school.pk) if school is not None and getattr(school, "pk", None) else None,
        "dry_run": dry_run,
        "final_status": status,
        "message": message,
        "failed_steps": failed_steps,
        "partial_steps": partial_steps,
        "steps": [
            {
                "run_id": r.pk,
                "migration_type": r.migration_type,
                "status": r.status,
                "profile_slug": (r.execution_summary or {}).get("profile_slug"),
                "step_index": (r.execution_summary or {}).get("step_index"),
                "quarantine_count": (
                    r.quarantine_records.count()
                    if getattr(r, "pk", None)
                    else 0
                ),
            }
            for r in runs
        ],
    }
    if extra_execution_summary:
        summary = {**summary, **extra_execution_summary}
    current_schema = getattr(connection, "schema_name", None)
    log = AutomationExecutionLog.objects.create(
        task_name="automation.playbook.execute",
        school=school if school is not None else None,
        schema_name=_normalize_tenant_schema_name(current_schema),
        execution_type=(
            AutomationExecutionLog.ExecutionType.DRY_RUN
            if dry_run
            else AutomationExecutionLog.ExecutionType.MANUAL
        ),
        triggered_by=user,
        status=AutomationExecutionLog.Status.PENDING,
    )
    log.mark_completed(
        status=exec_status,
        records_processed=len(runs),
        records_failed=failed_steps,
        error_message=(message or "")[:2000],
        summary=summary,
    )
    return log


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _estimate_preflight_confidence(
    playbook: MigrationPlaybook,
    profiles: list[MigrationProfile],
    *,
    dry_run: bool,
    steps_payload: Optional[list[dict[str, Any]]],
) -> tuple[int, dict[str, Any]]:
    """
    Estimate migration confidence from payload quality before execution.

    Signals:
    - required_field_coverage
    - duplicate_risk
    - rollback_readiness
    - quarantine_risk
    """
    payloads = steps_payload or []
    coverage_values: list[float] = []
    duplicate_risk_values: list[float] = []
    quarantine_risk_values: list[float] = []
    total_rows = 0
    has_payload_inputs = False

    for idx, profile in enumerate(profiles):
        payload = payloads[idx] if idx < len(payloads) and isinstance(payloads[idx], dict) else {}
        rows = payload.get("rows") or []
        mapping = payload.get("mapping") or {}
        if rows or mapping:
            has_payload_inputs = True
        required = profile.config.get("required_columns", []) if isinstance(profile.config, dict) else []
        required_list = [str(x) for x in required if str(x).strip()]
        if not required_list:
            if profile.domain == "students":
                required_list = ["first_name", "last_name", "admission_number"]
            elif profile.domain == "grades":
                required_list = ["student_identifier", "subject_code", "score"]
        mapped_targets = {
            str(k).strip() for k, v in (mapping.items() if isinstance(mapping, dict) else [])
            if str(k).strip() and str(v).strip()
        }
        row_keys: set[str] = set()
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    row_keys.update(str(k).strip() for k in row.keys() if str(k).strip())
        if required_list:
            covered = len(
                [
                    r
                    for r in required_list
                    if r in mapped_targets or r in row_keys
                ]
            )
            coverage_values.append(covered / len(required_list))
        else:
            coverage_values.append(1.0)

        # Duplicate risk from common identity keys in uploaded rows.
        if isinstance(rows, list) and rows:
            total_rows += len(rows)
            keys = ("admission_number", "student_number", "email", "id", "username")
            seen: set[str] = set()
            dup = 0
            missing_required = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for req in required_list:
                    if req and not row.get(req):
                        missing_required += 1
                for key in keys:
                    val = row.get(key)
                    if val in (None, ""):
                        continue
                    token = f"{key}:{str(val).strip().lower()}"
                    if token in seen:
                        dup += 1
                    else:
                        seen.add(token)
                    break
            duplicate_risk_values.append(min(1.0, dup / max(1, len(rows))))
            denom = max(1, len(rows) * max(1, len(required_list)))
            quarantine_risk_values.append(min(1.0, missing_required / denom))
        else:
            duplicate_risk_values.append(0.0)
            quarantine_risk_values.append(0.0)

    required_field_coverage = sum(coverage_values) / max(1, len(coverage_values))
    if not has_payload_inputs:
        return 100, {
            "playbook_slug": playbook.slug,
            "required_field_coverage": 1.0,
            "duplicate_risk": 0.0,
            "rollback_readiness": 1.0 if dry_run else 0.85,
            "quarantine_risk": 0.0,
            "rows_evaluated": 0,
            "input_mode": "empty_payload",
        }

    duplicate_risk = sum(duplicate_risk_values) / max(1, len(duplicate_risk_values))
    quarantine_risk = sum(quarantine_risk_values) / max(1, len(quarantine_risk_values))
    rollback_readiness = 1.0 if dry_run else (0.85 if total_rows > 0 else 0.7)

    # Weighted confidence score (0-100). Higher duplicate/quarantine risk lowers confidence.
    confidence = (
        required_field_coverage * 0.4
        + (1.0 - duplicate_risk) * 0.25
        + rollback_readiness * 0.2
        + (1.0 - quarantine_risk) * 0.15
    ) * 100.0
    score = int(round(max(0.0, min(100.0, confidence))))
    signals = {
        "playbook_slug": playbook.slug,
        "required_field_coverage": round(required_field_coverage, 4),
        "duplicate_risk": round(duplicate_risk, 4),
        "rollback_readiness": round(rollback_readiness, 4),
        "quarantine_risk": round(quarantine_risk, 4),
        "rows_evaluated": total_rows,
    }
    return score, signals


def execute_playbook(
    playbook: MigrationPlaybook,
    school,
    user=None,
    dry_run: bool = True,
    steps_payload: Optional[list[dict[str, Any]]] = None,
    *,
    override_reason: str | None = None,
) -> dict[str, Any]:
    """
    Run playbook profiles in sequence. Each step creates a MigrationRun.
    steps_payload: optional list of payloads (one per profile), each {"rows": [...], "mapping": {...}}.
    Returns {"runs": [MigrationRun, ...], "status": "SUCCESS"|"PARTIAL"|"FAILED"}.
    """
    profiles = playbook.get_profiles()
    if not profiles:
        msg = "Playbook has no valid profiles."
        _record_playbook_execution_log(
            playbook=playbook,
            school=school,
            user=user,
            dry_run=dry_run,
            runs=[],
            status="FAILED",
            message=msg,
        )
        response_preflight = {
            "preflight_confidence_score": 0,
            "preflight_min_score": int(
                _safe_float(os.getenv("MIGRATION_PLAYBOOK_MIN_CONFIDENCE_SCORE", "70"), 70)
            ),
            "preflight_signals": {"playbook_slug": playbook.slug, "input_mode": "no_profiles"},
            "override_applied": False,
            "override_reason": "",
        }
        return {
            "runs": [],
            "status": "FAILED",
            "message": msg,
            **response_preflight,
        }

    preflight_score, preflight_signals = _estimate_preflight_confidence(
        playbook, profiles, dry_run=dry_run, steps_payload=steps_payload
    )
    min_score = int(_safe_float(os.getenv("MIGRATION_PLAYBOOK_MIN_CONFIDENCE_SCORE", "70"), 70))
    min_score = max(0, min(100, min_score))
    normalized_override_reason = normalize_playbook_override_reason(override_reason)
    response_preflight = {
        "preflight_confidence_score": preflight_score,
        "preflight_min_score": min_score,
        "preflight_signals": preflight_signals,
        "override_applied": bool(normalized_override_reason),
        "override_reason": normalized_override_reason,
    }
    if preflight_score < min_score and not normalized_override_reason:
        msg = (
            "Playbook blocked: preflight confidence below threshold. "
            "Provide override_reason to proceed."
        )
        _record_playbook_execution_log(
            playbook=playbook,
            school=school,
            user=user,
            dry_run=dry_run,
            runs=[],
            status="FAILED",
            message=msg,
            extra_execution_summary={
                **response_preflight,
                "override_applied": False,
                "override_reason": "",
            },
        )
        return {
            "runs": [],
            "status": "FAILED",
            "message": msg,
            **response_preflight,
        }

    runs = []
    status = "SUCCESS"
    for i, profile in enumerate(profiles):
        payload = (steps_payload or [{}])[i] if steps_payload else {}
        run = _run_one_step(playbook, profile, i, school, user, dry_run, payload)
        runs.append(run)
        if run.status == MigrationRun.Status.FAILED:
            status = "FAILED"
            break
        if run.status == MigrationRun.Status.PARTIAL:
            status = "PARTIAL"

    _record_playbook_execution_log(
        playbook=playbook,
        school=school,
        user=user,
        dry_run=dry_run,
        runs=runs,
        status=status,
        message=None,
        extra_execution_summary=response_preflight,
    )
    return {"runs": runs, "status": status, **response_preflight}


def _run_one_step(
    playbook: MigrationPlaybook,
    profile: MigrationProfile,
    step_index: int,
    school,
    user,
    dry_run: bool,
    payload: dict,
) -> MigrationRun:
    """Create and optionally execute one step (one MigrationRun) for a profile."""
    from apps.accounts.migration_services import run_dry_run, run_migration_start

    rows = payload.get("rows") or []
    mapping = payload.get("mapping") or {}
    # migration_type for MigrationRun is profile.domain (students, grades, etc.)

    if dry_run:
        if rows or mapping:
            run_dry_run(
                school,
                profile.domain,
                rows,
                user=user,
                legacy_snapshot=payload.get("legacy_snapshot"),
            )
            # MigrationRun already created inside run_dry_run with migration_type=profile.domain
            # We want migration_type=profile.slug for playbook steps
            run = (
                MigrationRun.objects.filter(
                    school=school,
                    migration_type=profile.domain,
                    dry_run=True,
                    triggered_by=user,
                )
                .order_by("-started_at")
                .first()
            )
            if run:
                run.execution_summary = {
                    **(run.execution_summary or {}),
                    "playbook_slug": playbook.slug,
                    "step_index": step_index,
                    "profile_slug": profile.slug,
                }
                run.save(update_fields=["execution_summary"])
                return run
        # No payload: create a placeholder dry run
        run = MigrationRun.objects.create(
            school=school,
            migration_type=profile.domain,
            dry_run=True,
            row_count=0,
            status=MigrationRun.Status.SUCCESS,
            triggered_by=user,
            execution_summary={
                "playbook_slug": playbook.slug,
                "step_index": step_index,
                "profile_slug": profile.slug,
            },
        )
        return run

    # Real run
    run = run_migration_start(
        school,
        profile.domain,
        len(rows),
        user=user,
        legacy_snapshot=payload.get("legacy_snapshot"),
    )
    run.execution_summary = {
        **(run.execution_summary or {}),
        "playbook_slug": playbook.slug,
        "step_index": step_index,
        "profile_slug": profile.slug,
    }
    run.save(update_fields=["execution_summary"])

    if profile.domain == "students" and rows and school:
        from apps.accounts.migration_services import run_student_import

        result = run_student_import(school, rows, user=user)
        run.mark_completed(
            status=MigrationRun.Status.SUCCESS
            if not result.get("errors")
            else MigrationRun.Status.PARTIAL,
            created_count=result.get("created", 0),
            updated_count=result.get("updated", 0),
            error_count=len(result.get("errors", [])),
            summary={**run.execution_summary, "result": result},
        )
    elif profile.domain == "grades" and rows and school:
        from apps.accounts.migration_services import run_grade_import

        result = run_grade_import(school, rows, user=user)
        run.mark_completed(
            status=MigrationRun.Status.SUCCESS
            if not result.get("errors")
            else MigrationRun.Status.PARTIAL,
            created_count=result.get("created", 0),
            updated_count=result.get("updated", 0),
            error_count=len(result.get("errors", [])),
            summary={**run.execution_summary, "result": result},
        )
    else:
        run.mark_completed(
            status=MigrationRun.Status.SUCCESS, summary=run.execution_summary
        )

    return run
