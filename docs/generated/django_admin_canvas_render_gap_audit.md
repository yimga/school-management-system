# Django Admin Canvas Render Gap Audit

Generated: 2026-07-11

## Result

Status: PARTIAL_RENDER_PROOF_BLOCKED_BY_LOCAL_DB

The prior rollout was too weak: it proved that a CSS file and broad markers existed, but it did not force the approved design preview into real Django admin structure. This pass adds explicit structural DOM hooks to the shared admin templates and updates the audit so marker-only implementation can no longer pass.

## Root Cause Found

- The approved browser proof `var/design-previews/django-admin-canvas-intelligent-revamp.html` existed in the older working checkout as an untracked file.
- The pushed code had a large CSS overlay, but the real Django templates did not expose enough workbench structure for the approved command-surface layout to reliably render.
- The static asset cache key still referenced the older `20260710-intelligent-canvas-sweep` version.

## Fixes Applied

- Added structural change-form workspace markers:
  - `data-rmc-django-workspace="change-form"`
  - `data-rmc-django-command-band="change-form"`
  - `rmc-django-form-panel`
  - `data-rmc-django-form-body="1"`
- Added structural changelist workspace markers:
  - `data-rmc-django-workspace="change-list"`
  - `data-rmc-django-command-band="change-list"`
  - `data-rmc-django-table-panel="1"`
- Added structural side rail and action row markers:
  - `data-rmc-django-side-panel="1"`
  - `data-rmc-django-actions="static"`
- Added a final structural CSS closure layer in `static/css/rmc-admin-django-canvas-contract.css`.
- Bumped the loaded stylesheet cache key to `20260711-structural-canvas`.
- Added `docs/prompts/django-admin-canvas-render-gap-closure.md`.
- Added `scripts/verify_django_admin_canvas_templates_compile.py`.
- Strengthened `scripts/audit_django_admin_canvas_contract.py` to require structural hooks.

## Validation

Passed:

- `python scripts/audit_django_admin_canvas_contract.py`
- `SECRET_KEY=local-validation-only python manage.py check`
- `SECRET_KEY=local-validation-only python manage.py makemigrations --check --dry-run`
- `python -m compileall -q apps config scripts`
- `SECRET_KEY=local-validation-only python scripts/verify_django_admin_canvas_templates_compile.py`
- `git diff --check`

Blocked by local SQLite schema drift:

- `SECRET_KEY=local-validation-only python scripts/verify_admin_changelist_render_contract.py`
  - missing `siteconfig_dashboarduserpreference.role_dashboard_packs`
  - missing `compliance_auditlog.during_impersonation`
- `SECRET_KEY=local-validation-only python scripts/verify_dom_performance_budgets.py`
  - missing `schools_school.tenant_hash`

## Deployment Verification Required

After deploy, verify production source and screenshots:

- HTML source includes `rmc-admin-django-canvas-contract.css?v=20260711-structural-canvas`.
- Operator `/admin/auth/user/` has `data-rmc-django-workspace="change-list"`.
- Operator `/admin/auth/user/add/` has `data-rmc-django-workspace="change-form"`.
- Tenant `/admin/` equivalents have the same markers but tenant scope.
- Wide desktop screenshots show command bands, full-width tables/forms, static save row, and no cramped inline preview.
