# Migration Cloud — operator runbook

**Purpose:** Migration Cloud is the platform migration operating system. This runbook documents wizard steps, progress, rollback, and per-tenant history for operators.

## Canonical models

- **MigrationProfile** (`apps.automation.models.MigrationProfile`): Platform registry of migration connector profiles (CSV/XLSX, students/finance/grades, generic SIS). Seeded by `seed_migration_profiles`.
- **MigrationRun** (`apps.automation.models.MigrationRun`): Per-tenant migration execution; links to MigrationProfile; supports rollback via `trigger_rollback`.

## Entry points

- **Control plane:** `/super/migration/` — super_migration_cloud template. Use for running and monitoring migrations.
- **API/automation:** Use MigrationProfile and MigrationRun in code for wizard steps, progress, and history.

## Wizard steps (target flow)

1. **Select profile** — Choose MigrationProfile (e.g. CSV students, XLSX grades).
2. **Map fields** — Map source columns/fields to canonical schema.
3. **Run** — Start MigrationRun for the tenant; show progress.
4. **Verify** — Confirm row counts and validation results.
5. **Rollback** (optional) — Call `trigger_rollback` on MigrationRun when supported.

## Progress and history

- **Progress:** MigrationRun stores status; expose via API or super dashboard for live progress.
- **History:** List MigrationRun per tenant (filter by school_id) for audit and retry.

## Rollback

- When MigrationRun supports rollback, use `trigger_rollback` and re-run verification.
- Document which profile types support rollback in MigrationProfile or docs.

## References

- `docs/CANONICAL_OBJECTS_MAPPING.md` (Migration Profile, Migration Run)
- `apps/automation/models.py` (MigrationProfile, MigrationRun)
- `templates/schools/super_migration_cloud.html`
