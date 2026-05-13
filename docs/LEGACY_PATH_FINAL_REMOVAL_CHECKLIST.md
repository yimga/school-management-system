# Legacy Path Final Removal Checklist

## Purpose
This checklist captures the exact cleanup steps for removing the remaining redirect-only legacy siteconfig paths once product confirms final deletion.

## Current active legacy surfaces
- Redirect route definitions remain in:
  - `config/urls.py`
  - `config/tenant_urls.py`
  - `config/manager_urls.py`
- Redirect helper views exist for:
  - `admin/siteconfig/customizer/`
  - `/siteconfig/customizer/`
  - `/siteconfig/workflow-hub/`
  - `/siteconfig/report-library/`
  - `/siteconfig/reports/`
- Tests and verification scripts still assert legacy redirect behavior:
  - `apps/studio_os/tests/test_phase_05_legacy_redirects.py`
  - `scripts/verify_cursor_phase5_studio_os.py`
  - `scripts/dev/validate_urls.py`
- Studio OS still exposes legacy link helpers and CTAs:
  - `apps/studio_os/deep_links.py`
  - `templates/studio_os/partials/automation_mode_canvas.html`
  - `templates/studio_os/partials/shell_main_content.html`
  - `templates/studio_os/shell.html`
- Navigation/URL validation still includes legacy `siteconfig/customizer/` paths:
  - `apps/schools/control_plane_nav.py`

## Final removal checklist
1. Confirm product sign-off for removing redirect-only legacy paths and closing the `/siteconfig/*` bookmark support window.
2. Remove old redirect routes and helper views from:
   - `config/urls.py`
   - `config/tenant_urls.py`
   - `config/manager_urls.py`
3. Update or remove redirect-focused tests and verification scripts:
   - `apps/studio_os/tests/test_phase_05_legacy_redirects.py`
   - `scripts/verify_cursor_phase5_studio_os.py`
   - `scripts/dev/validate_urls.py`
   - any other Phase 5 legacy audit helpers.
4. Remove legacy shell link helpers from `apps/studio_os/deep_links.py` if they are no longer required.
5. Remove or replace Studio OS UI elements that still render legacy CTAs:
   - `templates/studio_os/partials/automation_mode_canvas.html`
   - `templates/studio_os/partials/shell_main_content.html`
   - `templates/studio_os/shell.html`
6. Review navigation and route whitelists for legacy paths:
   - `apps/schools/control_plane_nav.py`
   - other siteconfig nav / URL validation helpers.
7. Update documentation to reflect final removal:
   - `docs/LEGACY_PATH_INVENTORY.md`
   - `docs/SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md`
   - `docs/BACKLOG_AND_DEFERRED_CLOSURE.md`
   - `docs/docs_truth_ledger.md`
   - any phase audit docs that track the redirect-only status.
8. Validate final state with:
   - `manage.py check`
   - relevant unit tests
   - updated Phase 5/Phase H verification
   - site-level smoke checks for removed URLs (expect 404/410 or documented behavior).

## Note
The current scan found the remaining active references are all redirect-support code and verification/test coverage. There are no obvious live old `siteconfig.views.customizer`, `siteconfig.views.report_library`, or `siteconfig.views_dashboard_config.workflow_hub` route definitions remaining in the current active codebase.
