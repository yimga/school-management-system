# Phase 16 Post-Deploy Monitoring

Date: 2026-02-08

## First 15 Minutes
1. Validate service is up:
   - `/admin/login/`
   - `/authentication/backend/`
   - `/siteconfig/theme-colors/`
2. Confirm no startup migration errors in logs.
3. Confirm static assets are loading (admin sidebar/header CSS and JS present).

## First 2 Hours
1. Check auth and redirect flow:
   - login -> MFA/redirect behavior
   - admin header `Back to Backend` button
2. Verify admin quick-access links:
   - no 404/500 responses
3. Verify report flow:
   - report builder page loads
   - report publish term workflow still passes expected validations
4. Verify KB conversion command:
   - dry-run and one sample conversion (`odt`, `docx`)

## First 24 Hours
1. Watch error rates and repeated 5xx patterns.
2. Watch slow endpoints:
   - theme studio
   - report builder
   - admin dashboard
3. Validate no drift between environments:
   - compare `theme_pack_id` and `admin_theme_pack_id`
   - compare latest exported UI config snapshot hashes

## Trigger Thresholds
- Any sustained 5xx errors (>1% over 15 minutes): rollback candidate.
- Any broken admin quick link in production: hotfix same day.
- Any report publish regression: block rollout to wider users until fixed.

## Operator Command Set
- `python manage.py check`
- `python manage.py export_ui_config <path>`
- `python manage.py import_ui_config <path>`
- `powershell -ExecutionPolicy Bypass -File scripts/release/final_test_gate.ps1`
- `./scripts/release/final_test_gate.sh`
- `./scripts/release/release_hardening_dry_run.sh`
