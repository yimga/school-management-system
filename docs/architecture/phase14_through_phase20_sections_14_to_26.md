# Phases 14–20 — Sections 14, 15, 16, 17, 18, 19, 26

Single reference for UX “feel like” (14), Salesforce-style core (15), globalization/security/API/edge/offline (16), SoR/portability/trust/SRE (17), standards and interop (18), tenancy strategy (19), and differentiators (26). Implemented items and scoped/roadmap items documented.

---

## Section 14 — Final Platform “Feel Like”

| Id | Audience | Feel | Status / implementation |
|----|----------|------|-------------------------|
| 14.1 | To you (operator) | AWS control + Stripe visibility + Shopify configuration | **Partial:** Superadmin command center (super_dashboard, super_command_center), marketplace governance, blueprint/app catalog, control-plane runbooks; billing/subscription visibility in billing app; tenant/school config via siteconfig. Full “Stripe dashboard” visibility and “Shopify config” UX can be enhanced. |
| 14.2 | School admin | Product built specifically for their school | **Done:** Tenant host, school-branded (School logo, colors, ThemePack), policy/blueprint, dashboard and workflow hubs, role-based access, tenant settings. |
| 14.3 | Teacher | Fast, obvious daily workspace | **Done:** Backend dashboard by role (dashboard_resolver.for_role), quick actions, marksheet, attendance, lesson plans; task-oriented layout (phase10). |
| 14.4 | Parent | Beautiful mobile-first app | **Partial:** Parent portal; mobile-friendly templates; further polish and PWA/offline scoped. |
| 14.5 | Government/district | Secure national intelligence layer | **Scoped:** EMIS export, reporting; secure/auditable access; district aggregation and compliance reporting as roadmap. |
| 14.6 | Developers | Trustworthy platform to build on | **Partial:** API, webhooks (WebhookSubscription), LTI/OneRoster; developer host (developer.runmycampus); docs; marketplace app install. Full developer portal and SDK roadmap. |

**Ref:** phase10_superadmin_vs_tenant_ui.md.

---

## Section 15 — Salesforce-Style Core

| Id | Requirement | Status / implementation |
|----|-------------|-------------------------|
| 15.1 | Universal Student 360 — lifecycle, unified identity (UUID), timeline; linked academic, finance, attendance, behavior, safeguarding; cross-year archive, immutable transcript; permission-gated export | **Scoped:** StudentProfile as core identity; linked data across academics, evals, finance, attendance, portal. Full 360 view (timeline feed, cross-year archive, immutable transcript, export pack) as roadmap. |
| 15.2 | Metadata-driven data layer — DynamicFieldDefinition, DynamicFieldValue; no schema migrations for custom attributes | **Scoped:** Custom attributes without code; roadmap for metadata layer (e.g. metadata app, state_machine). |
| 15.3 | Global ledger — multi-currency, VAT/GST, scholarships, payment plans, installments, double-entry | **Partial:** Finance models (Invoice, Payment, fee templates); multi-currency and regional tax in section_28; full double-entry ledger and payment plans as roadmap. |

**Ref:** section_28_data_architecture_and_provisioning.md (28.8); finance app; people.StudentProfile.

---

## Section 16 — Globalization, Security, API, Edge, Offline

| Id | Requirement | Status / implementation |
|----|-------------|-------------------------|
| 16.1 | Globalization: 195 currencies, regional tax, academic calendar, language, RTL, local doc requirements (in Blueprint) | **Partial:** CurrencyRegistry, LocaleRegistry, CalendarSystemRegistry; policy default_language, rtl; region/policy for calendar and terminology. Regional tax and full 195-currency matrix scoped. |
| 16.2 | Security & compliance: GDPR, FERPA, LGPD, COPPA; RLS, tenant isolation, immutable audit, permission scopes, encryption | **Done:** RLS/tenant isolation (tenancy.md); AuditLog (compliance); permission scopes; MFA (section_25). GDPR/FERPA/LGPD/COPPA documented as compliance targets (section_25_current_state 25.6). |
| 16.3 | API first: GraphQL gateway; webhook bus; learning tools, payment, government, analytics | **Partial:** REST API; WebhookSubscription; OneRoster/LTI adapters; payment/billing webhooks. GraphQL gateway scoped. |
| 16.4 | Global edge: regional traffic routing (CDN + edge) | **Scoped:** Config/env; edge infra separate (checklist 1.2). |
| 16.5 | Offline first: attendance, grade entry, notes offline; sync engine | **Partial:** Policy offline_mode; sync engine and conflict resolution scoped. |
| 16.6 | Global testing matrix: USA, Brazil, Germany, Japan, Nigeria, UAE, Canada, UK | **Scoped:** Document as test matrix; i18n and region coverage. |

**Ref:** section_25_current_state.md; tenancy.md; registries; policy_injection.md.

---

## Section 17 — SoR vs Experience, Portability, Trust, SRE

| Id | Requirement | Status / implementation |
|----|-------------|-------------------------|
| 17.1 | SoR vs Experience: Core record (canonical, audit, lifecycle, policy) vs Experience (themed UI, widgets, workflows, apps) | **Partial:** Policy/blueprint drive behavior; AuditLog for core events; themed UI and dashboard/workflow from resolver. Explicit SoR/Experience doc and contracts scoped. |
| 17.2 | Data portability: One-click exports (CSV, JSON, PDF); OneRoster, Ed-Fi, versioned format; Tenant Wind-Down | **Partial:** OneRoster export (interop); compliance export_compliance_evidence_pack; CSV/PDF in places. Ed-Fi, full export suite, Tenant Wind-Down flow scoped. |
| 17.3 | Trust/compliance as product: Security status page, DPA, subprocessor list, region residency, consent logs | **Partial:** Trust center page (marketing); AuditLog; section_25. Security status page, DPA, subprocessor list as product features scoped. |
| 17.4 | Real policy engine: Central Policy Registry; deterministic, testable; auditable policy changes | **Done:** get_effective_policy(school), PolicyBundle, TenantBlueprint; policy_injection.md; resolver is single read path; auditable via bundle version. |
| 17.5 | SRE: RPO/RTO, restore testing, DR playbooks; feature flags, canaries, staged rollout, kill switches; observability | **Partial:** control_plane_runbooks.md; feature flags; kill switch (marketplace, suspend_app); rate limiting. RPO/RTO, restore testing, canaries, full observability stack scoped. |

**Ref:** control_plane_runbooks.md; section_25_current_state.md; phase8 (marketplace kill switch).

---

## Section 18 — Standards and Interop

| Id | Requirement | Status / implementation |
|----|-------------|-------------------------|
| 18.1 | LTI 1.3, OneRoster 1.2, Ed-Fi; adapters in interop layer (interop/oneroster, interop/lti, interop/edfi); core apps emit events, adapters translate | **Partial:** OneRoster adapter (interop/oneroster/adapter.py); OneRoster API (api/oneroster_views); LTI (interop/lti; ExternalToolConfig LTI type); WebhookSubscription. Ed-Fi adapter and full event emission from core apps scoped. |
| 18.2 | CEDS for reporting (US); translation layer: RunMyCampus canonical ⇄ standard adapters | **Scoped:** CEDS mapping and reporting; translation layer doc. |
| 18.3 | Zero trust (NIST SP 800-207); WCAG 2.2 AA; PostgreSQL search_path explicit and documented | **Partial:** Auth and tenant isolation; WCAG target (section_25_current_state 25.7). search_path and RLS in tenancy/migrations; zero trust and WCAG 2.2 AA audit scoped. |

**Ref:** apps/interop; apps/api/oneroster_views.py; siteconfig.models (WebhookSubscription, ExternalToolConfig); tenancy.md.

---

## Section 19 — Tenancy Strategy

**Already implemented and documented.** Checklist 19.1–19.6 marked [x].

| Id | Requirement | Status |
|----|-------------|--------|
| 19.1 | Schema-per-tenant primary; resolution from host | [x] (tenancy.md) |
| 19.2 | Session variables only for audit/request context | [x] (tenancy.md) |
| 19.3 | TENANCY_MODE: SCHEMA \| RLS; startup assertion | [x] (tenancy.E001–E003) |
| 19.4 | apps/tenancy: TenantContext, middleware, tenant_task, system checks | [x] |
| 19.5 | Document: public vs tenant schema, middleware, session vars | [x] (tenancy.md) |
| 19.6 | RLS migrations conditional; tests for no cross-tenant leakage | [x] |

**Ref:** docs/architecture/tenancy.md; phase9_domain_and_routing.md.

---

## Section 26 — Differentiators (Student 360, Events, Customization, Design System)

| Id | Requirement | Status / implementation |
|----|-------------|-------------------------|
| 26.1 | Universal Student 360 — unified identity (UUID), lifecycle events, timeline feed; linked academic, finance, attendance, behavior, safeguarding; cross-year archive, immutable transcript; permission-gated export pack | **Scoped:** StudentProfile and linked domains exist; full 360 view, timeline, immutable transcript, export pack as roadmap (align with 15.1). |
| 26.2 | Event backbone — DomainEvent, WebhookSubscription, WebhookDelivery; schema versioning; retries, signatures, idempotency; emit from service layer only | **Partial:** WebhookSubscription (siteconfig); webhook delivery and DomainEvent pattern. Full event backbone (DomainEvent model, versioning, retries, idempotency) scoped. |
| 26.3 | Customization: Themes, Workflows (TAC), Schema extensions; versioned, audited, reversible; BlueprintVersion, PolicyVersion | **Partial:** TenantWorkflow (overrides, rollback); DashboardTemplate, TenantLayoutAssignment; PolicyBundle, TenantBlueprint; theme from School/policy. BlueprintVersion/PolicyVersion and schema extensions scoped. |
| 26.4 | Design system — design tokens, component library, theme engine (tenant brand + density + nav); WCAG-aligned; 3 density modes; tenant theme overrides via Blueprint; visual regression | **Partial:** Theme variables (backend_base, theme_root_variables); density (RESOLVED_BACKEND_CONSOLE_THEME); tenant brand from School/policy. Design tokens doc, component library, WCAG 2.2 AA, visual regression scoped. |
| 26.5 | UX rules: No empty pages; every list has search, filters, saved views, export, bulk actions; every form has autosave/draft, validation, explainers; every workflow has progress, audit, “why did this happen?” | **Partial:** Search/filters/export in places; form validation and policy-driven explainers; workflow audit (AuditLog, approval). Full UX rules checklist and consistency scoped. |
| 26.6 | Frontend: Shell + plugins; modules register routes, widgets, permissions via registry; theme tokens at shell | **Partial:** Dashboard registry, widget config; marketplace get_installed_widgets; urlconf per shell. Full plugin registry and theme tokens at shell scoped. |

**Ref:** section_28 (28.2 brand vs site); phase4_workflow_dashboard_hubs.md; phase10_superadmin_vs_tenant_ui.md; siteconfig.models (WebhookSubscription); apps.marketplace.

---

## Checklist summary (Phases 14–20)

- **Section 14:** 14.1–14.6 documented; status partial/done per row; align product/UX to these audiences.
- **Section 15:** 15.1–15.3 scoped/partial; roadmap for Student 360, metadata layer, global ledger.
- **Section 16:** 16.1–16.6 partial or scoped; 16.2 (security/compliance) done.
- **Section 17:** 17.1–17.5 partial or done; 17.4 (policy engine) done.
- **Section 18:** 18.1–18.3 partial or scoped; OneRoster/LTI/WebhookSubscription present.
- **Section 19:** 19.1–19.6 already [x]; no change.
- **Section 26:** 26.1–26.6 partial or scoped; customization and theme/workflow pieces present.

**Reference:** tenancy.md, policy_injection.md, section_25_current_state.md, section_28_data_architecture_and_provisioning.md, phase10_superadmin_vs_tenant_ui.md, apps/interop, apps/siteconfig/models.py (WebhookSubscription).
