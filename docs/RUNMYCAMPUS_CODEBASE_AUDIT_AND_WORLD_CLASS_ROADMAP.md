# RunMyCampus Codebase Audit and World-Class Roadmap

**Purpose:** Single reference for strengths/weaknesses, all Q&A, schema-per-tenant as the config, Dashboard/Workflow catalogs, and full blueprint coverage so nothing is missed. No redundancy; professional and actionable.

---

## 0. Tenant-Per-Schema Is the Config (Locked In)

**Decision:** **Schema-per-tenant is the standard.** Data is isolated per tenant using a dedicated PostgreSQL schema per school.

**Current state in codebase:**

- **[config/settings.py](config/settings.py)** (lines 791–885): When `USE_DJANGO_TENANTS` is not set to `0`, PostgreSQL uses **django-tenants**: `django_tenants.postgresql_backend`, `TenantSyncRouter`, `TenantMainMiddleware`, `SHARED_APPS` (accounts, schools, siteconfig, compliance, customers, etc.), **TENANT_APPS** (academics, people, finance, evals, reports, communication, analytics, payroll). So **tenant-per-schema is already the default** for PostgreSQL.
- **Public (control) schema:** Identity, Tenant registry (Client, Domain), SiteSettings, RegionConfig, global support/feedback.
- **Tenant schemas:** One schema per school; all tenant-scoped tables (Students, Grades, Invoices, etc.) live in that schema. `TenantSchemaSchoolBridgeMiddleware` and `TenantMainMiddleware` set the connection to the correct schema per request.

**What to do:**

1. **Document it:** In deployment and architecture docs, state explicitly: "RunMyCampus uses schema-per-tenant (django-tenants) on PostgreSQL. Do not set USE_DJANGO_TENANTS=0 for production unless explicitly required."
2. **Onboarding script:** Implement an **OnboardingService** that: (a) validates slug uniqueness, (b) creates a new PostgreSQL schema for the tenant, (c) runs the **Master Table List** DDL/migrations in that schema, (d) seeds localized defaults (currency, grading, holidays) by country, (e) creates first admin, (f) registers Domain/subdomain. Include kill-switch (DROP SCHEMA on failure), idempotency, and audit logging in public schema.
3. **Master Table List:** Define the canonical list of tables (and indexes) created in every new tenant schema (Identity: Students, Staff, Guardians; Academic: Subjects, Classrooms, Terms, GradingScales, Attendance; Financial: LedgerEntries, FeeTemplates, Invoices, Payments; Exams; Logistics; plus audit_log). Use a single migration or DDL script that the onboarding script runs per schema.
4. **Migration runner:** When app schema changes, a script (or Graphile/custom runner) must apply migrations to **all** tenant schemas (or to a template schema) in an atomic/idempotent way; document rollback and per-schema failure handling.
5. **RLS:** Keep RLS on tenant tables as defense-in-depth even with schema isolation.

---

## 1. Answers to Your Specific Questions (Complete)

### 1.1 Where is the country and region of where the school is located in the settings?

- **SiteSettings** ([apps/siteconfig/models.py](apps/siteconfig/models.py)): free-text `country`, `region`, `ministry` (legacy/site-level).
- **School** ([apps/schools/models.py](apps/schools/models.py)): **`default_region`** FK to **RegionConfig** is the **canonical** school location (ISO code, timezone, currency, grading).
- **Gap:** No single "School location" picker in settings that uses RegionConfig (and optional Province) as dropdowns.
- **Action:** Add a clear "School location" (country + region) in Site Settings and/or School admin using **RegionConfig** (and Province) as dropdowns; deprecate or auto-fill SiteSettings.country/region from School.default_region.

### 1.2 What is the difference between module and feature centers?

- **Modules:** Enableable **product capabilities per school** (library, transport, canteen, etc.). Defined in [apps/schools/feature_registry.py](apps/schools/feature_registry.py), gated by [apps/schools/middleware.py](apps/schools/middleware.py) (`FEATURE_GATE_PATH_MAP`); resolved by `is_feature_enabled(school, code)`.
- **Feature center (Feature Control):** The **UI panel** at `/siteconfig/feature-control/` where you toggle modules **and** global/site flags (`SiteSettings.backend_feature_flags`, portal flags).
- **Action:** Document this in [docs/FEATURE_GATE_AND_MODULES.md](docs/FEATURE_GATE_AND_MODULES.md) or [docs/SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING.md](docs/SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING.md) in one short subsection.

### 1.3 In Region configuration, can we ensure ALL countries and regions are covered in the code?

- **Yes, in code.** [apps/siteconfig/global_catalog.py](apps/siteconfig/global_catalog.py) — `GlobalGeoCatalog.list_countries()` uses **pycountry** (ISO 3166-1) when available. [apps/siteconfig/management/commands/seed_global_regions.py](apps/siteconfig/management/commands/seed_global_regions.py) creates a **RegionConfig** per country.
- **Action:** (1) Run `seed_global_regions` (and `seed_global_data` if used) at deploy; (2) add a **verify_region_coverage** command that checks every country from the catalog has a RegionConfig; (3) document dependency on pycountry.

### 1.4 What is branding in system config vs site settings?

- **Same thing in this codebase.** "Site Settings" **is** the system/site-level config (singleton **SiteSettings**). Branding there: primary_color, accent_color, logo, theme_pack, etc.
- **Per-tenant:** **School** (logo_url, primary_color, accent_color) and optional **BrandSettings** (Phase F). When `request.school` is set, tenant branding overrides.
- **Action:** Document in [docs/SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING.md](docs/SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING.md): "Site-level branding = SiteSettings; tenant-level = School + BrandSettings."

### 1.5 If a country has different education systems, should they all be in region configs?

- **Yes, and they are.** **RegionConfig** (one per country) + **EducationSystemProfile** ([apps/siteconfig/models.py](apps/siteconfig/models.py)): multiple rows per country (e.g. CMR EN/FR) with sub_system, term_labels, grading_scale, subject_seed, config JSON. **education_profile_engine.py** has country packs (COUNTRY_PACK_OVERRIDES).
- **Action:** Ensure seed creates EducationSystemProfile for all relevant countries/sub-systems; expose "Education systems for this region" in region config UI.

### 1.6 Rather than having to input data, give users options to pick from (checkboxes + custom field)?

- **Action:** Use **catalog-backed dropdowns** (RegionConfig, GradingScaleConfig, languages) with optional **"Other (specify)"** where needed. Audit forms (Site Settings, School admin, portal onboarding); introduce a small pattern (e.g. CatalogChoiceField + allow_other); replace free-text for country/region, grading, language first.

### 1.7 Allow the school admin to determine how they want their admission number to be generated?

- **Current:** [apps/siteconfig/models.py](apps/siteconfig/models.py): `admission_number_mode` (AUTO, MANUAL, AUTO_OR_MANUAL), `admission_number_pattern` (regex **validation** only). [apps/people/models.py](apps/people/models.py): **Generation formula is fixed** (YY+SCHOOLCODE+####+SPEC+CLASS).
- **Action:** Add **configurable generation**: either (A) a few built-in **strategies** (current format, year+seq only, seq only) in a dropdown, or (B) an **admission number template** field with placeholders (e.g. `{year_2digit}{school_code}{seq_4digit}{spec_code}{class_segment}`) and a parser in `generate_admission_number()`. Keep `admission_number_pattern` for validation. Expose in Site Settings.

---

## 2. Dashboard Catalog (Not Yet Present — Add to Plan)

**Blueprint:** "Theme & Layout Store" where school admins **pick** dashboard styles (e.g. "Minimalist Academic," "Finance-First") and assign them by role; "Widget Store" to pin/unpin blocks.

**Current state:**

- **Widget catalog:** [apps/siteconfig/models_dashboard.py](apps/siteconfig/models_dashboard.py) — **DashboardWidget** (id, name, template_path, page, role, layout hints). This is a **widget** catalog, not a **dashboard template** catalog.
- **Layout:** **DashboardLayout** (per user/role/page, JSON layout) and **DashboardUserPreference** (visible_widgets, theme, presets). Resolution: user-specific → role default → legacy ([apps/siteconfig/dashboard_views.py](apps/siteconfig/dashboard_views.py)).
- **Missing:** No **DashboardTemplate** (or equivalent) table — i.e. no named **full-dashboard presets** (e.g. "Executive Powerhouse," "Campus Pulse") that schools **select** and assign to roles. No "Configuration Hub" where admins preview and assign layouts by role.

**Action (world-class):**

1. **Dashboard template catalog (public or control schema):** Add a **DashboardTemplate** (or reuse an extended model): id, name, description, thumbnail, **config_schema** (JSON: widgets, positions, theme). These are the "master templates" you provide.
2. **Tenant assignment (tenant schema):** Add **TenantLayoutAssignment** (or equivalent): role, template_id, styling overrides (JSON), is_active. So each school chooses which template applies to STUDENT, TEACHER, PARENT, ADMIN, etc.
3. **UI:** "Configuration Hub" / "Dashboard Selection" in school admin: list templates with preview; assign by role; optional live customizer (colors/fonts from DB).
4. **Runtime:** When loading a dashboard, resolve: TenantLayoutAssignment(role) → template → JSON layout + widgets; inject theme (e.g. CSS variables) from assignment styling. Keep existing DashboardLayout for per-user overrides if desired.

---

## 3. Workflow Catalog (Partially Present — Extend)

**Blueprint:** "Pick-a-Flow" library with pre-built workflows (e.g. Admissions: Minimalist vs Elite; Finance: Direct Pay vs Installment; Attendance: Silent vs Auto-SMS); "Custom Flow Builder" (trigger–action–condition); Flow Registry of "Powerhouse Packs."

**Current state:**

- **WorkflowConfig** ([apps/academics/models.py](apps/academics/models.py)): **workflow_key**, **steps** (JSON). Used for **JSON-driven wizards** (e.g. student_onboarding). [apps/academics/views_workflow.py](apps/academics/views_workflow.py): generic wizard loads steps and renders. This is **wizard step** configuration, not **business automation** flows.
- **Automation:** [apps/automation](apps/automation) has rules/approvals; no single "Flow Registry" of named, pre-built **business** workflows (e.g. "If absent 3 days → notify counselor") that tenants **activate** from a catalog.

**Action (world-class):**

1. **Workflow catalog (template library):** Define a **WorkflowTemplate** or **FlowRegistry** (public or control schema): id, code, name, description, **trigger** (event), **conditions** (JSON), **actions** (JSON). Pre-built entries: e.g. "Safety Net" (absent 3 days → counselor), "Fiscal Guardian" (fees 30 days overdue → pause access). These are the "Powerhouse Packs."
2. **Tenant workflow registry (tenant schema):** **WorkflowRegistry** or **TenantWorkflow**: template_id or code, is_active, overrides (JSON). School admin can **activate/deactivate** pre-built flows or clone and customize.
3. **Execution:** An engine (or integration with existing automation) evaluates **triggers** (e.g. attendance marked, fee overdue), checks **conditions**, and runs **actions** (send SMS, create task, update ledger). Ensure each execution is logged in the audit trail.
4. **UI:** "Workflow Command Center" or "Workflow Gallery" in school admin: list certified flows; toggle on/off; optional "Custom Flow Builder" (drag-and-drop or form-based trigger–action–condition) for tenant-specific flows. Keep WorkflowConfig for **wizard** steps separate from **business automation** flows.

---

## 4. Full Blueprint Checklist (Nothing Missed)

Use this to ensure every major world-class item is either already covered above or explicitly listed here.

### 4.1 Core Infrastructure

| Item | Status | Notes / Action |
|------|--------|----------------|
| Data isolation (schema-per-tenant) | Locked in | §0; onboarding + master table list + migration runner. |
| RLS as defense-in-depth | Present | Keep; verify all tenant tables have RLS. |
| i18n (translations, date/currency, RTL) | Partial | Complete gettext; catalog-backed forms; document. |
| Performance monitoring (noisy neighbor) | Gap | Add metrics (e.g. Prometheus/New Relic) and per-tenant/queue limits. |
| Connection pooling (PgBouncer) | Doc | Document for multi-schema scaling. |

### 4.2 Module & Workflow Mapping

| Item | Status | Notes / Action |
|------|--------|----------------|
| Admission: Inquiry → Active Student | Partial | Document handoff; zero-friction admission (magic link, OCR, one-tap pay) per blueprint. |
| Academic: metadata-driven rubrics, formula builder | Partial | RegionConfig/grading_rule; extend to tenant-configurable formula where needed. |
| Financial: double-entry, audit trail, multi-currency | Partial | Audit trail to be trigger-based + immutable; double-entry and FX per blueprint. |
| Dashboard catalog | Gap | §2. |
| Workflow catalog | Partial | §3; add FlowRegistry + TenantWorkflow + engine. |

### 4.3 Everything Inventory (Audit)

| Item | Status | Notes / Action |
|------|--------|----------------|
| Pages/tools: WCAG, mobile | Partial | Audit with pa11y/Lighthouse; fix gaps. |
| Scripts/jobs: idempotency, error handling | Partial | List all Celery tasks + management commands; document idempotency and tenant context. |
| Security scripts (SonarQube/Snyk) | Gap | Add to CI; record in REPORTS/AUDIT_LOG.md. |
| REPORTS/AUDIT_LOG.md | Gap | Create: queries missing tenant scope, hardcoded strings, API rate limiting, background jobs list. |

### 4.4 Tenant Autonomy & Feedback

| Item | Status | Notes / Action |
|------|--------|----------------|
| Feature flags (school turns on module without deploy) | Present | backend_feature_flags, get_tenant_modules, plan/addons. |
| Feedback module → product backlog | Gap | Ensure Feedback/Feature Request is tagged by region/module and visible in roadmap (Planned/In Development/Released). |

### 4.5 Schema-Per-Tenant Specifics

| Item | Status | Notes / Action |
|------|--------|----------------|
| Onboarding script | Gap | §0. |
| Master table list | Gap | §0. |
| Migration runner (all schemas) | Gap | Document; idempotent, atomic per schema. |
| Feedback in public schema | Design | Feature requests from tenant UI → public.feedback (or equivalent). |

### 4.6 Audit Trail (World-Class)

| Item | Status | Notes / Action |
|------|--------|----------------|
| Trigger-based logging (INSERT/UPDATE/DELETE) | Gap | Add PostgreSQL triggers on sensitive tables → tenant audit_log; INSERT-only. |
| Immutable audit_log (no UPDATE/DELETE) | Gap | DB permissions. |
| Who/What/Where/When/Why + correlation_id | Partial | Extend app-level audit to match; session context for "who." |
| Cryptographic chaining (optional) | Gap | Per blueprint. |
| Retention + cold storage | Partial | Document; implement retention policy. |

### 4.7 Compliance, Security, GSOC

| Item | Status | Notes / Action |
|------|--------|----------------|
| GESS/GEPS, data residency | Partial | regional_cluster; pin tenant to region; document. |
| Impossible travel, bulk export detection | Partial | ImpossibleTravelMiddleware present; enhance + alert. |
| Super-admin toggle center (kill-switch, per-tenant flags) | Partial | Build out per blueprint (grid, Redis Pub/Sub, audit). |
| Staging/sandbox schema per tenant | Gap | Optional; clone prod schema to tenant_staging for "View in Sandbox." |

### 4.8 Communication, Orchestration, UI

| Item | Status | Notes / Action |
|------|--------|----------------|
| Workflow Designer (trigger–action–condition, channels) | Gap | §3; CommunicationWorkflow table + UI. |
| Communication templates library | Partial | Localized templates pickable by school. |
| Progressive disclosure, one thing per page | Partial | Apply to long forms (stepper, defaults). |
| Command K / global search | Partial | Document; enhance if needed. |

### 4.9 Financial (World-Class)

| Item | Status | Notes / Action |
|------|--------|----------------|
| Double-entry, no delete (void only) | Partial | Design and implement where missing. |
| Multi-currency, FX, DCC | Partial | Exchange rates; document 195-country payment strategy. |
| Triple-match reconciliation | Gap | Per blueprint. |
| Tax (VAT/GST/nexus) | Gap | Document; integrate tax API where required. |

### 4.10 Other Blueprint Areas (Not Exhaustive)

- **Legacy Import Wizard:** AI-driven mapping, validation, dry-run, rollback — add to roadmap.
- **Interoperability / Developer Portal:** LTI 1.3, OneRoster, webhooks, versioned APIs — document and implement in phases.
- **Testing:** Synthetic data (e.g. 10 schools, 10 countries), migration dry-run test — add.
- **Crisis & DR:** Hot-standby, immutable backups, crisis schooling "flip" — document and implement.
- **Accreditation & Evidence:** ComplianceStandard, Evidence Harvester, Inspector Portal — add to roadmap.
- **Research Hub (anonymized):** Differential privacy, federated analytics — optional; document.

---

## 5. Strengths and Weaknesses (Summary)

**Strengths:** Schema-per-tenant (django-tenants) default on PostgreSQL; RLS on key tables; RegionConfig + GlobalGeoCatalog + seed; feature registry and Feature Control UI; admission number mode/pattern; app-level audit; Celery + Redis; REST API + OpenAPI + rate limiting; WorkflowConfig for wizards; DashboardWidget + DashboardLayout; existing docs (THREE_PLANS, FEATURE_GATE, etc.).

**Weaknesses:** No formal Dashboard **Template** catalog or TenantLayoutAssignment; no **Workflow/Flow** catalog of pre-built business flows; audit is app-level only (no DB triggers, no immutable audit_log); partial i18n; country/region in settings not unified on RegionConfig; admission number formula fixed; many forms still free-text; cache keys not always tenant-scoped (see world_engine plan); onboarding script and master table list not yet built.

---

## 6. Deep-Dive and Audit Execution

**How to do a deep-dive:**

1. **Create REPORTS/AUDIT_LOG.md** (or docs equivalent) with: (1) Queries missing tenant/schema scope, (2) Hardcoded strings (i18n), (3) API endpoints without rate limiting, (4) List of background scripts and idempotency/error-handling status, (5) Security scan results.
2. **Module/workflow mapping:** For each app, list pages, workflows (e.g. inquiry→enrolled), and jobs; cross-check with FEATURE_GATE_PATH_MAP and feature registry.
3. **Automate checks:** Script or Cursor prompt to scan for tenant scope, missing trans, throttle usage, Celery task tenant_context.
4. **Use existing docs:** THREE_PLANS_EXECUTION_GUIDE, KEY_MODULES_REFERENCE, MODULE_AUDIT_AND_IMPROVEMENT_PLAN — turn into checklist items and track in audit log.

---

## 7. Prioritized Action List (Consolidated)

1. **Config:** Document and enforce **schema-per-tenant** as the config; implement **OnboardingService** and **Master Table List**; add migration runner for all tenant schemas.
2. **Settings/region:** Add "School location" (country + region) with RegionConfig/Province dropdowns; deprecate or sync SiteSettings.country/region.
3. **Module vs feature center:** Document in FEATURE_GATE_AND_MODULES or SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING.
4. **Region coverage:** Run seed_global_regions at deploy; add verify_region_coverage; document pycountry.
5. **Branding:** Document site vs tenant branding.
6. **Education systems:** Keep RegionConfig + EducationSystemProfile; seed and expose in region UI.
7. **Forms:** Catalog-backed dropdowns + optional "Other" for country, region, grading, language.
8. **Admission number:** Configurable generation (strategies or template); keep pattern validation.
9. **Dashboard catalog:** Add DashboardTemplate (or equivalent) and TenantLayoutAssignment; "Configuration Hub" for role-based dashboard selection.
10. **Workflow catalog:** Add WorkflowTemplate/FlowRegistry and TenantWorkflow; Workflow Command Center / Flow Gallery; execution engine for trigger–action–condition.
11. **Audit:** Trigger-based, immutable audit_log per tenant schema; Who/What/Where/When/Why.
12. **Deep-dive:** Create REPORTS/AUDIT_LOG.md; run automated checks; map modules/workflows.

This document is the single place to ensure **every point is covered** and **tenant-per-schema is the config**, with no redundancy and a clear path to world-class standards.
