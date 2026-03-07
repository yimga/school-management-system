# Phase 14 Admin UI Smoke Checklist

Date: 2026-02-08

## Goal
Ensure `/admin` navigation (sidebar + header actions) is reliable, and keep `/admin` and `/backend` concerns clearly separated.

## Automated Checks
- `apps/siteconfig/tests/test_admin_ui_smoke.py`
  - Verifies quick-access links used in admin sidebar are resolvable (not 404/500).
  - Verifies sidebar child links rendered from app/model groups are resolvable (not 404/500).
  - Verifies admin header bridge shows `Back to Backend`.
  - Verifies settings managers (non-superuser) still receive configuration quick-access links.

## Manual Smoke Steps
1. Login as superuser and open `/admin/`.
2. Confirm header shows:
   - `Portal Home`
   - `Back to Backend`
3. Click each Quick access item once:
   - Dashboard
   - Site settings
   - Region Config
   - Integrations
   - Feature Control
   - Theme & Experience
   - Report Library
   - Knowledge Base
   - Document Library
   - Backend Console
4. Confirm no item returns a 404 page.
5. Confirm `/admin` keeps configuration links and `/backend` remains operations-focused.
6. Login as staff with `settings.manage` (not superuser):
   - Confirm Site settings quick link is visible from `/admin/`.

## Notes
- Quick-access visibility now keys off `CAN_MANAGE_SETTINGS`, not only `is_superuser`.
- Pinned sidebar item context now executes correctly (previous unreachable code path fixed).
