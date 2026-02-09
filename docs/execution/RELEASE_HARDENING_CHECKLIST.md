# Phase 16 Release Hardening Checklist

Date: 2026-02-08

## Objective
Minimize release risk by creating rollback points, validating migration safety, and preserving theme/UI parity.

## Pre-Deploy Hardening
1. Confirm final gate passes:
   - `powershell -ExecutionPolicy Bypass -File scripts/release/final_test_gate.ps1`
   - `./scripts/release/final_test_gate.sh`
   - Standalone parity check:
   - `powershell -ExecutionPolicy Bypass -File scripts/release/check_ui_parity.ps1 -ConfigPath fixtures/ui_config.json`
   - `./scripts/release/check_ui_parity.sh fixtures/ui_config.json`
   - Standalone KB export verification:
   - `powershell -ExecutionPolicy Bypass -File scripts/release/verify_kb_exports.ps1 -Formats odt,docx`
   - `./scripts/release/verify_kb_exports.sh odt,docx`
2. Run release dry-run:
   - `powershell -ExecutionPolicy Bypass -File scripts/release/release_hardening_dry_run.ps1`
   - `./scripts/release/release_hardening_dry_run.sh`
3. Save deploy metadata:
   - `git rev-parse HEAD`
   - deployment timestamp
4. Ensure backup artifacts exist:
   - DB snapshot (platform-level backup or dump)
   - UI config snapshot (`export_ui_config` output from dry-run)

## Deploy Sequence
1. Pull target commit.
2. Run migrations exactly once.
3. Run collectstatic.
4. Restart app workers.

## Rollback Plan
1. If app is unhealthy after deploy:
   - Roll back to previous working commit.
2. Restore DB backup only if schema/data corruption is confirmed.
3. Re-import known-good UI config snapshot:
   - `python manage.py import_ui_config <snapshot.json>`
4. Re-run smoke checks after rollback.

## Parity Guard
- Keep `theme_pack_id` and `admin_theme_pack_id` tracked per environment.
- Do not manually patch production UI values without exporting/importing config through managed commands.
