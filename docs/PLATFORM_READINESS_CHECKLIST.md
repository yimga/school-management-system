# Platform readiness checklist (pre-merge / pre-deploy)

Use this checklist to ensure the platform is properly linked, error-free, and ready for merge and deployment. All items should pass before release.

---

## 1. Entry points and routing

- [ ] **Manager host** (`manager.runmycampus.com` or configured host): unauthenticated → login; authenticated with control-plane access → `/super/` (dashboard).
- [ ] **Control plane nav** builds from `control_plane_nav.py`; every item uses a URL name that resolves under `config.manager_urls` (e.g. `super:dashboard`, `super:config_hub`, `platform_incidents_console`, `siteconfig:console_domains_hub`, `apicenter:dashboard`). No 404 from sidebar links.
- [ ] **Configuration Engine** (nav and header button/dropdown) points to `super:config_hub` (`/super/config/`), not Django admin index.
- [ ] **Sidebar fallback** (when `CONTROL_PLANE_NAV` is empty) still links "Configuration Engine" to `super:config_hub`.
- [ ] **Admin nav bridge** (when in Django admin on manager host): "Configuration Engine" button and dropdown → `super:config_hub`; "Backoffice" → `admin:index`.
- [ ] **backend_base.html** and **quick_actions.html**: On manager host (`request.public_host_kind == 'manager'`), "Configuration Engine" / "View All Admin" link → `super:config_hub`; on tenant → `admin:index`.

## 2. Buttons and shortcuts

- [ ] **Header:** "Configuration Engine" button and dropdown item resolve to `/super/config/`.
- [ ] **Keyboard shortcuts:** `?` opens shortcuts help; `g` then `d/c/t/o/a/b/s/m/u/h/p` navigate to Dashboard, Command Center, Studio OS, Orchestration, Configuration Engine, Billing, Support, Migration, Usage, School Health, Pulse. Shortcut URLs match manager URLconf (e.g. `/studio/` for Studio OS, `/super/` for dashboard).
- [ ] **Search (Ctrl+K):** `/api/search/` returns JSON; no 500 when portal or other optional apps are missing.

## 3. Error handling (no 500 from optional context)

- [ ] **403 (permission denied):** On manager host, uses `errors/403_control_plane.html`; shows "Back to Manager", "Control Plane", or "Tenant Mission Control" (staff hitting admin without superuser sees Control Plane button).
- [ ] **404 / 500:** On manager host, use control-plane error templates; "Back to Manager" link present.
- [ ] **Context processors:** Optional URL reverse (e.g. `portal:document_library_manage`, `portal:home`) wrapped in try/except; `NoReverseMatch` in `OPTIONAL_CONTEXT_ERRORS` so missing portal namespace does not 500.
- [ ] **Document Library (admin sidebar):** Shown only when `PORTAL_DOCUMENT_LIBRARY_MANAGE_URL` is set in context (guard in `templates/admin/app_list.html`).

## 4. Config hub and super pages

- [ ] **Config hub** (`/super/config/`): Renders with cards for Site settings, Regions & grading, Plans, Feature toggles, AI/model registry, Configuration Control Center, Advanced backoffice; operational links (Schools list, Incidents list, Pulse, Billing accounts, Billing, Migration runs, Migration). All links resolve or show "Coming soon" / hidden when URL is None.
- [ ] **Schools list** (`/super/schools/`): Pagination, filters (q, is_active, country_code); breadcrumb to Control Plane; "Open in backoffice" when admin changelist exists.
- [ ] **Site settings, Regions, Grading, Plans, Feature toggles:** List (and edit where applicable) pages render; breadcrumbs include dashboard and config hub; backoffice links when available.
- [ ] **Incidents list, Billing accounts list, Migration runs list:** Optional Phase 8 list views render; links to Pulse/Billing/Migration and admin when applicable.

## 5. UI/UX and layout

- [ ] **Frames:** No horizontal spill; `control_plane_skeleton.html` and `manager-control-plane.css` use `overflow-x: clip`, `max-width: 100%`, `min-width: 0` on body, main, and container-fluid so content stays in frame.
- [ ] **Labels and structure:** Pages use clear headings, breadcrumbs, and aria where appropriate; tables use `table-responsive` where needed.
- [ ] **Control plane shell:** Skip link "Skip to main content" present; main content has `id="cp-main-content"`.

## 6. Seeding and bootstrap

- [ ] **First-time deploy:** Run `python manage.py bootstrap_runmycampus_platform` or `python manage.py bootstrap_platform_catalog --all` after migrations so platform catalogs (regions, plans, feature toggles, marketplace, registries, etc.) are populated. See [BOOTSTRAP_PLATFORM_CATALOG.md](BOOTSTRAP_PLATFORM_CATALOG.md).
- [ ] **Default school/tenant:** Seed or migration provides at least one default school/tenant where required (e.g. Gilead default per migration `0012_seed_default_gilead_school`).

## 7. Tests and automation

- [ ] **URL verification:** `apps.schools.tests.test_super_config_migration_urls` (config hub, site settings, regions, grading, plans, feature toggles, schools list, incidents/billing/migration runs, etc.) pass.
- [ ] **Control plane boundary:** `test_control_plane_boundary` (no parent-tenant path in super URLs, etc.) pass.
- [ ] **Error pages:** `test_phase10_control_plane_verification` (403/404/500 use control-plane template and expected copy) pass.
- [ ] **Super dashboard:** `test_phase_execution_plan.SuperCommandCenterTests` (dashboard contains "Control Plane", "Operator queues", "School registry", "Control modules"; command center, metadata catalog, tenant studio routes render) pass.

---

## Quick verification commands

```bash
# Django checks
python manage.py check

# Config migration URL tests (13 tests)
python manage.py test apps.schools.tests.test_super_config_migration_urls --noinput -v 1

# Phase 10 error pages + phase execution plan (super dashboard)
python manage.py test apps.schools.tests.test_phase10_control_plane_verification apps.schools.tests.test_phase_execution_plan --noinput -v 1

# Full bootstrap (first-time or clean env)
python manage.py bootstrap_runmycampus_platform
```

---

**Last updated:** Second full pass. Configuration Engine → `super:config_hub` everywhere on manager: control_plane_base, sidebar (and fallback), admin_nav_bridge (manager branch + dropdown), backend_base, quick_actions. Admin nav bridge adds "Backoffice" button for `admin:index`. Config list views: regions/grading try both `global_registries_*` and `siteconfig_*` admin URL names for backoffice link.
