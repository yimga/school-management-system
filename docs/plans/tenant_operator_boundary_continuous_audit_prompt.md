# Tenant / Operator Boundary Continuous Audit Prompt

Use this prompt when auditing or improving RunMyCampus tenant/operator separation.

## Prompt

Audit the repository before changing code. Do not assume route ownership from labels or screenshots. Build an evidence matrix from the actual URLconfs, middleware, decorators, templates, admin-site registries, and browser/Django Client renders.

Required checks:

- Enumerate platform/operator surfaces: manager host `/super/`, manager `/admin/`, manager `/configuration/`, platform-only registries, fleet billing, fleet support, marketplace governance, global incidents, global observability, and platform infrastructure settings.
- Enumerate tenant surfaces: tenant `/admin/`, tenant `/configuration/`, `/authentication/backend/`, Studio work modes, siteconfig tenant configuration pages, dashboard previews, feature controls, report card builder, launch/onboarding, forms/admissions, communications, billing tenant self-service, theme/customizer, workflow center, and live preview routes.
- For each route, record owner as `OPERATOR_ONLY`, `TENANT_ONLY`, `TENANT_WITH_OPERATOR_IMPERSONATION`, `PUBLIC`, or `SHARED_READONLY`.
- For each route, prove the active URLconf, middleware gates, login/MFA/security-review gates, feature-plan gates, required role/permission, template marker, and forbidden markers.
- Verify tenant `/admin/` uses the tenant admin site, tenant admin login, tenant-scoped model registry, and tenant wording. It must not show platform manager labels, platform-only registries, or fleet controls.
- Verify manager `/admin/` uses the platform admin site and does not expose tenant-only namespaces except deliberate support/impersonation links.
- Verify tenant `/configuration/` renders the school configuration center and not the platform configuration center.
- Verify tenant users cannot reach `/super/`, manager configuration, fleet registry, platform billing controls, marketplace governance, global support queues, or platform observability without signed operator impersonation.
- Verify operators do not land in tenant backend/config surfaces on manager host unless a selected school and explicit support/impersonation flow is active.
- Verify live preview works for every configuration surface that changes visible tenant experience. Each surface must provide inline preview plus fallback actions: retry, modal, popout, and open new tab. If iframe preview is blocked, prove a readable fallback and direct open path.
- Verify no tenant-facing work mode has giant blank space, sticky overlays covering content, duplicate sidebars/search boxes, or controls hidden behind footer/tool/help elements.
- Verify every changed page uses the available screen width intelligently without overlapping left/right sidebars or fixed tool rails.

Required proof commands:

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python -m compileall -q apps config static\js`
- A Django Client smoke matrix for tenant host and manager host covering `/admin/`, `/configuration/`, `/authentication/backend/`, `/siteconfig/dashboard-configuration/`, `/siteconfig/feature-control/?embed=1`, `/siteconfig/reports/builder/`, `/studio/`, `/studio/experience/`, `/studio/automation/`, `/studio/output/`, `/studio/launch/`, and `/studio/control/`.
- Static marker scan for platform-only markers on tenant pages and tenant-only markers on manager pages.

Output required:

- A route ownership matrix with pass/fail evidence.
- A gap list with exact file, route, role, host, and observed status.
- Code fixes for every confirmed gap.
- Updated audit document under `docs/generated/`.
- Commit and push only after validation passes or after clearly documenting any local-environment-only blocker.
