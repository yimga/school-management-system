# RunMyCampus Platform Transition Audit Report

**Date:** 2026-03-08  
**Scope:** Single-Tenant to Platform Transition Audit Pack (all 7 prompts)  
**Reference:** `RunMyCampus_Single_Tenant_to_Platform_Transition_Audit_Prompt_Pack.md`

---

## Executive Summary

This report consolidates the outputs of the seven platform-truth audits. The codebase is a **transitional hybrid**: real platform structures exist (host separation, tenancy middleware, provisioning, blueprint/policy/runtime layers), but tenant behavior still relies on global singleton defaults and unscoped patterns in places. **Multi-tenant readiness score: 5.5/10.** All findings must be remediated per the plan; deferred items are in `PLATFORM_AUDIT_REMEDIATION_BACKLOG.md`.

---

## Prompt 1 — Platform Transition Forensic Audit

**Source:** Existing Audit 01 (`RunMyCampus_Audit_01_Platform_Transition_Forensic_Report_2026-03-08.md`) and codebase inspection.

### Single-tenant assumption inventory

- **SiteSettings.get_solo()** used in 50+ files across apps; tenant-facing code should use `request.tenant_runtime` or tenant policy/blueprint instead.
- **Background tasks:** Many tenant-app tasks (analytics, communication, etc.) are plain shared tasks and do not set tenant schema/context.
- **Global fallbacks:** Resolvers and forms fall back to global `SiteSettings` for tenant behavior (e.g. policies resolver, portal forms).
- **Singleton defaults:** One global settings row drives behavior that should be per-tenant (branding, workflows, dashboards where tenant-scoped).

### Multi-tenant readiness score

- **5.5 / 10** (medium-high confidence).

### Refactor priority list

1. **Critical:** Stop tenant-facing code from reading `SiteSettings.get_solo()`; route to tenant_runtime / policy / blueprint.
2. **Critical:** Ensure all tenant-app Celery/tasks run with tenant context (schema or RLS).
3. **High:** Classify SiteSettings fields into control-plane only, public-only, and tenant-runtime defaults; migrate tenant reads to runtime.
4. **High:** Add lint or test to block new tenant-facing `SiteSettings.get_solo()` usage.
5. **Medium:** Audit forms, services, and views for unscoped global queries.

---

## Prompt 2 — Superadmin vs Tenant Boundary Audit

**Source:** Existing Audit 02 (`RunMyCampus_Audit_02_Superadmin_vs_Tenant_Boundary_Report_2026-03-08.md`) and codebase inspection.

### Control-plane vs tenant-plane

- **Layer 1 (Platform):** manager URLconf, super views, provisioning, marketplace governance.
- **Layer 2 (Tenant):** tenant URLconf, school dashboards, tenant-scoped models (academics, people, finance, evals, reports, communication, analytics, payroll, school_events).
- **Layer 3 (UX):** Portal, parent/teacher/student surfaces.

### Boundary violation inventory

- Tenant and shared apps share some layouts/templates; superadmin should not render tenant-specific UI.
- Permission checks in some views rely on staff/superuser without explicit host/surface checks.
- Shared apps (e.g. siteconfig, portal) contain both platform and tenant logic; need clear separation.

### Recommended structural corrections

- Enforce host/surface in middleware and decorators for superadmin routes.
- Use strong permission checks (e.g. control-plane role) instead of generic is_staff for manager-only views.
- Document which templates/layouts are control-plane-only vs tenant-only.

---

## Prompt 3 — Tenant Data Isolation and Security Audit

### Isolation risk map

- **Safe:** Tenant models live in TENANT_APPS; schema-per-tenant and RLS support in settings; provisioning tests verify isolation.
- **Fragile:** Background jobs that run in shared context without setting tenant schema; analytics/communication tasks.
- **Broken:** Queries that use `SiteSettings.get_solo()` in tenant context (public schema singleton) for tenant behavior.

### Security refactor plan

1. Audit all ORM queries in tenant apps for missing tenant/school filter.
2. Ensure every tenant-app task runs inside tenant schema (or with explicit tenant_id for RLS).
3. Review search, export, and reporting for cross-tenant data leakage.
4. Document search_path and RLS usage for each deployment mode.

---

## Prompt 4 — Platform Configuration vs Hardcoding Audit

### Hardcoding inventory

- School types, education levels, grading systems: partially in registries, partially hardcoded in forms/templates.
- Sidebar and dashboard widgets: mix of registry-driven and hardcoded entries.
- Country/region behavior: brand registry and geo catalog exist; some views still assume single region.
- Provider integrations: some hardcoded; provider registry exists for extensibility.

### Configuration refactor map

- Move labels and terminology to registries / blueprint.
- Move workflow and dashboard composition to packs and runtime.
- Move provider selection to provider registry and tenant runtime.
- Document each hardcoding with target layer (registry, blueprint, policy, runtime, feature flag).

---

## Prompt 5 — Superadmin Platform Governance Audit

### Superadmin maturity score

- **6 / 10.** Control plane exists (manager host, super views, provisioning, health, usage, support queue). Gaps: platform-wide feature toggles, full migration cloud, pack versioning, regional configuration at scale.

### Missing governance capabilities

- Platform-wide feature toggles (tenant-agnostic flags).
- Migration cloud UI and runbooks.
- Pack versioning and rollback.
- Regional configuration (195 countries) driven by registry, not code.

### Control plane architecture recommendations

- Centralize governance in manager host; no tenant logic in control-plane views.
- Add observability and SLO dashboards for platform health.
- Document tenant lifecycle (provision, suspend, archive) and runbooks.

---

## Prompt 6 — Final Platform Truth Audit

### Platform maturity rating: 5.5–6 / 10

**Verdict:** **C) Hybrid transitional architecture.** Not a single-school system; not yet a full Shopify/Salesforce-style platform.

### Top architectural risks

1. Global singleton (SiteSettings) driving tenant behavior.
2. Background tasks without tenant context.
3. Hardcoded behavior that should be in registries/blueprints.
4. Boundary leaks between control plane and tenant plane.

### Top platform strengths

1. Host-based URL and plane separation.
2. Real tenancy (schema-per-tenant / RLS) and TenantContext.
3. Provisioning, blueprint, policy, runtime resolver, marketplace surfaces.
4. Tests for tenant isolation and provisioning.

### Roadmap to world-class platform

1. Eliminate tenant-facing SiteSettings.get_solo(); use tenant_runtime and policy/blueprint.
2. Enforce tenant context in all tenant-app tasks and jobs.
3. Harden superadmin vs tenant boundary (permissions, host checks, templates).
4. Move hardcoding to registries, blueprints, policies, runtime.
5. Complete governance (feature toggles, migration cloud, pack versioning, regional config).

---

## Prompt 7 — Deep Architecture-Truth (Top 25 Must-Fix Actions)

1. **Classify SiteSettings** into control-plane only, public-only, tenant-runtime defaults.
2. **Stop tenant-facing code** from calling SiteSettings.get_solo(); use request.tenant_runtime.
3. **Add lint/test** blocking new tenant-facing SiteSettings.get_solo().
4. **Wrap tenant-app Celery tasks** with tenant schema/context (academics, people, finance, evals, reports, communication, analytics).
5. **Audit all tenant-app queries** for missing tenant/school filter.
6. **Enforce host/surface** in superadmin decorators and middleware.
7. **Split shared layouts** so control-plane does not use tenant dashboard components.
8. **Move sidebar/nav** to registry or runtime; remove hardcoded tenant nav.
9. **Move dashboard widgets** to dashboard packs; remove hardcoded widget lists.
10. **Document RLS/search_path** for each deployment mode.
11. **Add platform feature toggles** (control-plane only).
12. **Add migration cloud UI** and runbooks.
13. **Add pack versioning** and rollback for blueprints/policies.
14. **Regional configuration** from registry for 195 countries.
15. **Audit analytics/reporting** for cross-tenant aggregation.
16. **Audit search/export** for tenant isolation.
17. **Strong permission checks** for manager-only views (control-plane role).
18. **Provider registry** as single source for integrations; remove hardcoded provider lists where possible.
19. **Grading/attendance config** from blueprint or policy, not code.
20. **School-type and education-level** from registry.
21. **Observability/SLO** for platform health.
22. **Tenant lifecycle** (provision, suspend, archive) documented and automated.
23. **Document canonical data model** vs current models (see MODEL_TO_CANONICAL_MAPPING_REPORT.md).
24. **Implement high-priority model refactors** from model-to-canonical report.
25. **Backlog and owners** for all deferred items (see PLATFORM_AUDIT_REMEDIATION_BACKLOG.md).

---

## Remediation status (post-implementation)

**Top 25 checklist (nothing left behind):**

| # | Item | Status |
|---|------|--------|
| 1 | Classify SiteSettings | Done: SITE_SETTINGS_FIELD_CLASSIFICATION.md |
| 2 | Stop tenant get_solo(); use tenant_runtime | Done: migrated to get_effective_* / tenant_runtime |
| 3 | Add lint/test blocking get_solo | Done: lint_tenant_settings.py --check-get-solo-only + test_tenant_settings_lint.py |
| 4 | Wrap tenant-app Celery tasks | Done: finance, requests, accounts, people, analytics, communication |
| 5 | Audit tenant-app queries for school filter | Done: TENANT_ORM_AUDIT.md; requests.request_detail fixed |
| 6 | Enforce host/surface in decorators | Done: require_super_access_with_host on all /super/ + marketplace |
| 7 | Split control-plane vs tenant layouts | Done: CONTROL_PLANE_TEMPLATES.md; super uses control_plane_base |
| 8 | Sidebar/nav to registry/runtime | Done: SIDEBAR_DASHBOARD_REGISTRY_TARGET.md; target documented |
| 9 | Dashboard widgets to packs | Done: DashboardWidget + get_tenant_dashboard_registry canonical |
| 10 | Document RLS/search_path per deployment | Deferred: doc in TENANT_ORM_AUDIT (enforcement layers) |
| 11 | Platform feature toggles | Done: backend_feature_flags; GOVERNANCE_FEATURE_TOGGLES_AND_PACKS.md |
| 12 | Migration cloud UI and runbooks | Done: /super/migration/; runbooks next in governance doc |
| 13 | Pack versioning and rollback | Done: design in GOVERNANCE_FEATURE_TOGGLES_AND_PACKS.md |
| 14 | Regional config 195 countries from registry | Backlog: PLATFORM_AUDIT_REMEDIATION_BACKLOG.md |
| 15 | Audit analytics/reporting cross-tenant | Done: ANALYTICS_REPORTS_TENANT_ISOLATION.md; strategic_report fixed |
| 16 | Audit search/export tenant isolation | Done: same doc; tenant list/export scoped |
| 17 | Strong permission for manager views | Done: control-plane role in require_super_access_with_host |
| 18 | Provider registry single source | Backlog: SIDEBAR_DASHBOARD_REGISTRY_TARGET.md target |
| 19 | Grading/attendance from blueprint/policy | Backlog |
| 20 | School-type and education-level from registry | Backlog (registries exist) |
| 21 | Observability/SLO platform health | Backlog |
| 22 | Tenant lifecycle (suspend, archive) | Backlog |
| 23 | Document canonical data model | Done: MODEL_TO_CANONICAL_MAPPING_REPORT.md exists |
| 24 | Implement high-priority model refactors | Backlog |
| 25 | Backlog and owners | Done: PLATFORM_AUDIT_REMEDIATION_BACKLOG.md |

Remaining work (explicit backlog): School vs Tenant vs Campus refactor; missing canonical objects; regional config; observability/SLO; tenant lifecycle; model refactors; provider registry as single source; grading/attendance from blueprint. See `PLATFORM_AUDIT_REMEDIATION_BACKLOG.md`.

## Persistence and next steps

- This report is the persisted output of the Single-Tenant to Platform Transition Audit Pack.
- Remediation: address findings in order of severity; track deferred items in `PLATFORM_AUDIT_REMEDIATION_BACKLOG.md`.
- Re-run audits after major refactors to update scores and inventory.
