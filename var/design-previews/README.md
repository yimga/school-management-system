# Tenant design previews

Static HTML mocks for validating layout direction **before** or **alongside** live deploys. Open in a browser via `file://` — no Django server required.

## Start here

| File | Purpose |
| --- | --- |
| **[tenant-role-dashboards-hub.html](tenant-role-dashboards-hub.html)** | **Canonical index** — admin, parent, teacher, wizard routes, live URLs, post-deploy checklist |
| **[full-width-sweep-browsable.html](full-width-sweep-browsable.html)** | **Role sweep** — horizontal tabs (Admin · Teacher · Parent · Student), inline full dark portal shell per role |
| **[archive/](archive/)** | Superseded previews (e.g. Threshold expanded lab) kept for reference |

## Role dashboards

| File | Live template / route |
| --- | --- |
| [tenant-admin-workspace-preview.html](tenant-admin-workspace-preview.html) | `accounts/backend_dashboard.html` · `/authentication/backend/` |
| [setup-command-surface-browsable.html](setup-command-surface-browsable.html) | `partials/tenant/setup_command_surface.html` (onboarding block only) |
| [tenant-parent-dashboard-preview.html](tenant-parent-dashboard-preview.html) | `parent/dashboard.html` · `/portal/parent/` |
| [tenant-teacher-dashboard-preview.html](tenant-teacher-dashboard-preview.html) | `teacher/dashboard.html` · `/portal/teacher/` |

## Wizards & fixes

| File | Notes |
| --- | --- |
| [mfa-wizard-review-void-fix-preview.html](mfa-wizard-review-void-fix-preview.html) | Before/after for completed MFA review void (SW v4.04.42) |
| [wizard-step-assist-preview.html](wizard-step-assist-preview.html) | Wizard copilot assist rail |
| [tenant-admin-workspace-audit-2026-06-18.html](tenant-admin-workspace-audit-2026-06-18.html) | Live audit: cache vs layout bugs |

## Other previews

- `page-explain-*.html` — page explain strip / next-action merge options
- `copilot-rail-diagnosis-browsable.html` — copilot rail layout
- `workflow-flight-deck-preview.html` — workflow flight deck operator UI

## Live wiring (code)

| Surface | CSS / JS | Shell |
| --- | --- | --- |
| Admin dashboard | `rmc-setup-surface.css`, `rmc-tenant-dashboard-v2.css`, `rmc-tenant-canvas-100x.css` | `portal_base.html` via `backend_base.html` |
| Parent / teacher | `rmc-tenant-dashboard-v2.css`, `rmc-tenant-workspace-canvas.css` | `portal_base.html` |
| Tenant wizards | `rmc-wizard.css` | `setup_studio/tenant_wizard.html` |
| Service worker | `static/js/service-worker.js` | `config/urls.py` manifest version lockstep |

After deploy: unregister service worker once, hard refresh. Confirm `caches.keys()` includes the version in `verify_service_worker_version.py`.
