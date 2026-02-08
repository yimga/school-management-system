# Master Execution Checklist (Phases 0-16)

This checklist is the execution contract for the approved plan:
- Theme catalog size: 24 ThemePacks + 12 Presets.
- Document output standard: DOCX + ODT.
- Release strategy: phased deploys, one commit per phase, tests pass before the next phase.

## Phase 0 - Baseline Snapshot and Rollback Point
- Goals:
  - Capture current code/UI baseline before new edits.
  - Create rollback artifacts for DB and UI config.
- File edits:
  - `docs/execution/MASTER_PHASE_EXECUTION_CHECKLIST.md` (this file)
  - `scripts/release/create_baseline_snapshot.ps1`
- Verification:
  - `python manage.py check`

## Phase 1 - Dev/Live Parity Audit and Permanent Sync
- Goals:
  - Make Render and local environments reproducible and aligned.
  - Standardize export/import of SiteSettings and ThemePack config.
- File edits:
  - `scripts/release/sync_ui_config.ps1`
  - `docs/execution/DEV_LIVE_PARITY_RUNBOOK.md`
  - `render.yaml` (if needed for predeploy consistency)
- Verification:
  - `python manage.py check`
  - `python manage.py export_ui_config <tmp.json>`
  - `python manage.py import_ui_config <tmp.json>`

## Phase 2 - Canonical Theme Surface (Single Source)
- Goals:
  - Keep `/siteconfig/theme-colors/` as canonical Theme editor.
  - Remove duplicate edit entry points in SiteSettings paths.
- File edits:
  - `apps/siteconfig/views.py`
  - `apps/siteconfig/urls.py`
  - `templates/admin/siteconfig/sitesettings/change_form.html`
  - `apps/siteconfig/tests/test_theme_studio.py`
- Verification:
  - `python manage.py test apps.siteconfig.tests.test_theme_studio`

## Phase 3 - Compact Theme UX (Shorter and Cleaner)
- Goals:
  - Reduce vertical page length when catalog is expanded.
  - Keep controls readable and professional.
- File edits:
  - `templates/siteconfig/theme_colors.html`
  - `static/css/admin-color-preview.css`
- Verification:
  - `python manage.py test apps.siteconfig.tests.test_theme_studio`

## Phase 4 - Active-State Visibility and Draft Status
- Goals:
  - Always show active site pack, active admin pack, and selected palette source.
  - Show draft-vs-saved state.
- File edits:
  - `templates/siteconfig/theme_colors.html`
  - `templates/admin/components/admin_dashboard_palette_selector.html`
  - `static/js/theme-studio-apply.js`
  - `apps/siteconfig/tests/test_theme_studio.py`
- Verification:
  - `python manage.py test apps.siteconfig.tests.test_theme_studio`

## Phase 5 - Preset + ThemePack Integration (No Redundancy)
- Goals:
  - Keep presets and map them into Theme & Experience fields.
  - Ensure ThemePack selection and presets do not conflict.
- File edits:
  - `templates/admin/components/color_palette_studio.html`
  - `static/js/color-palette-studio.js`
  - `static/js/theme-studio-apply.js`
  - `static/js/color-harmony-engine.js`
- Verification:
  - `python manage.py test apps.siteconfig.tests.test_theme_studio`

## Phase 6 - Larger Live Preview (Responsive Modes)
- Goals:
  - Increase preview fidelity and readability.
  - Add desktop/tablet/mobile preview modes.
- File edits:
  - `templates/admin/components/theme_preview_section.html`
  - `static/css/site-settings-preview.css`
  - `static/js/site-settings-preview.js`
  - `templates/siteconfig/theme_colors.html`
- Verification:
  - `python manage.py test apps.siteconfig.tests.test_preview`

## Phase 7 - Curated Catalog (24 Packs) + 12 Presets
- Goals:
  - Curate non-redundant ThemePacks with distinct design families.
  - Reduce preset clutter to 12 high-value presets.
- File edits:
  - `apps/siteconfig/management/commands/seed_admin_dashboard_palettes.py`
  - `apps/siteconfig/theme_palette_groups.py`
  - `static/js/color-harmony-engine.js`
  - `apps/siteconfig/tests/test_theme_palette_groups.py`
- Verification:
  - `python manage.py test apps.siteconfig.tests.test_theme_palette_groups`
  - `python manage.py seed_admin_dashboard_palettes --reset`

## Phase 8 - Theme Governance (Safety and Publish Discipline)
- Goals:
  - Enforce contrast and controlled publish behavior.
  - Expose recent theme change metadata in the UI.
- File edits:
  - `apps/siteconfig/forms.py`
  - `apps/siteconfig/views.py`
  - `templates/siteconfig/theme_colors.html`
  - `apps/siteconfig/tests/test_theme_studio.py`
- Verification:
  - `python manage.py test apps.siteconfig.tests.test_theme_studio`

## Phase 9 - Evals/Reports Integration Hardening
- Goals:
  - Validate report generation uses approved/published gating correctly.
  - Tighten edge-case handling around term publish and approvals.
- File edits:
  - `apps/reports/services.py`
  - `apps/reports/views.py`
  - `apps/evals/views.py` (if needed)
  - tests under `apps/reports/tests/` and/or `apps/evals/tests/`
- Verification:
  - targeted report/eval test modules touched in this phase.

## Phase 10 - Report Card Builder UX (Compact + Seamless)
- Goals:
  - Reduce long scrolling via compact sections.
  - Improve assignment and style workflows.
- File edits:
  - `templates/siteconfig/reportcard_builder.html`
  - `templates/siteconfig/partials/mock_reportcard_preview.html`
  - `apps/siteconfig/views.py`
- Verification:
  - targeted tests for builder view and template rendering.

## Phase 11 - Cameroon Reporting Flow Features
- Goals:
  - Support bilingual labels and sequence-oriented reporting cues.
  - Strengthen rank/position display consistency.
- File edits:
  - `apps/reports/services.py`
  - `templates/siteconfig/reportcard_style_preview.html`
  - `templates/reports/*` (only where required)
  - tests under `apps/reports/tests/`
- Verification:
  - targeted report rendering and logic tests.

## Phase 12 - KB Conversion Completion (DOCX + ODT)
- Goals:
  - Deliver production-ready conversion from Markdown to DOCX and ODT.
  - Keep style/template support for professional formatting.
- File edits:
  - `apps/portal/management/commands/generate_kb_odt.py` (extended)
  - `apps/portal/document_conversion.py`
  - `apps/portal/document_generation.py`
  - `docs/KB_LIBREOFFICE_ODT_INTEGRATION.md`
  - `docs/execution/KB_CONVERSION_RUNBOOK.md`
- Verification:
  - command-level tests and dry-run validation.

## Phase 13 - Security and Performance Gap Pass
- Goals:
  - Reduce risk from weak inputs and expensive queries.
  - Capture actionable findings and fixes.
- File edits:
  - targeted code paths discovered during audit
  - `docs/execution/SECURITY_PERFORMANCE_NOTES.md`
- Verification:
  - targeted tests for changed paths + `python manage.py check`.

## Phase 14 - Admin UI Reliability (Links and Responsiveness)
- Goals:
  - Ensure sidebar parent/child links and buttons resolve reliably.
  - Keep `/admin` and `/backend` responsibilities separated.
- File edits:
  - admin templates/routes touched by link and button audits
  - `docs/execution/ADMIN_UI_SMOKE_CHECKLIST.md`
- Verification:
  - URL smoke tests and targeted UI tests.

## Phase 15 - Final Test and Deploy Gate
- Goals:
  - Enforce final test gate before merge.
  - Verify migrations/static/deploy commands.
- File edits:
  - `docs/execution/FINAL_TEST_GATE.md`
  - optional test runner scripts under `scripts/release/`
- Verification:
  - final test suite selected for touched scope.

## Phase 16 - Release Hardening and Monitoring
- Goals:
  - Backfill legacy data safely and define rollback path.
  - Add post-deploy verification and monitoring checklist.
- File edits:
  - `docs/execution/RELEASE_HARDENING_CHECKLIST.md`
  - `docs/execution/POST_DEPLOY_MONITORING.md`
  - optional release scripts under `scripts/release/`
- Verification:
  - dry-run release checklist and parity checks.
