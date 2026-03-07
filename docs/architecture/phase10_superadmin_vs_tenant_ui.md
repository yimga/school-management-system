# Phase 10 — Superadmin vs Tenant UI (Section 8)

Design/system split between superadmin and tenant UI: same codebase, distinct variants/shells. Section 8 checklist verification.

---

## Control plane shell and manager-only experience (implemented)

On **manager.runmycampus.com** the superadmin has a dedicated experience; no tenant UX is shown.

| Component | Implementation |
|-----------|----------------|
| **Base shell** | `control_plane_skeleton.html`: minimal HTML, platform favicon, Bootstrap, design-tokens, theme-visibility-guard, manager-control-plane.css, navy/gold :root. No tenant/SITE. |
| **Layout** | `control_plane_base.html`: extends skeleton. Header: “RunMyCampus Manager” (link to super:dashboard), platform logo, header search, Configuration Engine link, user dropdown (Profile, Preferences, Configuration Engine, Logout). Sidebar column + main column; blocks: `control_plane_sidebar`, `breadcrumbs`, `breadcrumb_actions`, `cp_content`. |
| **Sidebar** | `partials/control_plane_sidebar.html`: Dashboard, Command Center, Provision tenant, Billing, Support, Marketplace (Governance, Blueprints, App catalog), Customer Success, Migration, Usage, Pulse, Tenant Health, Incidents, Configuration Engine. All super: or top-level URLs. |
| **Manager login** | `auth/manager_login.html`: “RunMyCampus Manager” / “Control plane sign-in”; single card (username, password). No role selector, no tenant links. “Back to public site” → runmycampus.com. Login view branches on `request.public_host_kind == "manager"` to use this template. |
| **Branding / context** | Control plane uses platform favicon/logo only (no SITE). Context processor sets `CONTROL_PLANE_SHELL` when `public_host_kind == "manager"` and path starts with `/super/`. |
| **Header search** | Search input in header wired to manager search API `GET /api/search/?q=...`; debounced fetch; dropdown results (title, description, link). |
| **Mobile** | Navbar toggler on small screens opens offcanvas `#cpSidebarOffcanvas` with same sidebar nav. |
| **Error pages** | On manager host, 403/404/500 use `errors/403_control_plane.html`, `errors/404_control_plane.html`, `errors/500_control_plane.html` (extend control_plane_skeleton; navy/gold; no tenant name; “Back to Manager” → super:dashboard). Branch in `config/urls.py` permission_denied, page_not_found, server_error when `request.public_host_kind == "manager"`. |

**Touchpoints:** `templates/control_plane_skeleton.html`, `templates/control_plane_base.html`, `templates/partials/control_plane_sidebar.html`, `templates/auth/manager_login.html`, `apps/accounts/views.py` (login_view), `apps/siteconfig/context_processors.py` (CONTROL_PLANE_SHELL), `config/urls.py` (error handlers), `config/manager_urls.py` (admin/, super/, api/search/, ops/incidents/).

---

## Manager vs tenant: complete separation (verified)

Manager (manager.runmycampus.com) and tenant (school subdomain / custom domain) are **fully separate**; no shared shell, no tenant UX on manager, no super UX on tenant.

| Layer | Manager (superadmin) | Tenant |
|-------|----------------------|--------|
| **Host** | `manager.<base_domain>` → `public_host_kind(host) == "manager"` | Subdomain or custom domain → tenant resolution |
| **URLConf** | `config.manager_urls` (set by UrlConfSwitcherMiddleware) | `config.tenant_urls` |
| **Routes** | `/`, `/super/*`, `/admin/`, `/api/search/`, `/ops/incidents/`, etc.; `/portal/`, `/finance/`, `/evals/`, etc. are **redirects** to super dashboard/billing, not real tenant app routes | `/portal/*`, `/finance/*`, `/evals/*`, `/backend/`, etc.; **no** `/super/` route |
| **Base template** | Control plane: `control_plane_skeleton.html` → `control_plane_base.html` | Tenant: `portal_base.html` → `backend_base.html` for backend |
| **Super templates** | All super views use `control_plane_base` and `cp_content` / `cp_title` (including `super_control_health.html`) | N/A — super views are not mounted on tenant urlconf |
| **Login** | `auth/manager_login.html` (platform navy/gold, “Control plane sign-in”, no role selector; chosen when `request.public_host_kind == "manager"`) | `auth/login.html` (school-branded, role selector when applicable) |
| **Post-login** | `accounts:redirect` → `super:dashboard` when on manager host (checked first in redirect_view) | `accounts:redirect` → tenant backend/portal by role and preference |
| **Errors** | 403/404/500 use `errors/*_control_plane.html` (control_plane_skeleton, “Back to Manager”) when `request.public_host_kind == "manager"` | 403/404/500 use `errors/403.html`, `errors/404.html`, `errors/500.html` (tenant/base branding) |
| **Context** | No SITE/school in control plane header/sidebar; CONTROL_PLANE_SHELL set for /super/ on manager | Tenant context (school, theme, sidebar) from middleware and context processors |

**Code references:** `apps/schools/host_routing.py` (`public_host_kind`), `apps/schools/middleware.py` (UrlConfSwitcherMiddleware, ReservedPublicHostAccessMiddleware), `config/manager_urls.py`, `config/tenant_urls.py`, `apps/accounts/views.py` (login_view template branch, redirect_view manager branch), `config/urls.py` (error handler template branch).

---

## 8.1 — Superadmin feels like: command center, observability, ecosystem manager, deployment cockpit, policy control plane

| Aspect | Implementation |
|--------|----------------|
| Command center | **super_command_center** (`/super/command-center/`): single entry for ops; links to dashboard, schools, marketplace, runbooks. Template: `schools/super_command_center.html`; class `control-plane-shell`. |
| Observability | Super dashboard (super_dashboard_v2) and customer success super_dashboard; health, alerts, tenant metrics. |
| Ecosystem manager | Marketplace governance console, blueprint marketplace, app catalog (super:marketplace/*). |
| Deployment / policy control | Control plane runbooks (control_plane_runbooks.md); super URLs for approve school, create school, sync repair; policy/blueprint applied via manager. |
| Shell | Manager host → `config.manager_urls`; super views use `require_super_access`; templates use `control-plane-shell`; `static/css/manager-control-plane.css` (`.control-plane-shell`). |

**Touchpoints:** `apps/schools/super_views.py` (super_dashboard_v2, super_command_center_v2), `apps/schools/super_urls.py`, `templates/schools/super_command_center.html`, `templates/schools/super_dashboard.html`, `templates/marketplace/governance_console.html`, `static/css/manager-control-plane.css`.

---

## 8.2 — Tenant UI feels like: school operating system, localized workspace, role-based productivity app

| Aspect | Implementation |
|--------|----------------|
| School OS | Tenant host → `config.tenant_urls`; backend dashboard (`/backend/`), portal, academics, evals, finance, reports; single “school” context. |
| Localized | Policy/blueprint: terminology, default_language, region, RTL; context processor `global_env`, `tenant_ctx`. |
| Role-based | `dashboard_resolver.for_role(school, role)`; TenantLayoutAssignment per role; sidebar from `portal_sidebar_items` (role-aware); RBAC. |
| Shell | `backend_base.html` extends `portal_base.html`; `body_extra_class`: `backend-shell`; tenant theme from School/SiteSettings (primary_color, accent_color, ThemePack). |

**Touchpoints:** `config/tenant_urls.py`, `templates/backend_base.html`, `templates/portal_base.html`, `apps/siteconfig/portal_sidebar_items.py`, `apps/siteconfig/dashboard_resolver.py`, policy resolver.

---

## 8.3 — Same codebase; design systems distinct variants, different shells

| Requirement | Implementation |
|-------------|----------------|
| Same codebase | One Django project; shared apps (siteconfig, policies, schools, etc.); no separate “super app” repo. |
| Distinct variants | **Shells:** Public (public_urls), Manager (manager_urls + super_urls), Tenant (tenant_urls). Each has its own base/layout. |
| Design systems | Superadmin: `control-plane-shell`, manager-control-plane.css, dark/default control styling. Tenant: `backend-shell`, portal_base, backend-dark-theme.css / backend-light-theme.css, school theme variables (--school-primary, --school-accent). Public: marketing templates. |

**Reference:** phase2_control_tenant_shells.md, phase9_domain_and_routing.md (7.4 separation).

---

## 8.4 — Superadmin: dark, high-density, operations-grade; Tenant: school-branded, role-centric, warm, local

| Audience | Implementation |
|----------|----------------|
| Superadmin | Dark (and optional light) themes; `backend-dark-theme.css` used on backend; control-plane-shell is operations-grade; high-density via layout and manager-control-plane.css. Super views are manager host only. |
| Tenant | School-branded: School.logo_url, primary_color, accent_color; ThemePack; policy branding. Role-centric: dashboard and sidebar by role. Warm/local: terminology and locale from policy; no control-plane chrome. |

**Touchpoints:** `templates/backend_base.html` (RESOLVED_BACKEND_CONSOLE_THEME, theme_root_variables), `static/css/backend-dark-theme.css`, `static/css/manager-control-plane.css`, School/siteconfig branding.

---

## 8.5 — Public: premium SaaS, product storytelling, demos; Teacher: fast, task-oriented; Parent/student: mobile-first, readable

| Audience | Implementation |
|----------|----------------|
| Public | Public urlconf: marketing, signup, demos, pricing, “why switch”, trust center, app marketplace page; premium SaaS positioning. |
| Teacher | Tenant backend: dashboard_for_role(teacher), quick actions, task-oriented widgets; evals, attendance, lesson plans. |
| Parent/student | Parent portal, student portal; mobile-friendly templates; readable typography; role-based dashboards. |

**Touchpoints:** `config/public_urls.py`, marketing_views; tenant backend dashboard and portal; parent/student templates.

---

## 8.6 — High-end admin experience and platform-wide premium styling (implemented)

| Area | Implementation |
|------|----------------|
| **Admin (Configuration Engine) login** | Same high-end feel as /super: dark background (#0B0E14), hero strip, gold accent (#d4af37). Template: `auth/admin_login.html`; copy: “Configuration Engine sign-in”, “superuser account”; “Back to public site”. No tenant wording. `config.admin.RunMyCampusAdminSite.login_template` = `auth/admin_login.html`. |
| **Admin: no tenant in UI** | Unfold `dashboard_callback` does not inject school/tenant branding when path is `/admin/` (platform primary/accent only). Context processor overrides admin colors on manager to gold. Admin index subtitle and header actions on manager: superadmin-only copy and links (Control plane, Command center, Billing). |
| **Platform-wide premium feel** | `static/css/platform-high-end.css`: premium tokens (radius, shadows), sidebar polish (portal, control plane, admin), card/chart/dashboard elevation, tables, buttons, alerts. Loaded from: `portal_base`, `control_plane_skeleton`, `admin/base_site`, `base.html` — so every page (tenant, super, admin, auth, marketing, errors) gets consistent high-end styling. |
| **Shared login styles** | `static/css/manager-login.css`: shared dark/gold login layout for manager and admin login. Design tokens: `--dashboard-card-radius` and shadow updated for premium elevation (light/dark). |

**Touchpoints:** `templates/auth/admin_login.html`, `config/admin.py`, `apps/siteconfig/unfold_dashboard.py`, `apps/siteconfig/context_processors.py`, `templates/admin/index.html`, `templates/admin/base_site.html`, `templates/admin/extra_user_links.html`, `static/css/platform-high-end.css`, `static/css/manager-login.css`, `static/css/design-tokens.css`. **Tests:** `apps.siteconfig.tests.test_admin_high_end` — admin login template, no-tenant copy, unfold callback no tenant branding. Run: `python manage.py test apps.siteconfig.tests.test_admin_high_end`.

---

## Checklist summary

| Id | Status | Notes |
|----|--------|--------|
| 8.1 | Done | Command center, observability, ecosystem (marketplace), policy control; control-plane-shell. |
| 8.2 | Done | Tenant urlconf, backend_base, role-based dashboard/sidebar, localized via policy. |
| 8.3 | Done | One codebase; public/manager/tenant urlconfs and distinct shells. |
| 8.4 | Done | Superadmin dark/ops; tenant school-branded, role-centric. |
| 8.5 | Done | Public premium/demos; teacher task-oriented; parent/student mobile-first. |

**Reference:** phase2_control_tenant_shells.md, phase9_domain_and_routing.md, section_28_data_architecture_and_provisioning.md (28.2 brand vs site).

---

## Verification checklist (control plane shell and manager login)

Use this to verify the manager-only experience is complete and tenant UX does not leak on manager.runmycampus.com.

| # | Check | How to verify |
|---|--------|----------------|
| 1 | Manager login copy | On manager host, open login page: title/card say “RunMyCampus Manager” / “Control plane sign-in”; no role selector; “Back to public site” links to runmycampus.com. |
| 2 | Super dashboard header/sidebar | After login on manager host, open /super/: header shows “RunMyCampus Manager”, platform logo, search, Configuration Engine, user dropdown; sidebar shows Dashboard, Command Center, Provision tenant, Billing, Support, Marketplace, etc. |
| 3 | Configuration Engine | Header “Configuration Engine” and sidebar entry both go to admin (Django admin). |
| 4 | Tenant login unchanged | On tenant host (or default host), login page is standard tenant login (auth/login.html); no manager-only copy. |
| 5 | Manager errors | On manager host, trigger 403/404/500: page uses control-plane styling (navy/gold, control_plane_skeleton), no tenant name; “Back to Manager” goes to super:dashboard. |
| 6 | Header search | In control plane header, type 2+ characters in search: dropdown shows results from /api/search/; clicking a result navigates to that URL. |
| 7 | Mobile sidebar | On manager host, narrow viewport: navbar toggler opens offcanvas with same sidebar nav; no desktop-only sidebar visible. |
| 8 | All super templates on control plane base | Every super view (dashboard, command center, billing, support, create school, migration, pulse, tenant health, usage, sync repair, governance, blueprints, app catalog, customer success, platform incidents) extends control_plane_base and uses cp_content / cp_title. |

**Automated tests:** `apps.schools.tests.test_phase10_control_plane_verification` — manager login template (check 1), non-manager login template (check 4), manager 403/404/500 use control-plane templates (check 5), tenant 403 uses standard template, and manager/tenant urlconf resolution (check 2/3). Run: `python manage.py test apps.schools.tests.test_phase10_control_plane_verification`.
