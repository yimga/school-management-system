# Django Admin Canvas Contract Audit

Generated: 2026-07-10

## Scope

Audited the deploy-state admin shell on `origin/main` for the approved canvas-first work:

- Operator `/admin/` Django surfaces.
- Tenant `/admin/` Django backend surfaces.
- Change lists, change forms, specialized admin pages, preview-heavy admin pages, SiteSettings, report/document preview patterns, and tenant/operator shell separation markers.

## Approved Contract

- Django admin pages use the available shell canvas by default.
- Tenant and operator admin both receive the same layout contract without sharing operator-only links or chrome.
- Change lists render native tables, not stacked narrow rows.
- Change forms use a full-width workbench with a side rail only when there is enough space.
- Submit actions must not overlap fields or pin over active work.
- Inline previews must not squeeze into unusable columns; preview frames and preview-heavy panels get full-width/fallback sizing.

## Findings

- `templates/admin/base_site.html` already loaded `rmc-admin-workspace-10x.css` and `rmc-admin-changelist-live.css` for both host types, but the admin surface rules were still distributed across older bundles.
- Several older rules were scoped to `body.admin-manager-shell`, which meant tenant admin relied on later partial parity rules instead of one final contract.
- Late inline preview/theme styles existed after earlier admin CSS, so a contract loaded only in the main `<head>` block could still be overwritten by later template output.
- The previous changelist fix closed the most visible stacked-row failure, but there was no single audit gate proving the whole Django admin contract remained loaded and host-neutral.

## Closed Gaps

- Added `static/css/rmc-admin-django-canvas-contract.css` as the final shared Django admin surface contract.
- Loaded the contract in `templates/admin/base_site.html` for both operator and tenant admin, including a terminal repeat after late preview/theme inline styles.
- Added `scripts/audit_django_admin_canvas_contract.py` to check:
  - contract stylesheet is loaded;
  - it is not lazy `media=print` CSS;
  - it loads after late preview/theme styles;
  - change form and change list markers exist;
  - CSS targets both `admin-manager-shell` and `admin-premium-shell`;
  - table, form, submit, and preview sizing rules exist.
- Wired the new audit into `scripts/verify_admin_manager_shell_aggressive.py`.
- Bumped the service worker cache version to force deployed browsers off stale admin CSS.
- Added deploy hardening on 2026-07-10 after production still showed stale/narrow surfaces:
  - cache-busted the final contract stylesheet URL;
  - added contract-marker selectors that do not depend solely on body class timing;
  - kept the same operator/tenant scope through Django admin shell markers.
- Added specificity hardening after production screenshots still showed the add/change
  form capped by older `--rmc-backoffice-form-max` rules from `admin-cp-parity.css`.
  The final contract now targets the exact manager and tenant form-frame selectors
  with higher specificity and a new cache-busted URL.

## Validation

- `python scripts/audit_django_admin_canvas_contract.py`: pass.
- `SECRET_KEY=local-validation-only python manage.py check`: pass.
- `python -m py_compile scripts/audit_django_admin_canvas_contract.py scripts/verify_admin_manager_shell_aggressive.py`: pass.
- `git diff --check`: pass.

## Remaining Local Proof Blocker

`scripts/verify_admin_changelist_render_contract.py` is blocked in this clean worktree by local database schema drift outside this CSS/template change:

- missing `siteconfig_dashboarduserpreference.role_dashboard_packs`;
- missing `compliance_auditlog.during_impersonation`.

The static/template audit now covers the approved platform-wide and tenant-wide Django admin canvas contract. A full browser/render sweep should be rerun in an environment with current migrations applied.
