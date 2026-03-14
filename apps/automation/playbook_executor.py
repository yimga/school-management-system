"""
Migration playbook executor: run multiple migration profiles in sequence.
Each step creates a MigrationRun (migration_type = profile.slug); when steps_payload
is provided, each step is executed via the existing migration services.
"""
from __future__ import annotations

from typing import Any, Optional

from apps.automation.models import MigrationPlaybook, MigrationProfile, MigrationRun


def execute_playbook(
    playbook: MigrationPlaybook,
    school,
    user=None,
    dry_run: bool = True,
    steps_payload: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Run playbook profiles in sequence. Each step creates a MigrationRun.
    steps_payload: optional list of payloads (one per profile), each {"rows": [...], "mapping": {...}}.
    Returns {"runs": [MigrationRun, ...], "status": "SUCCESS"|"PARTIAL"|"FAILED"}.
    """
    profiles = playbook.get_profiles()
    if not profiles:
        return {"runs": [], "status": "FAILED", "message": "Playbook has no valid profiles."}

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

    return {"runs": runs, "status": status}


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
            run = MigrationRun.objects.filter(
                school=school,
                migration_type=profile.domain,
                dry_run=True,
                triggered_by=user,
            ).order_by("-started_at").first()
            if run:
                run.execution_summary = {**(run.execution_summary or {}), "playbook_slug": playbook.slug, "step_index": step_index, "profile_slug": profile.slug}
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
            execution_summary={"playbook_slug": playbook.slug, "step_index": step_index, "profile_slug": profile.slug},
        )
        return run

    # Real run
    run = run_migration_start(school, profile.domain, len(rows), user=user, legacy_snapshot=payload.get("legacy_snapshot"))
    run.execution_summary = {**(run.execution_summary or {}), "playbook_slug": playbook.slug, "step_index": step_index, "profile_slug": profile.slug}
    run.save(update_fields=["execution_summary"])

    if profile.domain == "students" and rows and school:
        from apps.accounts.migration_services import run_student_import
        result = run_student_import(school, rows, user=user)
        run.mark_completed(
            status=MigrationRun.Status.SUCCESS if not result.get("errors") else MigrationRun.Status.PARTIAL,
            created_count=result.get("created", 0),
            updated_count=result.get("updated", 0),
            error_count=len(result.get("errors", [])),
            summary={**run.execution_summary, "result": result},
        )
    elif profile.domain == "grades" and rows and school:
        from apps.accounts.migration_services import run_grade_import
        result = run_grade_import(school, rows, user=user)
        run.mark_completed(
            status=MigrationRun.Status.SUCCESS if not result.get("errors") else MigrationRun.Status.PARTIAL,
            created_count=result.get("created", 0),
            updated_count=result.get("updated", 0),
            error_count=len(result.get("errors", [])),
            summary={**run.execution_summary, "result": result},
        )
    else:
        run.mark_completed(status=MigrationRun.Status.SUCCESS, summary=run.execution_summary)

    return run
