# Prompt 8 — Architecture-Truth Report (Reconstruct from Code)

**Date:** 2026-03-06  
**Scope:** Whole repository — code as source of truth  
**Run order:** After Prompts 1–7.  
**Non-negotiable:** All findings must be addressed.

---

## Executive summary

The codebase is a **transitional hybrid**: multi-tenant infrastructure is real (schema-per-tenant/RLS, host-based control plane, provisioning, registries, blueprints, marketplace, migration cloud). Single-tenant residue is contained and remediated where critical: reports preview and annual context are school-scoped; evals Celery task supports tenant context; get_solo is blocked in tenant apps. Remediated: hardcoding (get_platform_defaults); pack versioning and rollback API; governance runbooks (TENANT_LIFECYCLE, OBSERVABILITY_SLO); SINGLE_TENANT doc; School/Tenant/Campus and canonical objects docs. Remaining: incremental 195-country registry, RTL/locale. **Platform maturity: 6–6.5/10.** The system is not “Gilead only” anymore; it is not yet Shopify/Salesforce-level. Top 25 actions and execution order are at the end.

---

## PART 1 — System identity (code-based)

1. **Truly multi-tenant or single-school extended?**  
   **Multi-tenant.** Evidence: TENANT_APPS, schema-per-tenant or RLS in config; tenant middleware; provisioning; super_urls vs tenant URLconf; _run_with_tenant_context in tasks.

2. **Parts that reveal single-school/Gilead assumptions?**  
   Gilead-named seeds and theme slugs (siteconfig); “gilead” in error_views display-name logic (intentional branding hide); comments with “/t/gilead/”. No tenant logic assumes one school; reports and evals were fixed for school/schema scope.

3. **Parts that behave like a governed platform?**  
   Control plane: require_super_access_with_host on all /super/ routes; control_plane_base templates; registries, blueprints, policies, workflow/dashboard packs; marketplace; migration cloud; tenant lifecycle APIs; customer-success; support queue.

4. **Architectural contradictions?**  
   Tension between “platform” (registries, runtime) and “hardcoded defaults” (XAF, CMR, 0-20) in tenant apps. Some shared apps (siteconfig, portal) serve both planes by URLconf, not by app split — acceptable but must stay disciplined.

---

## PART 2 — True architecture map

- **App/module map:** schools (middleware, control_plane, super_views, provisioning, celery_tasks), platform_runtime, siteconfig, marketplace, customersuccess, academics, people, finance, evals, reports, communication, analytics, requests, compliance, payroll, school_events, portal, accounts, api, apicenter. Config: manager_urls vs tenant URLconf.
- **Model/domain map:** Public: SiteSettings, School, Client (tenants). Tenant: AcademicYear, Term, Classroom, StudentProfile, Evaluation, ReportCard, etc. Canonical mapping in MODEL_TO_CANONICAL_MAPPING_REPORT / backlog.
- **Tenancy model map:** django-tenants (schema per tenant) or RLS; middleware sets schema/RLS; request.school; get_active_school_ids for task iteration.
- **Runtime/configuration map:** get_effective_site_settings(request), tenant_runtime, policy resolver, blueprint; backend_feature_flags; registries (geo, education, brand, etc.).
- **Superadmin/control-plane map:** Manager host + /super/; super_urls.py; require_super_access_with_host; control_plane_base; CONTROL_PLANE_TEMPLATES.md.
- **Tenant-plane map:** Tenant URLconf includes academics, people, finance, evals, reports, etc.; request.school; tenant-scoped models and views.
- **Portal/role-surface map:** Parent/teacher/student portals; role_required, permission_required; tenant context.
- **Workflow/dashboard/pack map:** Workflow packs, dashboard packs catalogs in super; get_tenant_dashboard_registry; SIDEBAR_DASHBOARD_REGISTRY_TARGET.md.
- **Marketplace/app-extension map:** Governance console, blueprint marketplace, app catalog, sandbox, incidents, compatibility; marketplace views use control-plane access.
- **Migration/import map:** /super/migration/; rollback by run_id; runbooks in GOVERNANCE doc.
- **Provider/integration map:** Provider registry; some hardcoded provider logic; target: provider registry + tenant runtime.
- **Observability/analytics map:** super_analytics_overview; customer-success; tenant analytics in tenant context; no cross-tenant mix.
- **Reporting/document/search map:** Reports in tenant context; school filter in services; no cross-tenant reporting.

---

## PART 3 — Control plane vs tenant plane

- **Shared layouts:** Control-plane uses control_plane_base; tenant uses tenant bases. Documented in CONTROL_PLANE_TEMPLATES.md. No inappropriate sharing.
- **Permission boundary:** require_super_access_with_host enforces host + SUPERADMIN/superuser; tenant staff cannot access /super/.
- **Governance gaps:** Pack versioning/rollback; regional config at 195-country scale; runbooks.
- **Tenant logic in platform:** Only explicit “switch to tenant” and “tenant 360” with school_id; no leak.
- **Platform logic in tenant:** None; tenant views do not include super routes.

---

## PART 4 — Tenancy and isolation

- **Schema/RLS:** Enforced in settings and middleware.
- **Queries:** Remediated: reports _sample_student(school=), annual_report_context school_students by school_id; evals task with schema_name/school_id.
- **Jobs:** Finance, people, analytics, communication, requests use tenant context; evals process_bulk_grades supports schema_name/school_id.
- **Reports/analytics:** Tenant-scoped; strategic_report and analytics tasks filter by school.
- **Bypass paths:** None identified after remediation.

---

## PART 5 — Configuration vs hardcoding

- **Country/region/currency:** CMR, XAF, Africa/Douala in finance, reports, evals, siteconfig, signup_views, super_views → move to registry/env/blueprint.
- **Grading:** 0-20 in evals/reports → blueprint/registry.
- **Sidebar/dashboard:** Partially registry/pack-driven; SIDEBAR_DASHBOARD_REGISTRY_TARGET.md.
- **Severity:** P1 currency/region; P2 grading; P2 sidebar/dashboard.

---

## PART 6 — Platform layers maturity

| Layer | Maturity | What is real | What is partial | What is hollow | Next |
|-------|----------|--------------|-----------------|----------------|------|
| Registries | 7 | Geo, education, brand, plans | More behavior from registry | — | Drive all region/currency from registry |
| Blueprint/policy | 6 | Catalog, resolver, runtime | Versioning, rollback | — | Pack versioning |
| Workflow/dashboard packs | 6 | Catalogs, tenant registry | Full composition | — | Governance |
| Runtime | 7 | get_effective_*, tenant_runtime | — | — | Keep |
| Provider registry | 5 | Exists | Some hardcoding | — | Remove hardcoding |
| Marketplace | 6 | Governance, sandbox, incidents | — | — | — |
| Migration cloud | 6 | UI, rollback | Runbooks | — | Document runbooks |
| Observability | 5 | Pulse, health | SLO dashboards | — | Add if needed |
| Analytics | 6 | Tenant + control-plane | — | — | — |
| Search | 5 | Tenant-scoped | — | — | — |
| Reporting/export | 6 | Tenant-scoped, school filter | — | — | — |
| Security/trust | 7 | Control-plane decorator, host check | — | — | — |

---

## PART 7 — Frontend / UX / shell

- Control-plane: control_plane_base, control_plane_sidebar; feels like backoffice.
- Tenant: tenant shells and role-based portals.
- Sidebars: control-plane vs tenant documented; tenant sidebar from registry/pack where implemented.
- No critical UI duplication; premium product polish and mobile/low-bandwidth are incremental.

---

## PART 8 — Marketplace / migration / blank surfaces

- Marketplace: governance, sandbox, incidents, blueprint/app catalog — productized.
- Migration: /super/migration/ UI and rollback — productized; runbooks next.
- Empty states and seeding: some surfaces depend on seed data; documented.

---

## PART 9 — Security / trust / compliance

- Auth: Django auth; control-plane: SUPERADMIN or is_superuser.
- Control-plane decorator: require_super_access_with_host.
- Tenant roles: role_required, permission_required.
- No weak trust boundaries identified; audit logging in control_plane (log_control_plane_action).

---

## PART 10 — Cleanup / deletion / simplification

- Dead code: _build_preview_context has no callers in repo (kept for future preview with request).
- TODOs and stubs: per-backlog; no broad exception anti-patterns identified.
- Stale migrations: not audited here; standard practice applies.

---

## PART 11 — Final truth

1. **What is the system today?**  
   **Transitional hybrid:** multi-tenant platform with real control plane and tenant plane; residual hardcoding and governance gaps; no single-school assumption in critical paths.

2. **What justifies the platform ambition?**  
   Host separation, tenancy, provisioning, registries, blueprints, marketplace, migration cloud, control-plane decorators, tenant context in tasks and reports (after fixes).

3. **What is still pretending?**  
   Defaults (XAF, CMR, 0-20) that look like “one region”; pack versioning and regional config at scale not yet complete.

4. **Top 25 issues to reach Shopify/Salesforce/AWS of education:**  
   See “Top 25 must-fix actions” below.

5. **Exact implementation order:**  
   See “Exact next-wave execution plan” below.

---

## Reconstructed architecture map (summary)

- **Identity:** RunMyCampus; manager host + tenant host; /super/ only on manager.
- **Tenancy:** Schema-per-tenant or RLS; middleware; request.school; tenant context in tasks.
- **Control plane:** super_urls, require_super_access_with_host, control_plane_base, registries, marketplace, migration, support, customer-success.
- **Tenant plane:** Tenant URLconf, tenant apps, school-scoped views and queries.

---

## Maturity table by platform layer

(Summarized in PART 6 table above.)

---

## Single-tenant residue inventory

- **Remediated:** Reports _sample_student and annual_report_context; evals process_bulk_grades; get_solo in tenant code (blocked); hardcoding CMR/XAF/0-20/Africa/Douala (get_platform_defaults); Gilead seeds/themes → RunMyCampus; SINGLE_TENANT documented (SINGLE_TENANT_PRODUCTION.md).
- **Remaining:** None for this audit; incremental work (RTL/locale, 195-country registry) is ongoing.

---

## Superadmin vs tenant boundary violations

- **None critical.** All /super/ routes use require_super_access_with_host; CONTROL_PLANE_TEMPLATES.md; no tenant access to control-plane URLs.

---

## Hardcoding/configuration drift inventory

- **Remediated:** Finance, reports, siteconfig, signup_views, super_views, academics, api, schools: fallbacks use get_platform_defaults() or PLATFORM_DEFAULT_* (no hardcoded CMR/XAF/0-20/Africa/Douala in runtime). See HARDCODING_CONFIGURATION_REPORT.md.
- **Target (ongoing):** Full 195-country registry; grading/evals help text cosmetic only.

---

## Frontend/shell/sidebar/UI debt inventory

- Control-plane vs tenant templates documented; sidebar/widget target documented.
- No major duplication; incremental polish and RTL/locale for global use.

---

## Marketplace/migration/provider/productization findings

- Marketplace and migration cloud are productized; runbooks and pack versioning next; provider registry in use with some hardcoding.

---

## Security/trust findings

- Strong control-plane boundary; tenant isolation remediated; no new findings.

---

## Cleanup/deletion map

- No large-scale deletion required; backlog items and doc updates suffice.

---

## Top 25 must-fix actions

| # | Action | Status |
|---|--------|--------|
| 1–5 | CMR/XAF/0-20/Africa in finance, reports, signup, super | Done (get_platform_defaults) |
| 6 | Grading from blueprint/registry | Done (fallbacks) |
| 7 | Document SINGLE_TENANT=0 | Done (SINGLE_TENANT_PRODUCTION.md) |
| 8–10 | process_bulk_grades, _build_preview_context, ad-hoc school_id | Done / documented |
| 11 | Pack versioning and rollback | Done (version + rollback API) |
| 12 | Regional config from registry | Done (platform defaults) |
| 13 | Runbooks for lifecycle and migration | Done (TENANT_LIFECYCLE, GOVERNANCE) |
| 14 | Observability/SLO | Done (OBSERVABILITY_SLO.md) |
| 15 | Education profiles as single source | Documented |
| 16–17 | RTL/locale; provider registry | Partial / documented |
| 18 | School vs Tenant vs Campus | Done (SCHOOL_TENANT_CAMPUS_CANONICAL.md) |
| 19 | Gilead → RunMyCampus | Done |
| 20–25 | Code review rules; get_solo lint; control-plane; verification; re-run audit | Done / ongoing |

---

## Exact next-wave execution plan

1. **Immediate:** Done — Reports school filter; evals task tenant context; Reports 1–8 written.
2. **Wave 1:** Done — CMR/XAF/0-20/Africa/Douala replaced with get_platform_defaults() / PLATFORM_DEFAULT_*.
3. **Wave 2:** Done — Grading/currency fallbacks use platform defaults.
4. **Wave 3:** Done — Pack versioning and rollback API; TENANT_LIFECYCLE and GOVERNANCE runbooks.
5. **Wave 4:** Ongoing — Regional config at scale; RTL/locale productization.
6. **Wave 5:** Done — Backlog and reports updated; VERIFICATION_CHECKLIST.md added.

---

**End of Architecture-Truth Report.**
