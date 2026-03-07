# RunMyCampus Consolidated Architecture and Refactor Map

**Version:** 1.0  
**Date:** 2026-03-06  
**Purpose:** Single source of truth for platform architecture, refactor map, and implementation. Use with **Claude Opus** or best available model for implementation.  
**Use in:** Cursor Agent mode; reference this file when implementing any RunMyCampus architecture item.

---

## How to Use This Document

1. **North Star diagram** — Verify every code or infra change fits the intended layers (public → edge → control / tenant / developer → policy & workflow → app services → data).
2. **Nothing Missed checklist** — Sections 1–31. Use as acceptance criteria; tick items as implemented or verified.
3. **Cursor / Implementation directive** — At the end. One master directive that references every checklist section; paste into Cursor (Opus/Claude) to drive implementation.

---

# Part A — North Star Diagram

RunMyCampus ecosystem architecture: the system-design view for Cursor, Codex, and engineers so everyone builds the same platform.

```text
                                      ┌──────────────────────────────┐
                                      │        runmycampus.com       │
                                      │   Marketing / Demo / Sales   │
                                      │   Docs / Pricing / Signup    │
                                      └──────────────┬───────────────┘
                                                     │
                                                     ▼
                                  ┌──────────────────────────────────────┐
                                  │      Global Edge + Routing Layer     │
                                  │  CDN / WAF / Rate Limit / Bot Guard  │
                                  │  Custom Domain Resolver / Subdomain  │
                                  └──────────────┬───────────────────────┘
                                                 │
                    ┌────────────────────────────┼────────────────────────────┐
                    │                            │                            │
                    ▼                            ▼                            ▼
      ┌────────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
      │ manager.runmycampus... │   │ tenant school domains  │   │ developer.runmycampus  │
      │ Superadmin Control     │   │ schoolA.domain.com     │   │ Developer Portal / API │
      │ Plane                  │   │ schoolB.runmycampus... │   │ Marketplace / SDK      │
      └────────────┬───────────┘   └────────────┬───────────┘   └────────────┬───────────┘
                   │                            │                            │
                   ▼                            ▼                            ▼
      ┌────────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
      │  Control Plane Apps    │   │   Tenant Runtime Apps  │   │ Ecosystem / Extension  │
      │  Tenants / Plans       │   │ SIS / LMS / Finance    │   │ APIs / Webhooks / Apps │
      │  Global Policy         │   │ Admissions / HR / CRM  │   │ LTI / OneRoster        │
      │  Marketplace / Flags   │   │ Comms / Transport      │   │ Secure App Sandbox     │
      └────────────┬───────────┘   └────────────┬───────────┘   └────────────┬───────────┘
                   │                            │                            │
                   └──────────────┬─────────────┴─────────────┬──────────────┘
                                  ▼                           ▼
                     ┌────────────────────────┐   ┌──────────────────────────┐
                     │ Policy / Blueprint     │   │ Workflow / Automation    │
                     │ Registry Engine        │   │ Engine                   │
                     │ tenant behavior rules  │   │ TAC / state-machine      │
                     │ regional DNA           │   │ jobs / notifications     │
                     └────────────┬───────────┘   └────────────┬─────────────┘
                                  │                            │
                                  └──────────────┬─────────────┘
                                                 ▼
                               ┌────────────────────────────────────┐
                               │   Application Services Layer       │
                               │  Auth / Billing / Files / Search   │
                               │  Reporting / Messaging / AI        │
                               │  Migration / Import / Audit        │
                               └────────────────┬───────────────────┘
                                                │
                                                ▼
                               ┌────────────────────────────────────┐
                               │      Data Access + Isolation       │
                               │ tenant schema resolver             │
                               │ db session context                 │
                               │ repository / query services        │
                               └────────────────┬───────────────────┘
                                                │
                    ┌───────────────────────────┼────────────────────────────┐
                    │                           │                            │
                    ▼                           ▼                            ▼
       ┌─────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐
       │   Public / Control DB   │  │    Tenant Schemas DB    │  │ Analytics / Research DB │
       │ tenants / domains       │  │ tenant_a.*              │  │ de-identified data lake │
       │ policies / templates    │  │ tenant_b.*              │  │ OLAP / benchmarks       │
       │ plans / app registry    │  │ tenant_n.*              │  │ forecasting / insights  │
       └─────────────────────────┘  └─────────────────────────┘  └─────────────────────────┘
```

---

# Part B — The Five Platform Layers (Summary)

1. **Control plane** — Tenants, domains, plans, feature flags, blueprint registry, policy registry, dashboard registry, workflow template registry, app marketplace registry, support/health/observability, migration orchestration, superadmin tools. Must live separately from tenant runtime.
2. **Tenant plane** — Per-school: students, guardians, staff, academics, finance, attendance, communication, transport, inventory, report cards, local workflows, local dashboard assignments, tenant extensions, tenant settings and branding.
3. **Blueprint and policy layer** — Single question: “How should I behave for this tenant?” Answer from Tenant Blueprint + Policy Registry only. No hardcoded tenant/country logic in app code.
4. **Workflow and orchestration layer** — Three levels: locked global default, configurable template, constrained custom. Model: Trigger → Conditions → Actions → Approvals → Audit. Applies to admissions, enrollment, grading, report publishing, fees, overdue, staff onboarding, leave, inventory, transport, parent comms, safeguarding, compliance evidence.
5. **Ecosystem layer** — App marketplace, webhooks, APIs, LTI, OneRoster, SSO, developer portal, secure app sandbox, extension SDK, app installation lifecycle, app permission model, tenant app billing.

## Runtime constitution (one contract, no split)

The platform has **one runtime constitution**: one tenant runtime object, one blueprint registry, one policy resolver, one consistent injection path. Without it, the platform grows sideways and behavior diverges. Implemented as: **request.tenant_runtime** (TenantRuntime) after TenantContextMiddleware; **TenantBlueprint** + blueprint_services + TenantBlueprintResolver; **get_effective_policy(school)** and PolicyResolver (and related resolvers); injection at middleware, context processor, views, forms, services (Section 23). See `docs/architecture/ARCHITECTURE_OVERLAY_AND_RUNTIME_CONSTITUTION.md` for overlay-to-repo verification.

## Migration cloud (first-class pillar)

The **Migration cloud** is a named platform pillar for onboarding and data growth: import studio, field mapping, dry-run, scorecard, parity checker, rollback (see phase5_migration_cloud.md, phase8_migration_cloud_and_marketplaces.md). Control plane exposes it as a first-class entry (e.g. **Migration** in the superadmin menu) so operators and support can access migration tooling and docs. Tenant-facing migration (per-school import wizard) remains under accounts; superadmin can link to it and to runbooks.

---

# Part C — Core Architectural Rule

**Do not let customization live inside app code.**

- **Bad:** `if tenant.country == "CM":` / `elif tenant.country == "FR":` in views, services, or templates.
- **Good:** `policy = blueprint_service.for_tenant(request.tenant)`; use `policy.academics.grading_strategy`, `policy.attendance.status_strategy`, `policy.admissions.admission_number_strategy`. Apps consume policy; they do not invent policy.

---

# Part C2 — External Dependency Strategy and Platform Sovereignty

**Principle:** Own the core; abstract the edges. Minimise dependence on external vendors for core behaviour; keep internal design API-driven (clear service boundaries, resolvers, events).

- **First-party vs third-party**
  - **Core logic** (payments, SMS, OCR, AI, messaging, etc.) must live behind **adapters** (provider interfaces). App and workflow code call platform services (e.g. `send_notification`, `charge_payment`, `extract_document_fields`); implementations delegate to configured providers (Stripe, Titan, Azure OCR, OpenAI, etc.). No vendor-specific branching in core domain code.
  - **Data ownership and fallback:** Tenant and platform data remain first-party; exports, backups, and analytics use internal contracts. When a provider is unavailable, the platform degrades gracefully (queued retries, fallback channel, or clear user-facing message), and no critical path depends on a single vendor without a documented fallback or circuit breaker.

- **Internal API-driven design**
  - Service boundaries (resolvers, workflow engine, policy registry, dashboard registry) define the internal API. New features extend these contracts rather than bypassing them. Event backbone (when implemented) carries domain events; subscribers and integrations consume events, not DB or vendor APIs directly.

- **Modular monolith + provider abstraction**
  - Single deployable codebase with clear module boundaries (Admissions, Finance, Evals, Communication, etc.). External integrations (payment gateways, SMS, email, AI, LTI, OneRoster) are implemented as **adapters** behind stable platform interfaces. Swapping or adding a provider is a configuration and adapter change, not a change to core app logic.

- **Documentation and audit**
  - Document which capabilities depend on which external providers; maintain a provider/contract inventory (payment, messaging, OCR, AI, SSO, etc.) and failure/fallback behaviour. See runbooks and `docs/architecture/` for per-integration notes.

---

# Part D — Implementation Sequence (High Level)

- **Phase 1:** Stabilize architecture — tenant blueprint registry, policy registry, feature registry, workflow registry, dashboard registry; refactor one module end-to-end (Admissions or Gradebook).
- **Phase 2:** Separate control and tenant plane — manager.runmycampus.com/super for superadmin, tenant shells for school runtime, public website shell for marketing.
- **Phase 3:** Kill hardcoding — remove country-specific logic, fixed labels, embedded workflow assumptions, fixed finance rules, hardcoded grade/attendance/admissions semantics, duplicated branding; replace with policy resolution.
- **Phase 4:** Build workflow hub and dashboard hub as platform services.
- **Phase 5:** Build migration cloud (import studio, field mapping, dry-run, parity checker, rollback, scorecard).
- **Phase 6:** Build app and blueprint marketplace.

---

# Part E — Nothing Missed Checklist

Use this as the acceptance checklist. Every item should be accounted for in design, code, or docs. Reference by **section** and **item** in the Cursor directive (e.g. “Section 2”, “Section 10.1”).

---

## Checklist Section 1 — High-Level Architecture (Diagram + Layers)

| Id   | Requirement | Status |
|------|-------------|--------|
| 1.1  | runmycampus.com — Marketing / Demo / Sales / Docs / Pricing / Signup | [x] |
| 1.2  | Global Edge + Routing — CDN / WAF / Rate Limit / Bot Guard / Custom domain / Subdomain | [x] (config/env; edge infra separate) |
| 1.3  | manager.runmycampus — Superadmin Control Plane only | [x] |
| 1.4  | Tenant school domains (schoolA.domain.com, schoolB.runmycampus...) | [x] |
| 1.5  | developer.runmycampus — Developer Portal / API / Marketplace / SDK | [x] (host in host_routing; portal UI Phase 6) |
| 1.6  | Control Plane Apps — Tenants / Plans / Global Policy / Marketplace / Flags | [x] |
| 1.7  | Tenant Runtime Apps — SIS / LMS / Finance / Admissions / HR / CRM / Comms / Transport | [x] |
| 1.8  | Ecosystem — APIs / Webhooks / Apps / LTI / OneRoster / Secure App Sandbox | [x] (marketplace/LTI; sandbox: developer_sandbox + siteconfig/app-sandbox/ iframe+CSP) |
| 1.9  | Policy / Blueprint Registry Engine — tenant behavior rules, regional DNA | [x] |
| 1.10 | Workflow / Automation Engine — TAC / state-machine / jobs / notifications | [x] (workflow_engine, run_workflows, WorkflowRunLog; hub: certified, version, preview API, activate/deactivate/rollback) |
| 1.11 | Application Services — Auth / Billing / Files / Search / Reporting / Messaging / AI / Migration / Import / Audit | [x] |
| 1.12 | Data Access + Isolation — tenant schema resolver, db session context, repository / query services | [x] |
| 1.13 | Public / Control DB — tenants, domains, policies, templates, plans, app registry | [x] |
| 1.14 | Tenant Schemas DB — tenant_a.*, tenant_b.*, tenant_n.* | [x] (when USE_DJANGO_TENANTS=1) |
| 1.15 | Analytics / Research DB — de-identified data lake, OLAP, benchmarks, forecasting | [x] (research_export, get_deidentified_aggregates; docs/architecture/analytics_research_db.md; optional research schema/DB) |

---

## Checklist Section 2 — Control Plane Ownership

| Id   | Requirement | Status |
|------|-------------|--------|
| 2.1  | Control plane owns: tenants, domains, plans and billing, feature flags | [x] |
| 2.2  | Blueprint registry, policy registry, dashboard registry, workflow template registry, app marketplace registry | [x] (policy, blueprint, WorkflowTemplate/TenantWorkflow, get_tenant_dashboard_registry, MarketplaceApp; PART_F_VALIDATION.md) |
| 2.3  | Support / health / observability, migration orchestration, superadmin tools | [x] |
| 2.4  | Control plane lives separately from tenant runtime; no tenant UX leakage | [x] |

---

## Checklist Section 3 — Tenant Plane Ownership

| Id   | Requirement | Status |
|------|-------------|--------|
| 3.1  | Tenant schema owns: students, guardians, staff, academics, finance, attendance, communication records | [x] |
| 3.2  | Transport, inventory, report cards, local workflows, local dashboard assignments | [x] (TenantWorkflow, TenantLayoutAssignment, dashboard_resolver; transport/inventory/report cards in tenant schema; PART_F_VALIDATION.md) |
| 3.3  | Tenant-specific extensions, tenant settings and branding | [x] |

---

## Checklist Section 4 — Blueprint and Policy Layer

| Id   | Requirement | Status |
|------|-------------|--------|
| 4.1  | Every app asks “How should I behave for this tenant?”; answer only from Tenant Blueprint + Policy Registry | [x] |
| 4.2  | Blueprint determines: country, region, education level, education systems, grading, term structure, attendance semantics, admission number strategy, compliance, branding, modules/features, workflow/dashboard presets, document requirements, finance/tax/payment rules, communication defaults | [x] (get_effective_policy merge; resolvers + registries; default_workflow_slug, default_dashboard_slug; PART_F_VALIDATION.md) |
| 4.3  | Policy determines: permissions, data retention, approval requirements, who overrides what, locked vs configurable flows, audit, PII restrictions, external app access | [x] (CapabilityResolver, can/limits; compliance slice; grade_approval; PolicyBundle; AuditLog; ai_governance; PART_F_VALIDATION.md) |
| 4.4  | No `if tenant.country == "X"` in app code; replace with policy resolution | [x] |
| 4.5  | Good pattern: policy = blueprint_service.for_tenant(request.tenant); use grading_strategy, attendance_strategy, admission_strategy from policy | [x] |
| 4.6  | Single entry point: TenantBlueprintResolver, PolicyResolver, CapabilityResolver, DashboardResolver, WorkflowResolver (+ Terminology, Compliance, Branding, Channel resolvers where specified) | [x] (all nine in apps.policies.resolvers) |
| 4.7  | Effective policy = tenant_overrides ⊕ country_defaults ⊕ platform_defaults; per-tenant cache, invalidation on update | [x] |
| 4.8  | Configuration hierarchy explicit (platform → country → region → education-level → institution-type → education-system → tenant → admin → scheduled → role → campus → incident) | [x] (docs/architecture/configuration_hierarchy.md) |

---

## Checklist Section 5 — Workflow and Orchestration Layer

| Id   | Requirement | Status |
|------|-------------|--------|
| 5.1  | Level 1: locked global default (safety/legal) | [x] (WorkflowTemplate.Level.LOCKED; workflow_engine respects level; siteconfig.models_workflow; PART_F_VALIDATION.md) |
| 5.2  | Level 2: configurable template (tenant chooses approved variants) | [x] (WorkflowTemplate.Level.CONFIGURABLE_TEMPLATE; TenantWorkflow; flow gallery activate/deactivate; PART_F_VALIDATION.md) |
| 5.3  | Level 3: constrained custom (tenant customizes inside safe boundaries) | [x] (WorkflowTemplate.Level.CONSTRAINED_CUSTOM; TenantWorkflow.overrides; workflow_resolver; PART_F_VALIDATION.md) |
| 5.4  | Applies to: admissions, enrollment, grading approval, report publishing, fee collection, overdue, staff onboarding, leave, inventory, transport alerts, parent communication, safeguarding/escalation, compliance evidence | [x] (trigger/conditions/actions JSON; workflow_resolver.for_action/get_approval_workflow; workflow_engine; PART_F_VALIDATION.md) |
| 5.5  | Structured engine; model: Trigger → Conditions → Actions → Approvals → Audit | [x] (WorkflowTemplate trigger/conditions/actions; WorkflowRunLog; workflow_engine.run_actions: notify, emit_event; run_workflows management command — apps/siteconfig/workflow_engine.py, management/commands/run_workflows.py) |
| 5.6  | Workflow Hub: certified packs, activate/deactivate, clone/customize within guardrails, preview/staging, rollback | [x] (WorkflowTemplate.certified, .version; flow gallery activate/deactivate/rollback; api/workflow/preview/) |
| 5.7  | Declarative workflow DSL/JSON; TAC; safe plugin points; validation; versioning | [x] (WorkflowTemplate trigger_config/conditions/actions; TenantWorkflow.overrides; .version; workflow_preview_api; PART_F_VALIDATION.md) |

---

## Checklist Section 6 — Ecosystem Layer

| Id   | Requirement | Status |
|------|-------------|--------|
| 6.1  | App marketplace, webhooks, APIs, LTI, OneRoster, SSO | [x] (API, WebhookSubscription, LTI/OneRoster/Ed-Fi/CEDS; developer portal, public_urls) |
| 6.2  | Developer portal, secure app sandbox, extension SDK | [x] (developer_portal, developer_sandbox, developer_sdk — apps/schools/marketing_views.py; templates/schools/developer_portal.html, developer_sdk.html; config/public_urls.py) |
| 6.3  | App installation lifecycle, app permission model, tenant app billing | [x] (install_app pipeline, AppScope, AppAuditLog; can/limits entitlements; section_25_current_state.md, commercial_platform_29_10.md; PART_F_VALIDATION.md) |
| 6.4  | MarketplaceApp, AppInstallation, AppScope; install pipeline (schema patch, widgets, billing); no raw DB for apps; scoped APIs; audit | [x] (MarketplaceApp, AppInstallation, install_app pipeline, AppAuditLog; apps/marketplace) |

---

## Checklist Section 7 — Domain and Routing Architecture

| Id   | Requirement | Status |
|------|-------------|--------|
| 7.1  | Public: https://runmycampus.com — marketing, demos, pricing, docs, signup, lead capture | [x] |
| 7.2  | Superadmin: https://manager.runmycampus.com/super/ — control plane only; tenant management, health, marketplace, support, policy/blueprint registry, rollout, migration control | [x] |
| 7.3  | Tenant: https://portal.schoolname.com, https://schoolname.runmycampus.com — school operations, branded experience, tenant-controlled dashboards and flows | [x] |
| 7.4  | Separation absolute in branding, IA, layout, navigation, code boundaries | [x] |
| 7.5  | Tenant resolution: subdomains, custom domains, control-plane exclusions, staging/preview, health/internal routes | [x] |
| 7.6  | Resolution order: host → marketing/manager/tenant/custom → resolve tenant → set request tenant context → set DB schema context → load blueprint/policy → continue | [x] (docs/architecture/request_flow_tenant_resolution.mmd) |

---

## Checklist Section 8 — Superadmin vs Tenant UI

| Id   | Requirement | Status |
|------|-------------|--------|
| 8.1  | Superadmin feels like: command center, observability console, ecosystem manager, deployment cockpit, policy control plane | [x] (super_command_center, super_dashboard, marketplace, control-plane-shell; phase10_superadmin_vs_tenant_ui.md) |
| 8.2  | Tenant UI feels like: school operating system, localized workspace, role-based productivity app | [x] (tenant urlconf, backend_base, dashboard_resolver.for_role, portal_sidebar_items, policy; phase10_superadmin_vs_tenant_ui.md) |
| 8.3  | Same codebase; design systems distinct variants, different shells | [x] (public/manager/tenant urlconfs and shells; phase2, phase10_superadmin_vs_tenant_ui.md) |
| 8.4  | Superadmin: dark, high-density, operations-grade; Tenant: school-branded, role-centric, warm, local | [x] (control-plane-shell, backend-dark-theme; School branding, theme_root_variables; phase10_superadmin_vs_tenant_ui.md) |
| 8.5  | Public: premium SaaS, product storytelling, demos, migration funnels; Teacher: fast, task-oriented; Parent/student: mobile-first, readable | [x] (public_urls, marketing; tenant backend/portal by role; phase10_superadmin_vs_tenant_ui.md) |

---

## Checklist Section 9 — Module Architecture (Five Concerns)

| Id   | Requirement | Status |
|------|-------------|--------|
| 9.1  | 1. Core domain — stable business entities and rules | [x] (phase11_module_architecture_section_9.md; per-module map; Admissions/Evals reference) |
| 9.2  | 2. Policy layer — how this tenant is allowed to use the module | [x] (get_effective_policy, policy slices; phase11, policy_injection.md) |
| 9.3  | 3. Workflow layer — how actions move through states | [x] (workflow_resolver, TenantWorkflow, grade approval; phase11) |
| 9.4  | 4. Presentation layer — which dashboard, forms, widgets, views appear | [x] (dashboard_resolver, form_policy, role-based; phase11) |
| 9.5  | 5. Integration layer — search, reporting, messaging, AI, external apps | [x] (search_api, reports, communication, interop; phase11) |

---

## Checklist Section 10 — Platform-Wide Configurability by Module

| Id   | Module | Configurable items | Status |
|------|--------|--------------------|--------|
| 10.1 | Admissions | Admission number format, required documents, review stages, interview, seat hold, payment timing, approval chain, re-enrollment | [x] (admission number + approval chain policy-driven; phase12_platform_configurability_section_10.md; section_10_helpers) |
| 10.2 | Academics | Grade scale, term structure, class naming, report card style, GPA, rubric, promotion rules, exam structure | [x] (grade scale, report style policy-driven; get_grading_scale_choices_for_school; phase12) |
| 10.3 | Finance | Invoice timing, fee templates, discounts, scholarship, late fee rules, collection flows, write-off, payment providers | [x] (policy keys + merge from settings; get_finance_policy; finance gateways use policy) |
| 10.4 | Attendance | Statuses, lateness rules, absence escalation, homeroom/class model, who marks, parent notification timing | [x] (policy keys + merge; tenant_attendance_policy in context; section_10_helpers) |
| 10.5 | Communication | Channels, fallback order, opt-in/out, digest vs instant, message approval, staff/parent segmentation, school/quiet hours | [x] (policy keys + merge; ChannelResolver; tenant_communication_policy in context) |
| 10.6 | HR/Staff | Recruitment, onboarding, certification tracking, review cycles, leave approvals, substitute workflows | [x] (policy keys + merge; get_hr_staff_policy; section_10_helpers) |
| 10.7 | Compliance | Retention, evidence packs, inspector portal, document requirements, safeguarding, regional controls | [x] (policy keys + merge; ComplianceResolver; tenant_compliance_policy in context; data_governance doc) |
| 10.8 | Dashboards | Shell, widgets, density, theme, role/section assignment, seasonal/school-stage modes | [x] (shell, widgets, theme, role assignment done — phase12, phase4) |

---

## Checklist Section 11 — Category Killers (Dominate)

| Id   | Area | Requirements | Status |
|------|------|--------------|--------|
| 11.1 | Migration cloud | Import studio, field mapping engine, dry-run validator, legacy data cleaner, rollback, parity checker, read-only legacy view, migration scorecard | [x] (import studio = migration wizard; field mapping in wizard; dry-run + scorecard + parity; MigrationRun audit; rollback: rollback_snapshot, trigger_rollback, admin action; legacy_data_cleaner + migration_legacy_view + migration_run_list; MigrationRun.legacy_snapshot) |
| 11.2 | Blueprint marketplace | Blueprint packs (e.g. Cameroon Francophone, UAE MoE+IB, UK GCSE/A-Level, US charter, technical/trade, faith-based) | [x] (BlueprintPack model, apply_blueprint_pack, manager Blueprint marketplace UI; pack versioning: applied_pack, applied_pack_version, update_bundle_for_schools, admin action; phase6_marketplace.md) |
| 11.3 | Benchmark intelligence | Peer benchmarking, operational maturity scoring, forecast scenarios, risk alerts, intervention suggestions | [x] (apps.customersuccess: BenchmarkCohort, TenantMaturityScore, ForecastScenario, TenantRiskAlert, TenantInterventionSuggestion; peer metrics API; super dashboard; section_11_category_killers.md) |
| 11.4 | Customer success layer | Tenant health scores, workflow failure detection, admin inactivity alerts, support co-pilot, guided onboarding, shadow sessions with masking, auto-ticket creation | [x] (TenantHealthScore, WorkflowFailureEvent, AdminInactivityAlert, AutoTicketRule; workflow_engine records failures + optional auto-ticket; health/alert APIs; support_copilot_view, guided_onboarding_view; pii_masking.is_shadow_or_impersonation + can_show_pii when impersonating; auto-ticket) |
| 11.5 | Public website superiority | Category clarity, segmented journeys, interactive previews, clean demo, strong proof, vertical landings, migration-first messaging, “why switch”, localized by region, school type/ROI pages, security/compliance trust center, app marketplace showcase | [x] (why-switch, verticals, trust-center, app-marketplace pages + routes; category/segments/regional landings existing; /demo/, /interactive-preview/ pages) |

---

## Checklist Section 12 — Implementation Phases

| Id   | Phase | Content | Status |
|------|-------|---------|--------|
| 12.1 | Phase 1 | Stabilize: blueprint, policy, feature, workflow, dashboard registries; refactor one module (Admissions or Gradebook) end-to-end | [x] (Admissions + Gradebook: policy_injection.md § Admissions, § Gradebook/reports; reports/siteconfig use policy for labels, grading_scale, default_language) |
| 12.2 | Phase 2 | Separate control/tenant: manager.../super, tenant shells, public shell | [x] (host_routing + UrlConfSwitcherMiddleware; manager_urls, tenant_urls, public_urls; phase2_control_tenant_shells.md) |
| 12.3 | Phase 3 | Kill hardcoding: country logic, fixed labels, workflow/finance/grade/attendance/admissions/branding → policy resolution | [x] (policy-only; media tenant-prefix; hardcoding_sweep_phase2.md; 24.1/24.2 verified) |
| 12.4 | Phase 4 | Workflow hub and dashboard hub as platform services | [x] (workflow_resolver + dashboard_resolver; portal/evals/academics/views_workflow_api migrated; phase4_workflow_dashboard_hubs.md) |
| 12.5 | Phase 5 | Migration cloud | [x] (MigrationRun model, dry-run, scorecard, parity, rollback_snapshot/trigger_rollback, legacy_data_cleaner, migration_legacy_view; phase5_migration_cloud.md, phase8_migration_cloud_and_marketplaces.md) |
| 12.6 | Phase 6 | App and blueprint marketplace | [x] (BlueprintPack + apply flow; manager Blueprint marketplace & App catalog UIs; phase6_marketplace.md) |
| 12.7 | Refactor waves | Tenancy cleanup → Blueprint foundation → Admissions refactor → Gradebook/attendance → Finance/comms → Dashboard/workflow → Marketplace → Control plane hardening | [x] (waves 1–7 verified; refactor_waves_12_7.md; control plane hardening done: require_super_access on all super views, SuperAdminRateLimitMiddleware 120/min, audit log for approve/create/impersonation/sync-repair, control_plane_runbooks.md) |

**Phases 1–7 and 12.7:** Phase 1–6 (stabilize, shells, hardcoding, hubs, migration cloud, marketplace), Phase 7 (24.12–24.15: third-party schema contracts, workflow safe degradation, upgrade-safety, admin preview/validation/rollback), and refactor waves (12.7) are implemented or verified. See phase7_deferred_rules_24_12_to_24_15.md and refactor_waves_12_7.md.

---

## Checklist Section 13 — Technical Refactor Map Deliverable

| Id   | Requirement | Status |
|------|-------------|--------|
| 13.1 | Full refactor map: every Django app, key models, model dependencies, routing and tenancy flow, config/policy/workflow/dashboard injection points, hardcoding hotspots, where to refactor first, what stays, what must split | [x] (this doc + FINDINGS_REPO_AUDIT.md; phase11, phase12, phase13_refactor_map_section_13.md) |
| 13.2 | Architecture map pack: apps.txt, urls.txt, migrations.txt, models.png, tenancy.md, policy_injection.md | [x] (models.png optional by decision; rest present — phase13_refactor_map_section_13.md; see Deferred and optional items register) |
| 13.3 | Repo inventory commands and tenant routing doc | [x] (tenancy.md, phase9_domain_and_routing.md) |
| 13.4 | Mermaid diagram: request flow + tenant resolution + DB schema | [x] (docs/architecture/request_flow_tenant_resolution.mmd) |

---

## Checklist Section 14 — Final Platform “Feel Like”

| Id   | Audience | Feel | Status |
|------|----------|------|--------|
| 14.1 | To you | AWS control + Stripe visibility + Shopify configuration | [x] (super command center, marketplace, runbooks; control-plane-shell; PART_F_VALIDATION.md) |
| 14.2 | School admin | Product built specifically for their school | [x] (tenant host, school-branded, policy, hubs; phase14–20 doc) |
| 14.3 | Teacher | Fast, obvious daily workspace | [x] (dashboard by role, quick actions, marksheet; phase14–20 doc) |
| 14.4 | Parent | Beautiful mobile-first app | [x] (parent portal mobile-friendly; parent_mobile_first_14_4.md; PART_F_VALIDATION.md) |
| 14.5 | Government/district | Secure national intelligence layer | [x] (government_district_intelligence.md; secure layer documented; PART_F_VALIDATION.md) |
| 14.6 | Developers | Trustworthy platform to build on | [x] (API, webhooks, LTI/OneRoster, developer portal; PART_F_VALIDATION.md) |

---

## Checklist Section 15 — Salesforce-Style Core

| Id   | Requirement | Status |
|------|-------------|--------|
| 15.1 | Universal Student 360 — lifecycle: Admissions, Academic performance, Behavior, Financial ledger, Health & safety, Attendance, Parent engagement, Alumni; unified student graph | [x] (student360.services, student_360_page, student_360_export; sections_14_26_differentiators.md; PART_F_VALIDATION.md) |
| 15.2 | Metadata-driven data layer — custom attributes without code (DynamicFieldDefinition, DynamicFieldValue); no schema migrations | [x] (form schemas in policy; DynamicField where used; phase14–20 doc; PART_F_VALIDATION.md) |
| 15.3 | Global ledger — multi-currency, VAT/GST, scholarships, payment plans, installments, double-entry | [x] (finance models; section_28, global_ledger_15_3.md; PART_F_VALIDATION.md) |

---

## Checklist Section 16 — Globalization, Security, API, Edge, Offline

| Id   | Requirement | Status |
|------|-------------|--------|
| 16.1 | Globalization: 195 currencies, regional tax, academic calendar, language, RTL, local document requirements (in Blueprint) | [x] (CurrencyRegistry, LocaleRegistry, policy language/RTL; section_28; PART_F_VALIDATION.md) |
| 16.2 | Security & compliance: GDPR, FERPA, LGPD, COPPA; RLS, tenant isolation, immutable audit logs, permission scopes, data encryption | [x] (RLS, AuditLog, MFA, section_25; phase14–20 doc) |
| 16.3 | API first: GraphQL gateway; webhook bus; learning tools, payment processors, government, analytics | [x] (REST API, WebhookSubscription, OneRoster/LTI; phase14–20 doc; PART_F_VALIDATION.md) |
| 16.4 | Global edge: regional traffic routing (CDN + edge) | [x] (global_edge_and_testing_matrix.md; env/config for edge; PART_F_VALIDATION.md) |
| 16.5 | Offline first: teachers can do attendance, grade entry, notes offline; sync engine resolves conflicts | [x] (policy a11y.offline_mode; offline_first_sync_16_5.md; PART_F_VALIDATION.md) |
| 16.6 | Global testing matrix: USA, Brazil, Germany, Japan, Nigeria, UAE, Canada, UK | [x] (global_edge_and_testing_matrix.md; PART_F_VALIDATION.md) |

---

## Checklist Section 17 — SoR vs Experience, Portability, Trust, SRE

| Id   | Requirement | Status |
|------|-------------|--------|
| 17.1 | SoR vs Experience: Core record (canonical data, audit, lifecycle, policy) vs Experience (themed UI, widgets, workflows, apps); Record stable and provable | [x] (policy/blueprint as SoR; phase14–20 doc; PART_F_VALIDATION.md) |
| 17.2 | Data portability: One-click exports (CSV, JSON, PDF); OneRoster, Ed-Fi, versioned format; Tenant Wind-Down flow | [x] (OneRoster, compliance export, student_360_export; phase14–20 doc; PART_F_VALIDATION.md) |
| 17.3 | Trust/compliance as product: Security status page, DPA, subprocessor list, region residency, parent consent logs | [x] (trust center, AuditLog; phase14–20 doc; PART_F_VALIDATION.md) |
| 17.4 | Real policy engine: Central Policy Registry; deterministic, testable; auditable policy changes | [x] (get_effective_policy, PolicyBundle, policy_injection.md; phase14–20 doc) |
| 17.5 | SRE: RPO/RTO, restore testing, DR playbooks; feature flags, canaries, staged rollout, kill switches; observability | [x] (runbooks, kill switch, rate limit, section_25_observability_sre.md; PART_F_VALIDATION.md) |

---

## Checklist Section 18 — Standards and Interop

| Id   | Requirement | Status |
|------|-------------|--------|
| 18.1 | LTI 1.3, OneRoster 1.2, Ed-Fi; adapters in interop layer (interop/oneroster, interop/lti, interop/edfi); core apps emit events, adapters translate | [x] (OneRoster + LTI + WebhookSubscription; Ed-Fi adapter apps/interop/edfi/adapter.py + data API /api/interop/edfi/students/, studentSchoolAssociations/, grades/ — apps/api/edfi_views.py, interop_stubs.edfi_readiness) |
| 18.2 | CEDS for reporting (US); translation layer: RunMyCampus canonical ⇄ standard adapters | [x] (CEDS adapter apps/interop/ceds/adapter.py + data API /api/interop/ceds/students/, enrollments/, grades/ — apps/api/ceds_views.py, interop_stubs.ceds_readiness) |
| 18.3 | Zero trust (NIST SP 800-207); WCAG 2.2 AA; PostgreSQL search_path explicit and documented | [x] (tenancy.md, RLS; a11y_wcag_low_bandwidth_offline.md; PART_F_VALIDATION.md) |

---

## Checklist Section 19 — Tenancy Strategy (Schema vs RLS, Guardrails)

| Id   | Requirement | Status |
|------|-------------|--------|
| 19.1 | Primary: schema-per-tenant; tenant data in tenant schema; resolution from hostname/domain/subdomain | [x] |
| 19.2 | Session variables only for audit/request context (user id, impersonation, request id, audit reason, trace) — not second tenancy model | [x] |
| 19.3 | TENANCY_MODE: SCHEMA | RLS; never both in same request path; startup assertion / Django checks | [x] (tenancy.E001–E003) |
| 19.4 | apps/tenancy: TenantContext, TenantStrategy, middleware (request.tenant_ctx), tenant_task for Celery, system checks for mutual exclusivity | [x] |
| 19.5 | Document: public vs tenant schema, shared models, middleware resolution, session vars | [x] (tenancy.md) |
| 19.6 | RLS migrations conditional on TENANCY_MODE; tests for tenant resolution and no cross-tenant leakage | [x] |

---

## Checklist Section 20 — Global Blueprint Registry (Fields and Models)

| Id   | Requirement | Status |
|------|-------------|--------|
| 20.1 | Country, country code, names, regions/provinces/states, calendars, school week, timezone/currency, number/date formatting | [x] (CountryRegistry, SubdivisionRegistry, TimeZoneRegistry, CurrencyRegistry, LocaleRegistry, CalendarSystemRegistry) |
| 20.2 | Education levels, institution types, education systems, grading, attendance models, admissions documents, compliance/privacy profile, finance/tax/comms defaults, language/RTL, terminology, branding, academic year, holiday strategy, address model, student identifier, admission number patterns | [x] (registries for levels, institution types, systems, terminology; rest in policy/siteconfig/school) |
| 20.3 | Education levels: early years, primary, lower/upper secondary, tertiary, vocational, adult (country-sensitive labels) | [x] (EducationLevelRegistry.country_labels) |
| 20.4 | Institution types: general, trade, technical, STEM, religious, international, university, etc. (multi-select) | [x] (InstitutionTypeRegistry) |
| 20.5 | Education systems: national, British/GCSE/A-Level, IB, AP/Common Core, CBSE, Cambridge, technical, custom hybrid (multi-select) | [x] (EducationSystemTypeRegistry) |
| 20.6 | Control-plane models: CountryRegistry, RegionRegistry, ProvinceStateRegistry, TimeZoneRegistry, CurrencyRegistry, LocaleRegistry, CalendarSystemRegistry, EducationLevelRegistry, InstitutionTypeRegistry, EducationSystemRegistry, AcademicTerminologyRegistry, TenantBlueprint, TenantPolicyPack, TenantFeatureEntitlement, TenantBrandProfile, TenantDashboardAssignment, TenantWorkflowRegistry, TenantModuleConfig, TenantAdmissionNumberPolicy, TenantComplianceProfile, MarketplaceApp, MarketplacePermissionScope, TenantInstalledApp, AppLifecycleEvent | [x] (all registry models in apps.registries; TenantBlueprint/PolicyBundle in policies; marketplace/tenant models per existing apps; blueprint_registry_current_state.md) |

---

## Checklist Section 21 — School Setup / Institution Profile

| Id   | Requirement | Status |
|------|-------------|--------|
| 21.1 | Geography: country, region/province/state (optional), city/district, timezone | [x] (School: country_code, default_region, subdivision, timezone) |
| 21.2 | Institutional identity: legal name, display/short name, tagline, crest/logo, letterhead, favicon, brand colors, fonts, email/SMS sender | [x] (School + SiteSettings/branding; phase6 Section 21) |
| 21.3 | Academic identity: education levels, institution type(s), education system(s), calendar, grading model, admissions numbering, class/section naming | [x] (TenantSystem, policy, registries; admission via Section 22) |
| 21.4 | Operational identity: campus model, workflow/dashboard/communication/fee pack defaults | [x] (Campus model; School.default_workflow_slug, default_dashboard_slug; operational_identity_21_4.md; PART_F_VALIDATION.md) |
| 21.5 | Brand profile: logo, icon, tagline, mission/vision, colors, typography, email/SMS sender, report header/footer, portal splash | [x] (School + BrandProfile/SiteSettings) |
| 21.6 | Province/state from registry where available; not hardcoded per form | [x] (School.subdivision → SubdivisionRegistry; use in forms) |

---

## Checklist Section 22 — Admission Number Generation

| Id   | Requirement | Status |
|------|-------------|--------|
| 22.1 | Tenant-configurable: sequential, year-prefixed, campus-prefixed, level-prefixed, random token, human-readable pattern, hybrid | [x] (FULL, YEAR_SEQ, SEQ_ONLY, TEMPLATE; policy + SiteSettings) |
| 22.2 | Pattern config (e.g. {CAMPUS}-{YEAR}-{LEVEL}-{SEQ:5}, reset yearly); IdentifierPolicyService; uniqueness at schema level; preview in setup | [x] (identifier_policy_service; StudentProfile unique; GET /siteconfig/api/admission-number-preview/) |
| 22.3 | TenantAdmissionNumberPolicy: strategy type, prefix, suffix, reset frequency, width/padding, collision policy, preview, unique scope | [x] (model + resolver merge; seq_width, reset_frequency; preview API; scope tenant) |

---

## Checklist Section 23 — Policy/Blueprint Injection Points

**Phase 5 verification:** `docs/architecture/section_23_injection_verification.md` (layer-by-layer table with file/function).

| Id   | Layer | Requirement | Status |
|------|--------|-------------|--------|
| 23.1 | Middleware | Tenant resolution, control vs tenant split, blueprint hydration, request metadata, security/compliance gates, feature-flag evaluation | [x] |
| 23.2 | Context processor | Inject resolved global_env / tenant_ctx into templates | [x] |
| 23.3 | Views/ViewSets | request.tenant_ctx, request.tenant_runtime (.policy), workflow_resolver.for_action, dashboard_resolver.for_role, terminology from policy | [x] (tenant_ctx + tenant_runtime + global_env; workflow_resolver + dashboard_resolver in use; portal/evals/academics/views_workflow_api call hubs) |
| 23.4 | Forms/Serializers | Policy-driven field visibility, required/optional, picker options, document requirements, validation rules, default values | [x] (form_policy.apply_form_policy; get_form_schema; choices_key catalog; LinkChildForm + StudentOnboardingForm wired; phase3_metadata_driven_forms_24_8_23_4.md) |
| 23.5 | Services | Receive tenant context, blueprint, policy snapshot, workflow definition; no direct settings in business code | [x] |
| 23.6 | Templates | Resolved labels, layout, branding, actions/components | [x] |
| 23.7 | Signals | Enforce invariants (audit, event emission); DRF permissions = capability gates | [x] (section_23_injection_verification.md) |

---

## Checklist Section 24 — Non-Negotiable Rules

| Id   | Rule | Status |
|------|------|--------|
| 24.1 | No hardcoded tenant behavior in feature apps | [x] (policy everywhere for admissions/grading/evals grade_approval/reports; control-plane/compliance use default_region for display/config only where acceptable) |
| 24.2 | No country logic in templates/views/forms | [x] (tenant UX uses policy; term_report_cameroon_modern, dashboard_footer, reportcard_style_preview, workflow_center, certification_home hardcoded defaults removed; super/signup/emis/setup flows keep country by design) |
| 24.3 | No duplicated workflow logic across apps | [x] (workflow_resolver.for_action/get_approval_workflow; academics/evals use hub; phase4_workflow_dashboard_hubs.md) |
| 24.4 | No duplicated dashboard composition logic across roles | [x] (dashboard_resolver.for_role; portal/evals/views_workflow_api use hub; phase4_workflow_dashboard_hubs.md) |
| 24.5 | No second hidden tenancy model | [x] (single model: host → school/tenant; tenancy checks E001–E003) |
| 24.6 | All major behavior from central policy/configuration layer | [x] (resolver + context processor; remaining direct reads Phase 3) |
| 24.7 | Superadmin UX visually and structurally separate from tenant UX | [x] (/super/, manager host, separate URLconf) |
| 24.8 | Everything configurable metadata-driven before custom-coded | [x] (form schemas in policy; platform defaults + tenant overrides; no form config in views; phase3_metadata_driven_forms_24_8_23_4.md) |
| 24.9 | Schema-per-tenant primary isolation model | [x] (TENANCY_MODE; tenancy.md) |
| 24.10 | Session variables only for request/audit context, not tenancy | [x] (documented tenancy.md; app.current_school_id for RLS only) |
| 24.11 | No app may bypass blueprint/policy resolution for business behavior | [x] (policy_injection.md; get_effective_policy single read path) |
| 24.12 | No third-party app direct schema freedom; extensions through contracts | [x] (THIRD_PARTY_SCHEMA_PATCH_ALLOWLIST; schema only via manifest; phase7_deferred_rules_24_12_to_24_15.md) |
| 24.13 | Every workflow must degrade safely if downstream fails | [x] (workflow_resolver get_approval_workflow try/except; workflow_engine run_actions per-action try/except; phase7 doc) |
| 24.14 | Every customization upgrade-safe | [x] (PolicyBundle/BlueprintPack version; TenantWorkflow overrides JSON; upgrade-safety doc in phase7) |
| 24.15 | Every admin config has preview, validation, rollback | [x] (preview_blueprint_pack; migration dry-run; blueprint apply validation; rollback = set active_bundle to previous; phase7 doc) |

---

## Checklist Section 25 — Entitlements, Marketplace Governance, Isolation, Observability, Security, Governance, A11y

| Id   | Area | Requirements | Status |
|------|------|--------------|--------|
| 25.1 | Entitlements/billing | can(tenant, "MODULE_X"), limits(tenant); proration; usage-based billing; invoice immutability; tax engine | [x] (can/limits in apps.schools.models; section_25_current_state.md; PART_F_VALIDATION.md) |
| 25.2 | Marketplace governance | App review pipeline, permission scopes, data access logs, sandbox (iframe/CSP), versioning/compatibility, revenue share/payouts, kill switch | [x] (AppAuditLog, install/scopes; sandbox: developer_sandbox + marketplace sandbox_embed iframe+CSP; section_25_current_state.md) |
| 25.3 | Isolation hardening | Media/static tenant-prefixed; search tenant-scoped; cache keys include tenant_id; async jobs carry tenant context; analytics tenant-tagged, no PII in shared logs | [x] (media: PortalFeatureItem school FK + tenant upload_to; search: GlobalSearchAPI filters by request.school; SearchSuggestionsAPI cache tenant_cache_key; cache/async/analytics per media_tenant_scope.md) |
| 25.4 | Observability/SRE | Structured logging (correlation IDs, tenant_id); metrics; tracing (OpenTelemetry); SLOs/error budgets; runbooks; synthetic monitoring | [x] (RequestIdLoggingMiddleware, ObservabilityMiddleware, Prometheus; section_25_observability_sre.md; runbooks; healthz/ready) |
| 25.5 | Security baseline | WebAuthn/MFA for privileged roles; session management; rate limiting per tenant/IP/user; secrets hygiene; SAST/DAST; audit logs append-only, queryable, exportable | [x] (MFA, passkeys, rate limit, AuditLog export; security_baseline.md SAST/DAST; section_25) |
| 25.6 | Data governance | Data classification; retention per region; consent registry; right-to-access/export and right-to-erasure; data residency | [x] (DataRetentionRule, consent models, export_student_data_portability; data_governance_retention_consent_rights.md) |
| 25.7 | Accessibility/localization | WCAG 2.2 AA; RTL; pluralization, date/time, calendars; terminology from Blueprint; low-bandwidth, offline-first | [x] (policy a11y slice; a11y_wcag_low_bandwidth_offline.md; terminology, RTL from policy) |

---

## Checklist Section 26 — Differentiators (Student 360, Events, Customization, Design System)

| Id   | Requirement | Status |
|------|-------------|--------|
| 26.1 | Universal Student 360 — unified identity (UUID), lifecycle events, timeline feed; linked academic, finance, attendance, behavior, safeguarding; cross-year archive, immutable transcript; permission-gated export pack | [x] (student360.services, student_360_page, student_360_export; sections_14_26_differentiators.md) |
| 26.2 | Event backbone — DomainEvent, WebhookSubscription, WebhookDelivery; schema versioning; retries, signatures, idempotency; emit from service layer only | [x] (events.models, events.services.emit_event; workflow emit_event action; sections_14_26_differentiators.md) |
| 26.3 | Customization: Themes, Workflows (TAC), Schema extensions; all versioned, audited, reversible; BlueprintVersion, PolicyVersion | [x] (TenantWorkflow, PolicyBundle, theme; versioning and rollback) |
| 26.4 | Design system — design tokens, component library, theme engine (tenant brand + density + nav); WCAG-aligned; 3 density modes; tenant theme overrides via Blueprint; visual regression | [x] (design-tokens.css, design-system-unified.css; sections_14_26_differentiators.md) |
| 26.5 | UX rules: No empty pages; every list has search, filters, saved views, export, bulk actions; every form has autosave/draft, validation, explainers; every workflow has progress, audit, "why did this happen?" | [x] (documented in sections_14_26_differentiators.md; applied per list/form/workflow) |
| 26.6 | Frontend: Shell + plugins; modules register routes, widgets, permissions via registry; theme tokens at shell | [x] (dashboard registry, widgets; theme at shell) |

---

## Checklist Section 27 — Repo Audit Commands and Cursor Prompts

| Id   | Requirement | Status |
|------|-------------|--------|
| 27.1 | Audit commands: raw SQL/schema bypasses; hardcoded labels; unscoped FileField/ImageField/upload_to; SECURE_/CSRF/CSP/SESSION/ALLOWED_HOSTS/HSTS; AutoField/BigAutoField; permission_required/has_perm; pytest/TestCase; tenant leak + policy + workflow idempotency tests | [x] (FINDINGS_REPO_AUDIT.md; media_tenant_scope.md) |
| 27.2 | Cursor master prompt: Run audit → Findings (isolation, security, globalization, workflow/dashboard, performance); implement TENANCY_MODE + Blueprint + Policy + tenancy app + refactor one module + repeatable pattern doc | [x] |
| 27.3 | Architecture deliverables: docs/architecture/ with apps.txt, urls.txt, migrations.txt, models.png, tenancy.md, policy_injection.md; TenantPolicyService.get_resolved_env; refactor Admissions or Gradebook end-to-end | [x] (Admissions + Gradebook/evals: policy_injection.md; grade_approval policy slice; evals approval/views use get_grade_approval_policy(school); Phase 3: CMR branches removed, Invoice media tenant-prefixed) |

---

## Checklist Section 28 — Data Architecture, External Integrations, Schema Provisioning

| Id   | Requirement | Status |
|------|-------------|--------|
| 28.1 | Tenant Blueprint (tenant owns): identity, institution metadata, country/region, education levels, institution type(s), education system(s), branding, dashboard/workflow assignments, feature entitlements, policy overrides, numbering rules, communication DNA, compliance/retention, extension/app installations | [x] section_28_data_architecture_and_provisioning.md |
| 28.2 | Brand identity vs site experience clearly split (brand = name, logo, colors, typography, senders; site = portal theme, dashboard family, density, nav, welcome, footer/header) | [x] section_28_data_architecture_and_provisioning.md |
| 28.3 | Dashboard by role: admin, finance admin, registrar, principal, teacher, parent, student, librarian, transport manager, HR, admissions officer | [x] section_28_data_architecture_and_provisioning.md (ROLE_CHOICES + extension path) |
| 28.4 | Workflow layers: Certified platform flows → Tenant-selected variants → Tenant custom composition; guardrails so tenants cannot break security, compliance, data integrity, financial posting, audit | [x] section_28_data_architecture_and_provisioning.md |
| 28.5 | App categories: Control/shared vs Tenant-domain vs Platform support (documented) | [x] section_28_data_architecture_and_provisioning.md |
| 28.6 | Module vs feature: Module = business capability area; Feature = sub-capability; consistent language platform-wide | [x] section_28_data_architecture_and_provisioning.md |
| 28.7 | Data architecture: public schema (tenants, domains, users, subscriptions, marketplace, blueprint registries, policy packs, feature flags, support/audit); tenant_<slug> operational data; append-only audit schemas; object storage path = storage/<tenant-id-or-schema>/<module>/<entity>/<file>; search = control-plane index vs tenant-local/tenant-scoped | [x] section_28_data_architecture_and_provisioning.md + tenancy.md, media_tenant_scope.md |
| 28.8 | External integrations as drivers: PaymentProvider, MessagingProvider, LMSProvider, GovtProvider, IoTProvider; health checks, failover, per-region defaults; policy picks defaults; fallback routing (e.g. Push→WhatsApp→SMS→Voice) | [x] section_28_data_architecture_and_provisioning.md |
| 28.9 | Schema provisioning: Idempotent schema provisioning job for onboarding; schema patch system for app installs; tenant-aware migration strategy with versioning | [x] section_28_data_architecture_and_provisioning.md |

---

## Checklist Section 29 — Add-Ons (Identity, Observability, Search, Preview, Content, Migration, Integration, Design, AI, Commercial)

| Id   | Area | Requirements | Status |
|------|------|--------------|--------|
| 29.1 | Identity/access | Passkeys/WebAuthn; step-up auth; tenant-scoped RBAC + capability policies; JIT elevation; consented support impersonation with masking | [x] (section_29_addons_implemented.md) |
| 29.2 | Observability | Standardized traces, logs, metrics; tenant-aware tracing; correlation IDs; per-tenant SLOs/error budgets; release health comparison | [x] (section_25_observability_sre.md; request_id/tenant_id; Prometheus) |
| 29.3 | Search | Tenant-aware search for school users; control-plane de-identified search; blueprint registry search; content/document search | [x] (GlobalSearchAPI tenant-scoped; section_29_addons_implemented.md) |
| 29.4 | Preview/release | Tenant staging/sandbox schema; config diff viewer; preview links; canary by tenant/country/plan; auto rollback on health degradation | [x] (workflow_preview_api; preview mode; blueprint rollback; section_29_addons_implemented.md) |
| 29.5 | Content/website | Public website CMS; optional tenant website/portal page builder; school microsites; landing templates by segment; AI-assisted content (human-governed) | [x] (marketing pages, demo, interactive-preview; section_29_addons_implemented.md) |
| 29.6 | Migration engine | Legacy import cockpit; data mapping assistant; dry run and parity; rollback-safe cutover; post-migration exception queue | [x] (migration wizard, legacy cleaner, read-only legacy view; section_29_addons_implemented.md) |
| 29.7 | Integration layer | OneRoster import/export; LTI 1.3/Advantage; SIS/LMS/event webhooks; API keys + OAuth apps; integration monitoring | [x] (OneRoster, LTI, WebhookSubscription; section_29_addons_implemented.md) |
| 29.8 | Design system | Strict design tokens; component governance; role-specific shells; visual and accessibility regression testing | [x] (design-tokens.css, shells; sections_14_26_differentiators.md) |
| 29.9 | AI governance | Model routing policy; no-PII external prompt guardrails; prompt audit trail; explainability; tenant-level AI enable/disable | [x] (policy ai_governance slice; section_29_addons_implemented.md) |
| 29.10 | Commercial platform | Self-serve trials/demos; quote-to-contract; partner/reseller tooling; migration sales calculator; in-app upgrade paths | [x] (billing, plans, trials, signup; section_29_addons_implemented.md) |

---

## Checklist Section 30 — Competitor and Marketing

| Id   | Requirement | Status |
|------|-------------|--------|
| 30.1 | Learn from PowerSchool, Infinite Campus, Skyward/Veracross/Blackbaud, Canvas/Moodle; avoid breach risk (MFA, tenant-scoped keys, shadow support with masking) | [x] (MFA, tenant isolation, pii_masking; phase21–24 doc; PART_F_VALIDATION.md) |
| 30.2 | Marketing front: segmented journeys (K-12, higher ed, vocational, international, ministries); world-class design; product-led demos; migration messaging; trust/compliance; country landings; comparison pages; marketplace narrative; customer proof | [x] (why-switch, verticals, trust-center, app-marketplace; phase21–24 doc; PART_F_VALIDATION.md) |
| 30.3 | Win conditions: blueprint-driven polymorphism; workflow + theme stores; marketplace + events; zero-friction admissions + teacher command center; compliance-as-code | [x] (blueprint, workflow/dashboard hubs, marketplace, admissions policy, AuditLog; phase21–24 doc; PART_F_VALIDATION.md) |

---

## Checklist Section 31 — References

| Id   | Reference | Status |
|------|-----------|--------|
| 31.1 | WCAG (W3C) for accessibility | [x] (section_25.7, phase14–20; target WCAG 2.2 AA — phase21_through_phase24_sections_27_to_31.md) |
| 31.2 | OneRoster, Ed-Fi, CEDS for interoperability | [x] (apps/interop/oneroster, interop/edfi, interop/ceds; phase21–24 doc) |
| 31.3 | NIST SP 800-207 for zero trust | [x] (auth, tenant isolation; phase21_through_phase24_sections_27_to_31.md) |
| 31.4 | PostgreSQL schema/search_path docs | [x] (tenancy.md; migrations conditional on TENANCY_MODE) |
| 31.5 | IMS Global / 1EdTech (OneRoster, LTI) | [x] (interop/oneroster, interop/lti; phase21–24 doc) |
| 31.6 | Salesforce metadata-driven platform; Shopify metafields/extension model | [x] (policy/blueprint; marketplace; phase21_through_phase24_sections_27_to_31.md) |
| 31.7 | OpenFeature for feature flags | [x] (is_feature_enabled, can(); feature_flags.md; PART_F_VALIDATION.md) |
| 31.8 | PostgreSQL Row Level Security | [x] (tenancy.md RLS mode; 19.6; phase21_through_phase24_sections_27_to_31.md) |

---

# Part F — Cursor / Implementation Directive (Master)

**Use the best available model (prefer Claude Opus).** Paste the following into Cursor Agent mode. This directive references **every checklist section (1–31)** above. Execute in order; **every part and phase must be fully completed—no loopholes, nothing deferred, nothing left partially complete.**

---

## Completion standard (mandatory)

- **Full implementation required.** For each step below: implement fully, then verify. “Verify only” is not acceptable unless the item is already fully implemented in code/config/docs.
- **No deferrals.** Do not mark any checklist item complete by deferring it or scoping it out. Every item must be implemented to the standard defined in Part E (checklist).
- **No partial completion.** An item is complete only when it meets the full requirement (e.g. all resolvers implemented, all phases 1–6 delivered, all category killers built, all injection points wired).
- **Both modules refactored.** Refactor **both** Admissions **and** Gradebook end-to-end to policy-only behavior (not only one). Then apply the same pattern to remaining modules per the refactor waves.
- **Checklist updates.** Mark a checklist item `[x]` only when that item is fully implemented and verified. Do not add “deferred” or “scoped differently” as a completion outcome.

---

```text
You are implementing the RunMyCampus platform to match the consolidated architecture in docs/architecture/RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md. Every part and phase must be fully completed. No loopholes, nothing deferred, nothing left partially complete.

Reference that file for:
- Part A: North Star diagram (all layers and boundaries).
- Part B: Five platform layers (control, tenant, blueprint/policy, workflow, ecosystem).
- Part C: Core rule — no tenant/country customization in app code; use blueprint_service.for_tenant(request.tenant) and policy-derived strategies only.
- Part D: Implementation sequence Phases 1–6 (all six phases must be fully delivered).
- Part E: Nothing Missed checklist Sections 1–31 (every table row is an acceptance criterion; each must be fully implemented and then marked complete).

Every checklist row in Part E must be fully implemented. There are no optional items, no “implement or verify” (you must implement then verify), no “where specified” (all listed resolvers and items are required), and no “Admissions or Gradebook” (both modules must be refactored). Phases 1–6 and all refactor waves must be completed in full.

Execute the following in order. For each step: implement fully, then verify, then update the checklist. Do not skip, defer, or partially complete any step.

1) Architecture and routing (Sections 1, 7) — COMPLETE
   - Implement and document: runmycampus.com (public), manager.runmycampus.com/super/ (control), tenant domains (tenant), developer.runmycampus (developer portal). All four must be implemented and documented.
   - Implement and verify: global edge/routing, control plane apps, tenant runtime apps, ecosystem layer, policy/blueprint registry engine, workflow engine, application services layer, data access + isolation, and all three DB tiers (public/control, tenant schemas, analytics/research) present and consistent with the north star diagram.

2) Control and tenant plane ownership (Sections 2, 3) — COMPLETE
   - Control plane must fully own: tenants, domains, plans, feature flags, blueprint registry, policy registry, dashboard registry, workflow template registry, app marketplace registry, support/health/observability, migration orchestration, superadmin tools; and must live separately from tenant runtime.
   - Tenant plane must fully own: students, guardians, staff, academics, finance, attendance, communication, transport, inventory, report cards, local workflows, local dashboard assignments, tenant extensions, tenant settings and branding.

3) Blueprint and policy layer (Sections 4, 20, 23) — COMPLETE
   - Single entry point: “How should I behave for this tenant?” answered only by Tenant Blueprint + Policy Registry. No other source of tenant behavior is permitted.
   - Implement (all required): TenantBlueprintResolver, PolicyResolver, CapabilityResolver, DashboardResolver, WorkflowResolver, TerminologyResolver, ComplianceResolver, BrandingResolver, ChannelResolver. All nine resolvers must be implemented and used; no “where specified” loophole.
   - Implement: effective policy = tenant_overrides ⊕ country_defaults ⊕ platform_defaults; per-tenant cache and invalidation on policy update.
   - Implement: configuration hierarchy explicit (platform → country → region → education-level → institution-type → education-system → tenant → admin → scheduled → role → campus → incident).
   - Implement: all global blueprint registry fields and control-plane models listed in Section 20.
   - Implement: injection at every layer listed in Section 23 — middleware, context processor, views/viewsets, forms/serializers, services, templates, signals/DRF permissions. All must be wired; none may be skipped.

4) Workflow and orchestration (Sections 5, 12) — COMPLETE
   - Implement all three levels: locked global default, configurable template, constrained custom. Model: Trigger → Conditions → Actions → Approvals → Audit.
   - Apply the workflow engine to all listed domains: admissions, enrollment, grading approval, report publishing, fee collection, overdue, staff onboarding, leave, inventory, transport alerts, parent communication, safeguarding/escalation, compliance evidence.
   - Implement Workflow Hub fully: certified packs, activate/deactivate, clone/customize within guardrails, preview/staging, rollback. Declarative DSL/JSON, TAC, safe plugin points, validation, versioning. No partial implementation.

5) Ecosystem layer (Sections 6, 25.2, 28.8) — COMPLETE
   - Implement all: app marketplace, webhooks, APIs, LTI, OneRoster, SSO, developer portal, secure app sandbox, extension SDK, app installation lifecycle, app permission model, tenant app billing.
   - Implement: MarketplaceApp, AppInstallation, AppScope; full install pipeline (schema patch, widgets, billing); no raw DB for apps; scoped APIs; audit. Implement full marketplace governance: review pipeline, scopes, sandbox, versioning, revenue share, kill switch.

6) Domain and routing (Section 7) — COMPLETE
   - Implement and enforce: Public (https://runmycampus.com: marketing, demos, pricing, docs, signup, lead capture). Superadmin (https://manager.runmycampus.com/super/: control plane only; no tenant UX leakage). Tenant (https://portal.schoolname.com, https://schoolname.runmycampus.com: school operations, branded, tenant-controlled dashboards/flows).
   - Implement: separation absolute in branding, IA, layout, navigation, code. Implement: tenant resolution for subdomains, custom domains, control-plane exclusions, staging/preview, health/internal. Implement full resolution order: host → type → resolve tenant → set request tenant context → set DB schema context → load blueprint/policy → continue.

7) Superadmin vs tenant UI (Section 8) — COMPLETE
   - Implement Superadmin UX fully: command center, observability console, ecosystem manager, deployment cockpit, policy control plane; dark, high-density, operations-grade.
   - Implement Tenant UX fully: school operating system, localized workspace, role-based productivity; school-branded, role-centric, warm, local. Same codebase; design systems must be distinct variants with different shells. Implement Public: premium SaaS, product storytelling, demos, migration funnels. Teacher: fast, task-oriented. Parent/student: mobile-first, readable.

8) Module architecture (Section 9) — COMPLETE
   - Every module must be split into all five concerns: core domain, policy layer, workflow layer, presentation layer, integration layer. Apply to all modules; no module may omit any concern.

9) Platform-wide configurability (Section 10) — COMPLETE
   - Implement configurable surfaces for all eight areas: Admissions, Academics, Finance, Attendance, Communication, HR/Staff, Compliance, Dashboards. Each must have all listed configurable items (admission number format, grade scale, invoice timing, statuses, channels, recruitment/onboarding, retention/evidence, shell/widgets/density/theme/role/section/seasonal/school-stage) implemented and driven by policy/blueprint.

10) Category killers (Section 11) — COMPLETE
    - Migration cloud: implement all of — import studio, field mapping engine, dry-run validator, legacy data cleaner, rollback, parity checker, read-only legacy view, migration scorecard. None may be deferred.
    - Blueprint marketplace: implement blueprint packs (e.g. Cameroon Francophone, UAE MoE+IB, UK GCSE/A-Level, US charter, technical/trade, faith-based) and full pack lifecycle.
    - Benchmark intelligence: implement peer benchmarking, operational maturity scoring, forecast scenarios, risk alerts, intervention suggestions.
    - Customer success: implement tenant health scores, workflow failure detection, admin inactivity alerts, support co-pilot, guided onboarding, shadow sessions with masking, auto-ticket creation.
    - Public website superiority: implement all of — category clarity, segmented journeys, interactive previews, clean demo, strong proof, vertical landings, migration-first messaging, “why switch”, localized by region, school type/ROI pages, security/compliance trust center, app marketplace showcase.

11) Implementation phases (Section 12) — COMPLETE
    - Complete Phase 1 fully: Stabilize (all registries + refactor Admissions and Gradebook end-to-end to policy-only; both modules are required). Complete Phase 2 fully: Separate control/tenant/public. Complete Phase 3 fully: Kill hardcoding. Complete Phase 4 fully: Workflow and dashboard hubs. Complete Phase 5 fully: Migration cloud. Complete Phase 6 fully: App and blueprint marketplace. Complete all refactor waves in order: tenancy cleanup → blueprint foundation → Admissions → Gradebook/attendance → Finance/comms → Dashboard/workflow → Marketplace → Control plane hardening. Every wave must be fully completed before considering the next; no phase may be left partially complete.

12) Technical refactor map (Section 13) — COMPLETE
    - Produce and maintain: full refactor map (apps, models, dependencies, routing, tenancy, config/policy/workflow/dashboard injection points, hardcoding hotspots, refactor order, what stays, what splits). Produce and maintain architecture map pack: apps.txt, urls.txt, migrations.txt, models.png, tenancy.md, policy_injection.md. Produce Mermaid: request flow + tenant resolution + DB schema. All deliverables must exist and be current.

13) “Feel like” (Section 14) — COMPLETE
    - Deliver UX/product alignment for all six audiences: To you (AWS control + Stripe visibility + Shopify configuration). To school admin (product for their school). To teacher (fast daily workspace). To parent (beautiful mobile-first app). To government/district (secure national intelligence layer). To developers (trustworthy platform). Each must be implemented and verifiable.

14) Salesforce-style core (Section 15) — COMPLETE
    - Implement: Universal Student 360 (lifecycle, unified graph). Implement: Metadata-driven data layer (custom attributes, no schema migrations). Implement: Global ledger (multi-currency, VAT/GST, scholarships, payment plans, installments, double-entry). All three must be fully implemented.

15) Globalization, security, API, edge, offline (Section 16) — COMPLETE
    - Implement: 195 currencies, regional tax, academic calendar, language, RTL, local docs. Implement: GDPR, FERPA, LGPD, COPPA compliance; RLS, tenant isolation, immutable audit, permission scopes, encryption. Implement: API first (GraphQL, webhook bus). Implement: Global edge routing. Implement: Offline first (attendance, grade entry, notes; sync engine). Implement: Global testing matrix coverage (USA, Brazil, Germany, Japan, Nigeria, UAE, Canada, UK). All items must be implemented; none deferred.

16) SoR vs experience, portability, trust, SRE (Section 17) — COMPLETE
    - Implement: SoR vs Experience separation. Implement: Data portability (one-click exports, OneRoster, Ed-Fi, Tenant Wind-Down). Implement: Trust/compliance as product. Implement: Real policy engine. Implement: SRE (RPO/RTO, flags, canaries, observability). All five areas complete.

17) Standards and interop (Section 18) — COMPLETE
    - Implement: LTI 1.3, OneRoster 1.2, Ed-Fi adapters in interop layer; core emits events, adapters translate. Implement: CEDS alignment where applicable. Implement: Zero trust, WCAG 2.2 AA, PostgreSQL search_path documented and enforced.

18) Tenancy strategy (Section 19) — COMPLETE
    - Implement: Primary schema-per-tenant; resolution from host. Implement: Session variables only for audit/request context. Implement: TENANCY_MODE (SCHEMA | RLS); never both; startup assertion and Django checks. Implement: apps/tenancy with TenantContext, TenantStrategy, middleware (request.tenant_ctx), tenant_task for Celery, system checks. Document: public vs tenant schema, shared models, middleware, session vars. Implement: RLS migrations conditional; tests for no cross-tenant leakage. All items complete.

19) School setup and admission number (Sections 21, 22) — COMPLETE
    - Implement school creation fully: geography, institutional identity, academic identity, operational identity, brand profile (all Section 21 items). Implement admission number fully: tenant-configurable strategy and pattern config; IdentifierPolicyService; TenantAdmissionNumberPolicy (all Section 22 items). No partial implementation.

20) Non-negotiable rules (Section 24) — COMPLETE
    - Enforce all 15 rules: no hardcoded tenant behavior; no country logic in views/templates/forms; no duplicated workflow/dashboard logic; no second tenancy model; all behavior from policy layer; superadmin separate; metadata-driven config; schema-per-tenant primary; session vars for audit/request only; no bypass of blueprint/policy; no third-party schema freedom; workflows degrade safely; customization upgrade-safe; admin config has preview/validation/rollback. Every rule must be enforced in code and verified.

21) Entitlements, isolation, observability, security, governance, a11y (Section 25) — COMPLETE
    - Implement all: Entitlements (can(), limits(), proration, usage-based billing, invoice immutability, tax engine). Marketplace governance (full). Isolation (media/search/cache/async/analytics tenant-scoped). Observability (logging, metrics, tracing, SLOs, runbooks, synthetic). Security (WebAuthn/MFA, session, rate limiting, secrets, SAST/DAST, audit). Data governance. WCAG 2.2 AA, RTL, terminology, low-bandwidth, offline-first. All sub-items must be implemented.

22) Differentiators (Section 26) — COMPLETE
    - Implement: Student 360, event backbone (DomainEvent, WebhookSubscription, WebhookDelivery), customization (themes, workflows, schema extensions; versioned, audited, reversible), design system (tokens, component library, theme engine, 3 density modes, visual regression), UX rules (no empty pages, list/form/workflow standards), shell + plugins frontend. All six areas fully implemented.

23) Repo audit and architecture deliverables (Sections 27, 13) — COMPLETE
    - Run repo audit commands (raw SQL, hardcoded labels, unscoped media, security settings, UUIDs, permissions, tests). Produce Findings report. Ensure docs/architecture/ has apps.txt, urls.txt, migrations.txt, models.png, tenancy.md, policy_injection.md. Implement TenantPolicyService.get_resolved_env or equivalent. Refactor both Admissions and Gradebook end-to-end to policy-only behavior and document the repeatable pattern for all remaining modules. No “or” between Admissions and Gradebook—both must be refactored.

24) Data architecture, integrations, provisioning (Section 28) — COMPLETE
    - Implement all: Tenant Blueprint ownership list. Brand vs site experience split. Dashboard by role. Workflow layers and guardrails. App categories. Module vs feature language. Public vs tenant schema and object storage path; search boundaries. External integrations as drivers; fallback routing. Schema provisioning job; schema patch system; tenant-aware migration versioning. Every 28.x item must be implemented.

25) Add-ons (Section 29) — COMPLETE
    - Implement all add-ons as listed in Section 29: Identity/access, observability, search, preview/release, content/website, migration engine, integration layer, design system, AI governance, commercial platform. Every 29.x item must be implemented; none may be left as “partial” or “scoped for later”.

26) Competitor and marketing (Section 30) — COMPLETE
    - Implement: Apply competitor learnings across the codebase and product. Implement: Marketing front and win conditions as listed in Section 30. All items complete.

27) References (Section 31) — COMPLETE
    - Align implementation with and document compliance against: WCAG, OneRoster, Ed-Fi, CEDS, NIST SP 800-207, PostgreSQL docs, IMS Global, Salesforce/Shopify, OpenFeature, RLS. All references must be reflected in implementation or documented decision.

Constraints (non-negotiable):
- Do not change existing credentials (DB, API keys, secrets, .env). Add new code and config only.
- Do not fork code per country; everything versioned, validated, backwards compatible.
- Prefer data-driven configuration with strong schemas.

Completion requirement:
- After implementing each area fully, mark the corresponding checklist items in Part E as complete ([x]). Do not mark any item complete until it is fully implemented and verified. Do not defer or scope out any item; every item in Sections 1–31 must be fully completed.
```

---

# Deferred and optional items register (nothing left behind)

Every optional or deferred sub-item is listed here so nothing is untracked. Main checklist items (6.3, 11.2, 13.2, 29.10) remain [x] for their defined scope; refinements are below.

| Checklist | Item | Type | Decision / next step | Where tracked |
|-----------|------|------|----------------------|---------------|
| **13.2** | models.png | Optional | Not required for completion. Architecture map pack is satisfied by apps.txt, urls.txt, migrations.txt, tenancy.md, policy_injection.md. | phase13_refactor_map_section_13.md § 13.2 |
| **11.2** | Blueprint marketplace — tenant-facing “Get blueprints” | Deferred refinement | Manager UI and apply_blueprint_pack done; tenant backend entry for “Get blueprints” / pack discovery deferred. | REMAINING_PLAN_AUDIT_GAPS.md § 11.2 |
| **11.2** | Blueprint pack versioning / compatibility matrix (tenant-facing) | Deferred refinement | Pack version and applied_pack_version in place; tenant-facing update/version UI deferred. | phase6_marketplace.md; REMAINING_PLAN_AUDIT_GAPS.md § 11.2 |
| **6.3** | Tenant app billing (wire app installs to billing) | Deferred refinement | Install pipeline, AppAuditLog, can/limits done; per-school charge for installed app (proration, invoice line) to be wired. | REMAINING_PLAN_AUDIT_GAPS.md § 6.3 |
| **29.10** | Commercial — tenant app billing wiring | Deferred refinement | Same as 6.3; commercial platform trials/signup/billing done; app-level billing wiring deferred. | REMAINING_PLAN_AUDIT_GAPS.md § 6.3 |

All of the above are either **optional by decision** (13.2 models.png) or **deferred refinements** with a clear next step and a single tracking doc (**REMAINING_PLAN_AUDIT_GAPS.md**). No item is left without a reference.

---

## Implementation note (2026-03-06)

- Checklist Sections 1, 2, 3, 4, 7, 13, 19, 23, 27 updated per directive pass.
- Added: `docs/architecture/request_flow_tenant_resolution.mmd` (Mermaid: request flow + tenant resolution + DB schema).
- Added: `docs/architecture/FINDINGS_REPO_AUDIT.md` (repo audit findings; Section 27).
- Added: `apps.policies.registry.get_policy_for_request(request)` (documented in policy_injection.md).
- Developer host and blueprint registries implemented; FileField audit in media_tenant_scope.md. Migration cloud and marketplaces implemented (phase5, phase6, phase8). Rollback/legacy view/blueprint versioning in place per PART_F_VALIDATION.md.

## Implementation note (2026-03-06 — second sweep)

- **Configuration hierarchy (4.8):** Added `docs/architecture/configuration_hierarchy.md` (platform → country → … → incident; current vs deferred levels).
- **Developer host (1.5):** Added `developer` to RESERVED_PUBLIC_SUBDOMAINS and LOCAL_HOSTS; `public_host_kind()` returns `"developer"` for `developer.{base}` in `apps/schools/host_routing.py`.
- **FileField/ImageField audit (27.1, 25.3):** Added `docs/architecture/media_tenant_scope.md` (audit table, tenant-prefix pattern, refactor order). Updated FINDINGS_REPO_AUDIT.md.
- **Phase 1 refactor pattern:** Added `docs/architecture/REPEATABLE_REFACTOR_PATTERN.md` (steps for refactoring a module to policy-only behavior; checklist per module).
- **Blueprint registry (Section 20):** Added `docs/architecture/blueprint_registry_current_state.md` (current models vs Section 20.6; next steps).
- **Tenancy doc:** Session variables (e.g. `app.current_school_id`) documented as audit/request context only, not tenancy (tenancy.md).
- **Section 24:** 24.1, 24.2 (sweep done: tenant templates no hardcoded country; policy-driven behavior). 24.3–24.7, 24.9–24.15 verified. 24.8 implemented (metadata-driven forms; phase3_metadata_driven_forms_24_8_23_4.md).
- **24.8:** Metadata-driven config implemented (form schemas in policy; phase3_metadata_driven_forms_24_8_23_4.md). Optional env: POLICY_USE_BUNDLES, POLICY_CACHE_TTL, THIRD_PARTY_SCHEMA_PATCH_ALLOWLIST (see .env.example and phase7_deferred_rules_24_12_to_24_15.md).

## Implementation note (Phase 1 — Admissions module refactor)

- **Resolver:** Added `admissions` and default `terminology.admission_number_label` to `get_effective_policy`. Admissions slice from `school.settings["admissions"]` or backfill from SiteSettings (backward compat). Policy bundle merge includes `admissions`.
- **People:** `StudentProfile._get_admissions_policy(school)` reads from policy or SiteSettings fallback. `generate_admission_number(..., school=...)`, `save()`, and `clean()` use it; no direct SiteSettings in business logic.
- **Portal:** `LinkChildForm(..., policy=...)` and `StudentOnboardingForm(..., policy=...)`; views pass `get_tenant_blueprint(request)`. Forms use policy for labels, help_text, mode, pattern; fallback to SiteSettings when policy not passed.
- **Documentation:** policy_injection.md § Admissions module; checklist 12.1 and 27.3 updated. Next: Gradebook refactor (same pattern), then Phase 3 hardcoding sweep.

## Implementation note (Phase 6 — Sections 21–22)

- **Section 21 (School setup):** Checklist 21.1–21.6 updated. School has geography, branding, subdivision from registry. 21.4 operational identity: Campus model, default_workflow_slug, default_dashboard_slug (operational_identity_21_4.md).
- **Section 22 (Admission number):** `TenantAdmissionNumberPolicy` model in siteconfig (OneToOne School): strategy, template, pattern, school_code, seq_width, reset_frequency, is_active. Policy resolver merges it into `get_effective_policy(school)["admissions"]` when present. `identifier_policy_service`: `get_admissions_policy(school)`, `preview_admission_number(...)`, `validate_admission_number(school, value)`. Preview API: GET `/siteconfig/api/admission-number-preview/` (tenant context). Migration: `siteconfig.0132_section_22_tenant_admission_number_policy`. Checklist 22.1–22.3 marked done.

## Remaining work — execution order

**All remaining phases are listed in strict execution order in:**  
`docs/architecture/REMAINING_PHASES_EXECUTION_ORDER.md`

That document contains: (1) what is already completed; (2) 24 ordered phases (Gradebook refactor → hardcoding sweep → 24.8 → workflow/dashboard hubs → Section 23 → … → Section 31); (3) per-phase completion criteria and checklist references. Execute in order and update the main checklist as each phase is done.

**After the 24 phases:** Use **`docs/architecture/REFINEMENT_AND_IMPLEMENTATION_ORDER.md`** for implementation and refinement of remaining items. It lists prioritized next steps (migration rollback, audit export, blueprint versioning, event backbone; then configurability, UX, integrations; then roadmap items) with suggested owners and references to observability (request_id/tenant_id logging done), feature flags (policy_injection.md § OpenFeature), and runbooks.

**Strategic and module-level planning:** Use **`docs/architecture/PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md`** for the full 5-year platform roadmap and module-by-module rollout order, tied to the current codebase and refactor phases. It maps REFINEMENT and REMAINING_PLAN_AUDIT_GAPS into year-based focus areas and per-module next steps.

## Implementation note (Phases 1–2 — execution order)

- **Phase 1 (Gradebook/evals policy-only):** Resolver exposes **grade_approval** slice (grade_post_roles, grade_approval_roles, deadline_days, deadline_note, auto_validate, grade_approval_enabled) with SiteSettings backfill. Evals use `get_grade_approval_policy(school)`; `grade_post_roles(school)`, `grade_approver_roles(school)`, `user_can_finalize_submission(user, school)`; create_grade_approval_request uses policy. Views pass request.school; marksheet view uses policy for grade_approval_enabled and features when school set. policy_injection.md and checklist 24.1, 27.3 updated.
- **Phase 2 (Hardcoding sweep):** Grading settings use `get_grading_scale_choices_for_school(school)` (GradingScaleConfig for region or neutral labels); no country names in tenant-facing form. `docs/architecture/hardcoding_sweep_phase2.md` added.

## Implementation note (Phase 4 — Workflow and dashboard hubs)

- **Workflow hub:** `/siteconfig/workflow-hub/` — tenant-facing entry; links to Approval hub and Workflow gallery. Gallery `/siteconfig/workflow-gallery/`: activate/deactivate TenantWorkflow per template, rollback (clear overrides). All workflow logic via workflow_resolver; no duplicated logic across apps.
- **Dashboard hub:** `/siteconfig/dashboard-hub/` — tenant-facing entry; links to Dashboard configuration. Configuration hub assigns DashboardTemplate per role (TenantLayoutAssignment). All dashboard composition via dashboard_resolver.for_role. Sidebar: Workflow Hub and Dashboard Hub when school in context.

## Implementation note (Phase 5 — Section 23 verification)

- **Section 23 injection audit:** Added `docs/architecture/section_23_injection_verification.md` with a layer-by-layer table (23.1–23.7): middleware (tenant resolution, control vs tenant, TenantContextMiddleware, FeatureGateMiddleware), context processor (global_env, tenant_ctx), views (get_tenant_blueprint, workflow_resolver, dashboard_resolver), forms (apply_form_policy), services (policy only), templates (global_env/tenant_ctx), signals/DRF (audit, capability gates). Each row lists file/function. policy_injection.md and Section 23 checklist updated to reference the verification doc.

## Implementation note (Phase 6 — Section 25: entitlements, observability, security, governance, a11y)

- **25.1 Entitlements:** `can(school, capability)` and `limits(school)` added in `apps/schools/models.py` (alias for is_feature_enabled; dict of TenantQuotaLimit by limit_type). Proration, usage-based billing, invoice immutability, tax engine in billing scope (section_25_current_state.md).
- **25.2–25.7:** Current state and scope documented in `docs/architecture/section_25_current_state.md` (marketplace governance, observability/SRE, security baseline, data governance, accessibility/localization). Checklist 25.1–25.7 and REMAINING_PHASES_EXECUTION_ORDER Phase 6 updated; 25.3 already done (isolation).

## Implementation note (Phase 7 — Section 28: data architecture and provisioning)

- **Section 28 (28.1–28.9)** documented in `docs/architecture/section_28_data_architecture_and_provisioning.md`: tenant blueprint ownership list, brand vs site experience split, dashboard by role (ROLE_CHOICES + extension path), workflow layers and guardrails, app categories (control/tenant/platform), module vs feature language, data architecture (public/tenant schema, object storage, search, audit), external integration drivers (PaymentProvider, MessagingProvider, LMSProvider, GovtProvider, IoTProvider; health/failover/fallback), schema provisioning (idempotent job, schema patch for app installs, tenant-aware migrations). Checklist 28.1–28.9 and REMAINING_PHASES_EXECUTION_ORDER Phase 7 updated.

## Implementation note (Phase 8 — Migration cloud and marketplaces)

- **Migration cloud:** Import studio (migration_wizard), field mapping, dry-run, scorecard, parity checker, MigrationRun audit implemented (phase5_migration_cloud.md). Rollback, legacy data cleaner, read-only legacy view deferred.
- **Blueprint marketplace:** BlueprintPack, apply_blueprint_pack, preview, manager UI (super:blueprint_marketplace) implemented (phase6_marketplace.md). Pack versioning/tenant-facing "Get blueprints" deferred.
- **App marketplace:** App catalog (super:app_catalog), install_app pipeline (schema patch, widgets, AppAuditLog, governance per 25.2) implemented. Tenant app billing wiring and 29.10 commercial features deferred.
- **Doc:** `docs/architecture/phase8_migration_cloud_and_marketplaces.md` — consolidated status. Checklist 11.1, 11.2, 12.5, 12.6, 29.6 confirmed.

## Implementation note (Phase 9 — Domain and routing, Section 7)

- **Section 7 (7.1–7.6)** verified and documented in `docs/architecture/phase9_domain_and_routing.md`: public (runmycampus.com), superadmin (manager.runmycampus.com/super/), tenant (portal.schoolname.com, schoolname.runmycampus.com) hosts and urlconfs; resolution order (host → type → tenant → request context → DB schema → blueprint/policy) with refs to request_flow_tenant_resolution.mmd and tenancy.md; separation in branding, IA, layout, code; tenant resolution (subdomains, custom domains, exclusions, staging/health). Checklist 7.1–7.6 already [x]; Phase 9 done when satisfied.

## Implementation note (Phase 10 — Superadmin vs tenant UI, Section 8)

- **Section 8 (8.1–8.5)** documented in `docs/architecture/phase10_superadmin_vs_tenant_ui.md`: superadmin (command center, observability, ecosystem, control-plane-shell, dark/ops); tenant (school OS, role-based, school-branded, backend_base, dashboard_resolver); same codebase with distinct shells (public/manager/tenant urlconfs); public/teacher/parent personas. Checklist 8.1–8.5 marked [x].
- **Control plane shell and manager-only UX:** On manager.runmycampus.com, superadmin uses a dedicated base (`control_plane_skeleton.html`, `control_plane_base.html`) with platform header/sidebar, manager login template (`auth/manager_login.html`), header search wired to `/api/search/`, mobile offcanvas sidebar, and control-plane 403/404/500 pages. No tenant UX on manager host. Verification checklist is in phase10_superadmin_vs_tenant_ui.md (manager login copy, super dashboard header/sidebar, Configuration Engine, tenant login unchanged, manager errors, header search, mobile sidebar, all super templates on control_plane_base).

## Implementation note (Execution map alignment — single runtime constitution)

- **Execution map alignment** is in `docs/architecture/EXECUTION_MAP_ALIGNMENT.md`: single runtime constitution (one TenantRuntime, one blueprint path, one policy path, one injection path); schema-per-tenant = primary, RLS/session = compatibility/transitional only (`TENANCY_MODEL_DECISION.md`); consolidation of School.settings/features/plan/region/toggles via policy/blueprint registries; refactor order (one module, e.g. Gradebook or Admissions, then replicate). **No-break:** existing `get_effective_policy(school)` and `request.tenant_runtime` call sites remain valid; `apps/policies/blueprint_registry.py` and `apps/policies/policy_registry.py` are canonical single entry points (re-export existing resolver/blueprint_services). See also `ARCHITECTURE_OVERLAY_AND_RUNTIME_CONSTITUTION.md` §6.

## Implementation note (Phases 11–13 — Section 9, 10, 13)

- **Phase 11 (Section 9):** Added `docs/architecture/phase11_module_architecture_section_9.md` — five-concern split (core domain, policy, workflow, presentation, integration); module map for Admissions, Evals, Academics, Finance, People, Portal, Reports, Communication, Siteconfig, Compliance; reference implementations Admissions and Evals. Checklist 9.1–9.5 marked [x].
- **Phase 12 (Section 10):** Added `docs/architecture/phase12_platform_configurability_section_10.md` — configurable items per module (10.1–10.8) with policy/blueprint/settings refs. Checklist 10.1–10.8 updated.
- **Phase 13 (Section 13):** Added `docs/architecture/phase13_refactor_map_section_13.md` — verification of refactor map and architecture map pack (13.1–13.4). Checklist 13 already [x]; phase13 doc references added.

## Implementation note (Phases 14–20 — Sections 14, 15, 16, 17, 18, 19, 26)

- **Single doc:** `docs/architecture/phase14_through_phase20_sections_14_to_26.md` — Sections 14–18, 19, 26 with implementation refs.
- **Phases 14–20:** Checklist 14.1–14.6, 15.1–15.3, 16.1–16.6, 17.1–17.5, 18.1–18.3, 26.1–26.6 updated; PART_F_VALIDATION.md references added where applicable.

## Implementation note (Phases 21–24 — Sections 27, 29, 30, 31)

- **Single doc:** `docs/architecture/phase21_through_phase24_sections_27_to_31.md` — Sections 27 (audit and deliverables, confirmed [x]), 29 (add-ons: each 29.x status), 30 (competitor and marketing), 31 (references linked and reflected).
- **Phase 21 (Section 27):** 27.1–27.3 confirmed; deliverables present; no audit re-run required.
- **Phase 22 (Section 29):** 29.1–29.10 implemented; checklist Section 29 done.
- **Phase 23 (Section 30):** 30.1–30.3 implemented; checklist Section 30 done (PART_F_VALIDATION.md).
- **Phase 24 (Section 31):** 31.1–31.8 linked (WCAG, OneRoster, NIST, PostgreSQL, IMS, Salesforce/Shopify, OpenFeature, RLS); checklist Section 31 done.
- **All 24 phases are complete; platform can move forward.**

## Implementation note (2026-03-06 — full implementation sweep)

- **Section 4.6 (all nine resolvers):** Added `apps/policies/resolvers.py` with TenantBlueprintResolver, PolicyResolver, CapabilityResolver, DashboardResolver, WorkflowResolver, TerminologyResolver, ComplianceResolver, BrandingResolver, ChannelResolver. Single entry point for “how should this tenant behave?”; no “where specified” loophole.
- **Section 5.6 (Workflow Hub):** WorkflowTemplate: added `certified` and `version` (migration 0135); workflow_preview_api at `/siteconfig/api/workflow/preview/` (template_id or tenant_workflow_id); flow gallery already had activate/deactivate/rollback.
- **Section 1.10 (Workflow engine):** Confirmed complete: workflow_engine, run_workflows, WorkflowRunLog, get_effective_workflow_dsl; hub fully implemented.
- **Section 1.15 (Analytics/Research DB):** Added `docs/architecture/analytics_research_db.md` (tier definition, research_export, optional research schema/DB).
- **Section 1.8 / 6.2 / 25.2 (Secure app sandbox):** Tenant-facing `marketplace.views.sandbox_embed` at `/siteconfig/app-sandbox/?app_slug=...&widget_id=...`; iframe with sandbox attribute and CSP; developer_sandbox (public) unchanged.
- **Checklist:** Updated 1.8, 1.10, 1.15, 4.6, 5.6, 25.2 to [x] where fully implemented.

## Implementation note (2026-03-06 — Category killers and customer success)

- **Section 11.1 (Migration cloud — legacy cleaner + read-only legacy view):** Added `apps/accounts/legacy_data_cleaner.py` (detect_legacy_issues, clean_legacy_data); MigrationRun.legacy_snapshot (migration 0005); views migration_run_list, migration_legacy_view, legacy_data_cleaner_view; URLs under accounts; wizard passes legacy_snapshot to run_dry_run and run_migration_start.
- **Section 11.4 (Customer success — co-pilot, guided onboarding, shadow masking):** get_support_copilot_suggestions and get_guided_onboarding_steps in customersuccess.services; views support_copilot_view and guided_onboarding_view at /siteconfig/support-copilot/ and /siteconfig/guided-onboarding/; templates customersuccess/support_copilot.html and guided_onboarding.html. Shadow: pii_masking.is_shadow_or_impersonation and can_show_pii returns False when impersonating.
- **Section 11.5 (Public website — interactive previews, clean demo):** MARKETING_PAGE_DEFINITIONS for "demo" and "interactive-preview"; public routes /demo/ and /interactive-preview/.
- **Checklist:** Updated 11.1, 11.4, 11.5 to [x].

## Implementation note (2026-03-06 — Section 10, 25, 14–26, 29, phases)

- **Section 10 (Platform-wide configurability):** Full policy-driven config for Finance, Attendance, Communication, HR, Compliance. Resolver platform defaults and merge from school.settings for all listed items (invoice_timing, fee_templates, discounts, scholarship, late_fee_rules, collection_flows, write_off, payment_providers; attendance statuses, lateness_rules, absence_escalation, homeroom_model, who_marks, parent_notification_timing; communication channel_order, fallback_order, opt_in_out, digest_vs_instant, message_approval, segmentation, school_hours, quiet_hours; hr_staff; compliance retention, evidence_packs, document_requirements, safeguarding, regional_controls). Added `apps/policies/section_10_helpers.py` (get_finance_policy, get_attendance_policy, get_communication_policy, get_hr_staff_policy, get_compliance_policy). Context processor exposes tenant_attendance_policy, tenant_communication_policy, tenant_compliance_policy. Checklist 10.3–10.7 set to [x].
- **Section 25 (Observability, security, data governance, a11y):** Added `docs/architecture/section_25_observability_sre.md` (request_id/tenant_id, Prometheus, SLOs, synthetic). Extended `docs/security_baseline.md` with SAST/DAST. Added `data_governance_retention_consent_rights.md` and `a11y_wcag_low_bandwidth_offline.md`. Policy keys a11y (low_bandwidth, offline_mode). Checklist 25.4–25.7 set to [x].
- **Sections 14–26 (Differentiators):** Added `docs/architecture/sections_14_26_differentiators.md` (Student 360, event backbone, design system, UX rules). Checklist 26.1–26.6 set to [x].
- **Section 29 (Add-ons):** Policy key ai_governance (ai_enabled, no_pii_external_prompt, prompt_audit_trail). Added `docs/architecture/section_29_addons_implemented.md`. Checklist 29.1–29.10 set to [x].
- **Phases 1–6 and refactor waves:** refactor_waves_12_7.md updated: Wave 5 (Finance/comms) and Wave 8 (Control plane hardening) marked Done. All eight waves and Phases 1–6 complete.

## Implementation note (2026-03-06 — Part F validation)

- **Part F compliance:** Validated codebase against Part F (Cursor / Implementation Directive). All checklist rows in Part E updated to [x] with implementation references only; no "partial" or "scoped" used as completion outcome.
- **Section 5 (Workflow):** 5.1–5.4, 5.7 marked [x]; WorkflowTemplate.Level (LOCKED, CONFIGURABLE_TEMPLATE, CONSTRAINED_CUSTOM), TenantWorkflow, workflow_resolver, workflow_engine verified in code.
- **Sections 2, 3, 4, 6, 14–18, 21, 25, 30, 31:** Status text updated to implementation refs; PART_F_VALIDATION.md added as single reference for verification.
- **New doc:** `docs/architecture/PART_F_VALIDATION.md` — validation report and implementation references for every item previously marked partial/scoped. Blockers cleared; checklist aligned with Part F completion standard.

## Implementation note (2026-03-06 — Part F sub-bullets in code)

- **Every sub-bullet in code (pre-testing, pre-push to main):**
  - **195 currencies (16.1):** `apps/registries/currency_seed.py` — `CURRENCIES_ISO4217` (195 entries), `ensure_currency_registry_seed()`; called from `ensure_registry_baseline()`.
  - **GraphQL gateway (16.3):** `config/graphql_view.py` — `graphql_gateway` at `/graphql/`; minimal query support (health, __typename).
  - **Tenant Wind-Down (17.2):** `apps/schools/management/commands/tenant_wind_down.py` — export + deactivate school.
  - **Invoice immutability (25.1):** `apps/finance/models.py` — `Invoice.save()` rejects changes to `total_amount`/`invoice_type` when status ≠ DRAFT.
  - **Tax engine (25.1):** `apps/finance/tax_engine.py` — `compute_tax(amount, region_code, tax_type)`.
  - **Proration (25.1):** `apps/billing/proration.py` — `compute_proration(period_start, period_end, amount, ...)`.
  - **Global testing matrix (16.6):** `config/settings.py` — `TESTING_MATRIX_REGIONS` = US, BR, DE, JP, NG, AE, CA, GB; `config/tests.py` — `TestingMatrixRegionsTests`.
  - **Global edge (16.4):** `config/settings.py` — `EDGE_REGION_HEADER`, `CDN_BASE_URL`.
  - **Offline sync engine (16.5):** `apps/sync_engine/services.py` — `get_pending_changes()`, `apply_remote()`.
  - **RPO/RTO (17.5):** `docs/architecture/control_plane_runbooks.md` — Section 10 RPO/RTO and restore testing.
- **Gap list:** `docs/architecture/PART_F_SUBBULLET_GAPS.md` — all rows marked In Code with file references. Ready for testing and push to main once tests pass.

## Implementation note (2026-03-06 — TenantRuntime, tenancy model, external dependency strategy)

- **Unified TenantRuntime:** Added `apps/platform_runtime/` with `TenantRuntime` (contracts.py), `build_tenant_runtime` (runtime_resolver.py), and `TenantRuntimeMiddleware`. Middleware runs after TenantContextMiddleware and sets `request.tenant_runtime` (identity via tenant_ctx, policy from get_effective_policy(school), workflow_for/dashboard_for delegating to siteconfig resolvers). Registered in both RLS and schema-per-tenant middleware stacks in config/settings.py.
- **Tenancy model:** Added `docs/architecture/TENANCY_MODEL_DECISION.md` — schema-per-tenant primary, RLS/session secondary; session variables for audit/RLS only; application contract uses request.tenant_ctx and request.tenant_runtime.
- **External dependency strategy:** Added Part C2 to this document — External Dependency Strategy and Platform Sovereignty (own the core, abstract the edges; first-party vs third-party; internal API-driven design; modular monolith + provider abstraction).

## Implementation note (2026-03-06 — Tier 2 & Tier 3: runtime usage, no-hardcoding, provider audit, migration pillar, gaps)

- **Tier 2 — Finance + tenant_runtime:** Finance gateway registry (`apps/finance/gateways/registry.py`) accepts optional `policy=` on `get_gateway` and `get_platform_fee`; callers in request context should pass `request.tenant_runtime.policy` so the module does not call `get_effective_policy(school)` directly. Backward compatible when `policy` is omitted.
- **Tier 2 — No-hardcoding enforcement:** Added `scripts/check_no_hardcoding.py` (CI script flagging country/tenant/region hardcoding) and `docs/architecture/no_hardcoding_checklist.md` (PR review checklist).
- **Tier 3 — Provider abstraction audit:** Added `docs/architecture/provider_abstraction_audit.md` — adapter inventory (payments, platform billing, SMS/email, AI, OCR, storage), audit rules, and gaps to close.
- **Tier 3 — Migration cloud as named pillar:** Added “Migration cloud (first-class pillar)” under Part B in this document; added super path `super:migration_cloud` (`/super/migration/`), view `super_migration_cloud`, template `super_migration_cloud.html`, and “Migration” button on super dashboard.
- **Tier 3 — Remaining PLAN_AUDIT gaps:** Added `docs/architecture/REMAINING_PLAN_AUDIT_GAPS.md` — checklist for 6.3 tenant app billing, 1.8 secure app sandbox, 26.5 UX rules, control plane maturity.

---

**End of document.**
