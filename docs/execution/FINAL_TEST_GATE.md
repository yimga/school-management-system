# Phase 15 Final Test Gate

Date: 2026-02-08

## Purpose
Provide one deterministic gate before merge/deploy so UI, theme, KB conversion, and report publishing changes are validated together.

## Gate Command
From project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release/final_test_gate.ps1
```

## What It Enforces
1. `python manage.py check`
2. `python manage.py makemigrations --check --dry-run`
3. Targeted regression suite:
   - `apps.portal.tests.test_generate_kb_odt_command`
   - `apps.siteconfig.tests.test_theme_studio`
   - `apps.siteconfig.tests.test_preview`
   - `apps.siteconfig.tests.test_reportcard_builder`
   - `apps.siteconfig.tests.test_redirect_safety`
   - `apps.siteconfig.tests.test_admin_ui_smoke`
   - `apps.requests.tests.test_views_security`
   - `apps.accounts.tests.test_mfa_redirect_safety`
   - `apps.reports.tests.test_publish_term`

## Pass Criteria
- All commands exit with code `0`.
- No migration drift.
- No regressions in the listed modules.

## Merge Rule
- Do not merge unless this gate has passed on the exact commit to be merged.
