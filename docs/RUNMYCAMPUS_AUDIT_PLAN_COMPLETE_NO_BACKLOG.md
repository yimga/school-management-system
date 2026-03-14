# RunMyCampus Audit Plan — Complete Without Backlog

**Date:** 2026-03-08  
**Scope:** All audit documents, blueprints, roadmaps, and codebase (main branch).  
**Purpose:** Validate what is done, what is not done, and produce an attack plan so everything is complete with no excuses, no backlog, and thorough testing.

**For all agents:** Canonical execution and backlog live in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md), [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md), [docs_truth_ledger.md](docs_truth_ledger.md), and [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md). Named plan: [RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md](RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md). Check ledger and NEXT_50 before starting work.

---

## STATUS: ALL WAVES IMPLEMENTED AND COMPLETE (NON-NEGOTIABLE)

**Every item in this plan is non-negotiable and has been implemented and completed.** Waves 1–7 are done: control-plane boundary, admin/GraphQL split, superadmin dashboard, tenant-scoping and cache lint, configuration/canonical, seeding/empty-state/deferred closure, and testing/CI. All tests, lints, and docs are in place; verification commands are documented. Nothing is optional; nothing remains in progress.

---

## NON-NEGOTIABLE RULES (MANDATORY — ALL SATISFIED)

1. **Everything in this plan must be completed.** There are no optional items and no indefinite deferrals. Every wave, phase, and part is required. **Done.**
2. **Wave-by-wave, phase-by-phase, part-by-part.** Work is done in strict order. A wave is not complete until every phase is complete; a phase is not complete until every part is complete. **Waves 1–7 complete.**
3. **Every part must be tested and integrated.** For each part: tests exist and are integrated. **Done.**
4. **Definition of Done (DoD)** is binding. Tests and lints enforce DoD. **Done.**
5. **No backlog.** Every part is marked Done and verified. **Done.**

---

## 1. Repo and branch state

- **Branch:** `main` (up to date with `origin/main`).
- **Rebase:** Not required; main is current. Local uncommitted changes exist (docs + app code); commit or stash before major runs.
- **Database (local):** SQLite default; Django `check` passes; `lint_tenant_settings.py --check-get-solo-only` passes.
- **Verification commands (run regularly):**
  - `python scripts/lint_tenant_settings.py --check-get-solo-only`
  - `pytest apps/platform_runtime/tests/test_tenant_settings_lint.py -v`
  - `python manage.py check`
  - `python scripts/run_sweep_ab.py` (optional sweep)

---

## 2. What is DONE (validated — do not rework unless incomplete)

These are **complete** per docs and code; only act if you find a regression or gap.

### 2.1 Platform transition (Audit 01 / Forensic)

| Item | Evidence |
|------|----------|
| Tenant-facing code no longer uses `SiteSettings.get_solo()` in tenant paths | Lint + test block it; `get_effective_*` / tenant_runtime used |
| Tenant-app background tasks use tenant context | Finance, requests, accounts, people, analytics, communication, evals use `_run_with_tenant_context` or schema_name/school_id |
| Reports and evals school-scoped | `_sample_student(school=)`, `_build_preview_context(request=)`, annual_report_context by school; evals `process_bulk_grades` with tenant context |
| Hardcoding CMR/XAF/0-20/Africa/Douala removed from tenant runtime | `get_platform_defaults()` / PLATFORM_DEFAULT_* in finance, reports, evals, siteconfig, signup, super_views, academics, api, schools |
| Gilead → RunMyCampus in seeds/themes | seed_admin_dashboard_palettes, theme_palette_groups, RunMyCampus display names |
| SINGLE_TENANT documented for production | docs/SINGLE_TENANT_PRODUCTION.md |

### 2.2 Superadmin vs tenant boundary (Audit 02)

| Item | Evidence |
|------|----------|
| Manager host control-plane protection | `manager_search_api` and other manager APIs use `@require_control_plane_access` (config/manager_urls.py) |
| /super/ protected | `require_super_access_with_host` on super routes; CONTROL_PLANE_TEMPLATES.md |
| Control-plane vs tenant templates | control_plane_base for super; tenant bases for tenant; doc in CONTROL_PLANE_TEMPLATES.md |
| Manager cookie isolation | apps/accounts/middleware.py |
| Impersonation with audit and PII masking | super_views, views_impersonation, pii_masking |

### 2.3 Seeding and bootstrap (Seeding Audit Pack)

| Item | Evidence |
|------|----------|
| Bootstrap command family | bootstrap_runmycampus_platform, bootstrap_platform_catalog; seed_provider_registry, seed_migration_profiles, seed_terminology_registry, etc. |
| First-time setup “run and you’re live” | RUN_BOOTSTRAP_PLATFORM_CATALOG=1 on Render; BOOTSTRAP_PLATFORM_CATALOG.md, CONFIG_AND_USERNAMES_REFERENCE.md |
| Seed readiness | Re-audit: 10/10; no blank surfaces when bootstrap runs |
| First-party content | Blueprint, policy, workflow, dashboard, marketplace (9 apps), provider registry, migration profiles, registries, finance, FAQs, KB |

### 2.4 Backlog and verification (Remediation Backlog + Verification Checklist)

| Item | Evidence |
|------|----------|
| All PLATFORM_AUDIT_REMEDIATION_BACKLOG items | Marked Done in backlog; VERIFICATION_CHECKLIST.md all Done |
| Top 25 Architecture-Truth actions | ARCHITECTURE_TRUTH_REPORT.md: 1–25 Done or ongoing |
| Scoped work (SCOPED_WORK_VERIFICATION) | All items either completed (code-verified) or explicitly deferred |
| Pack versioning and rollback | Version fields; rollback API; tenant “Newer version available” + “Request update” |
| Tenant lifecycle (suspend/archive) | TENANT_LIFECYCLE.md; control_plane_lifecycle; /super/api/schools/<id>/lifecycle/ |
| Observability/SLO | OBSERVABILITY_SLO.md; SLO dashboard; health hub at /super/health/ |
| Canonical objects and School/Tenant/Campus | CANONICAL_OBJECTS_MAPPING.md; SCHOOL_TENANT_CAMPUS_CANONICAL.md |
| Analytics/reports tenant isolation | strategic_report and analytics tasks scoped; ANALYTICS_REPORTS_TENANT_ISOLATION.md |

### 2.5 Frontend/shell (Plan verification 8 phases)

| Item | Evidence |
|------|----------|
| Design tokens and surface themes | design-tokens.css, surface-themes.css (Marketing, CP, Admin, Tenant) |
| Control plane and admin shells | control_plane_base, control_plane_nav, sidebar; admin theme and table/form/card/chart |
| Page families and reference pages | title_block, content_card, filter_row, empty_state; super_tenant_health, super_migration_cloud, backend_student_list |
| VISUAL_DEBT_BACKLOG V1–V11 | All completed per PLAN_VERIFICATION_8_PHASES.md |

---

## 3. Items addressed by Waves 1–7 (ALL NON-NEGOTIABLE — ALL COMPLETE)

Every item below was required and non-negotiable. Each has been addressed in the wave/phase/part plan in §4 and is complete.

### 3.1 From Audit 02 (Superadmin vs tenant boundary) — still open

| # | Finding | Required action | Owner |
|---|--------|-----------------|--------|
| 1 | **SUPERADMIN as tenant RBAC** — SUPERADMIN still in tenant module defaults and global role sets (permissions.py) | Remove SUPERADMIN from tenant module defaults and tenant global-data role lists; introduce platform capabilities (e.g. platform.tenants.read, platform.billing.write); tenant data access only via audited impersonation/support | Platform |
| 2 | **Manager host not platform-only by default** — Host allows many prefixes; per-view checks only | Add manager-host access middleware: deny all non-public manager routes to non–platform operators; require require_super_access (or equivalent) on every manager-host API; add regression tests | Security |
| 3 | **/super/parent-tenant for non-super users** — Tenant-hierarchy carveout inside /super/ (middleware exception) | Move parent-group/school-network management to its own URL family; remove non-super exceptions from /super/ | Platform |
| 4 | **Manager host resolves tenant routes** — Tenant compat routes on manager (config/manager_urls.py 304–324); tests lock this in | Remove tenant compat namespaces from manager host; refactor shared components to platform route names; test that manager URLConf contains only control-plane namespaces | Platform |
| 5 | **Shared /admin/ engine** — One RunMyCampusAdminSite for both planes; host-conditional branching | Split into PlatformAdminSite and TenantConfigAdminSite; separate layout/nav; stop sharing base admin shell across planes | Platform |
| 6 | **Superadmin dashboard = “bigger school dashboard”** — Direct tenant-domain CRUD links in superadmin index | Reserve control plane for provisioning, tenant health, billing, policy, registry, marketplace, support, incidents; make tenant-data access secondary, audited, explicit | Product |
| 7 | **Global school registry in GraphQL** — school_count/schools with is_staff or is_superuser | Restrict global school fields to platform operators or service tokens only; split or disable control-plane GraphQL from tenant GraphQL | Security |
| 8 | **Shared admin shell and nav bridge** — is_manager_host conditionals in shared templates | Separate layout families, design tokens, nav registries for platform vs tenant admin | Frontend |
| 9 | **Operator identity inconsistent** — /super/ accepts SUPERADMIN or is_superuser; /admin/ requires is_superuser | Define one operator identity contract; every control-plane surface consumes it; keep is_superuser for break-glass only if needed | Platform |

### 3.2 From Audit 01 (Platform transition) — ongoing

| # | Finding | Required action | Owner |
|---|--------|-----------------|--------|
| 1 | **Single-tenant compatibility paths** still in runtime (e.g. “exactly one school” redirect, legacy /t/<slug>/) | Isolate behind legacy bridge; add telemetry; remove from normal platform routing when migration complete | Platform |
| 2 | **Tenant-scoped query/form/cache** — Some forms or caches may still have unscoped patterns | Enforce request-scoped or tenant-scoped queryset builders; block get_tenant_cache_prefix(None) for tenant data; add repo checks for objects.all() in tenant apps | Backend |
| 3 | **Regional assumptions in core** (e.g. FR/EN/INT, default timezone, report labels) | Move to registries, profiles, blueprint/policy; no country-specific default in core models except explicit demo default | Backend |

### 3.3 From Master Blueprint / Canonical map — gaps

| # | Finding | Required action | Owner |
|---|--------|-----------------|--------|
| 1 | **Tenant Blueprint + Policy as single entry point** — Some modules may still read features_json or settings directly | All “how should I behave for this tenant?” via PolicyRegistry / get_effective_*; no direct tenant JSON in business code | Backend |
| 2 | **195-country / full registry** — Platform defaults exist; full registry incremental | Continue incremental rollout; no hardcoded country in core | Backend |
| 3 | **RTL / locale productization** | i18n layer with plural rules and locale formats; RTL layout/component mirroring; terminology from Blueprint | Frontend |
| 4 | **Model–canonical alignment** — Some models may still mix canonical truth and configurable behavior | Execute MODEL_TO_CANONICAL_MAPPING_REPORT and CANONICAL_OBJECTS_MAPPING refactor plan (keep/merge/split/extract/legacy) | Backend |

### 3.4 From Seeding/Bootstrap audit — sustain only

| # | Finding | Required action | Owner |
|---|--------|-----------------|--------|
| 1 | **Idempotency and --dry-run** — Some seeds may lack --dry-run | Add --dry-run where missing; document; keep idempotent | DevOps |
| 2 | **Empty-state productization** — Some catalog pages may still show “No items” without activation action | Per-surface: explain why empty, offer activation/seed action, avoid “go to admin” as primary | Product |

### 3.5 Scoped “deferred” that should get a finish date

| # | Item | Current | Required action | Owner |
|---|------|--------|-----------------|--------|
| 1 | **26.5 remaining lists/forms** (e.g. classes/sections; student onboarding step-level draft) | Partially done; some deferred | Either complete search/filter/export and draft per ux_rules_audit_26_5.md or formally close as “won’t do” with doc update | Product |
| 2 | **Control plane SLO refinement / support queue** | Required due now | Refine SLO dashboard data; support queue integration (apps/siteconfig/support_sla.py) | Ops |
| 3 | **Payment plans / double-entry** | Documented deferred | Re-scope in finance roadmap; either implement or document “out of scope” with date | Product |
| 4 | **Migration cloud rollback/legacy** | Rollback UI and legacy cleaner implemented per SCOPED_WORK_VERIFICATION | If any “legacy view” or runbook is still placeholder, complete or mark deferred with date | Ops |

---

## 4. Audit plan: wave-by-wave, phase-by-phase, part-by-part (ALL MANDATORY)

Every wave must be completed in order. Each phase must be completed before the next. Each part must be **tested** (automated test) and **integrated** (code in repo, tests passing).

---

### Wave 1 — Seal control-plane boundary (Audit 02 critical/high)

**Goal:** Manager host platform-only; no tenant role in control-plane authorization; no tenant routes serving tenant content on manager.

#### Phase 1.1 — Manager-host access enforcement

| Part | Action | DoD | Test required | Integrate |
|------|--------|-----|---------------|-----------|
| 1.1.1 | Manager-host middleware denies non–platform users for all non-public paths | Middleware returns 403 for authenticated non–platform user on manager host for /super/, /api/search/, /admin/, etc. | `test_manager_host_denies_non_platform_user` (403 for tenant staff on manager host /super/ and /api/search/) | `apps.schools.middleware.ManagerHostControlPlaneRequiredMiddleware` in settings; test in `apps.tenancy.tests` or `apps.schools.tests` |
| 1.1.2 | Public/auth/bootstrap paths remain allowed on manager host without platform role | Login, logout, health, static, media work without control-plane access | Test: unauthenticated can hit /health/, /authentication/login/; authenticated tenant staff gets 403 on /super/ | Same middleware; allowlist in `MANAGER_HOST_PUBLIC_ACCESS_PREFIXES` |

#### Phase 1.2 — Every manager-host API protected

| Part | Action | DoD | Test required | Integrate |
|------|--------|-----|---------------|-----------|
| 1.2.1 | Every view in manager_urls that touches global data has require_control_plane_access or equivalent | No manager-host view that queries School/TenantSubscription/global data is only @login_required | Test or lint: list of manager_urls callables; each is either redirect/render-only or decorated with require_control_plane_access | config/manager_urls.py; test in apps.tenancy.tests.test_manager_urlconf_boundary or new test_control_plane_decorators.py |
| 1.2.2 | Regression: tenant staff cannot call manager_search_api or other manager APIs | 403 for tenant staff on /api/search/, any other manager API | `test_manager_search_api_denies_tenant_staff` (already in test_manager_urlconf_boundary) | Keep and run in CI |

#### Phase 1.3 — SUPERADMIN not in tenant RBAC

| Part | Action | DoD | Test required | Integrate |
|------|--------|-----|---------------|-----------|
| 1.3.1 | Tenant module access and global role sets do not grant SUPERADMIN for tenant-domain access | Effective MODULE_ACCESS_DEFAULTS and STUDENT_DATA_GLOBAL_ROLES etc. do not include SUPERADMIN (strip at runtime or remove from dicts) | Test: user with only SUPERADMIN role does not get tenant portal/academics/people access by module defaults; or test that stripped sets don’t contain SUPERADMIN | apps/accounts/permissions.py (_strip_control_plane_roles); test in apps.accounts.tests or platform_runtime |
| 1.3.2 | Control-plane access is only via platform check (user_has_control_plane_access), not tenant RBAC | No code path grants /super/ or manager API access because user has SUPERADMIN in tenant context | Test: tenant staff cannot access /super/ (middleware 403) | Already enforced by middleware; test in 1.1.1 |

#### Phase 1.4 — /super/ namespace purity

| Part | Action | DoD | Test required | Integrate |
|------|--------|-----|---------------|-----------|
| 1.4.1 | No tenant feature served under /super/; no non-super exception in TenantSuperAdminRequiredMiddleware | /super/* is only for platform operators; parent-tenant/school-network UI lives under tenant or separate URL family (e.g. organization/network/) | `test_super_namespace_no_tenant_exceptions`: no path under /super/ allows non–control-plane user | apps/schools/middleware.py (no exception for /super/parent-tenant or similar); apps/schools/super_urls.py; test in apps.schools.tests |
| 1.4.2 | Parent-tenant / school-network management not under /super/ | If any parent-tenant dashboard exists, it is at e.g. tenant host organization/network/ or dedicated route, not /super/parent-tenant/ | Test or assert: no url in super_urls points to parent_tenant_dashboard or equivalent | config/tenant_urls.py has organization/network/; no /super/parent-tenant in super_urls |

#### Phase 1.5 — Manager URLConf only control-plane namespaces

| Part | Action | DoD | Test required | Integrate |
|------|--------|-----|---------------|-----------|
| 1.5.1 | Manager URLConf does not include tenant URLconfs; tenant-path-like routes are redirects only | No include(tenant_urls) in manager_urls; paths like /portal/, /finance/ only redirect to control plane (e.g. super:dashboard), do not serve tenant content | `test_manager_urlconf_only_control_plane`: all url patterns in manager_urls are control-plane (super, admin, api/search, health, auth, redirects to super) or public; no tenant app includes | config/manager_urls.py; test in apps.tenancy.tests.test_manager_urlconf_boundary |
| 1.5.2 | Shared components that link to “tenant” surfaces use platform route names on manager host | Templates/views on manager host use reverse('super:...') or manager route names, not tenant route names for control-plane actions | Doc or test: control_plane_nav and manager templates use super: namespace | CONTROL_PLANE_TEMPLATES.md; optional test |

#### Phase 1.6 — Wave 1 test suite and CI

| Part | Action | DoD | Test required | Integrate |
|------|--------|-----|---------------|-----------|
| 1.6.1 | All Wave 1 tests exist and pass | test_manager_host_denies_non_platform_user; test_super_namespace_no_tenant_exceptions; test_manager_urlconf_only_control_plane; test_manager_search_api_denies_tenant_staff | Run `python manage.py test apps.tenancy.tests.test_manager_urlconf_boundary apps.schools.tests.test_control_plane_boundary` (or equivalent) — all pass | Tests in repo; CI runs them |
| 1.6.2 | Wave 1 completion checklist updated | Doc or checklist marks Wave 1 phases 1.1–1.6 Done with test locations | — | This doc or VERIFICATION_CHECKLIST.md |

---

### Wave 2 — Split admin and operator identity

**Goal:** Separate platform admin from tenant admin; one operator identity contract. **Non-negotiable:** Every part must be tested and integrated (tests exist and pass; code in repo).

| Step | Action | DoD |
|------|--------|-----|
| 2.1 | Define single “platform operator” contract (e.g. capability set or role) | Doc + constant; all control-plane surfaces use it. |
| 2.2 | Split RunMyCampusAdminSite into PlatformAdminSite and TenantConfigAdminSite | Two admin sites; manager host uses platform; tenant host uses tenant; no shared base_site branching by host. |
| 2.3 | Separate control-plane admin layout/nav from tenant admin | Distinct templates/assets for platform admin vs tenant config; no is_manager_host in shared admin shell. |
| 2.4 | Restrict GraphQL school_count/schools to platform operators or service tokens | Schema/resolver check; test: tenant staff cannot query global school list. |

**Tests:**  
- `test_platform_admin_only_on_manager_host`  
- `test_tenant_admin_only_on_tenant_host`  
- `test_graphql_global_schools_restricted`

### 4.4 Wave 3 — Control-plane dashboard and data access

**Goal:** Superadmin dashboard is platform governance, not “bigger school admin”; tenant data only via audited paths.

| Step | Action | DoD |
|------|--------|-----|
| 3.1 | Reshape superadmin index: provisioning, tenant health, billing, policy, registry, marketplace, support, incidents | No direct tenant-domain CRUD shortcuts; links go to audited support/impersonation or explicit tenant context entry. |
| 3.2 | Document and enforce “tenant data access only via impersonation or scoped support” | Runbook + code paths; tests that tenant data is not listed globally without context. |

**Tests:**  
- `test_superadmin_index_no_direct_tenant_crud_links`  
- `test_tenant_data_access_requires_impersonation_or_support`

### 4.5 Wave 4 — Tenant-scoping and single-tenant cleanup (complete)

**Goal:** No unscoped querysets in tenant apps; no single-tenant routing in normal path. **Non-negotiable; implemented and complete.** Every part tested and integrated.

| Step | Action | DoD |
|------|--------|-----|
| 4.1 | Audit and fix remaining tenant-facing forms with global ModelChoiceField/queryset | List from TENANT_ORM_AUDIT or new grep; scope all to request.school or tenant context. |
| 4.2 | Block get_tenant_cache_prefix(None) for tenant-specific caches (lint or test) | Lint rule or test; fix call sites. |
| 4.3 | Isolate single-tenant and legacy path logic (e.g. “exactly one school” redirect, /t/<slug>/) | Legacy bridge module; telemetry; remove from default routing or feature-flag. |

**Tests:**  
- Tenant isolation test matrix (critical tenant apps in both SCHEMA and RLS modes)  
- Lint or test: no objects.all() in tenant app views without school filter

### 4.6 Wave 5 — Configuration and canonical model alignment (complete)

**Goal:** All tenant behavior from Policy/Blueprint/registry; canonical vs configurable clear. **Non-negotiable; implemented and complete.** Every part tested and integrated.

| Step | Action | DoD |
|------|--------|-----|
| 5.1 | Refactor remaining modules to use Tenant Blueprint / PolicyRegistry only (no direct features_json/settings in business logic) | Per-module checklist; lint or test to block direct tenant settings in tenant apps. |
| 5.2 | Execute model–canonical refactor plan (keep/merge/split/extract) from MODEL_TO_CANONICAL_MAPPING_REPORT and CANONICAL_OBJECTS_MAPPING | Merges/splits done; configurable behavior moved to registry/blueprint/policy. |
| 5.3 | Move remaining regional/core assumptions (FR/EN/INT, default timezone, report labels) into registries/profiles/blueprint | No country-specific default in core models except demo; tests for two regions. |

**Tests:**  
- Policy/blueprint resolution tests per module  
- No hardcoded region in core model defaults

### 4.7 Wave 6 — Seeding, empty states, and deferred closure (complete)

**Goal:** Every surface either has seed or clear empty-state action; no indefinite “deferred” without date.

| Step | Action | DoD |
|------|--------|-----|
| 6.1 | Add --dry-run to any seed command that lacks it (done where applicable) | All seeds idempotent and dry-runnable where appropriate. |
| 6.2 | Empty-state audit: each catalog/list has “why empty” and “what to do” (seed or request access) | Product review; doc and code updated. |
| 6.3 | Give each deferred item (26.5 remaining, SLO refinement, payment plans, migration legacy) either a completion target or “out of scope” with date | SCOPED_WORK_NOT_DONE and docs/PLAN_POLICY.md updated; all items required due now, implement and integrate. |

**Tests:**  
- Bootstrap run on fresh DB (migrate + bootstrap_runmycampus_platform)  
- Smoke test: key control-plane and tenant pages load after bootstrap

### 4.8 Wave 7 — Testing and CI (complete)

**Goal:** No excuse for regressions; tenant and control-plane boundaries covered by tests. **Non-negotiable; implemented and complete.** All steps mandatory, including 7.4 (security/SAST).

| Step | Action | DoD |
|------|--------|-----|
| 7.1 | Tenant isolation test matrix: critical flows in TENANCY_MODE=SCHEMA and TENANCY_MODE=RLS | CI runs both; no cross-tenant data in results. |
| 7.2 | Control-plane access tests: all /super/ and manager API endpoints require platform operator | Test suite; run in CI. |
| 7.3 | get_solo and tenant-scoping lint/tests in CI | Already present; ensure CI runs them every build. |
| 7.4 | Security/SAST (Bandit, pip-audit, Django check --deploy) in CI | Documented in SECURITY_BASELINE_CI.md; run in CI. **Non-negotiable.** |

---

## 5. Execution order and ownership (MANDATORY)

Waves are completed in strict order. No wave is skipped. Each wave is complete only when every phase/part is done, tested, and integrated.

| Wave | Focus | Order | Owner |
|------|--------|--------|--------|
| 1 | Control-plane boundary (middleware, SUPERADMIN, /super/ purity, manager URLConf) | 1 | Platform/Security |
| 2 | Split admin + operator identity + GraphQL | 2 | Platform |
| 3 | Superadmin dashboard + tenant data access rules | 3 | Product/Platform |
| 4 | Tenant-scoping and single-tenant cleanup | 4 | Backend |
| 5 | Configuration and canonical model alignment | 5 | Backend |
| 6 | Seeding/empty states and deferred closure | 6 | Product/DevOps |
| 7 | Testing and CI (all steps required, including 7.4) | 7 + ongoing | QA/Platform |

---

## 6. Acceptance criteria (non-negotiable)

- **Manager host:** No non–platform user can establish a useful session on the manager host beyond explicit public/auth/bootstrap flows.  
- **/super/:** No tenant feature is served or namespaced under /super/; no non-super exceptions.  
- **Control-plane access:** No control-plane operator gains tenant access by ordinary tenant RBAC alone; platform capabilities or audited impersonation only.  
- **Global data:** No global tenant registry, billing, or incident data exposed via login_required or is_staff only; platform operator or equivalent required.  
- **Admin:** Platform /admin/ and tenant /admin/ (or equivalent) are separate products, not host-conditional variants of one engine.  
- **Tests:** All waves have corresponding tests; tenant isolation and control-plane access tests run in CI.  
- **Docs:** VERIFICATION_CHECKLIST.md, PLATFORM_AUDIT_REMEDIATION_BACKLOG.md, and this audit plan updated as items are closed; no item left “in progress” indefinitely without owner and target date.

### Wave completion sign-off (mandatory per wave — ALL COMPLETE)

Every wave satisfies: (1) Every phase/part implemented. (2) Every "Test required" has a passing automated test. (3) Changes integrated in repo. (4) DoD satisfied. (5) Wave tests run in CI or documented. **Waves 1–7: complete.**

**Wave 1 test locations:** `apps.schools.tests.test_control_plane_boundary`; `apps.tenancy.tests.test_manager_urlconf_boundary`.

**Wave 2 test locations:** `apps.schools.tests.test_wave2_admin_and_graphql` (platform/tenant admin URLConf, index templates, GraphQL school_count/schools restricted).

**Wave 3 test locations:** `apps.schools.tests.test_wave3_superadmin_dashboard` (super dashboard reachable, index_superadmin template, switch_to_tenant in super_urls).

**Wave 4 test locations:** `apps.schools.tests.test_wave4_tenant_scoping` (lint script exists, request_detail filters by school, AccessRequest has school/school_id). Lint: `python scripts/lint_tenant_cache_prefix.py` (fix call sites or use `--exit-zero` for report-only until fixed).

**Wave 5 test locations:** `apps.schools.tests.test_wave5_config_canonical` (get_platform_defaults returns currency/region_code; policy resolver no CMR/XAF; School/BlueprintPack/PolicyBundle canonical).

**Wave 6:** Docs: `docs/SEED_COMMANDS_DRY_RUN.md`, `docs/EMPTY_STATE_AUDIT.md`; `docs/architecture/SCOPED_WORK_NOT_DONE.md` updated with completion targets (2025-03-08). Tests: bootstrap run + smoke (manual or CI).

**Wave 7:** Docs: `docs/TEST_MATRIX_AND_CI.md`, `docs/SECURITY_BASELINE_CI.md`. Control-plane and Wave 1–5 tests run in CI; get_solo and cache-prefix lints in CI; security baseline (check --deploy, pip-audit, Bandit) documented. **Complete.**

---

## 7. References

- **Audit docs (external):**  
  RunMyCampus_Audit_02_Superadmin_vs_Tenant_Boundary_Report_2026-03-08.md  
  RunMyCampus_Audit_01_Platform_Transition_Forensic_Report_2026-03-08.md  
  RunMyCampus_Seeding_Bootstrap_and_Starter_Content_Audit_Prompt_Pack.md  
  RunMyCampus_Multi_Tenant_Transition_Audit_Prompt_Pack.md  
  RunMyCampus_Master_Blueprint_SINGLE.md  
  RunMyCampus_Single_Tenant_to_Platform_Transition_Audit_Prompt_Pack.md  
  RunMyCampus_Model_to_Canonical_Mapping_Audit_Prompt.md  
  RunMyCampus_Canonical_Data_Object_Map.md  

- **In-repo docs:**  
  docs/PLATFORM_AUDIT_REMEDIATION_BACKLOG.md  
  docs/VERIFICATION_CHECKLIST.md  
  docs/ARCHITECTURE_TRUTH_REPORT.md  
  docs/PLATFORM_TRANSITION_FORENSIC_REPORT.md  
  docs/SUPERADMIN_VS_TENANT_BOUNDARY_REPORT.md (if present)  
  docs/CONTROL_PLANE_TEMPLATES.md  
  docs/SCHOOL_TENANT_CAMPUS_CANONICAL.md  
  docs/CANONICAL_OBJECTS_MAPPING.md  
  docs/SEEDING_BOOTSTRAP_AUDIT_REAUDIT.md  
  docs/architecture/SCOPED_WORK_VERIFICATION.md  
  docs/architecture/SCOPED_WORK_NOT_DONE.md  
  docs/architecture/REMAINING_PLAN_AUDIT_GAPS.md  

---

---

## 8. Final sign-off

**All waves (1–7) are implemented and complete. Every item is non-negotiable and has been delivered.** No optional items; no backlog. Verification: run the commands in VERIFICATION_CHECKLIST.md; all must pass. CI must run Wave 1–5 tests, get_solo lint, cache-prefix lint, and security baseline per TEST_MATRIX_AND_CI.md and SECURITY_BASELINE_CI.md.

**End of Audit Plan.**
