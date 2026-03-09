# Migration Cloud — operator runbook

**Purpose:** Migration Cloud is the platform migration operating system. This runbook documents wizard steps, progress, rollback, and per-tenant history for operators.

**Non-negotiable:** The full Migration Cloud Strategy and Implementation Plan (including all phases A–O and universal migration capabilities) is binding. Every item in that plan and in this runbook must be implemented; nothing is optional or indefinitely deferred. See the plan for phase order and DoD.

## Canonical models

- **MigrationProfile** (`apps.automation.models.MigrationProfile`): Platform registry of migration connector profiles (CSV/XLSX, students/finance/grades, generic SIS). Seeded by `seed_migration_profiles`.
- **MigrationRun** (`apps.automation.models.MigrationRun`): Per-tenant migration execution; links to MigrationProfile; supports rollback via `trigger_rollback`.

## Entry points

- **Control plane:** `/super/migration/` — super_migration_cloud template. Use for running and monitoring migrations.
- **API/automation:** Use MigrationProfile and MigrationRun in code for wizard steps, progress, and history.

## Wizard steps (target flow)

1. **Select system** — Choose source system (PowerSchool, Blackbaud, Veracross, Infinite Campus, Other).
2. **Select profile / Upload** — Choose MigrationProfile and upload CSV.
3. **Map fields** — Map source columns to canonical schema (schema hints pre-filled for competitor profiles; inferred for Other).
4. **Validate (dry run)** — Pre-migration validation runs with **categorized issues** (duplicates, missing required, invalid refs); scorecard and drill-down UI show details.
5. **Run** — Start MigrationRun for the tenant; show progress.
6. **Verify** — Confirm row counts and validation results.
7. **Rollback** (required) — Call `trigger_rollback` on MigrationRun when supported; UI must expose rollback per plan.

## Pre-migration validation (Phase C)

- **Categorized issues:** Dry run calls `run_pre_migration_validation`; issues are grouped as **duplicates**, **missing_required**, **invalid_refs**.
- **Drill-down:** Wizard scorecard shows an accordion per category with row numbers and messages.
- **Storage:** `validation_issues` is stored in MigrationRun `execution_summary` and passed in the wizard scorecard for display.

## Progress and history

- **Progress:** MigrationRun stores status; expose via API or super dashboard for live progress.
- **History:** List MigrationRun per tenant (filter by school_id) for audit and retry.

## Rollback

- When MigrationRun supports rollback, use `trigger_rollback` and re-run verification.
- Document which profile types support rollback in MigrationProfile or docs.

## References

- **Migration Cloud Strategy and Implementation Plan** (all phases A–O non-negotiable)
- `docs/CANONICAL_OBJECTS_MAPPING.md` (Migration Profile, Migration Run)
- `docs/architecture/phase5_migration_cloud.md`, `docs/architecture/phase8_migration_cloud_and_marketplaces.md`
- `apps/automation/models.py` (MigrationProfile, MigrationRun)
- `templates/schools/super_migration_cloud.html`
