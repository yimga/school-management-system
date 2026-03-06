# Phase 10 — Superadmin vs Tenant UI (Section 8)

Design/system split between superadmin and tenant UI: same codebase, distinct variants/shells. Section 8 checklist verification.

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

## Checklist summary

| Id | Status | Notes |
|----|--------|--------|
| 8.1 | Done | Command center, observability, ecosystem (marketplace), policy control; control-plane-shell. |
| 8.2 | Done | Tenant urlconf, backend_base, role-based dashboard/sidebar, localized via policy. |
| 8.3 | Done | One codebase; public/manager/tenant urlconfs and distinct shells. |
| 8.4 | Done | Superadmin dark/ops; tenant school-branded, role-centric. |
| 8.5 | Done | Public premium/demos; teacher task-oriented; parent/student mobile-first. |

**Reference:** phase2_control_tenant_shells.md, phase9_domain_and_routing.md, section_28_data_architecture_and_provisioning.md (28.2 brand vs site).
