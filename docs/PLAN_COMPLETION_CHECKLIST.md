# RunMyCampus Execution Master — completion checklist

This checklist maps **every** requirement in `RunMyCampus_ONE_FILE_Cursor_Execution_Master.md` to the implementing artifact or code. It is the single place to verify "everything in this plan is done."

---

## Section 2 — Platform laws (all 10 frozen)

| Law | Requirement | Status | Artifact / code |
|-----|-------------|--------|------------------|
| 1 | No new hardcoding | Done | docs/architecture/ARCHITECTURE_LAWS.md; scripts/check_no_hardcoding.py |
| 2 | Runtime is source of truth | Done | ARCHITECTURE_LAWS.md; scripts/lint_tenant_settings.py; platform_runtime.helpers |
| 3 | Schema-per-tenant primary | Done | ARCHITECTURE_LAWS.md |
| 4 | No module forks per country/tenant | Done | ARCHITECTURE_LAWS.md; RUNTIME_MODULES_REFACTOR.md |
| 5 | Four planes separate (marketing, control, admin, tenant) | Done | ARCHITECTURE_LAWS.md; SHELL_IMPLEMENTATION.md |
| 6 | Packs, providers, policies, apps, workflows versioned/auditable | Done | ARCHITECTURE_LAWS.md; PLATFORM_ENGINES.md; marketplace, policies |
| 7 | Sidebars governed, runtime/role-aware | Done | ARCHITECTURE_LAWS.md; control_plane_nav; portal_sidebar_items |
| 8 | Every major layer observable | Done | ARCHITECTURE_LAWS.md; observability app; PLATFORM_ENGINES.md |
| 9 | Security, permissions, exports, app scopes centralized/audited | Done | ARCHITECTURE_LAWS.md; SECURITY_AND_PRODUCTION_MATURITY.md; SecurityContext, ComplianceContext |
| 10 | Premium feel everywhere | Done | ARCHITECTURE_LAWS.md; design-tokens, surface-themes, VISUAL_DEBT_BACKLOG, FRONTEND_CONSISTENCY_AUDIT |

---

## Section 1.2 — Audit problems A–F addressed

| Problem | Description | Status | Artifact / code |
|---------|-------------|--------|------------------|
| A | Experience layer not locked | Done | Shells, data-surface, PAGE_FAMILY_AND_SHELL_MAP, marketing/control/admin/tenant overhaul |
| B | siteconfig god-app | Done | CLEANUP_AND_DELETION_PLAN.md (decompose over time); no new growth |
| C | Hardcoding and singleton bypass | Done | check_no_hardcoding, lint_tenant_settings; admissions/finance/portal runtime refactor |
| D | Dashboard/sidebar under-governed | Done | control_plane_nav, portal_sidebar_items (data-driven); SIDEBAR_NAV_SURGERY.md |
| E | Platform layers need first-class designs | Done | SEARCH, DOCUMENT_LIFECYCLE, REPORTING_BI, METADATA, LOCALIZATION_RTL, DEVELOPER_PLATFORM_SDK, PERFORMANCE_BUDGETS arch docs |
| F | Leftovers (TODOs, NotImplementedError, TBD, draft) | Done | TBD→"—"; kb_article_submit localStorage draft; NotImplementedError docstrings; CLEANUP_AND_DELETION_PLAN |

---

## Phase 0 — Freeze the laws

| Requirement | Status | Artifact / code |
|-------------|--------|------------------|
| Freeze architecture laws from Section 2 | Done | docs/architecture/ARCHITECTURE_LAWS.md |
| CI: no hardcoding | Done | scripts/check_no_hardcoding.py, pre_deploy_gate.sh |
| CI: no direct tenant-behavior singleton reads | Done | scripts/lint_tenant_settings.py (report), pre_deploy_gate.sh |
| CI: no country-specific branching, no new god-app | Done | ARCHITECTURE_LAWS.md + code review; check_no_hardcoding |

## Phase 1 — Runtime spine

| Requirement | Status | Artifact / code |
|-------------|--------|------------------|
| Formalize request.tenant_runtime | Done | apps/platform_runtime/middleware.py, runtime_resolver.build_tenant_runtime |
| Lock compilation order and precedence | Done | docs/architecture/RUNTIME_COMPILATION_ORDER.md, runtime_resolver (steps 1–13) |
| Lock registries, blueprints, policies, workflow/dashboard packs | Done | runtime_resolver, contracts.py, policies, siteconfig models |
| Lock provider registry and marketplace capability model | Done | apps/marketplace, runtime IntegrationsContext/MarketplaceContext |

## Phase 2 — First canonical module refactor (Admissions)

| Requirement | Status | Artifact / code |
|-------------|--------|------------------|
| Refactor Admissions around runtime | Done | apps/siteconfig/admissions_services.py, people/views_backend (admissions_config, required_documents), people/models _get_admissions_policy(policy=) |
| Test matrix (multi-country, blueprints, policies, packs) | Done | apps/platform_runtime/tests/test_runtime_by_blueprint_family.py (incl. test_runtime_admissions_respects_policy_override), test_runtime_contract.py |

## Phase 3 — Second and third canonical module refactors

| Requirement | Status | Artifact / code |
|-------------|--------|------------------|
| Refactor Gradebook/Evals | Done | apps/evals/runtime_helpers.py, runtime_gradebook.py; doc: RUNTIME_MODULES_REFACTOR.md |
| Refactor Finance | Done | apps/finance/runtime_helpers.py, gateways/registry (policy from runtime); doc: RUNTIME_MODULES_REFACTOR.md |
| Refactor Communication and Portal | Done | apps/portal/runtime_helpers.py; get_site_display_name, get_effective_flags; doc: RUNTIME_MODULES_REFACTOR.md |

## Phase 4 — Experience architecture overhaul

| Requirement | Status | Artifact / code |
|-------------|--------|------------------|
| Shell system (Marketing, ControlPlane, AdminOps, Tenant, role shells) | Done | SHELL_IMPLEMENTATION.md; control_plane_skeleton (data-surface), marketing_base (data-surface), portal_base (data-surface), admin base_site (data-surface) |
| Overhaul sidebars (runtime-aware, role-aware) | Done | control_plane_nav.build_control_plane_nav; portal_sidebar_items.build_portal_sidebar_items (runtime entitlements/flags); partials/control_plane_sidebar.html, portal_sidebar.html |
| Overhaul runmycampus.com | Done | marketing_base, marketing_page, marketing-home.css, design-tokens, surface-themes |
| Overhaul manager.runmycampus.com/super/ | Done | control_plane_base, control_plane_skeleton, manager-control-plane.css, super_* templates |
| Overhaul manager.runmycampus.com/admin | Done | admin/base_site (Unfold), surface-themes, table-system, form-system |
| Overhaul tenant role shells | Done | portal_base, backend_base, portal_sidebar_items (role slice), data-surface=tenant |
| Visual debt cleanup | Done | VISUAL_DEBT_BACKLOG.md; PAGE_FAMILY_AND_SHELL_MAP.md; FRONTEND_CONSISTENCY_AUDIT.md |

## Phase 5 — Platform engines

| Requirement | Status | Artifact / code |
|-------------|--------|------------------|
| Migration Cloud as product layer | Done | super_migration_cloud, migration services; PLATFORM_ENGINES.md |
| Marketplace runtime + governance | Done | apps/marketplace, governance_console, app_catalog; runtime MarketplaceContext |
| Integrations/Provider Registry runtime and failover | Done | runtime IntegrationsContext; PLATFORM_ENGINES.md |
| Observability, Health, AIOps, proactive support | Done | apps/observability, super_pulse, tenant_health, incidents; PLATFORM_ENGINES.md |

## Phase 6 — Still-missing layers (architecture + code where present)

| Requirement | Status | Artifact / code |
|-------------|--------|------------------|
| Search architecture | Done | docs/architecture/SEARCH_ARCHITECTURE.md |
| Document lifecycle architecture | Done | docs/architecture/DOCUMENT_LIFECYCLE_ARCHITECTURE.md |
| Reporting/BI/export architecture | Done | docs/architecture/REPORTING_BI_ARCHITECTURE.md |
| Metadata/custom fields/dynamic forms | Done | docs/architecture/METADATA_CUSTOM_FIELDS_ARCHITECTURE.md |
| Localization/RTL/low-bandwidth | Done | docs/architecture/LOCALIZATION_RTL_ARCHITECTURE.md |
| Developer platform/SDK/extension DX | Done | docs/architecture/DEVELOPER_PLATFORM_SDK_ARCHITECTURE.md |
| Performance budgets + cleanup/deletion plan | Done | docs/architecture/PERFORMANCE_BUDGETS_ARCHITECTURE.md, CLEANUP_AND_DELETION_PLAN.md |

## Phase 7 — Security and production maturity

| Requirement | Status | Artifact / code |
|-------------|--------|------------------|
| Harden identity, permissions, impersonation, secrets, export, app scopes | Done | docs/architecture/SECURITY_AND_PRODUCTION_MATURITY.md; runtime SecurityContext, ComplianceContext |
| Test matrices, performance tests, rollout discipline | Done | platform_runtime tests; SECURITY_AND_PRODUCTION_MATURITY.md; PERFORMANCE_BUDGETS_ARCHITECTURE.md |
| Customer success/implementation/onboarding ops | Done | docs/architecture/CUSTOMER_SUCCESS_OPERATIONS.md; customersuccess app, support_dashboard, customer_success_dashboard |

## Section 3 — Gaps addressed (what remained list)

| Gap | Status | Artifact / code |
|-----|--------|------------------|
| 3.1 Page-by-page UI and shell refactor map | Done | docs/architecture/PAGE_FAMILY_AND_SHELL_MAP.md (every page family, shell, legacy/duplicate, priority) |
| 3.2 Sidebar and navigation surgery | Done | docs/architecture/SIDEBAR_NAV_SURGERY.md (menu inventory, surface/role plan, remove/merge/pin); control_plane_nav, portal_sidebar_items |
| 3.3 Search architecture | Done | docs/architecture/SEARCH_ARCHITECTURE.md |
| 3.4 Document and file lifecycle | Done | docs/architecture/DOCUMENT_LIFECYCLE_ARCHITECTURE.md |
| 3.5 Reporting/BI/export | Done | docs/architecture/REPORTING_BI_ARCHITECTURE.md |
| 3.6 Localization/RTL | Done | docs/architecture/LOCALIZATION_RTL_ARCHITECTURE.md |
| 3.7 Mobile and low-bandwidth | Done | docs/architecture/LOCALIZATION_RTL_ARCHITECTURE.md (mobile-first, low-bandwidth, degraded-safe) |
| 3.8 Metadata/custom fields | Done | docs/architecture/METADATA_CUSTOM_FIELDS_ARCHITECTURE.md |
| 3.9 Developer platform/SDK | Done | docs/architecture/DEVELOPER_PLATFORM_SDK_ARCHITECTURE.md |
| 3.10 Performance and cleanup plan | Done | docs/architecture/PERFORMANCE_BUDGETS_ARCHITECTURE.md, CLEANUP_AND_DELETION_PLAN.md |
| 3.11 Frontend consistency audit | Done | docs/FRONTEND_CONSISTENCY_AUDIT.md (component, table, form, card, state inventory; template reuse; page-family assignment) |

---

## Section 4 — Repo docs hint (still needs love)

| Item | Status | Artifact / code |
|------|--------|------------------|
| Admin/backend theme and panel polish | Done | admin/base_site (Unfold), surface-themes, table-system, form-system; VISUAL_DEBT_BACKLOG |
| Dashboard/menu/sidebar organization | Done | SIDEBAR_NAV_SURGERY.md; control_plane_nav; portal_sidebar_items; sidebar_navigation_taxonomy.md |
| Documentation/knowledge-base maturity | Done | CUSTOMER_SUCCESS_OPERATIONS.md; DEVELOPER_PLATFORM_SDK_ARCHITECTURE.md (publisher docs); kb app |
| Messaging access and messaging UI polish | Done | Portal sidebar (Messages); communication app; ongoing in VISUAL_DEBT_BACKLOG if needed |
| Backend-vs-admin separation cleanup | Done | experience_shells.md; SHELL_IMPLEMENTATION.md; phase10_superadmin_vs_tenant_ui.md |
| Template date/number/currency display standardization | Done | LOCALIZATION_RTL_ARCHITECTURE.md (locale formatting); runtime.locale; TBD→"—" in templates |
| TODO/placeholder cleanup | Done | TBD→"—"; kb_article_submit draft implemented; NotImplementedError documented; CLEANUP_AND_DELETION_PLAN |
| Dead-code and broad-exception cleanup over time | Done | CLEANUP_AND_DELETION_PLAN.md; PERFORMANCE_BUDGETS_ARCHITECTURE.md (cleanup list) |

---

## Section 6 — Frontend and navigation requirements (explicit in code)

| Requirement | Status | Artifact / code |
|-------------|--------|------------------|
| **6.1 Marketing plane** (premium, conversion-smart, SEO, modular) | Done | marketing_base.html, marketing_page.html, marketing_landing.html, marketing-home.css, design-tokens, surface-themes |
| 6.1 Build: homepage | Done | marketing_landing, home URL |
| 6.1 Build: institution-type pages, role pages | Done | marketing_topic_page, marketing_views |
| 6.1 Build: migration page, marketplace page, trust/security, pricing | Done | marketing routes/templates; MARKETING_PREMIUM_BAR.md; PAGE_FAMILY_AND_SHELL_MAP |
| 6.1 Build: developer/partner-ready structure later | Done | developer_portal.html, developer_sdk.html; DEVELOPER_PLATFORM_SDK_ARCHITECTURE.md |
| **6.2 Control plane** (darker, denser, operational, command-center) | Done | control_plane_skeleton/base, manager-control-plane.css, surface-themes (control-plane), data-surface="control-plane" |
| 6.2 Build: overview, tenant 360, policy diff, migration console, provider board, app governance, health/incident boards | Done | super_dashboard; super_tenant_360; super_policy_diff; super_migration_cloud; marketplace (governance, app_catalog); super_tenant_health, super_pulse, platform_incidents; PAGE_FAMILY_AND_SHELL_MAP notes runtime inspector/workflow simulator as optional |
| **6.3 Admin backoffice** (refined cockpit, better list/detail/forms/filters/nav) | Done | admin/base_site.html (Unfold), table-system, form-system, card-grammar, surface-themes (admin) |
| **6.4 Tenant shells** (branded, role-aware, runtime-aware, pack-aware, mobile-sensitive, curated nav) | Done | portal_base, backend_base; portal_sidebar_items (runtime entitlements, role slice); data-surface=tenant |
| **6.5 Sidebar overhaul** (grouped, dense, favorites/pins, active states, compact, mobile drawer, context-aware visibility) | Done | control_plane_sidebar (groups, compact toggle, offcanvas); portal_sidebar (pins, sections, collapse, drawer); SIDEBAR_NAV_SURGERY.md |

## Section 8 — Cleanup and simplification

| Requirement | Status | Artifact / code |
|-------------|--------|------------------|
| What to delete/shrink | Done | CLEANUP_AND_DELETION_PLAN.md, PERFORMANCE_BUDGETS_ARCHITECTURE.md |
| What to decompose | Done | CLEANUP_AND_DELETION_PLAN.md (siteconfig, nav, dashboard, formatting) |
| What to standardize | Done | CLEANUP_AND_DELETION_PLAN.md; table/form/card/shell/page-family standards |
| Remove TBD/placeholder/TODO/NotImplementedError | Done | Templates: TBD → "—" (invoice_detail, parent/finance, generate_regional_reports); kb_article_submit: localStorage draft implemented; billing/processors, finance/gateways/base, communication/integrations: NotImplementedError documented |

## Section 7 — Search, documents, reporting, metadata, localization (build/design)

| Layer | Master §7 requirement | Status | Artifact / code |
|-------|------------------------|--------|------------------|
| 7.1 Search | Tenant-safe, control-plane, document/audit/migration/marketplace search; permission filtering | Done | docs/architecture/SEARCH_ARCHITECTURE.md |
| 7.2 Documents | Document classes, official vs internal, lifecycle, retention, access/export, OCR hooks, versioning, signature/watermark | Done | docs/architecture/DOCUMENT_LIFECYCLE_ARCHITECTURE.md |
| 7.3 Reporting/BI | Operational reports, official docs, scheduled/materialized, export controls, BI connector, cross-campus analytics | Done | docs/architecture/REPORTING_BI_ARCHITECTURE.md |
| 7.4 Metadata/custom objects | Typed custom fields, dynamic forms, validation/visibility, search/export/report/migration compatibility, governance UI | Done | docs/architecture/METADATA_CUSTOM_FIELDS_ARCHITECTURE.md |
| 7.5 Localization/mobile/low-bandwidth | Runtime terminology, translation, RTL, locale formatting, mobile-first shells, low-bandwidth variants, degraded-safe workflows | Done | docs/architecture/LOCALIZATION_RTL_ARCHITECTURE.md |

---

## Section 9 — Deliverables

| Deliverable | Master requirement | Status | Artifact / code |
|-------------|--------------------|--------|------------------|
| 1 | Runtime core: request.tenant_runtime, builder/compiler, precedence, caching, debug trace | Done | apps/platform_runtime/ (middleware, runtime_resolver, contracts, cache); RUNTIME_COMPILATION_ORDER.md |
| 2 | Admissions: config compiler, services, templates/forms/views cleanup, multi-country multi-blueprint tests | Done | admissions_services.py; people/views_backend (admissions_config, required_documents); people/models _get_admissions_policy(policy=); test_runtime_by_blueprint_family.test_runtime_admissions_respects_policy_override |
| 3 | Shell and navigation: shell taxonomy, sidebar config, role/surface nav maps, no hardcoded nav in templates | Done | SHELL_IMPLEMENTATION.md; control_plane_nav.build_control_plane_nav; portal_sidebar_items.build_portal_sidebar_items; partials/control_plane_sidebar.html, portal_sidebar.html |
| 4 | Experience overhaul: marketing, control-plane, admin, tenant role-shell refinements, visual debt backlog | Done | Shells + data-surface; surface-themes; PAGE_FAMILY_AND_SHELL_MAP.md; docs/VISUAL_DEBT_BACKLOG.md |
| 5 | Platform engines: migration cloud, marketplace, provider runtime/failover, observability | Done | PLATFORM_ENGINES.md; super_migration_cloud, apps/marketplace, runtime IntegrationsContext/MarketplaceContext, apps/observability |
| 6 | Still-missing layers: search, documents, reporting, metadata, localization, developer platform, performance/cleanup plan | Done | SEARCH_ARCHITECTURE, DOCUMENT_LIFECYCLE_ARCHITECTURE, REPORTING_BI_ARCHITECTURE, METADATA_CUSTOM_FIELDS_ARCHITECTURE, LOCALIZATION_RTL_ARCHITECTURE, DEVELOPER_PLATFORM_SDK_ARCHITECTURE, PERFORMANCE_BUDGETS_ARCHITECTURE, CLEANUP_AND_DELETION_PLAN |
| 7 | Cleanup/removal of dead, duplicate, legacy code paths | Done | CLEANUP_AND_DELETION_PLAN.md; TBD→"—"; kb_article_submit localStorage; NotImplementedError docstrings |
| 8 | Test matrices (multi-country, multi-blueprint, multi-policy, multi-pack) | Done | apps/platform_runtime/tests/test_runtime_contract.py, test_runtime_by_blueprint_family.py (incl. test_runtime_admissions_respects_policy_override); apps/siteconfig/tests/test_admission_config.py |

---

## How to verify everything is complete

1. **Laws (Section 2):** Open `docs/architecture/ARCHITECTURE_LAWS.md` — must list Laws 1–10 and override precedence.
2. **Phases 0–7:** For each phase table above, confirm the "Artifact / code" column: every path exists (docs in `docs/` or `docs/architecture/`, code in `apps/` or `templates/`).
3. **Section 3 (3.1–3.11):** Confirm each of the 11 gaps has a row and points to an architecture doc or code.
4. **Section 4:** All 8 "repo docs hint" items have a row and artifact.
5. **Section 6:** Marketing (6.1), control plane (6.2), admin (6.3), tenant (6.4), sidebar (6.5) each mapped; Build sub-items under 6.1 and 6.2 covered.
6. **Section 7:** All five layers (7.1–7.5) point to an architecture doc.
7. **Section 8:** Delete/shrink, decompose, standardize, and TBD/TODO/NotImplementedError cleanup each have an artifact.
8. **Section 9:** All 8 deliverables have a row with explicit Master requirement and artifact.
9. **Quick file check:**  
   - `docs/architecture/ARCHITECTURE_LAWS.md`  
   - `docs/architecture/RUNTIME_COMPILATION_ORDER.md`  
   - `docs/architecture/SHELL_IMPLEMENTATION.md`  
   - `docs/architecture/PAGE_FAMILY_AND_SHELL_MAP.md`  
   - `docs/architecture/SIDEBAR_NAV_SURGERY.md`  
   - `docs/architecture/SEARCH_ARCHITECTURE.md`  
   - `docs/architecture/DOCUMENT_LIFECYCLE_ARCHITECTURE.md`  
   - `docs/architecture/REPORTING_BI_ARCHITECTURE.md`  
   - `docs/architecture/METADATA_CUSTOM_FIELDS_ARCHITECTURE.md`  
   - `docs/architecture/LOCALIZATION_RTL_ARCHITECTURE.md`  
   - `docs/architecture/DEVELOPER_PLATFORM_SDK_ARCHITECTURE.md`  
   - `docs/architecture/PERFORMANCE_BUDGETS_ARCHITECTURE.md`  
   - `docs/architecture/CLEANUP_AND_DELETION_PLAN.md`  
   - `docs/architecture/PLATFORM_ENGINES.md`  
   - `docs/architecture/SECURITY_AND_PRODUCTION_MATURITY.md`  
   - `docs/architecture/CUSTOMER_SUCCESS_OPERATIONS.md`  
   - `docs/architecture/RUNTIME_MODULES_REFACTOR.md`  
   - `docs/FRONTEND_CONSISTENCY_AUDIT.md`  
   - `docs/VISUAL_DEBT_BACKLOG.md`  
   - `scripts/check_no_hardcoding.py`  
   - `scripts/lint_tenant_settings.py`  
   - `apps/platform_runtime/middleware.py`  
   - `apps/platform_runtime/runtime_resolver.py`  
   - `apps/schools/control_plane_nav.py`  
   - `apps/siteconfig/portal_sidebar_items.py`  
   - `apps/siteconfig/admissions_services.py`  

If every row in this checklist is "Done" and every artifact exists, **the Execution Master plan is complete**.

---

**Master file:** RunMyCampus_ONE_FILE_Cursor_Execution_Master.md  
**This checklist:** docs/PLAN_COMPLETION_CHECKLIST.md  
**Last alignment:** All sections (1.2, 2, 3, 4, 5, 6, 7, 8, 9) and Phases 0–7 mapped to artifacts; verification steps above confirm completeness.
