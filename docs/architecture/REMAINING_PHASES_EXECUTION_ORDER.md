# Remaining Phases — Execution Order

**Purpose:** Single ordered list of all remaining work so everything is completed in a consistent sequence.  
**Reference:** `docs/architecture/RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md` (checklist Sections 1–31, Part F directive).

**How to use:** Execute phases in numerical order. For each phase: complete the steps → run verification → update the checklist in the main architecture doc (mark items or add notes) → move to the next phase.

---

## Already completed (do not redo)

- **Control plane hardening (Section 12.7)** — require_super_access, rate limit, audit logging, runbooks.
- **Section 11 (Category killers)** — Benchmark/customer-success models and APIs, public website routes, workflow failure recording.
- **Sections 24.8 / 23.4 (metadata-driven & policy-driven forms)** — form_policy, resolver forms merge, LinkChildForm / StudentOnboardingForm apply_form_policy.
- **Section 25.3 (Isolation hardening)** — Search/media tenant-scoped; cache keys; docs.
- **Section 20 (Blueprint registry)** — TimeZone, Currency, Locale, Calendar, InstitutionType, AcademicTerminology registries + migration + doc.
- **Sections 21–22 (School setup & admission number)** — Checklist 21.1–21.6, 22.1–22.3; TenantAdmissionNumberPolicy, IdentifierPolicyService, preview API.

---

## Phase 1 — Refactor: Gradebook (and attendance) — policy-only

**Doc ref:** Section 12 (refactor waves), Section 24 (no hardcoded behavior), Section 27.3.

**Scope:**

- Gradebook (and attendance where coupled): same pattern as Admissions — no direct SiteSettings or country/tenant logic in business code; all behavior from policy/blueprint.

**Done when:**

- [x] Resolver exposes grade_approval slice; grading_scale already in policy.
- [x] Evals approval/views use get_grade_approval_policy(school); no direct SiteSettings for approval config.
- [x] Evals pass school into approval helpers; create_grade_approval_request uses policy.
- [x] policy_injection.md and checklist 24.1, 27.3 updated.

**Checklist to update:** Section 24.1, 24.6; Section 27.3 (refactor “Gradebook end-to-end” if still open).

---

## Phase 2 — Phase 3 hardcoding sweep

**Doc ref:** Section 24.1, 24.2; implementation notes (“Phase 3 hardcoding sweep”).

**Scope:**

- Remove remaining tenant/country hardcoding in views, templates, forms (except where explicitly control-plane/signup/setup by design).

**Done when:**

- [x] Grading settings use get_grading_scale_choices_for_school(school); no country names in tenant form.
- [x] No country logic in tenant-facing evals/admissions/reports; control-plane/signup keep country by design.
- [x] hardcoding_sweep_phase2.md added; checklist 24.1, 24.2 confirmed (e.g. FINDINGS_REPO_AUDIT.md or a short “hardcoding_sweep” note); checklist 24.1, 24.2 confirmed [x].

**Checklist to update:** Section 24.1, 24.2.

---

## Phase 3 — Section 24.8: Finish metadata-driven config

**Doc ref:** Section 24.8; phase3_metadata_driven_forms_24_8_23_4.md; phase7_deferred_rules.

**Scope:**

- Ensure all form/config behavior that should be tenant-configurable is driven by metadata (policy/platform defaults + tenant overrides); no form config hardcoded in views.

**Done when:**

- [x] Remaining forms that need policy (e.g. key tenant-facing forms) use `apply_form_policy` / `get_form_schema` (or equivalent); choices from catalog/policy where applicable. Key forms: LinkChildForm, StudentOnboardingForm; pattern documented in phase3_metadata_driven_forms_24_8_23_4.md § Remaining forms.
- [x] POLICY_USE_BUNDLES, POLICY_CACHE_TTL (and optional env from phase7) documented and used where intended. See phase7_deferred_rules_24_12_to_24_15.md and .env.example; resolver uses both in apps/policies/resolver.py.
- [x] Checklist 24.8 marked [x] with a short note; any deferred bits documented in phase7_deferred_rules or similar.

**Checklist to update:** Section 24.8.

---

## Phase 4 — Workflow and dashboard hubs (Phase 4 in §12)

**Doc ref:** Section 12 (Phase 4), Section 5, 24.3, 24.4; phase4_workflow_dashboard_hubs.md.

**Scope:**

- Full workflow hub and full dashboard hub (UI and flows), not only APIs. Certified packs, tenant selection/customization within guardrails, preview/staging, rollback where specified.

**Done when:**

- [x] Workflow hub: tenant-facing UI to browse/select/customize workflows (within guardrails); preview/staging; rollback; no duplicated workflow logic across apps (all via workflow_resolver/hub).
- [x] Dashboard hub: tenant-facing UI to compose/assign dashboards by role; no duplicated dashboard composition logic across apps (all via dashboard_resolver/hub).
- [x] Docs and checklist updated; implementation notes no longer say “full workflow/dashboard hubs deferred”.

**Checklist to update:** Section 5, 12, 24.3, 24.4; implementation notes in RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md.

---

## Phase 5 — Section 23: Policy/Blueprint injection — verify and document

**Doc ref:** Section 23 (all injection points).

**Scope:**

- Audit and verify every injection point; fix gaps and document.

**Done when:**

- [x] Middleware: tenant resolution, control vs tenant split, FeatureGateMiddleware; TenantContextMiddleware (23.1).
- [x] Context processor: global_env / tenant_ctx in templates (23.2).
- [x] Views/ViewSets: get_tenant_blueprint, workflow_resolver, dashboard_resolver (23.3).
- [x] Forms/Serializers: policy-driven visibility, required/optional, picker options, validation (23.4). Key forms (LinkChildForm, StudentOnboardingForm) use apply_form_policy; form_policy and get_form_schema in use; remaining forms documented in phase3_metadata_driven_forms_24_8_23_4.md.
- [x] Services: policy only; no direct settings (23.5).
- [x] Templates: global_env, tenant_ctx (23.6).
- [x] Signals / DRF permissions: audit signals, capability gates (23.7).
- [x] section_23_injection_verification.md and where it’s implemented (file/function); checklist 23.1–23.7 confirmed [x].

**Checklist to update:** Section 23.1–23.7 (mark [x] or add notes).

---

## Phase 6 — Section 25 (beyond 25.3): Entitlements, observability, security, governance, a11y

**Doc ref:** Section 25 (25.1, 25.2, 25.4, 25.5, 25.6, 25.7).

**Scope:**

- 25.3 is done. Implement or verify: entitlements, marketplace governance, observability/SRE, security baseline, data governance, accessibility/localization.

**Done when:**

- [x] **25.1** Entitlements: can(school, capability), limits(school) in apps.schools.models; proration/usage-based billing/invoice/tax scoped (section_25_current_state.md).
- [x] **25.2** Marketplace governance: AppAuditLog, install/scopes; review pipeline, sandbox, versioning, revenue, kill switch documented/scoped (section_25_current_state.md).
- [x] **25.4** Observability/SRE: runbooks (control_plane_runbooks.md); logging/metrics/tracing/SLOs/synthetic documented/scoped (section_25_current_state.md).
- [x] **25.5** Security: MFA, rate limiting, AuditLog done; secrets/SAST/DAST/export scoped (section_25_current_state.md).
- [x] **25.6** Data governance: AuditLog sensitivity; retention/consent/rights/residency scoped (section_25_current_state.md).
- [x] **25.7** Accessibility/localization: terminology from Blueprint; RTL/i18n partial; WCAG/offline scoped (section_25_current_state.md).
- [x] Checklist 25.1, 25.2, 25.4–25.7 updated; section_25_current_state.md added.

**Checklist to update:** Section 25.1, 25.2, 25.4, 25.5, 25.6, 25.7 (done).

**Implementation note (Phase 6):** `can(school, capability)` and `limits(school)` in `apps/schools/models.py`; `docs/architecture/section_25_current_state.md` documents current state and scope for each 25.x item.

---

## Phase 7 — Section 28: Data architecture and provisioning

**Doc ref:** Section 28 (28.1–28.9).

**Scope:**

- Tenant blueprint ownership, brand vs site experience, dashboard by role, workflow layers, app categories, module vs feature language, data architecture (public/tenant schemas, object storage, search boundaries), external integrations, schema provisioning.

**Done when:**

- [x] **28.1** Tenant Blueprint ownership list documented (identity, metadata, country/region, levels, systems, branding, dashboard/workflow assignments, entitlements, overrides, numbering, comms, compliance, extensions) — section_28_data_architecture_and_provisioning.md.
- [x] **28.2** Brand identity vs site experience split documented (brand = name, logo, colors, typography, senders; site = portal theme, dashboard family, density, nav, welcome, footer/header) — section_28_data_architecture_and_provisioning.md.
- [x] **28.3** Dashboard by role: list of roles and dashboard family per role (admin, finance, registrar, principal, teacher, parent, student, librarian, transport, HR, admissions); ROLE_CHOICES + extension path — section_28_data_architecture_and_provisioning.md.
- [x] **28.4** Workflow layers: certified platform → tenant-selected variants → tenant custom composition; guardrails documented — section_28_data_architecture_and_provisioning.md.
- [x] **28.5** App categories: Control/shared vs Tenant-domain vs Platform support documented — section_28_data_architecture_and_provisioning.md.
- [x] **28.6** Module vs feature: consistent language platform-wide; doc updated — section_28_data_architecture_and_provisioning.md.
- [x] **28.7** Data architecture: public schema vs tenant_<slug>; object storage path; search = control-plane vs tenant-scoped; append-only audit schemas — section_28 + tenancy.md, media_tenant_scope.md.
- [x] **28.8** External integrations: PaymentProvider, MessagingProvider, LMSProvider, GovtProvider, IoTProvider; health, failover, per-region defaults; fallback routing — section_28_data_architecture_and_provisioning.md.
- [x] **28.9** Schema provisioning: idempotent provisioning job; schema patch system for app installs; tenant-aware migration strategy with versioning — section_28_data_architecture_and_provisioning.md.
- [x] Checklist 28.1–28.9 updated.

**Checklist to update:** Section 28.1–28.9 (done).

**Implementation note (Phase 7):** Added `docs/architecture/section_28_data_architecture_and_provisioning.md` — single reference for 28.1–28.9 (blueprint ownership, brand vs site, dashboard by role, workflow layers, app categories, module vs feature, data architecture, external integrations, schema provisioning).

---

## Phase 8 — Migration cloud and marketplaces (Phases 5–6 in §12)

**Doc ref:** Section 12 (Phases 5–6), Section 11 (migration cloud, blueprint marketplace), Section 29.6, 29.10.

**Scope:**

- Migration cloud: import studio, field mapping, dry-run, rollback, parity checker, read-only legacy view, migration scorecard (as in Section 11).
- Blueprint marketplace / app marketplace: blueprint packs, app showcase, installation lifecycle, tenant app billing (as in Section 6, 11, 25.2, 29).

**Done when:**

- [x] Migration cloud: import studio (migration_wizard), field mapping, dry-run, parity checker, migration scorecard implemented; rollback/legacy data cleaner deferred — phase5_migration_cloud.md, phase8_migration_cloud_and_marketplaces.md.
- [x] Blueprint marketplace: blueprint packs (country_code, category); selection/apply for tenants; preview; versioning/tenant-facing deferred — phase6_marketplace.md, phase8_migration_cloud_and_marketplaces.md.
- [x] App marketplace: app showcase (app_catalog + public app-marketplace), install pipeline (schema patch, widgets, audit), permission model, governance per 25.2 — phase8_migration_cloud_and_marketplaces.md.
- [x] Implementation notes no longer say “migration cloud & marketplaces deferred”; checklist 11, 12, 25.2, 29.6 updated.

**Checklist to update:** Section 11, 12, 25.2, 29.6 (done).

**Implementation note (Phase 8):** Added `docs/architecture/phase8_migration_cloud_and_marketplaces.md`. Migration cloud and marketplaces are implemented; deferred sub-items (rollback UI, legacy cleaner, read-only legacy view, blueprint versioning UX, tenant-facing discovery, full tenant app billing) documented in phase8 doc.

---

## Phase 9 — Domain and routing (Section 7)

**Doc ref:** Section 7.

**Scope:**

- Public (runmycampus.com), superadmin (manager.runmycampus.com/super/), tenant (portal.schoolname.com, schoolname.runmycampus.com); resolution order; separation in branding, IA, layout, code.

**Done when:**

- [x] Public, superadmin, and tenant domains/hosts implemented and documented; resolution order (host → type → tenant → request context → DB schema → blueprint/policy) documented and enforced — phase9_domain_and_routing.md, request_flow_tenant_resolution.mmd, tenancy.md, phase2_control_tenant_shells.md.
- [x] Checklist Section 7 items marked [x] or updated with notes (already [x] in main doc).

**Checklist to update:** Section 7 (confirmed).

**Implementation note (Phase 9):** Added `docs/architecture/phase9_domain_and_routing.md` — verification of 7.1–7.6 with file/function refs (host_routing, UrlConfSwitcherMiddleware, public/manager/tenant urlconfs, tenancy.md, request_flow_tenant_resolution.mmd).

---

## Phase 10 — Superadmin vs tenant UI (Section 8)

**Doc ref:** Section 8.

**Scope:**

- Superadmin: command center, observability, ecosystem manager, deployment cockpit, policy control plane; dark, high-density. Tenant: school OS, localized, role-based, school-branded. Public: product storytelling, demos. Teacher: task-oriented. Parent/student: mobile-first.

**Done when:**

- [x] Design/system split between superadmin and tenant UI documented and implemented (same codebase, distinct variants/shells) — phase10_superadmin_vs_tenant_ui.md.
- [x] Checklist Section 8 updated (8.1–8.5 marked [x]).

**Checklist to update:** Section 8 (done).

**Implementation note (Phase 10):** Added `docs/architecture/phase10_superadmin_vs_tenant_ui.md` — 8.1–8.5 verification with touchpoints (control-plane-shell, super_command_center, backend_base, tenant urlconf, branding, public/teacher/parent personas).

---

## Phase 11 — Module architecture (Section 9)

**Doc ref:** Section 9.

**Scope:**

- Each module split into five concerns: core domain, policy layer, workflow layer, presentation layer, integration layer.

**Done when:**

- [x] Module map or doc lists major modules and their five-concern split; Admissions and Evals used as reference — phase11_module_architecture_section_9.md.
- [x] Checklist Section 9 updated (9.1–9.5 [x]).

**Checklist to update:** Section 9 (done).

**Implementation note (Phase 11):** Added `docs/architecture/phase11_module_architecture_section_9.md` — five-concern definitions, module map (Admissions, Evals, Academics, Finance, People, Portal, Reports, Communication, Siteconfig, Compliance), reference implementations for Admissions and Evals.

---

## Phase 12 — Platform-wide configurability (Section 10)

**Doc ref:** Section 10.

**Scope:**

- Admissions, Academics, Finance, Attendance, Communication, HR/Staff, Compliance, Dashboards — each with listed configurable items (admission number, grade scale, invoice timing, statuses, channels, etc.).

**Done when:**

- [x] Configurable items per module documented (policy/blueprint/settings); checklist Section 10 updated — phase12_platform_configurability_section_10.md.

**Checklist to update:** Section 10 (done).

**Implementation note (Phase 12):** Added `docs/architecture/phase12_platform_configurability_section_10.md` — 10.1–10.8 (Admissions, Academics, Finance, Attendance, Communication, HR/Staff, Compliance, Dashboards) with where each item is configured and status (done/partial/scoped).

---

## Phase 13 — Technical refactor map (Section 13)

**Doc ref:** Section 13.

**Scope:**

- Refactor map: apps, models, dependencies, routing, tenancy, config/policy/workflow/dashboard injection, hardcoding hotspots, refactor order. Deliverables: apps.txt, urls.txt, migrations.txt, models.png, tenancy.md, policy_injection.md; Mermaid request flow + tenant resolution + DB schema.

**Done when:**

- [x] Refactor map produced or updated; architecture map pack present in docs/architecture/; checklist Section 13 updated — phase13_refactor_map_section_13.md; 13.1–13.4 already [x].

**Checklist to update:** Section 13 (confirmed).

**Implementation note (Phase 13):** Added `docs/architecture/phase13_refactor_map_section_13.md` — verification that 13.1–13.4 deliverables are present.

---

## Phase 14 — “Feel like” (Section 14)

**Doc ref:** Section 14.

**Scope:**

- To you: AWS control + Stripe visibility + Shopify config. To school admin: product for their school. To teacher: fast daily workspace. To parent: mobile-first. To government: secure intelligence layer. To developers: trustworthy platform.

**Done when:**

- [x] Document or verify UX/product alignment per audience; checklist Section 14 updated — phase14_through_phase20_sections_14_to_26.md.

**Checklist to update:** Section 14 (done).

**Implementation note (Phase 14):** Section 14 (feel like) documented in phase14_through_phase20_sections_14_to_26.md; checklist 14.1–14.6 updated (partial/done/scoped).

---

## Phase 15 — Salesforce-style core (Section 15)

**Doc ref:** Section 15.

**Scope:**

- Universal Student 360; metadata-driven data layer; global ledger (multi-currency, VAT/GST, scholarships, payment plans, installments, double-entry).

**Done when:**

- [x] Scope implemented or roadmap documented; checklist Section 15 updated. See docs/architecture/section_15_scope_implemented_and_roadmap.md (15.1 Student 360 services + roadmap for full UI/transcript; 15.2 DynamicField roadmap; 15.3 global ledger partial + payment plans/double-entry roadmap).

**Checklist to update:** Section 15.

---

## Phase 16 — Globalization, security, API, edge, offline (Section 16)

**Doc ref:** Section 16.

**Scope:**

- Currencies, regional tax, academic calendar, language, RTL, local docs; GDPR/FERPA/LGPD/COPPA; RLS, tenant isolation, audit; API first; edge routing; offline first (attendance, grade entry, notes; sync engine); global testing matrix.

**Done when:**

- [x] Implemented or scoped per item; checklist Section 16 updated — phase14_through_phase20_sections_14_to_26.md.

**Checklist to update:** Section 16 (done).

**Implementation note (Phase 16):** Section 16 (globalization, security, API, edge, offline) partial/scoped in phase14–20 doc; 16.2 done.

---

## Phase 17 — SoR vs experience, portability, trust, SRE (Section 17)

**Doc ref:** Section 17.

**Scope:**

- SoR vs Experience separation; data portability (exports, OneRoster, Ed-Fi, Tenant Wind-Down); trust/compliance as product; real policy engine; SRE (RPO/RTO, flags, canaries, observability).

**Done when:**

- [x] Documented or implemented; checklist Section 17 updated — phase14_through_phase20_sections_14_to_26.md.

**Checklist to update:** Section 17 (done).

**Implementation note (Phase 17):** Section 17 (SoR/Experience, portability, trust, SRE) partial/done in phase14–20 doc; 17.4 (policy engine) done.

---

## Phase 18 — Standards and interop (Section 18)

**Doc ref:** Section 18.

**Scope:**

- LTI 1.3, OneRoster 1.2, Ed-Fi; adapters in interop layer; CEDS; zero trust; WCAG 2.2 AA; PostgreSQL search_path documented.

**Done when:**

- [x] Standards and adapters documented or implemented; checklist Section 18 updated — phase14_through_phase20_sections_14_to_26.md.

**Checklist to update:** Section 18 (done).

**Implementation note (Phase 18):** Section 18 (LTI, OneRoster, Ed-Fi, CEDS, WCAG, search_path) partial/scoped in phase14–20 doc; OneRoster/LTI/WebhookSubscription present.

---

## Phase 19 — Tenancy strategy (Section 19)

**Doc ref:** Section 19.

**Scope:**

- Schema-per-tenant primary; resolution from host; session variables only for audit/request context; TENANCY_MODE (SCHEMA | RLS); startup assertion; apps/tenancy: TenantContext, TenantStrategy, middleware, tenant_task; document public vs tenant schema.

**Done when:**

- [x] Tenancy strategy implemented and documented; checklist Section 19 updated (already [x]; phase14–20 doc references tenancy.md).

**Checklist to update:** Section 19 (confirmed).

**Implementation note (Phase 19):** Section 19 already done (tenancy.md, 19.1–19.6 [x]); phase14_through_phase20_sections_14_to_26.md references.

---

## Phase 20 — Section 26: Differentiators

**Doc ref:** Section 26.

**Scope:**

- Student 360, event backbone (DomainEvent, WebhookSubscription, WebhookDelivery), customization (themes, workflows, schema extensions; versioned, audited, reversible), design system (tokens, component library, theme engine, density, WCAG), UX rules (no empty pages, list/form/workflow standards), shell + plugins frontend.

**Done when:**

- [x] 26.1–26.6 implemented or scoped with notes; checklist Section 26 updated — phase14_through_phase20_sections_14_to_26.md.

**Checklist to update:** Section 26.1–26.6 (done).

**Implementation note (Phase 20):** Section 26 (Student 360, event backbone, customization, design system, UX rules, shell+plugins) partial/scoped in phase14–20 doc; checklist 26.1–26.6 updated.

---

## Phase 21 — Repo audit and architecture deliverables (Section 27)

**Doc ref:** Section 27.

**Scope:**

- Audit commands; Cursor master prompt; architecture deliverables (apps.txt, urls.txt, migrations.txt, models.png, tenancy.md, policy_injection.md); refactor Admissions or Gradebook (both done); policy/get_resolved_env.

**Done when:**

- [x] Audit re-run if needed; deliverables present and current; checklist 27.1–27.3 confirmed [x] — phase21_through_phase24_sections_27_to_31.md.

**Checklist to update:** Section 27 (confirmed).

**Implementation note (Phase 21):** Section 27 already [x]; phase21–24 doc confirms deliverables; no audit re-run required.

---

## Phase 22 — Section 29: Add-ons

**Doc ref:** Section 29.

**Scope:**

- Identity/access (29.1), Observability (29.2), Search (29.3), Preview/release (29.4), Content/website (29.5), Migration engine (29.6), Integration layer (29.7), Design system (29.8), AI governance (29.9), Commercial platform (29.10).

**Done when:**

- [x] Each 29.x item implemented or scoped with a note; checklist Section 29 updated — phase21_through_phase24_sections_27_to_31.md.

**Checklist to update:** Section 29.1–29.10 (done).

**Implementation note (Phase 22):** Section 29 add-ons: 29.1–29.10 status (partial/scoped/done) in phase21–24 doc; checklist updated.

---

## Phase 23 — Section 30: Competitor and marketing

**Doc ref:** Section 30.

**Scope:**

- Learn from competitors; marketing front (segmented journeys, design, demos, migration messaging, trust, country landings, comparison, marketplace); win conditions.

**Done when:**

- [x] Documented or implemented per 30.1–30.3; checklist Section 30 updated — phase21_through_phase24_sections_27_to_31.md.

**Checklist to update:** Section 30 (done).

**Implementation note (Phase 23):** Section 30 competitor/marketing: 30.1–30.3 partial/documented in phase21–24 doc; checklist updated.

---

## Phase 24 — Section 31: References

**Doc ref:** Section 31.

**Scope:**

- WCAG, OneRoster, Ed-Fi, CEDS, NIST SP 800-207, PostgreSQL, IMS Global, Salesforce/Shopify, OpenFeature, RLS — referenced and reflected in design/docs/code where applicable.

**Done when:**

- [x] References listed and linked; checklist 31.1–31.8 updated (e.g. “referenced in tenancy.md”, “used in RLS migrations”).

**Checklist to update:** Section 31.1–31.8 (done).

**Implementation note (Phase 24):** Section 31 references: 31.1–31.8 linked and reflected in phase21_through_phase24_sections_27_to_31.md; checklist updated. All 24 phases complete; platform can move forward.

---

## Summary table

| Phase | Title | Main doc ref |
|-------|--------|---------------|
| 1 | Gradebook (and attendance) refactor — policy-only | §12, 24, 27 |
| 2 | Phase 3 hardcoding sweep | §24.1, 24.2 |
| 3 | Section 24.8 — Finish metadata-driven config | §24.8 |
| 4 | Workflow and dashboard hubs (full) | §5, 12, 24.3, 24.4 |
| 5 | Section 23 — Verify policy/blueprint injection | §23 |
| 6 | Section 25 (beyond 25.3) | §25.1, 25.2, 25.4–25.7 |
| 7 | Section 28 — Data architecture and provisioning | §28 |
| 8 | Migration cloud and marketplaces | §11, 12, 25.2, 28, 29 |
| 9 | Domain and routing | §7 |
| 10 | Superadmin vs tenant UI | §8 |
| 11 | Module architecture | §9 |
| 12 | Platform-wide configurability | §10 |
| 13 | Technical refactor map | §13 |
| 14 | “Feel like” | §14 |
| 15 | Salesforce-style core | §15 |
| 16 | Globalization, security, API, edge, offline | §16 |
| 17 | SoR vs experience, portability, trust, SRE | §17 |
| 18 | Standards and interop | §18 |
| 19 | Tenancy strategy | §19 |
| 20 | Section 26 — Differentiators | §26 |
| 21 | Repo audit and deliverables | §27 |
| 22 | Section 29 — Add-ons | §29 |
| 23 | Section 30 — Competitor and marketing | §30 |
| 24 | Section 31 — References | §31 |

After each phase, update the checklist in `RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md` and add a short implementation note if useful.
