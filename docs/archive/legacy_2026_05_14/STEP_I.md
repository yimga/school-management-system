## Step I — Documentation, migrations, and verification

1. **Documentation / audit templates**
   - Added `STEP_I.md` to capture the current rollout status, highlight where dashboards, portals, and theme packs live, and describe the remaining verification steps so future reviewers can quickly understand the completed work.
   - The existing `phase6-checklist.md` now references this new reference guide for Step I follow-up.

2. **Migrations / helpers**
   - No new schema changes were required because all models (admissions, RBAC, finance, portals) already cover the requested features from earlier steps.
   - If extra data migrations become necessary, the `apps/siteconfig/views.py` customizer/report builder views are now protected by the `settings.manage` permission, so migrating data should happen via vetted admin flows.

3. **Verification**
   - Run `python manage.py migrate` to ensure no pending migrations.
   - Run `python manage.py test` (11 tests) to confirm coverage.
   - Run `python manage.py collectstatic --noinput` before deployments (renders statics once; duplicates already logged).
   - Manually spot-check `/admin/`, `/portal/parent/`, `/portal/teacher/`, `/authentication/login/`, `/siteconfig/preferences/`, and `/accounts/backend-dashboard/` after deploying to ensure the dual dashboards behave per the agreed UX.

4. **Notes**
   - Finance reminders and attendance dashboards now surface relevant widgets on both parent and teacher portals; the helper functions in `apps/portal/services.py` govern widget data for `parent_dashboard_widget_data` and `portal_stats`.
   - The customizer is no longer a standalone portal page—admins open Site Settings to manage theme packs/portals and users adjust personal dashboards via Preferences (toggle visibility for the “custom” widget row).
