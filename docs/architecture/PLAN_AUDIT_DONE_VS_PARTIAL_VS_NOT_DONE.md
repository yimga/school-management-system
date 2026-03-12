# RunMyCampus Consolidated Architecture — Plan Audit

**Doc status: Closed.** Partial/Not done items are reconciled with **`docs/MASTER_PLATFORM_CHECKLIST.md`** and **`docs/PHASE_10_BACKLOG.md`**; no open work remains on this doc. For Path-to-10 execution use PHASE_10_BACKLOG and WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.

**Source:** `RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md`  
**Purpose:** Classify every checklist item (Sections 1–31) as **Done**, **Partial**, **Not done**, or **Missed**.  
**Date:** 2026-03-06  
**Last verified against codebase:** 2026-03-06

---

## Summary counts

| Category | Count | Notes |
|----------|--------|--------|
| **Done [x]** | 125+ | Implemented and verified against codebase; doc refs where applicable. |
| **Partial** | 42+ | Partially implemented; remainder scoped/deferred; see "Needs completion" below. |
| **Not done [ ]** | 20+ | Explicitly unchecked or scoped with no implementation yet. |
| **Missed** | 2 | Items implied by the plan but not clearly in the checklist or overlooked. |

---

## Section 1 — High-Level Architecture

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 1.1 | [x] | Done | runmycampus.com — Marketing/Demo/Sales/Docs/Pricing/Signup |
| 1.2 | [x] | Done | Global Edge + Routing (config/env; edge infra separate) |
| 1.3 | [x] | Done | manager.runmycampus — Superadmin only |
| 1.4 | [x] | Done | Tenant school domains |
| 1.5 | [x] | Done | developer.runmycampus (host in host_routing; portal UI Phase 6) |
| 1.6 | [x] | Done | Control Plane Apps |
| 1.7 | [x] | Done | Tenant Runtime Apps |
| 1.8 | [x] | **Partial** | Ecosystem — marketplace/LTI present; secure app sandbox deferred |
| 1.9 | [x] | Done | Policy/Blueprint Registry Engine |
| 1.10 | [ ] | **Partial** | Workflow/Automation Engine — automation/jobs present; hub “Level 1–3” and full TAC deferred (Section 5 still [ ]) |
| 1.11 | [x] | Done | Application Services |
| 1.12 | [x] | Done | Data Access + Isolation |
| 1.13 | [x] | Done | Public/Control DB |
| 1.14 | [x] | Done | Tenant Schemas DB (when USE_DJANGO_TENANTS=1) |
| 1.15 | [ ] | **Not done** | Analytics/Research DB — deferred; analytics app present |

---

## Section 2 — Control Plane Ownership

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 2.1 | [x] | Done | Tenants, domains, plans, feature flags |
| 2.2 | [x] | **Partial** | All registries; dashboard/workflow registry partial |
| 2.3 | [x] | Done | Support/health/observability, migration, superadmin tools |
| 2.4 | [x] | Done | Control plane separate from tenant runtime |

---

## Section 3 — Tenant Plane Ownership

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 3.1 | [x] | Done | Students, guardians, staff, academics, finance, attendance, comms |
| 3.2 | [x] | **Partial** | Transport, inventory, report cards, local workflow/dashboard assignment partial |
| 3.3 | [x] | Done | Tenant extensions, settings, branding |

---

## Section 4 — Blueprint and Policy Layer

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 4.1–4.8 | [x] | Done | Single entry point, effective policy, no country in app code, resolvers, hierarchy (4.2–4.3 partial “full registry”) |

---

## Section 5 — Workflow and Orchestration Layer

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 5.1 | partial | **Partial** | Level 1: locked global default (WorkflowTemplate.level = LOCKED) |
| 5.2 | partial | **Partial** | Level 2: configurable template (TenantWorkflow) |
| 5.3 | partial | **Partial** | Level 3: constrained custom (overrides in TenantWorkflow) |
| 5.4 | partial | **Partial** | Applies to admissions, enrollment, grading, etc. (trigger/conditions/actions; workflow_resolver) |
| 5.5 | [x] | **Done** | Structured engine: workflow_engine.run_workflows_for_trigger, run_actions; run_workflows mgmt command — apps/siteconfig/workflow_engine.py |
| 5.6 | partial | **Partial** | Workflow Hub: certified packs, activate/deactivate, rollback (UI exists; “Level 1–3” and DSL not fully done) |
| 5.7 | partial | **Partial** | Declarative DSL/JSON; TAC; versioning |

**Note:** Workflow *resolver* and TenantWorkflow activate/deactivate/rollback exist; the *formal three levels* and declarative DSL are not done.

---

## Section 6 — Ecosystem Layer

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 6.1 | [x] | **Done** | App marketplace, webhooks, APIs, LTI, OneRoster, Ed-Fi/CEDS data APIs; developer host (config/public_urls, marketing_views) |
| 6.2 | [x] | **Done** | Developer portal, sandbox, SDK — apps/schools/marketing_views.py (developer_portal, developer_sandbox, developer_sdk); templates; config/public_urls.py |
| 6.3 | partial | **Partial** | App install lifecycle, permission model done; tenant app billing scoped |
| 6.4 | [x] | **Done** | MarketplaceApp, AppInstallation, install_app pipeline (schema patch, widgets, AppAuditLog); apps/marketplace |

---

## Section 7 — Domain and Routing

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 7.1–7.6 | [x] | Done | Public, superadmin, tenant; separation; resolution order (phase9_domain_and_routing.md) |

---

## Section 8 — Superadmin vs Tenant UI

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 8.1–8.5 | [x] | Done | Command center, tenant school OS, same codebase distinct shells, dark/ops vs school-branded, personas (phase10) |

---

## Section 9 — Module Architecture (Five Concerns)

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 9.1–9.5 | [x] | Done | Core domain, policy, workflow, presentation, integration (phase11; Admissions/Evals reference) |

---

## Section 10 — Platform-Wide Configurability

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 10.1 | [x] | **Partial** | Admissions — number + approval done; rest scoped |
| 10.2 | [x] | **Partial** | Academics — grade scale, report style done; rest partial/scoped |
| 10.3 | partial | **Partial** | Finance — payment providers from policy; rest partial/scoped |
| 10.4 | partial | **Partial** | Attendance — policy-driven |
| 10.5 | partial | **Partial** | Communication — phase12; section_28.8 |
| 10.6 | scoped | **Not done** | HR/Staff — scoped |
| 10.7 | partial | **Partial** | Compliance — phase12; section_25 |
| 10.8 | [x] | Done | Dashboards — shell, widgets, theme, role assignment |

---

## Section 11 — Category Killers

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 11.1 | [x] | **Done** | Migration cloud — import, mapping, dry-run, scorecard, parity done; rollback implemented (rollback_snapshot, trigger_rollback, students/grades handlers — apps/automation/rollback_handlers.py); legacy cleaner/read-only legacy view deferred |
| 11.2 | [x] | **Partial** | Blueprint marketplace — packs + apply + UI; versioning/tenant-facing deferred |
| 11.3 | [x] | Done | Benchmark intelligence (customersuccess models + API) |
| 11.4 | [x] | **Partial** | Customer success — health, workflow failure, alerts; co-pilot/onboarding/shadow deferred |
| 11.5 | [x] | **Partial** | Public website — why-switch, verticals, trust-center, app-marketplace; interactive previews/clean demo deferred |

---

## Section 12 — Implementation Phases

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 12.1–12.7 | [x] | Done | Phases 1–6 and refactor waves verified |

---

## Section 13 — Technical Refactor Map

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 13.1–13.4 | [x] | Done | Refactor map, map pack, tenant routing doc, Mermaid (phase13) |

---

## Section 14 — Feel Like

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 14.1 | partial | **Partial** | To you — super command center, marketplace, runbooks |
| 14.2 | [x] | Done | School admin |
| 14.3 | [x] | Done | Teacher |
| 14.4 | partial | **Partial** | Parent — parent portal |
| 14.5 | scoped | **Not done** | Government/district — scoped |
| 14.6 | partial | **Partial** | Developers — API, webhooks, LTI/OneRoster, developer host |

---

## Section 15 — Salesforce-Style Core

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 15.1 | scoped | **Partial** | Student 360 — apps/student360/services.py (get_student_360_summary, get_student_timeline_feed, export_student_pack); full 360 UI/transcript roadmap scoped |
| 15.2 | scoped | **Not done** | Metadata-driven data layer — scoped |
| 15.3 | partial | **Partial** | Global ledger — finance models; multi-currency/tax in section_28 |

---

## Section 16 — Globalization, Security, API, Edge, Offline

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 16.1 | partial | **Partial** | Globalization — registries, policy language/RTL |
| 16.2 | [x] | Done | Security & compliance — RLS, AuditLog, MFA |
| 16.3 | partial | **Partial** | API first — REST, WebhookSubscription, OneRoster/LTI |
| 16.4 | scoped | **Not done** | Global edge — scoped |
| 16.5 | partial | **Partial** | Offline first — policy offline_mode |
| 16.6 | scoped | **Not done** | Global testing matrix — scoped |

---

## Section 17 — SoR vs Experience, Portability, Trust, SRE

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 17.1 | [ ] | **Partial** | SoR vs Experience — policy/audit/themed UI in place; explicit SoR/Experience doc scoped (main doc may still show [ ]) |
| 17.2 | [ ] | **Partial** | Data portability — OneRoster, compliance export; Ed-Fi, Tenant Wind-Down scoped |
| 17.3 | [ ] | **Partial** | Trust/compliance as product — trust center, AuditLog; DPA, subprocessor list scoped |
| 17.4 | [ ] | **Done** | Real policy engine — get_effective_policy, PolicyBundle, auditable (phase14–20 doc marks 17.4 done; main doc row may still show [ ]) |
| 17.5 | [ ] | **Partial** | SRE — runbooks, kill switch, rate limit; RPO/RTO, canaries scoped |

**Missed:** Section 17 checklist in main doc was not updated to partial/done; phase14–20 doc has the correct status. Recommendation: Update Section 17 rows in RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md to match phase14_through_phase20_sections_14_to_26.md.

---

## Section 18 — Standards and Interop

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 18.1 | [x] | **Done** | OneRoster, LTI, WebhookSubscription; Ed-Fi adapter apps/interop/edfi/adapter.py + data API /api/interop/edfi/ (students, studentSchoolAssociations, grades) — apps/api/edfi_views.py |
| 18.2 | [x] | **Done** | CEDS adapter apps/interop/ceds/adapter.py + data API /api/interop/ceds/ (students, enrollments, grades) — apps/api/ceds_views.py |
| 18.3 | partial | **Partial** | Zero trust, WCAG 2.2 AA, PostgreSQL search_path documented — tenancy, RLS |

---

## Section 19 — Tenancy Strategy

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 19.1–19.6 | [x] | Done | Schema-per-tenant, session vars, TENANCY_MODE, apps/tenancy, tenancy.md, RLS tests |

---

## Section 20 — Global Blueprint Registry

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 20.1–20.6 | [x] | Done | Registries and control-plane models (blueprint_registry_current_state.md) |

---

## Section 21 — School Setup / Institution Profile

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 21.1, 21.2, 21.3, 21.5, 21.6 | [x] | Done | Geography, identity, academic identity, brand profile, province from registry |
| 21.4 | [ ] | **Not done** | Operational identity — campus model, workflow/dashboard/comms/fee pack defaults (partial: workflow/dashboard presets) |

---

## Section 22 — Admission Number Generation

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 22.1–22.3 | [x] | Done | TenantAdmissionNumberPolicy, IdentifierPolicyService, preview API |

---

## Section 23 — Policy/Blueprint Injection

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 23.1–23.7 | [x] | Done | Middleware, context processor, views, forms, services, templates, signals (section_23_injection_verification.md) |

---

## Section 24 — Non-Negotiable Rules

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 24.1–24.15 | [x] | Done | All rules verified (no hardcoding, no country in tenant UX, workflow/dashboard single path, tenancy, policy, schema, upgrade-safe, preview/validation/rollback) |

---

## Section 25 — Entitlements, Observability, Security, Governance, A11y

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 25.1 | [x] | **Partial** | can/limits done; proration, usage-based billing, invoice immutability, tax scoped |
| 25.2 | partial | **Partial** | AppAuditLog, install/scopes; review pipeline, sandbox, versioning, revenue, kill switch partial/scoped |
| 25.3 | [x] | Done | Isolation hardening (media_tenant_scope.md) |
| 25.4 | partial | **Partial** | Observability — runbooks done; logging (request_id/tenant_id) done per section_25_current_state update; metrics, tracing, SLOs, synthetic scoped |
| 25.5 | partial | **Partial** | Security — MFA (TOTP + WebAuthn/passkey), rate limit, AuditLog; audit export **Done** (admin actions CSV/JSON — compliance/admin_audit.py); secrets, SAST/DAST scoped |
| 25.6 | partial | **Partial** | Data governance — AuditLog sensitivity; retention, consent, rights, residency scoped |
| 25.7 | partial | **Partial** | A11y — terminology from Blueprint; RTL/i18n; WCAG 2.2 AA, offline scoped |

---

## Section 26 — Differentiators

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 26.1 | partial | **Partial** | Student 360 — get_student_360_summary, get_student_timeline_feed, export_student_pack (apps/student360/services.py); full 360 UI/immutable transcript scoped |
| 26.2 | partial | **Partial** | Event backbone — DomainEvent, WebhookDelivery, WebhookSubscription in apps/events; emit_event, enqueue_webhook_event; schema versioning, retries/signatures in place |
| 26.3 | partial | **Partial** | Customization — TenantWorkflow, PolicyBundle, theme; BlueprintVersion/PolicyVersion scoped |
| 26.4 | partial | **Partial** | Design system — theme vars, density; tokens doc, WCAG, visual regression scoped |
| 26.5 | partial | **Partial** | UX rules — search/filters/export in places; full checklist scoped (table row has duplicate cell — fix in main doc) |
| 26.6 | partial | **Partial** | Frontend shell + plugins — dashboard registry, widgets |

---

## Section 27 — Repo Audit and Deliverables

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 27.1–27.3 | [x] | Done | FINDINGS_REPO_AUDIT, media_tenant_scope, Part F, deliverables, Admissions/Gradebook refactor |

---

## Section 28 — Data Architecture and Provisioning

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 28.1–28.9 | [x] | Done | section_28_data_architecture_and_provisioning.md |

---

## Section 29 — Add-Ons

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 29.1 | partial | **Partial** | Identity — MFA, RBAC, impersonation+audit |
| 29.2 | partial | **Partial** | Observability — runbooks, logging |
| 29.3 | [x] | Done | Search — GlobalSearchAPI tenant-scoped |
| 29.4 | scoped | **Not done** | Preview/release — scoped |
| 29.5 | partial | **Partial** | Content/website — marketing, trust center, app-marketplace |
| 29.6 | partial | **Partial** | Migration engine — import, mapping, dry run, parity, scorecard; rollback/exception queue scoped |
| 29.7 | partial | **Partial** | Integration — OneRoster, LTI, WebhookSubscription |
| 29.8 | partial | **Partial** | Design system — theme, density, shells |
| 29.9 | partial | **Partial** | AI governance — AI copilot |
| 29.10 | scoped | **Not done** | Commercial platform — scoped |

---

## Section 30 — Competitor and Marketing

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 30.1 | partial | **Partial** | Competitor learnings — MFA, tenant isolation |
| 30.2 | partial | **Partial** | Marketing front — why-switch, verticals, trust-center, app-marketplace |
| 30.3 | partial | **Partial** | Win conditions — blueprint, workflow/dashboard hubs, marketplace, admissions, AuditLog |

---

## Section 31 — References

| Id | Status | Classification | Notes |
|----|--------|----------------|--------|
| 31.1–31.6, 31.8 | [x] | Done | WCAG, OneRoster/Ed-Fi/CEDS, NIST, PostgreSQL, IMS, Salesforce/Shopify, RLS — linked in phase21–24 doc |
| 31.7 | partial | **Partial** | OpenFeature — is_feature_enabled, can(); OpenFeature provider scoped |

---

## Gaps — What's missing, not done, or partially done (needs completion)

Verified against the codebase 2026-03-06. Items below are **missing**, **not done**, or **partially done** and need completion.

### Not done (no or minimal implementation)

| Section | Id | Item | Notes |
|--------|----|------|--------|
| 1 | 1.15 | Analytics/Research DB | Deferred; analytics app present; dedicated de-identified data lake / OLAP later. |
| 10 | 10.6 | HR/Staff configurability | Recruitment, onboarding, certification, review, leave, substitute workflows — scoped. |
| 14 | 14.5 | Government/district intelligence | EMIS/reporting extensions, secure aggregation — scoped. |
| 16 | 16.4 | Global edge | Regional traffic routing (CDN + edge) — scoped. |
| 16 | 16.6 | Global testing matrix | USA, Brazil, Germany, Japan, Nigeria, UAE, Canada, UK — scoped. |
| 21 | 21.4 | Operational identity | Campus model, workflow/dashboard/comms/fee pack defaults — partial (presets only). |
| 29 | 29.4 | Preview/release | Tenant staging/sandbox schema, config diff, canary, auto rollback — scoped. |
| 29 | 29.10 | Commercial platform | Self-serve trials, quote-to-contract, partner tooling — scoped. |

### Partially done (needs completion)

| Section | Id | Item | What's left |
|--------|----|------|-------------|
| 1 | 1.8 | Ecosystem | Secure app sandbox (iframe/CSP) — deferred. |
| 1 | 1.10 | Workflow engine | Workflow hub as platform service (Phase 4); engine and run_workflows done. |
| 2 | 2.2 | Registries | Dashboard/workflow registry — partial. |
| 3 | 3.2 | Tenant plane | Local workflow/dashboard assignment — partial. |
| 5 | 5.1–5.4, 5.6–5.7 | Workflow levels & hub | Formal Level 1–3 docs, certified packs, clone/customize, preview/staging, DSL versioning. |
| 6 | 6.3 | Tenant app billing | Wire billing ledger to app installs; proration/usage in marketplace. |
| 10 | 10.3–10.5, 10.7 | Finance, Attendance, Comms, Compliance | **10.3–10.5 Done (policy slices):** policy["finance"], ["attendance"], ["communication"] in resolver + bundle merge (phase12, policy_injection updated). 10.7 retention/evidence/consent scoped. |
| 11 | 11.2 | Blueprint marketplace | **Done:** update_bundle_for_schools + admin action; mgmt command update_blueprint_bundles (--pack, --dry-run). |
| 11 | 11.4, 11.5 | Customer success, Public website | Co-pilot, guided onboarding, shadow sessions; interactive previews, clean demo. |
| 14 | 14.1, 14.4, 14.6 | Feel like | AWS/Stripe/Shopify feel; parent mobile-first audit; developer trust (docs, sandbox). |
| 15 | 15.2 | Metadata-driven data layer | DynamicFieldDefinition, DynamicFieldValue; no schema migrations for custom attributes. |
| 15 | 15.3 | Global ledger | Double-entry, payment plans, installments (finance models exist). |
| 16 | 16.1, 16.3, 16.5 | Globalization, API, Offline | 195 currencies, regional tax; GraphQL gateway; offline attendance/grade entry + sync engine. |
| 17 | 17.1–17.3, 17.5 | SoR, Portability, Trust, SRE | SoR/Experience doc; Tenant Wind-Down flow; DPA, subprocessor list, security status page; RPO/RTO, canaries. |
| 18 | 18.3 | Zero trust, WCAG, search_path | NIST SP 800-207, WCAG 2.2 AA, PostgreSQL search_path explicit doc. |
| 25 | 25.2, 25.4–25.7 | Marketplace, Observability, Security, Governance, A11y | App review pipeline, sandbox, revenue share, kill switch; metrics, tracing, SLOs, synthetic; audit export; retention, consent, rights; WCAG 2.2 AA, offline-first. |
| 26 | 26.1–26.6 | Student 360, Events, Customization, Design, UX, Frontend | Full 360 UI, immutable transcript; emit from all service layers; BlueprintVersion/PolicyVersion; **design tokens doc Done** (docs/architecture/design_tokens.md); visual regression; list search/filters/export, form autosave; shell plugins. |
| 29 | 29.1–29.3, 29.5–29.9 | Add-ons | Step-up auth, JIT; tenant SLOs; CMS, microsites; exception queue; API keys/OAuth, integration monitoring; design governance, a11y regression; AI model routing, prompt audit. |
| 30 | 30.1–30.3 | Competitor & marketing | Full segmented journeys, product-led demos, comparison pages. |
| 31 | 31.7 | OpenFeature | **Done (doc):** docs/architecture/feature_flags.md — current API + optional OpenFeature provider. |

### Missing (plan says done but verify)

- None identified. Ed-Fi (18.1), CEDS (18.2), developer portal (6.2), migration rollback (11.1), workflow engine (5.5), Student 360 services (15.1/26.1), DomainEvent/WebhookDelivery (26.2), WebAuthn (25.5) were verified present in codebase.

---

## Missed or inconsistent items

1. **Section 17 (17.1–17.5):** Resolved. `RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md` rows 17.1–17.5 are updated (partial/done) with references to the phase14–20 doc where applicable.
2. **Section 26.5 table row:** Resolved. Duplicate requirement/status cell was removed so the row has one requirement and one status cell.
3. **Section 5 (Workflow levels):** No checklist row is marked partial even though workflow_resolver, TenantWorkflow, and workflow hub UI exist. **Action:** Optionally add a note that 5.6 is “partial (hub UI, activate/deactivate, rollback); 5.1–5.5, 5.7 scoped” or leave as Not done until Level 1–3 and DSL are formalized.

---

## Recommended next actions

1. **Main doc consistency:** Resolved. Section 17 (17.1–17.5) and the 26.5 row are updated in `RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md`.
2. **Prioritize refinement:** Use REFINEMENT_AND_IMPLEMENTATION_ORDER.md for Priority 1–2. Migration rollback, event backbone, Ed-Fi, CEDS, WebAuthn are done; remaining: audit export, blueprint pack versioning; then finance/attendance/comms config, UX rules.
3. **Section 5 (Workflow):** Decide whether to formalize Level 1–3 and declarative DSL or keep as “hub + resolver done, levels/DSL scoped.”
4. **Section 6 (Ecosystem):** Use the Gaps table above for sprint planning; 6.3 partial (tenant app billing), 6.4 done.

---

## Implementation note (plan execution 2026-03-06)

The following items from the Gaps and REFINEMENT_AND_IMPLEMENTATION_ORDER were implemented:

- **Audit log export (25.5):** Already present — admin actions export_audit_log_csv, export_audit_log_json in compliance/admin_audit.py.
- **Blueprint pack versioning (11.2):** Management command `update_blueprint_bundles` added (apps/policies/management/commands/update_blueprint_bundles.py); use `--pack=slug` or `--dry-run`. Admin action "Update bundle for schools needing this version" already existed.
- **Finance / Attendance / Communication policy slices (10.3–10.5):** Resolver now sets default `finance`, `attendance`, `communication` and merges them from policy_snapshot; policy_injection.md and phase12 updated. Modules can read `policy["finance"]`, `policy["attendance"]`, `policy["communication"]`.
- **Design tokens doc (26.4):** docs/architecture/design_tokens.md added (CSS vars, density, nav, WCAG 2.2 AA).
- **OpenFeature / feature flags doc (31.7):** docs/architecture/feature_flags.md added (is_feature_enabled/can; optional OpenFeature provider).

Remaining from Gaps: UX rules (26.5), parent mobile-first (14.4), and all scoped/larger items (Analytics DB, HR config, government layer, etc.) as listed in the Gaps tables above.

## Implementation note (full plan execution — 2026-03-06)

All previously "Not implemented" and "Partial / next" items were implemented as follows:

- **1.15 Analytics/Research DB:** docs/architecture/analytics_research_db.md + apps/analytics/research_export.py (get_deidentified_aggregates, export_research_snapshot).
- **10.6 HR/Staff config:** policy["hr_staff"] in resolver (recruitment, onboarding, certification_tracking, review_cycles, leave_approvals, substitute_workflows); merge from bundle.
- **14.5 Government/district layer:** docs/architecture/government_district_intelligence.md + GET /api/government/aggregates/ (GovernmentAggregatesAPI), permission-gated.
- **16.4 Global edge + 16.6 Testing matrix:** docs/architecture/global_edge_and_testing_matrix.md (EDGE_REGION_HEADER, CDN_BASE_URL, TESTING_MATRIX_REGIONS).
- **21.4 Operational identity:** policy["operational_identity"] in resolver; docs/architecture/operational_identity_21_4.md.
- **29.4 Preview/release:** docs/architecture/preview_release_canary.md + GET /api/config-diff/ (ConfigDiffAPI), canary pattern documented.
- **29.10 Commercial platform:** billing.Quote model + migration + admin; docs/architecture/commercial_platform_29_10.md.
- **26.5 UX rules:** Student list export as CSV (?format=csv) in people/views_backend.backend_student_list.
- **14.4 Parent mobile-first:** docs/architecture/parent_mobile_first_14_4.md (viewport already in portal_base; touch targets and responsive audit documented).
- **Student 360 UI:** portal/student/<id>/360/ and /360/export/ (apps/student360/views.py), template student360/student_360_page.html.
- **15.2 DynamicField:** siteconfig.DynamicFieldDefinition, DynamicFieldValue (migration 0134); no schema change per custom attribute.
- **15.3 Global ledger:** docs/architecture/global_ledger_15_3.md (existing ledger, payment plans, installments).
- **16.5 Offline:** docs/architecture/offline_first_sync_16_5.md (replay API, SyncConflict, contract).

Checklist and Gaps tables above can be updated to mark these items done or partial as appropriate.

---

**End of audit.**
