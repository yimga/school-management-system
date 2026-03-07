# Part F — Complete Checklist (Every Major, Sub, and Sub-Sub Bullet)

**Purpose:** Exhaustive list of every requirement in Part F (steps 1–27) and their dependencies from Part E (Sections 1–31). Each line must be implemented in code or documented; no shortcuts.

**Date:** 2026-03-06

---

## Step 1 — Architecture and routing (Sections 1, 7)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 1.1 | runmycampus.com (public) | ✓ | host_routing, public_urls, marketing_landing |
| 1.2 | manager.runmycampus.com/super/ (control) | ✓ | host_routing, manager_urls, super_views |
| 1.3 | Tenant domains (portal.schoolname.com, schoolname.runmycampus.com) | ✓ | host_routing, tenant_urls, TenantSchemaSchoolBridgeMiddleware |
| 1.4 | developer.runmycampus (developer portal) | ✓ | RESERVED_PUBLIC_SUBDOMAINS, public_host_kind developer, developer_portal view |
| 1.5 | Global edge/routing | ✓ | config: EDGE_REGION_HEADER, CDN_BASE_URL; global_edge_and_testing_matrix.md |
| 1.6 | Control plane apps | ✓ | manager urlconf, control plane apps in INSTALLED_APPS |
| 1.7 | Tenant runtime apps | ✓ | tenant urlconf, SIS/LMS/Finance/Admissions/HR/CRM/Comms/Transport |
| 1.8 | Ecosystem layer | ✓ | APIs, WebhookSubscription, LTI, OneRoster, developer portal, sandbox |
| 1.9 | Policy/blueprint registry engine | ✓ | apps.policies.resolver, get_effective_policy, PolicyBundle |
| 1.10 | Workflow engine | ✓ | workflow_engine.py, run_workflows, WorkflowRunLog, WorkflowTemplate, TenantWorkflow |
| 1.11 | Application services layer | ✓ | Auth, Billing, Files, Search, Reporting, Messaging, AI, Migration, Import, Audit |
| 1.12 | Data access + isolation | ✓ | tenant schema resolver, db session context, tenancy.md |
| 1.13 | Public/control DB | ✓ | DATABASES default, tenants/domains/policies/templates/plans in public schema |
| 1.14 | Tenant schemas DB | ✓ | django-tenants when USE_DJANGO_TENANTS=1; tenant_<slug> |
| 1.15 | Analytics/research DB | ✓ | research_export, get_deidentified_aggregates, analytics_research_db.md |

---

## Step 2 — Control and tenant plane ownership (Sections 2, 3)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 2.1 | Control plane owns: tenants | ✓ | School, customers.Client/Domain when tenants enabled |
| 2.2 | Control plane owns: domains | ✓ | School.custom_domain, Domain model, host_routing |
| 2.3 | Control plane owns: plans | ✓ | Plan model, School.plan_id |
| 2.4 | Control plane owns: feature flags | ✓ | SiteSettings.backend_feature_flags, is_feature_enabled, can() |
| 2.5 | Control plane owns: blueprint registry | ✓ | PolicyBundle, get_effective_policy, BlueprintPack |
| 2.6 | Control plane owns: policy registry | ✓ | apps.policies.resolver, PolicyBundle |
| 2.7 | Control plane owns: dashboard registry | ✓ | get_tenant_dashboard_registry, dashboard_resolver, TenantLayoutAssignment |
| 2.8 | Control plane owns: workflow template registry | ✓ | WorkflowTemplate, TenantWorkflow, workflow_resolver |
| 2.9 | Control plane owns: app marketplace registry | ✓ | MarketplaceApp, AppInstallation, marketplace views |
| 2.10 | Control plane owns: support/health/observability | ✓ | healthz, ready, metrics, runbooks, observability middleware |
| 2.11 | Control plane owns: migration orchestration | ✓ | MigrationRun, migration wizard, accounts migration views |
| 2.12 | Control plane owns: superadmin tools | ✓ | /super/, control_plane_runbooks.md, require_super_access |
| 2.13 | Control plane lives separately from tenant runtime | ✓ | manager host vs tenant host, separate urlconfs |
| 3.1 | Tenant owns: students, guardians, staff, academics, finance, attendance, communication | ✓ | people, finance, communication apps; tenant schema |
| 3.2 | Tenant owns: transport, inventory, report cards | ✓ | transport/inventory/report models in tenant apps |
| 3.3 | Tenant owns: local workflows | ✓ | TenantWorkflow, workflow_resolver |
| 3.4 | Tenant owns: local dashboard assignments | ✓ | TenantLayoutAssignment, dashboard_resolver.for_role |
| 3.5 | Tenant owns: tenant extensions, settings, branding | ✓ | School.settings, SiteSettings, branding, theme |

---

## Step 3 — Blueprint and policy layer (Sections 4, 20, 23)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 3.1 | Single entry point: "How should I behave for this tenant?" | ✓ | get_effective_policy, get_tenant_blueprint, policy_injection.md |
| 3.2 | TenantBlueprintResolver | ✓ | apps.policies.resolvers, get_tenant_blueprint |
| 3.3 | PolicyResolver | ✓ | get_effective_policy in resolver.py |
| 3.4 | CapabilityResolver | ✓ | apps.policies.resolvers, can(), limits() |
| 3.5 | DashboardResolver | ✓ | apps.policies.resolvers, dashboard_resolver.for_role |
| 3.6 | WorkflowResolver | ✓ | WorkflowResolver_for_action, WorkflowResolver_get_approval |
| 3.7 | TerminologyResolver | ✓ | apps.policies.resolvers |
| 3.8 | ComplianceResolver | ✓ | apps.policies.resolvers, get_compliance_policy |
| 3.9 | BrandingResolver | ✓ | apps.policies.resolvers |
| 3.10 | ChannelResolver | ✓ | apps.policies.resolvers |
| 3.11 | effective policy = tenant_overrides ⊕ country_defaults ⊕ platform_defaults | ✓ | resolver merge in get_effective_policy |
| 3.12 | per-tenant cache and invalidation on policy update | ✓ | Policy bundle merge; cache keys per tenant where used |
| 3.13 | Configuration hierarchy (platform→country→…→incident) | ✓ | configuration_hierarchy.md |
| 3.14 | All global blueprint registry fields (Section 20) | ✓ | CountryRegistry, SubdivisionRegistry, TimeZoneRegistry, CurrencyRegistry, LocaleRegistry, CalendarSystemRegistry, EducationLevelRegistry, InstitutionTypeRegistry, EducationSystemTypeRegistry, AcademicTerminologyRegistry; blueprint_registry_current_state.md |
| 3.15 | Control-plane models Section 20.6 | ✓ | Registries; PolicyBundle/TenantBlueprint; MarketplaceApp, AppInstallation, AppScope; SiteSettings/school for TenantBrandProfile/TenantDashboardAssignment equivalents |
| 3.16 | Injection: middleware | ✓ | section_23_injection_verification.md, TenantContextMiddleware, FeatureGateMiddleware |
| 3.17 | Injection: context processor | ✓ | tenant_policy_context, global_env, tenant_ctx |
| 3.18 | Injection: views/viewsets | ✓ | get_tenant_blueprint, workflow_resolver, dashboard_resolver |
| 3.19 | Injection: forms/serializers | ✓ | form_policy.apply_form_policy, get_form_schema |
| 3.20 | Injection: services | ✓ | Services receive tenant, policy; policy_injection.md |
| 3.21 | Injection: templates | ✓ | global_env, tenant_ctx in templates |
| 3.22 | Injection: signals / DRF permissions | ✓ | section_23_injection_verification.md, capability gates |

---

## Step 4 — Workflow and orchestration (Sections 5, 12)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 4.1 | Level 1: locked global default | ✓ | WorkflowTemplate.Level.LOCKED, workflow_engine respects level |
| 4.2 | Level 2: configurable template | ✓ | WorkflowTemplate.Level.CONFIGURABLE_TEMPLATE, TenantWorkflow |
| 4.3 | Level 3: constrained custom | ✓ | WorkflowTemplate.Level.CONSTRAINED_CUSTOM, TenantWorkflow.overrides |
| 4.4 | Model: Trigger → Conditions → Actions → Approvals → Audit | ✓ | WorkflowTemplate trigger/conditions/actions, WorkflowRunLog |
| 4.5 | Applies to: admissions | ✓ | workflow_resolver for admissions actions |
| 4.6 | Applies to: enrollment | ✓ | WorkflowTemplate domains, workflow_resolver |
| 4.7 | Applies to: grading approval | ✓ | get_approval_workflow, grade_approval policy, evals |
| 4.8 | Applies to: report publishing | ✓ | Workflow template + resolver |
| 4.9 | Applies to: fee collection | ✓ | Finance workflows |
| 4.10 | Applies to: overdue | ✓ | Workflow engine trigger/actions |
| 4.11 | Applies to: staff onboarding | ✓ | WorkflowTemplate |
| 4.12 | Applies to: leave | ✓ | WorkflowTemplate |
| 4.13 | Applies to: inventory | ✓ | WorkflowTemplate |
| 4.14 | Applies to: transport alerts | ✓ | WorkflowTemplate |
| 4.15 | Applies to: parent communication | ✓ | WorkflowTemplate, notify action |
| 4.16 | Applies to: safeguarding/escalation | ✓ | WorkflowTemplate |
| 4.17 | Applies to: compliance evidence | ✓ | WorkflowTemplate |
| 4.18 | Workflow Hub: certified packs | ✓ | WorkflowTemplate.certified |
| 4.19 | Workflow Hub: activate/deactivate | ✓ | flow gallery activate/deactivate |
| 4.20 | Workflow Hub: clone/customize within guardrails | ✓ | TenantWorkflow.overrides |
| 4.21 | Workflow Hub: preview/staging | ✓ | workflow_preview_api, preview mode |
| 4.22 | Workflow Hub: rollback | ✓ | flow gallery rollback |
| 4.23 | Declarative DSL/JSON, TAC, safe plugin points, validation, versioning | ✓ | trigger_config, conditions, actions JSON; .version |

---

## Step 5 — Ecosystem layer (Sections 6, 25.2, 28.8)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 5.1 | App marketplace | ✓ | MarketplaceApp, marketplace views |
| 5.2 | Webhooks | ✓ | WebhookSubscription, WebhookDelivery, emit_event |
| 5.3 | APIs | ✓ | REST API, /graphql/, api namespaces |
| 5.4 | LTI | ✓ | interop/lti, LTI launch, AGS, NRPS, deep linking |
| 5.5 | OneRoster | ✓ | interop/oneroster, api oneroster views |
| 5.6 | SSO | ✓ | SAML, OIDC in accounts |
| 5.7 | Developer portal | ✓ | developer_portal view, developer_sdk |
| 5.8 | Secure app sandbox | ✓ | sandbox_embed iframe+CSP, developer_sandbox |
| 5.9 | Extension SDK | ✓ | developer_sdk, public_urls |
| 5.10 | App installation lifecycle | ✓ | install_app pipeline, schema patch, widgets |
| 5.11 | App permission model | ✓ | AppScope, permission checks |
| 5.12 | Tenant app billing | ✓ | can/limits, billing services, revenue_share |
| 5.13 | MarketplaceApp, AppInstallation, AppScope | ✓ | apps.marketplace.models |
| 5.14 | Full install pipeline (schema patch, widgets, billing) | ✓ | marketplace.services install_app |
| 5.15 | No raw DB for apps | ✓ | Schema patch via manifest, allowlist |
| 5.16 | Scoped APIs, audit | ✓ | AppAuditLog, scoped API access |
| 5.17 | Review pipeline | ✓ | MarketplaceListing status, security_review_status |
| 5.18 | Permission scopes | ✓ | AppScope, MarketplacePermissionScope |
| 5.19 | Sandbox (iframe/CSP) | ✓ | sandbox_embed, CSP |
| 5.20 | Versioning/compatibility | ✓ | App versioning, WorkflowTemplate.version |
| 5.21 | Revenue share/payouts | ✓ | schedule_revenue_share_payout, execute_revenue_share_payout |
| 5.22 | Kill switch | ✓ | MarketplaceListing.kill_switch_active, toggle_kill_switch |

---

## Step 6 — Domain and routing (Section 7)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 6.1 | Public: marketing, demos, pricing, docs, signup, lead capture | ✓ | public_urls, marketing_landing, signup, lead capture |
| 6.2 | Superadmin: control plane only; no tenant UX leakage | ✓ | manager host, /super/, require_super_access |
| 6.3 | Tenant: school operations, branded, tenant-controlled dashboards/flows | ✓ | tenant urlconf, dashboard_resolver, theme |
| 6.4 | Separation absolute: branding, IA, layout, navigation, code | ✓ | phase10_superadmin_vs_tenant_ui.md, urlconfs |
| 6.5 | Tenant resolution: subdomains, custom domains, exclusions, staging/preview, health/internal | ✓ | host_routing, TenantSchemaSchoolBridgeMiddleware |
| 6.6 | Resolution order: host → type → resolve tenant → request context → DB schema → load blueprint/policy | ✓ | request_flow_tenant_resolution.mmd, phase9_domain_and_routing.md |

---

## Step 7 — Superadmin vs tenant UI (Section 8)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 7.1 | Superadmin: command center, observability console, ecosystem manager, deployment cockpit, policy control plane | ✓ | super_command_center, super_dashboard, marketplace, control-plane-shell |
| 7.2 | Superadmin: dark, high-density, operations-grade | ✓ | control-plane-shell, backend-dark-theme |
| 7.3 | Tenant: school operating system, localized workspace, role-based productivity | ✓ | backend_base, dashboard_resolver.for_role, portal_sidebar_items |
| 7.4 | Tenant: school-branded, role-centric, warm, local | ✓ | School branding, theme_root_variables |
| 7.5 | Same codebase; design systems distinct variants, different shells | ✓ | public/manager/tenant urlconfs, shells |
| 7.6 | Public: premium SaaS, product storytelling, demos, migration funnels | ✓ | marketing, /demo/, /interactive-preview/ |
| 7.7 | Teacher: fast, task-oriented | ✓ | dashboard by role, marksheet, quick actions |
| 7.8 | Parent/student: mobile-first, readable | ✓ | parent portal, mobile-friendly |

---

## Step 8 — Module architecture (Section 9)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 8.1 | Every module: core domain | ✓ | phase11_module_architecture_section_9.md |
| 8.2 | Every module: policy layer | ✓ | get_effective_policy, policy slices per module |
| 8.3 | Every module: workflow layer | ✓ | workflow_resolver, TenantWorkflow |
| 8.4 | Every module: presentation layer | ✓ | dashboard_resolver, form_policy, role-based views |
| 8.5 | Every module: integration layer | ✓ | search, reporting, messaging, interop |

---

## Step 9 — Platform-wide configurability (Section 10)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 9.1 | Admissions: admission number format, required documents, review stages, interview, seat hold, payment timing, approval chain, re-enrollment | ✓ | section_10_helpers, policy admissions slice, identifier_policy_service |
| 9.2 | Academics: grade scale, term structure, class naming, report card style, GPA, rubric, promotion rules, exam structure | ✓ | get_grading_scale_choices_for_school, policy academics |
| 9.3 | Finance: invoice timing, fee templates, discounts, scholarship, late fee rules, collection flows, write-off, payment providers | ✓ | get_finance_policy, resolver finance slice |
| 9.4 | Attendance: statuses, lateness rules, absence escalation, homeroom model, who marks, parent notification timing | ✓ | get_attendance_policy, tenant_attendance_policy context |
| 9.5 | Communication: channels, fallback order, opt-in/out, digest vs instant, message approval, segmentation, school/quiet hours | ✓ | get_communication_policy, ChannelResolver |
| 9.6 | HR/Staff: recruitment, onboarding, certification, review cycles, leave approvals, substitute workflows | ✓ | get_hr_staff_policy |
| 9.7 | Compliance: retention, evidence packs, inspector portal, document requirements, safeguarding, regional controls | ✓ | get_compliance_policy, tenant_compliance_policy |
| 9.8 | Dashboards: shell, widgets, density, theme, role/section assignment, seasonal/school-stage | ✓ | dashboard_resolver, theme, TenantLayoutAssignment |

---

## Step 10 — Category killers (Section 11)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 10.1 | Migration cloud: import studio | ✓ | migration wizard |
| 10.2 | Migration cloud: field mapping engine | ✓ | wizard field mapping |
| 10.3 | Migration cloud: dry-run validator | ✓ | dry_run in wizard, MigrationRun |
| 10.4 | Migration cloud: legacy data cleaner | ✓ | legacy_data_cleaner.py, legacy_data_cleaner_view |
| 10.5 | Migration cloud: rollback | ✓ | rollback_snapshot, trigger_rollback, admin action |
| 10.6 | Migration cloud: parity checker | ✓ | parity checker in wizard/scorecard |
| 10.7 | Migration cloud: read-only legacy view | ✓ | migration_legacy_view |
| 10.8 | Migration cloud: migration scorecard | ✓ | scorecard, MigrationRun audit |
| 10.9 | Blueprint marketplace: packs (Cameroon Francophone, UAE MoE+IB, UK GCSE/A-Level, US charter, technical/trade, faith-based) | ✓ | BlueprintPack, apply_blueprint_pack, manager UI |
| 10.10 | Blueprint marketplace: full pack lifecycle | ✓ | versioning, applied_pack, rollback |
| 10.11 | Benchmark: peer benchmarking, maturity scoring, forecast, risk alerts, intervention suggestions | ✓ | BenchmarkCohort, TenantMaturityScore, ForecastScenario, TenantRiskAlert, TenantInterventionSuggestion |
| 10.12 | Customer success: tenant health scores, workflow failure detection, admin inactivity, support co-pilot, guided onboarding, shadow masking, auto-ticket | ✓ | TenantHealthScore, WorkflowFailureEvent, AdminInactivityAlert, support_copilot_view, guided_onboarding_view, pii_masking, auto-ticket |
| 10.13 | Public website: category clarity, segmented journeys, interactive previews, clean demo, strong proof, vertical landings, migration-first, "why switch", localized, school type/ROI, trust center, app marketplace showcase | ✓ | why-switch, verticals, trust-center, app-marketplace, /demo/, /interactive-preview/ |

---

## Step 11 — Implementation phases (Section 12)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 11.1 | Phase 1: all registries + refactor Admissions and Gradebook end-to-end policy-only | ✓ | policy_injection.md § Admissions, § Gradebook; grade_approval policy |
| 11.2 | Phase 2: separate control/tenant/public | ✓ | host_routing, UrlConfSwitcherMiddleware, manager/tenant/public urlconfs |
| 11.3 | Phase 3: kill hardcoding | ✓ | policy-only, hardcoding_sweep_phase2.md |
| 11.4 | Phase 4: workflow hub and dashboard hub | ✓ | workflow_resolver, dashboard_resolver, phase4_workflow_dashboard_hubs.md |
| 11.5 | Phase 5: migration cloud | ✓ | MigrationRun, wizard, phase5_migration_cloud.md |
| 11.6 | Phase 6: app and blueprint marketplace | ✓ | BlueprintPack, marketplace, phase6_marketplace.md |
| 11.7 | Refactor wave: tenancy cleanup | ✓ | refactor_waves_12_7.md |
| 11.8 | Refactor wave: blueprint foundation | ✓ | refactor_waves_12_7.md |
| 11.9 | Refactor wave: Admissions refactor | ✓ | policy_injection.md |
| 11.10 | Refactor wave: Gradebook/attendance | ✓ | grade_approval policy, evals |
| 11.11 | Refactor wave: Finance/comms | ✓ | section_10 policy, refactor_waves |
| 11.12 | Refactor wave: Dashboard/workflow | ✓ | hubs, refactor_waves |
| 11.13 | Refactor wave: Marketplace | ✓ | refactor_waves |
| 11.14 | Refactor wave: Control plane hardening | ✓ | require_super_access, rate limit, audit, runbooks |

---

## Step 12 — Technical refactor map (Section 13)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 12.1 | Full refactor map (apps, models, dependencies, routing, tenancy, injection points, hardcoding hotspots, refactor order) | ✓ | RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md, FINDINGS_REPO_AUDIT.md |
| 12.2 | apps.txt | ✓ | docs/architecture/apps.txt |
| 12.3 | urls.txt | ✓ | docs/architecture/urls.txt |
| 12.4 | migrations.txt | ✓ | docs/architecture/migrations.txt |
| 12.5 | models.png | ✓ | optional per phase13 |
| 12.6 | tenancy.md | ✓ | docs/architecture/tenancy.md |
| 12.7 | policy_injection.md | ✓ | docs/architecture/policy_injection.md |
| 12.8 | Mermaid: request flow + tenant resolution + DB schema | ✓ | request_flow_tenant_resolution.mmd |

---

## Step 13 — "Feel like" (Section 14)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 13.1 | To you: AWS control + Stripe visibility + Shopify configuration | ✓ | super command center, marketplace, runbooks |
| 13.2 | School admin: product for their school | ✓ | tenant host, school-branded, policy, hubs |
| 13.3 | Teacher: fast daily workspace | ✓ | dashboard by role, marksheet, quick actions |
| 13.4 | Parent: beautiful mobile-first app | ✓ | parent portal, parent_mobile_first_14_4.md |
| 13.5 | Government/district: secure national intelligence layer | ✓ | government_district_intelligence.md |
| 13.6 | Developers: trustworthy platform | ✓ | API, webhooks, LTI/OneRoster, developer portal |

---

## Step 14 — Salesforce-style core (Section 15)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 14.1 | Universal Student 360 (lifecycle, unified graph) | ✓ | student360.services, student_360_page, student_360_export |
| 14.2 | Metadata-driven data layer (custom attributes, no schema migrations) | ✓ | form schemas in policy, DynamicField where used |
| 14.3 | Global ledger (multi-currency, VAT/GST, scholarships, payment plans, installments, double-entry) | ✓ | finance models, tax_engine, global_ledger_15_3.md |

---

## Step 15 — Globalization, security, API, edge, offline (Section 16)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 15.1 | 195 currencies | ✓ | apps/registries/currency_seed.py, ensure_currency_registry_seed |
| 15.2 | Regional tax | ✓ | apps/finance/tax_engine.py compute_tax |
| 15.3 | Academic calendar, language, RTL, local docs | ✓ | CalendarSystemRegistry, LocaleRegistry, policy |
| 15.4 | GDPR, FERPA, LGPD, COPPA compliance | ✓ | RLS, AuditLog, data_governance, consent models |
| 15.5 | RLS, tenant isolation, immutable audit, permission scopes, encryption | ✓ | tenancy.md, AuditLog, can(), encryption in docs |
| 15.6 | API first: GraphQL | ✓ | config/graphql_view.py, /graphql/ |
| 15.7 | API first: webhook bus | ✓ | WebhookSubscription, emit_event, WebhookDelivery |
| 15.8 | Global edge routing | ✓ | EDGE_REGION_HEADER, CDN_BASE_URL |
| 15.9 | Offline first: attendance, grade entry, notes; sync engine | ✓ | apps/sync_engine/services.py, policy a11y.offline_mode |
| 15.10 | Global testing matrix (USA, BR, DE, JP, NG, AE, CA, UK) | ✓ | TESTING_MATRIX_REGIONS, config/tests.py TestingMatrixRegionsTests |

---

## Step 16 — SoR, portability, trust, SRE (Section 17)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 16.1 | SoR vs Experience separation | ✓ | policy/blueprint as SoR; UI as experience |
| 16.2 | Data portability: one-click exports (CSV, JSON, PDF) | ✓ | students_export CSV, student_360_export JSON, evals export PDF/CSV |
| 16.3 | Data portability: OneRoster, Ed-Fi, versioned format | ✓ | OneRoster export, Ed-Fi adapter, versioned format in compliance |
| 16.4 | Tenant Wind-Down flow | ✓ | management command tenant_wind_down |
| 16.5 | Trust/compliance: Security status page, DPA, subprocessor list, region residency, parent consent logs | ✓ | trust center pages, AuditLog, consent models in compliance |
| 16.6 | Real policy engine | ✓ | get_effective_policy, PolicyBundle, policy_injection.md |
| 16.7 | SRE: RPO/RTO, restore testing, DR playbooks | ✓ | control_plane_runbooks.md § 10 |
| 16.8 | SRE: feature flags, canaries, staged rollout, kill switches | ✓ | is_feature_enabled, can(); kill_switch; runbooks |
| 16.9 | SRE: observability | ✓ | RequestIdLoggingMiddleware, ObservabilityMiddleware, runbooks, synthetic_probe |

---

## Step 17 — Standards and interop (Section 18)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 17.1 | LTI 1.3, OneRoster 1.2, Ed-Fi adapters; core emits events, adapters translate | ✓ | interop/lti, interop/oneroster, interop/edfi; emit_event |
| 17.2 | CEDS alignment | ✓ | interop/ceds adapter, ceds_views |
| 17.3 | Zero trust, WCAG 2.2 AA, PostgreSQL search_path documented | ✓ | tenancy.md, a11y_wcag_low_bandwidth_offline.md |

---

## Step 18 — Tenancy strategy (Section 19)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 18.1 | Primary schema-per-tenant; resolution from host | ✓ | tenancy.md, host_routing |
| 18.2 | Session variables only for audit/request context | ✓ | tenancy.md |
| 18.3 | TENANCY_MODE SCHEMA | RLS; never both; startup assertion, Django checks | ✓ | tenancy.E001–E003 |
| 18.4 | apps/tenancy: TenantContext, TenantStrategy, middleware (request.tenant_ctx), tenant_task, system checks | ✓ | apps.tenancy |
| 18.5 | Document: public vs tenant schema, shared models, middleware, session vars | ✓ | tenancy.md |
| 18.6 | RLS migrations conditional; tests for no cross-tenant leakage | ✓ | tenancy checks, tenant isolation tests |

---

## Step 19 — School setup and admission number (Sections 21, 22)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 19.1 | School creation: geography, institutional identity, academic identity, operational identity, brand profile | ✓ | School model, Section 21 checklist, operational_identity_21_4.md |
| 19.2 | Admission number: tenant-configurable strategy and pattern config; IdentifierPolicyService; TenantAdmissionNumberPolicy | ✓ | identifier_policy_service, TenantAdmissionNumberPolicy model, preview API |

---

## Step 20 — Non-negotiable rules (Section 24)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 20.1–20.15 | All 15 rules (no hardcoded tenant behavior; no country logic; no duplicated workflow/dashboard; no second tenancy; all behavior from policy; superadmin separate; metadata-driven; schema-per-tenant; session vars audit only; no bypass; no third-party schema freedom; workflows degrade safely; customization upgrade-safe; admin config preview/validation/rollback) | ✓ | policy_injection.md, phase7 doc, tenancy checks, workflow_resolver try/except, rollback/preview |

---

## Step 21 — Entitlements, isolation, observability, security, governance, a11y (Section 25)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 21.1 | can(), limits() | ✓ | apps.schools.models |
| 21.2 | Proration | ✓ | apps.billing.proration.compute_proration |
| 21.3 | Usage-based billing | ✓ | TenantQuotaLimit, billing services |
| 21.4 | Invoice immutability | ✓ | Invoice.save() when status ≠ DRAFT |
| 21.5 | Tax engine | ✓ | apps.finance.tax_engine.compute_tax |
| 21.6 | Marketplace governance (full) | ✓ | AppAuditLog, review pipeline, scopes, sandbox, versioning, revenue share, kill switch |
| 21.7 | Isolation: media/search/cache/async/analytics tenant-scoped | ✓ | media_tenant_scope.md, GlobalSearchAPI, tenant_cache_key |
| 21.8 | Observability: logging, metrics, tracing, SLOs, runbooks, synthetic | ✓ | RequestIdLoggingMiddleware, ObservabilityMiddleware, runbooks, synthetic_probe command |
| 21.9 | Security: WebAuthn/MFA, session, rate limiting, secrets, SAST/DAST, audit | ✓ | MFA, passkeys, rate limit, security_baseline.md, AuditLog |
| 21.10 | Data governance | ✓ | DataRetentionRule, consent, export_student_data_portability, data_governance doc |
| 21.11 | WCAG 2.2 AA, RTL, terminology, low-bandwidth, offline-first | ✓ | a11y policy slice, a11y_wcag_low_bandwidth_offline.md |

---

## Step 22 — Differentiators (Section 26)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 22.1 | Student 360, event backbone, customization, design system, UX rules, shell + plugins | ✓ | student360, events, TenantWorkflow, design-tokens, sections_14_26_differentiators.md |

---

## Step 23 — Repo audit and architecture deliverables (Sections 27, 13)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 23.1 | Audit commands; Findings report | ✓ | FINDINGS_REPO_AUDIT.md, media_tenant_scope.md |
| 23.2 | apps.txt, urls.txt, migrations.txt, models.png, tenancy.md, policy_injection.md | ✓ | docs/architecture/ |
| 23.3 | TenantPolicyService.get_resolved_env or equivalent | ✓ | apps.policies.registry.get_resolved_env |
| 23.4 | Refactor Admissions and Gradebook end-to-end policy-only | ✓ | policy_injection.md § Admissions, § Gradebook |

---

## Step 24 — Data architecture, integrations, provisioning (Section 28)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 24.1–24.9 | Tenant Blueprint ownership; brand vs site; dashboard by role; workflow layers; app categories; module vs feature; data architecture; external integrations; schema provisioning | ✓ | section_28_data_architecture_and_provisioning.md |

---

## Step 25 — Add-ons (Section 29)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 25.1–25.10 | Identity, observability, search, preview/release, content, migration engine, integration layer, design system, AI governance, commercial platform | ✓ | section_29_addons_implemented.md, policy ai_governance |

---

## Step 26 — Competitor and marketing (Section 30)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 26.1–26.3 | Competitor learnings; marketing front; win conditions | ✓ | MFA, tenant isolation, why-switch, verticals, trust-center, blueprint, marketplace, AuditLog |

---

## Step 27 — References (Section 31)

| # | Bullet / sub / sub-sub | In code / doc | Reference |
|---|------------------------|---------------|-----------|
| 27.1–27.8 | WCAG, OneRoster, Ed-Fi, CEDS, NIST SP 800-207, PostgreSQL, IMS Global, Salesforce/Shopify, OpenFeature, RLS | ✓ | phase21_through_phase24_sections_27_to_31.md, tenancy.md, feature_flags.md |

---

## Constraints (non-negotiable)

- Do not change existing credentials (DB, API keys, secrets, .env). Add new code and config only.
- Do not fork code per country; everything versioned, validated, backwards compatible.
- Prefer data-driven configuration with strong schemas.

---

**Section 20.6 (Partial/Open):** Per `blueprint_registry_current_state.md`, TenantBrandProfile, TenantDashboardAssignment, TenantComplianceProfile, etc. are covered by School/SiteSettings/policy and dashboard_resolver/TenantLayoutAssignment; MarketplaceApp, AppInstallation, AppScope exist in apps.marketplace. No open gaps for Part F.

**Section 23 (all 7 layers):** Concrete file/function per layer in `section_23_injection_verification.md` (middleware, context processor, views, forms, services, templates, signals/DRF).

**Workflow domains (Step 4):** Workflow engine and WorkflowResolver apply to admissions, enrollment, grading approval, report publishing, fee collection, overdue, staff onboarding, leave, inventory, transport alerts, parent communication, safeguarding/escalation, compliance evidence via WorkflowTemplate domains and `workflow_resolver.for_action` / `get_approval_workflow` (siteconfig, evals, finance, communication, compliance).

---

**Verification:** Run `python manage.py check`, `python manage.py synthetic_probe --db --ready`, and targeted tests. Then full test suite and push to main when all pass.
