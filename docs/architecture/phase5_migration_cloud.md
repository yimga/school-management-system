# Phase 5: Migration Cloud

Scope and implementation status for the migration cloud (checklist 11.1, 12.5).

## Goals

- **Import studio**: One place to upload, map, preview, and run data migrations (students, grades, etc.).
- **Field mapping engine**: CSV columns → target fields with validation and required-field checks.
- **Dry-run validator**: Validate and preview impact without committing (would create X, update Y, errors Z).
- **Migration scorecard**: Per-run audit (row count, created, updated, errors, duration, status).
- **Parity checker**: Compare source row count to actual created + updated + errors.
- **Rollback** (later): Optional snapshot/rollback for last run.
- **Legacy data cleaner** (later): Migrate legacy integrations, etc.; backfill_service_integrations is one example.
- **Read-only legacy view** (later): View legacy data in read-only mode.

## Current State (Pre–Phase 5)

- **Import studio**: `accounts.migration_wizard` — upload CSV → map columns → preview first 15 rows → run. Backed by API entity student bulk-commit and `evals.importers.apply_import` (grades).
- **Field mapping**: Session-stored mapping; wizard POST sends mapping JSON; rows transformed before calling backend.
- **No dry-run**: Run commits immediately; no “validate only” path.
- **No migration audit**: No persistent record of runs; only flash messages.
- **No parity checker**: No comparison of source vs outcome.

## Implemented in Phase 5

1. **MigrationRun model** (`apps.automation.models.MigrationRun`): Persists each run (school, migration_type, dry_run, row_count, created_count, updated_count, error_count, status, started_at, completed_at, triggered_by, execution_summary). Used for audit and scorecard.
2. **Dry-run path**: “Validate only (dry run)” in the wizard runs validation and simulation (no DB writes), returns a scorecard (would create, would update, errors), and optionally creates a MigrationRun with `dry_run=True`.
3. **Scorecard**: After run (and in dry-run result), show row_count, created, updated, errors, status, duration. Stored in MigrationRun.execution_summary and displayed in the wizard.
4. **Parity checker**: Helper `compute_parity(migration_run)` comparing `row_count` to `created_count + updated_count + error_count`; surface in scorecard or admin.
5. **Wizard wiring**: Wizard creates MigrationRun on run; supports dry_run action; displays scorecard in success/error message or inline.

## Deferred

- **Rollback**: Store enough info to revert last run; UI to trigger rollback (later).
- **Legacy data cleaner**: Broader tooling for legacy schema migration; keep using backfill commands where needed.
- **Read-only legacy view**: Separate feature for viewing legacy data read-only.

## Touchpoints

- `apps/accounts/views.migration_wizard`: Uses migration service for dry_run and run; creates MigrationRun.
- `apps/automation/models.MigrationRun`: New model; migration added.
- `apps/evals/importers`: `dry_run_grade_import()` for grades dry-run; `apply_import()` already used for real run.
- Student path: Dry-run validates required fields and reports row-level errors; “would create” from valid row count (no DB write).
