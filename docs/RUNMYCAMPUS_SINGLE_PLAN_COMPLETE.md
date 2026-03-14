---
name: RunMyCampus Codebase Audit and World-Class Roadmap
overview: Single plan for RunMyCampus—schema-per-tenant as config, all Q&A, dashboard/workflow catalogs, full blueprint checklist, strengths/weaknesses, prioritized actions, deep-dive execution, and world-class blueprint index. One plan only; nothing missed.
todos: []
isProject: false
---

**Superseded:** Execution and completion authority are in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md), [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md), [docs_truth_ledger.md](docs_truth_ledger.md), and [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md). This file is **reference only** (historical). Do not use for status or new work.

---

# RunMyCampus Codebase Audit and World-Class Roadmap (Single Plan)

This is the **one plan** for the codebase audit and world-class roadmap (reference; see supersession notice above). It covers: tenant-per-schema as the config, all your questions, dashboard catalog, workflow catalog, full blueprint checklist, strengths/weaknesses, deep-dive execution, world-class blueprint index, and prioritized actions. **Nothing is missed.**

---

## Part 0: Tenant-Per-Schema Is the Config (Locked In)

**Decision:** **Schema-per-tenant is the standard.** Data is isolated per tenant using a dedicated PostgreSQL schema per school.

**Current state in codebase:**

- **config/settings.py** (lines 791–885): When `USE_DJANGO_TENANTS` is not set to `0`, PostgreSQL uses **django-tenants**: `django_tenants.postgresql_backend`, `TenantSyncRouter`, `TenantMainMiddleware`, `SHARED_APPS` (accounts, schools, siteconfig, compliance, customers, etc.), **TENANT_APPS** (academics, people, finance, evals, reports, communication, analytics, payroll). So **tenant-per-schema is already the default** for PostgreSQL.
- **Public (control) schema:** Identity, Tenant registry (Client, Domain), SiteSettings, RegionConfig, global support/feedback.
- **Tenant schemas:** One schema per school; all tenant-scoped tables live in that schema. `TenantSchemaSchoolBridgeMiddleware` and `TenantMainMiddleware` set the connection to the correct schema per request.

**What to do:**

1. **Document it:** In deployment and architecture docs, state explicitly: "RunMyCampus uses schema-per-tenant (django-tenants) on PostgreSQL. Do not set USE_DJANGO_TENANTS=0 for production unless explicitly required."
2. **Onboarding script:** Implement an **OnboardingService** that: (a) validates slug uniqueness, (b) creates a new PostgreSQL schema for the tenant, (c) runs the **Master Table List** DDL/migrations in that schema, (d) seeds localized defaults (currency, grading, holidays) by country, (e) creates first admin, (f) registers Domain/subdomain. Include kill-switch (DROP SCHEMA on failure), idempotency, and audit logging in public schema.
3. **Master Table List:** Define the canonical list of tables created in every new tenant schema (Identity: Students, Staff, Guardians; Academic: Subjects, Classrooms, Terms, GradingScales, Attendance; Financial: LedgerEntries, FeeTemplates, Invoices, Payments; Exams; Logistics; plus audit_log). Use a single migration or DDL script that the onboarding script runs per schema.
4. **Migration runner:** When app schema changes, a script must apply migrations to **all** tenant schemas in an atomic/idempotent way. **Per-schema rollback:** If a migration fails on one schema, roll back **only that schema** and alert; other schemas proceed. Document rollback and per-schema failure handling. **Optional:** Use a "Bridge" model (schema sharding) where schemas are grouped into clusters (e.g. by region) for phased rollout (e.g. update Europe while Asia is asleep).
5. **Isolation is schema-per-tenant only:** Primary data isolation is by PostgreSQL schema (one schema per school). **Do not rely on RLS or tenant_id for isolation.** Optional: add RLS on tenant tables as defense-in-depth only if desired; it is not required for correctness.

---

## Part 1: Answers to Your Specific Questions

### 1. Where is the country and region of where the school is located in the settings?

**Current state:** [apps/siteconfig/models.py](apps/siteconfig/models.py) — `SiteSettings` has **free-text** `country`, `region`, `ministry`. [apps/schools/models.py](apps/schools/models.py) — `School.default_region` is **ForeignKey to `RegionConfig`** (canonical structured location). **Gap:** No single "School location" picker in Site Settings that uses RegionConfig (and Province) as dropdowns. **Recommendation:** Add "School location" section in Site Settings and/or School admin using RegionConfig/Province as dropdowns; deprecate or auto-fill SiteSettings.country/region from School.default_region.

### 2. What is the difference between module and feature centers?

**Modules:** Enableable **product capabilities per school** (library, transport, canteen, etc.). Defined in [apps/schools/feature_registry.py](apps/schools/feature_registry.py), gated by [apps/schools/middleware.py](apps/schools/middleware.py) (`FEATURE_GATE_PATH_MAP`); resolved by `is_feature_enabled(school, code)`. **Feature center (Feature Control):** The **UI panel** at [apps/siteconfig/views_feature_control.py](apps/siteconfig/views_feature_control.py) — `/siteconfig/feature-control/` — where you toggle modules **and** global/site flags (`SiteSettings.backend_feature_flags`). Document in [docs/FEATURE_GATE_AND_MODULES.md](docs/FEATURE_GATE_AND_MODULES.md) or [docs/SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING.md](docs/SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING.md).

### 3. Region configuration: can we ensure ALL countries and regions are covered in the code?

**Current state:** [apps/siteconfig/global_catalog.py](apps/siteconfig/global_catalog.py) — `GlobalGeoCatalog.list_countries()` uses **pycountry** (ISO 3166-1) when available. [apps/siteconfig/management/commands/seed_global_regions.py](apps/siteconfig/management/commands/seed_global_regions.py) creates a **RegionConfig** per country. **Recommendation:** Run `seed_global_regions` (and `seed_global_data` if used) at deploy; add **verify_region_coverage** command; document dependency on pycountry. Province optional; seed or document per deployment.

### 4. What is branding in system config vs site settings?

**Current state:** "Site Settings" **is** the system/site-level config (singleton **SiteSettings** in [apps/siteconfig/models.py](apps/siteconfig/models.py) — primary_color, accent_color, logo, theme_pack, etc.). **Per-tenant:** [apps/schools/models.py](apps/schools/models.py) — **School** (logo_url, primary_color, accent_color) and optional **BrandSettings** (Phase F). When `request.school` is set, tenant branding overrides. Document in [docs/SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING.md](docs/SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING.md): site-level = SiteSettings; tenant-level = School + BrandSettings.

### 5. If a country has different education systems, should they all be in region configs?

**Current state:** **RegionConfig** (one per country) + **EducationSystemProfile** ([apps/siteconfig/models.py](apps/siteconfig/models.py)) — multiple rows per country (e.g. CMR EN/FR) with sub_system, term_labels, grading_scale, config JSON. [apps/siteconfig/education_profile_engine.py](apps/siteconfig/education_profile_engine.py) has country packs. **Recommendation:** Keep model; ensure seed creates EducationSystemProfile for all relevant countries/sub-systems; expose "Education systems for this region" in region config UI.

### 6. Rather than input data, give users options to pick from (checkboxes, custom field)?

**Current state:** Many fields are free-text across Site Settings, School admin, portal. **Recommendation:** Use **catalog-backed dropdowns** (RegionConfig, GradingScaleConfig, languages) with optional **"Other (specify)"**. Audit forms; introduce pattern (e.g. CatalogChoiceField + allow_other); replace free-text for country/region, grading, language first.

### 7. Allow the school admin to determine how admission number is generated?

**Current state:** [apps/siteconfig/models.py](apps/siteconfig/models.py) — `admission_number_mode` (AUTO, MANUAL, AUTO_OR_MANUAL), `admission_number_pattern` (regex **validation** only). [apps/people/models.py](apps/people/models.py) — **Generation formula is fixed** (YY+SCHOOLCODE+####+SPEC+CLASS). **Recommendation:** Add **configurable generation**: (A) built-in **strategies** (current format, year+seq only, seq only) in a dropdown, or (B) **admission number template** field with placeholders (e.g. `{year_2digit}{school_code}{seq_4digit}{spec_code}{class_segment}`) and parser in `generate_admission_number()`. Keep `admission_number_pattern` for validation. Expose in Site Settings.

---

## Part 2: Strengths and Weaknesses

### Strengths

Multi-tenancy and isolation (**schema-per-tenant**, django-tenants); tenant resolution; Region and i18n foundation; feature and module model; admission number mode/pattern; audit and compliance; Celery + Redis; REST API + OpenAPI + rate limiting; existing docs and plans.

### Weaknesses

- No DB-level audit triggers; partial i18n; country/region UX split; admission number formula fixed; forms still free-text; cache keys may miss tenant/schema; role normalization inconsistent.
- **Schema-per-tenant:** Now locked in (Part 0). Remaining gaps: OnboardingService, Master Table List, and migration runner for all tenant schemas still to be built.

---

### Part 2b: Dashboard Catalog (Not Yet Present)

**Blueprint:** Theme & Layout Store; Widget Store; role-based assignment.

**Current state:** DashboardWidget, DashboardLayout, DashboardUserPreference exist ([apps/siteconfig/models_dashboard.py](apps/siteconfig/models_dashboard.py)). **Missing:** No DashboardTemplate or "Configuration Hub" for role-based dashboard selection.

**Action:** (1) Add DashboardTemplate (public/control schema): id, name, description, thumbnail, config_schema (JSON). (2) Add TenantLayoutAssignment (tenant schema): role, template_id, styling overrides, is_active. (3) Configuration Hub UI: list templates, assign by role, optional live customizer. (4) Runtime: resolve TenantLayoutAssignment(role) → template → layout + theme; keep DashboardLayout for per-user overrides.

---

### Part 2c: Workflow Catalog (Partially Present — Extend)

**Blueprint:** Pick-a-Flow library; Custom Flow Builder (trigger–action–condition); Flow Registry "Powerhouse Packs."

**Current state:** WorkflowConfig ([apps/academics/models.py](apps/academics/models.py)) = wizard steps; no catalog of pre-built **business** workflows (e.g. "If absent 3 days → notify counselor").

**Action:** (1) WorkflowTemplate/FlowRegistry (public/control): trigger, conditions, actions (JSON); pre-built e.g. "Safety Net", "Fiscal Guardian". (2) TenantWorkflow (tenant): template_id/code, is_active, overrides. (3) Execution engine; log each run in audit trail. (4) Workflow Command Center / Flow Gallery UI; optional Custom Flow Builder. Keep WorkflowConfig for wizards separate.

---

## Part 3: Deep-Dive Audit and World-Class Alignment

### 3.1 How to do a deep-dive on every module, feature, workflow, job, page, script, tool

**Scope (nothing excluded):** Every module, feature, workflow, background job, page/view, script, and tool across the platform and codebase. The goal is to ensure the codebase meets world-class standards.

**Isolation principle:** Data isolation is **schema-per-tenant only**. Every tenant-scoped query must run in the correct PostgreSQL schema (search_path/connection). Do not rely on manual `tenant_id` filters or RLS for isolation; the schema is the single source of truth. Audit for: (a) shared-app code that touches tenant data without setting schema, (b) tenant-app code that might run in wrong schema.

1. **Create REPORTS/AUDIT_LOG.md** with: queries missing **schema/tenant scope** (wrong or missing search_path for tenant tables); hardcoded strings (i18n); API endpoints without rate limiting; background scripts/jobs (idempotency, error handling, tenant context); security scan results; accessibility (WCAG) gaps; **Clean Architecture & SOLID** (e.g. domain/application/infrastructure separation, dependency rule, SOLID principles — flag violations).
2. **Module and workflow mapping:** Per app — pages/views (URL → view → template), workflows (e.g. inquiry → admission → active student), jobs (Celery, commands). Cross-check FEATURE_GATE_PATH_MAP and feature registry.
3. **Leverage existing docs:** THREE_PLANS_EXECUTION_GUIDE, KEY_MODULES_REFERENCE, ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS, MODULE_AUDIT_AND_IMPROVEMENT_PLAN — checklist in audit log.
4. **Automate:** Cursor/CI prompt to scan for tenant scope, missing trans, throttle usage, Celery tenant_context; output to REPORTS/AUDIT_LOG.md.

### 3.2 Rigid architectural framework (blueprint vs current)

| Blueprint item | Current state | Action |
|----------------|---------------|--------|
| Data isolation | Schema-per-tenant locked in (Part 0) | OnboardingService, master table list, migration runner. Primary isolation = schema (search_path); optional RLS as defense-in-depth only. |
| i18n | Partial | Complete gettext; catalog-backed forms; date/currency/numbers by region. |
| Performance / noisy neighbor | Celery, Redis | Add Prometheus/New Relic; per-tenant/queue limits. |
| Audit trail | App-level | PostgreSQL triggers → immutable audit_log; optional chain hash. |
| Feature flags | Present | Centralize; tenant/regional overrides. |
| Admission workflow | Partial | Configurable generation; keep validation. |
| Region/country | Partial | verify_region_coverage; dropdowns from RegionConfig. |
| Branding | Present | Document; CSS variables on tenant host. |

### 3.3 Tenant schema (schema-per-tenant) — locked in

**Schema-per-tenant is the config** (Part 0). To complete alignment:

1. Treat django-tenants as default for PostgreSQL.
2. Implement OnboardingService + Master Table List + migration runner.
3. Ensure every tenant-scoped query runs in the correct schema (search_path/connection); **never rely on tenant_id or RLS for isolation** — schema is the single source of isolation.
4. Optional: RLS on tenant tables as defense-in-depth only (not required).

No "if shared DB" branch — schema-per-tenant is the standard.

---

### Part 3.4: Full Blueprint Checklist (Nothing Missed)

#### 4.1 Core Infrastructure

| Item | Status | Notes / Action |
|------|--------|----------------|
| Data isolation (schema-per-tenant) | Locked in | Part 0; onboarding + master table list + migration runner. **Primary isolation = schema only.** |
| Optional RLS (defense-in-depth) | Optional | Only if desired; not required. Primary isolation is schema-per-tenant. |
| i18n (translations, date/currency, RTL) | Partial | Complete gettext; catalog-backed forms; document. |
| Performance monitoring (noisy neighbor) | Gap | Add metrics (e.g. Prometheus/New Relic) and per-tenant/queue limits. |
| Connection pooling (PgBouncer) | Doc | Document for multi-schema scaling. |

#### 4.2 Module & Workflow Mapping

| Item | Status | Notes / Action |
|------|--------|----------------|
| Admission: Inquiry → Active Student | Partial | Document handoff; zero-friction admission (magic link, OCR, one-tap pay) per blueprint. |
| Academic: metadata-driven rubrics, formula builder | Partial | Extend to tenant-configurable formula where needed. |
| Financial: double-entry, audit trail, multi-currency | Partial | Trigger-based + immutable audit; double-entry and FX per blueprint. |
| Dashboard catalog | Gap | Part 2b. |
| Workflow catalog | Partial | Part 2c; add FlowRegistry + TenantWorkflow + engine. |

#### 4.3 Everything Inventory (Audit)

| Item | Status | Notes / Action |
|------|--------|----------------|
| Pages/tools: WCAG, mobile | Partial | Audit with pa11y/Lighthouse; fix gaps. |
| Scripts/jobs: idempotency, error handling | Partial | List all Celery tasks + management commands; document. |
| Security scripts (SonarQube/Snyk) | Gap | Add to CI; record in REPORTS/AUDIT_LOG.md. |
| REPORTS/AUDIT_LOG.md | Gap | Create with tenant scope, i18n, rate limiting, jobs list, **Clean Architecture & SOLID** (flag violations). |

#### 4.4 Tenant Autonomy & Feedback

| Item | Status | Notes / Action |
|------|--------|----------------|
| Feature flags | Present | backend_feature_flags, get_tenant_modules, plan/addons. |
| Feedback module → product backlog | Gap | Tag by region/module; **upvoting by same-region admins**; **top 1% of requests auto-promoted to Dev Sprint**; visible in roadmap (Planned/In Development/Released). |

#### 4.5 Schema-Per-Tenant Specifics

| Item | Status | Notes / Action |
|------|--------|----------------|
| Onboarding script | Gap | Part 0. |
| Master table list | Gap | Part 0. |
| Migration runner (all schemas) | Gap | Document; idempotent, atomic per schema; **on failure roll back only that schema and alert, others proceed**; optional bridge/schema sharding for phased rollout. |
| Feedback in public schema | Design | Feature requests from tenant UI → public.feedback. |

#### 4.6 Audit Trail (World-Class)

| Item | Status | Notes / Action |
|------|--------|----------------|
| Trigger-based logging | Gap | PostgreSQL triggers → tenant audit_log; INSERT-only. |
| Immutable audit_log | Gap | DB permissions. |
| Who/What/Where/When/Why + correlation_id | Partial | Extend app-level audit; session context. |
| Cryptographic chaining (optional) | Gap | Per blueprint. |
| Retention + cold storage | Partial | Document; retention policy. |
| PII masking in audit | Gap | Never log passwords, card last-4, or full PII in old_values/new_values. |
| Real-time alerts (global/super-admin changes) | Gap | Webhook or alert to security team for global-setting or super-admin account changes. |

#### 4.7 Compliance, Security, GSOC

| Item | Status | Notes / Action |
|------|--------|----------------|
| GESS/GEPS, data residency | Partial | regional_cluster; pin tenant to region; document. |
| PODs (Privacy Obligation Documents) | Gap | Provide tenants with **automated PODs** that prove compliance with local privacy laws (e.g. FERPA, LGPD); add to roadmap. |
| Impossible travel, bulk export detection | Partial | ImpossibleTravelMiddleware; enhance + alert. |
| Super-admin toggle center | Partial | Build out (grid, Redis Pub/Sub, audit). |
| Staging/sandbox schema per tenant | Gap | Optional; clone prod → tenant_staging "View in Sandbox." |

#### 4.8 Communication, Orchestration, UI

| Item | Status | Notes / Action |
|------|--------|----------------|
| Workflow Designer (trigger–action–condition, channels) | Gap | Part 2c; CommunicationWorkflow + UI. |
| Communication templates library | Partial | Localized templates pickable by school. |
| Progressive disclosure, one thing per page | Partial | Stepper, defaults. |
| Command K / global search | Partial | Document; enhance if needed. |
| Three platform layers | Doc | **Marketing Engine** (internet-facing site, hero, demo, trust signals); **Superadmin / Ecosystem Controller** (global health, tenant lifecycle, financial command, shadow support); **Tenant / White-Label Views** (school command center, localized workflows, tenant autonomy hub). Document and implement per blueprint. |

#### 4.9 Financial (World-Class)

| Item | Status | Notes / Action |
|------|--------|----------------|
| Double-entry, no delete (void only) | Partial | Design and implement where missing. |
| Multi-currency, FX, DCC | Partial | Exchange rates; 195-country payment strategy. |
| Triple-match reconciliation | Gap | Per blueprint. |
| Tax (VAT/GST/nexus, FATCA, GloBE) | Gap | Document; integrate tax API; nexus tracking; FATCA/GloBE reporting where required. |
| Transparency (total price upfront, "junk fee" guardrails) | Gap | Per consumer-protection standards. |
| Sanctions/AML screening (cross-border payments) | Gap | Real-time screening; KYC where required. |

#### 4.10 Other Blueprint Areas

- **Legacy Import Wizard:** AI-driven mapping, validation, dry-run, rollback — add to roadmap. **4-phase migration:** (1) Discovery & Audit (deep-clean, identify junk/archive data), (2) Mapping & Transformation (standardized APIs, regional grading/currency conversion), (3) Pilot (subset into sandbox schema; validate with staff), (4) Big Bang (full migration in low-activity window; zero-downtime rollback in under 60s if checksum fails). **Dry-run report format:** Total Records Processed, Successfully Mapped, Duplicates Blocked, Missing Critical Fields, Schema Integrity Check; **checksum verification** (e.g. SHA-256) so live migration can be verified against dry-run; human-in-the-loop for records with missing critical fields. **Idempotent importer:** safe to re-run without duplicating records.
- **10-school test matrix:** Use synthetic data for **10 schools in 10 countries** (e.g. JP-01 Aoyama, UAE-02 Al-Hikmah, BR-03 São Paulo, IN-04 Green Valley, UK-05 St. Andrews, NG-06 Lagos, DE-07 Berlin, SG-08 Singapore, AU-09 Ozzie, US-10 Liberty) with distinct curricula, school weeks, and currencies to validate universal schema and migration.
- **Interoperability / Developer Portal:** LTI 1.3, OneRoster, webhooks, versioned APIs — document and implement in phases.
- **Testing:** Synthetic data (10 schools, 10 countries), migration dry-run test — add.
- **Crisis & DR:** Hot-standby, immutable backups, crisis schooling "flip" — document and implement.
- **Accreditation & Evidence:** ComplianceStandard, Evidence Harvester, Inspector Portal — add to roadmap.
- **Research Hub (anonymized):** Differential privacy, federated analytics — optional; document.

#### 4.11 Marketing Page & Public-Facing Site (What Visitors See Online)

The **internet-facing marketing page** (runmycampus.com / base domain) must be audited and aligned with the full design so every section is covered and conversion/trust are world-class. **Codebase refs:** [apps/schools/marketing_views.py](apps/schools/marketing_views.py), [templates/schools/marketing_landing.html](templates/schools/marketing_landing.html), [config/public_urls.py](config/public_urls.py), [docs/MARKETING_PUBLIC_SURFACE_BACKLOG.md](docs/MARKETING_PUBLIC_SURFACE_BACKLOG.md).

| Section (from public site) | Current state | Action |
|----------------------------|---------------|--------|
| **Header / Nav** | Product, Solutions, Pricing, Compare, Case Studies, Security, Integrations, Book Demo; regional (e.g. /cm/, /ca/) | Add **About**, **Features**, **Blog**, **Contact Us** to nav; ensure **Request a Demo** and **Login** / **Find your school** are prominent. |
| **Hero** | Headline, subheadline, CTAs (Start free trial, Self-guided tour, Find your school, Login), Global platform map, authority metrics | Align copy with "Global School Operations for Global [Schools]" and one-stop solution; add explicit **Global features** list: Multi-Language, Multi-Currency, Timezone, Country-Specific Grading, Localized Holiday Calendars, Data Residency, AI-Powered Insights, Customizable Workflows, Scalable Architecture, 24/7 Global Support. |
| **Post-enrollment revenue** | Not present as a section | Add section: **School Events** (Event Ticketing, Venue Management, Sponsor Engagement), **Online Courses** (Course Creation, Student Tracking, Certification), **Alumni Network** (Mentorship Programs, Fundraising Campaigns, Career Services). Plan product modules for Events (ticketing/venue) and public-facing **Online Courses / LMS for revenue** (distinct from internal curriculum). |
| **Easy search / Announcement** | School finder bento on landing | If design shows an "Announcement here" / search bar, implement as **feature showcase** or **interactive demo snippet**; document whether it is in-app preview or marketing-only. |
| **Three key features** | Proof points and segments in context | Add explicit **AI Co-pilot**, **Real-time Analytics**, **Customizable Workflows** cards with "Learn more" and link to product/solutions. |
| **Admissions and enrollment** | Admissions funnel section and admissions_flow in context | Align with **Online Applications** (Customizable Forms, Document Upload, Progress Tracking), **Applicant Tracking** (Status Updates, Communication Tools, Interview Scheduling), **Enrollment Management** (Offer Letters, Deposit Payments, Student Onboarding). Ensure copy and CTAs match. |
| **What you get (benefits)** | Trust strip, proof points, trust_controls | Add/expand: **Data Security** (End-to-End Encryption, GDPR Compliance, Regular Security Audits, Data Backup & Recovery), **24/7 Support** (Dedicated Account Manager, Live Chat & Email, Knowledge Base, On-demand Training), **Customizable Branding** (Logo & Color, Custom Domains, Themed Dashboards, Personalized Communications). |
| **Pricing That Speaks Your Language** | pricing_snapshot, /pricing/ page | Ensure **Basic, Premium, Enterprise** (or equivalent) tiers with "Flexible pricing, no hidden fees" and localized pricing where applicable. |
| **Compliance and data security** | trust_controls, /security-compliance/ | Align section with **GDPR & Data Privacy** (Consent, Data Subject Rights, Encryption, Privacy by Design), **Accreditation Support** (Evidence Management, Audit Trails, Reporting, Customizable Frameworks), **Security & Access Control** (RBAC, MFA, Audit Logs, Penetration Testing). |
| **How the platform scales globally** | rollout_steps, "Three clear phases" | Align with **Global Infrastructure** (geographically distributed, low latency, high availability), **Local Regulations** (country-specific standards, calendars, grading), **Open Architecture** (modular, third-party integrations, custom development). |
| **Topics of leading faculties / Blog** | Topical landing clusters (solutions by topic); no blog | Add **Blog / News** module ("Topics of leading faculties"): content cards with titles/source; power via **Headless CMS** (e.g. Strapi, Contentful, or DB-backed) for marketing team to update without code. |
| **Final CTA + Footer** | close-cta section; Book a demo, Start onboarding | Ensure **Privacy Policy** and **Terms of Service** links in footer; "Made with ❤️ by RunMyCampus" and copyright. |

**Additional items (from codebase + suggestions — all part of the plan):**

- **School Discovery & Tenant Login Workflow:** Document and audit the **Find your school** flow: user on base domain → /discover/ or /find/ → email or search → redirect to tenant subdomain (e.g. school.runmycampus.com) for login. Ensure no broken links and clear UX. [apps/schools/section8_views.py](apps/schools/section8_views.py) (global_login_discovery, find_school).
- **Marketing CMS:** Implement a **Headless CMS** or DB-driven content layer for marketing copy, pricing text, blog posts, and case studies so marketing can update without developer deployment. Add to roadmap.
- **Marketing Analytics & A/B Testing:** Add **Marketing Analytics** (e.g. Google Analytics, Hotjar, or privacy-preserving alternative) and **A/B testing** for hero copy, CTA order, and conversion funnels (visit → discovery → signup → activation). Per [docs/MARKETING_PUBLIC_SURFACE_BACKLOG.md](docs/MARKETING_PUBLIC_SURFACE_BACKLOG.md) Wave 4.
- **Public API Gateway / Developer Portal:** The marketing page states "Open Architecture" and "seamless integration with third-party tools." Add **Public API design and documentation** (auth, rate limiting, versioned endpoints) and **Developer Portal** so partners and schools can build integrations; align with Interoperability (4.10).
- **Marketing Demo Environment:** Optional but recommended: a **read-only interactive demo** on the marketing site (e.g. "Try it now" sandbox) so visitors can experience key flows without signing up; separate from tenant staging. Add to roadmap.
- **Post-enrollment revenue modules (product):** Plan **School Event Management** (ticketing, venue, sponsors) and **Online Courses (LMS)** for external/revenue courses (creation, tracking, certification), and **Alumni & Endowment** (mentorship, fundraising CRM), as product modules; link from marketing copy to roadmap.

**Deep-dive:** Include **public marketing routes and templates** in the "everything inventory" (Part 5): list all marketing views, templates, and nav items; check i18n, WCAG, and mobile on marketing pages; record in REPORTS/AUDIT_LOG.md.

---

## Part 4: Prioritized Action List (13 Items)

1. **Config:** Document and enforce schema-per-tenant; implement OnboardingService and Master Table List; add migration runner for all tenant schemas.
2. **Settings/region:** Add "School location" (country + region) with RegionConfig/Province dropdowns; deprecate or sync SiteSettings.country/region.
3. **Module vs feature center:** Document in FEATURE_GATE_AND_MODULES or SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING.
4. **Region coverage:** Run seed_global_regions at deploy; add verify_region_coverage; document pycountry.
5. **Branding:** Document site vs tenant branding.
6. **Education systems:** Keep RegionConfig + EducationSystemProfile; seed and expose in region UI.
7. **Forms:** Catalog-backed dropdowns + optional "Other" for country, region, grading, language.
8. **Admission number:** Configurable generation (strategies or template); keep pattern validation.
9. **Dashboard catalog:** Add DashboardTemplate and TenantLayoutAssignment; "Configuration Hub" for role-based dashboard selection.
10. **Workflow catalog:** Add WorkflowTemplate/FlowRegistry and TenantWorkflow; Workflow Command Center / Flow Gallery; execution engine for trigger–action–condition.
11. **Audit:** Trigger-based, immutable audit_log per tenant schema; Who/What/Where/When/Why.
12. **Deep-dive:** Create REPORTS/AUDIT_LOG.md; run automated checks; map modules/workflows.
13. **Marketing page & public site:** Audit and align the internet-facing marketing page with the full design (4.11): all sections (hero, post-enrollment revenue, three key features, admissions, benefits, pricing, compliance, scaling, blog, footer); add nav (About, Features, Blog, Contact); School Discovery workflow; plan Marketing CMS, analytics/A/B, Public API/Developer Portal, and marketing demo; add post-enrollment revenue modules (Events, Online Courses, Alumni) to product roadmap.

---

## Part 5: Deep-Dive Execution (Step-by-Step)

Use this to run a deep-dive on every module, feature, workflow, job, page, script, and tool so the codebase meets world-class standards.

1. **Single audit artifact:** Create and maintain **REPORTS/AUDIT_LOG.md** with sections: (1) Queries missing **schema scope** (tenant-scoped queries not running in correct schema; we use schema-per-tenant, not tenant_id/RLS for isolation), (2) Hardcoded strings (i18n), (3) API endpoints without rate limiting, (4) Background scripts/jobs (idempotency, error handling, tenant context), (5) Security scan results, (6) Accessibility (WCAG) and mobile, (7) **Clean Architecture & SOLID** (e.g. domain/application/infrastructure separation, dependency rule, SOLID principles — list violations).
2. **Core infrastructure audit:** Verify data isolation (**schema-per-tenant** — every tenant query uses correct schema/search_path; no reliance on tenant_id for isolation); i18n (locale, date/currency, RTL); performance/noisy-neighbor (metrics, per-tenant/queue limits). Record in REPORTS/AUDIT_LOG.md.
3. **Module and workflow mapping:** For each app, list pages/views, workflows, and jobs; cross-check FEATURE_GATE_PATH_MAP and feature registry. Produce a module/workflow map; link from audit log.
4. **Everything inventory:** List key pages/tools (WCAG/mobile status); full list of scripts/jobs with idempotency and tenant context; security tooling in CI. **Include public marketing site:** all marketing views ([apps/schools/marketing_views.py](apps/schools/marketing_views.py)), templates (marketing_landing.html, marketing_page.html, etc.), and public routes ([config/public_urls.py](config/public_urls.py)); check i18n and accessibility on marketing pages. Keep in audit log.
5. **Tenant autonomy and feedback:** Confirm feature flags allow "flip without deploy"; ensure Feedback/Feature Request tagged by region/module and visible in roadmap (Planned/In Development/Released).
6. **Automate checks:** Run the following **Cursor audit prompt** (Django: use `apps/` and `config/`; no `src/`). Output → REPORTS/AUDIT_LOG.md.

   **Exact Cursor prompt:** *"Perform a Technical Audit of the entire apps/ and config/ directories. We use **schema-per-tenant**: isolation is by PostgreSQL schema (search_path), not by tenant_id. Create a REPORTS/AUDIT_LOG.md that lists: (1) Any tenant-scoped database query that does not run in the correct tenant schema (e.g. missing or wrong search_path/schema context), or any shared-app query that accesses tenant data without schema scope. (2) Hardcoded strings that are not using the i18n translation library (gettext/trans). (3) Any API endpoint lacking rate-limiting. (4) A list of all background scripts (Celery tasks, management commands) and their error-handling and idempotency status. Ensure the code meets Clean Architecture and SOLID principles — flag any violations (e.g. missing domain/application/infrastructure separation, SOLID breaches)."*

7. **Tie to existing docs:** Turn THREE_PLANS_EXECUTION_GUIDE, KEY_MODULES_REFERENCE, ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS, MODULE_AUDIT_AND_IMPROVEMENT_PLAN into checklist items in the audit log; add Blueprint alignment (each major blueprint area: In plan / In roadmap / Not yet).

8. **Day 1 / Master architecture (world-class baseline):** (1) **Master Control** — Public schema for tenant registry, auth, subscription. (2) **Tenant Provisioner** — OnboardingService creates schema and runs Master Table List per school. (3) **Schema-aware middleware** — Subdomain/slug → set search_path to tenant schema for every request. (4) **Security Sentinel** — Immutable audit trail (trigger-based) in each tenant schema. (5) **Command Center UI** — Superadmin dashboard for health, toggles, and tenant lifecycle. Document as the "three-layer shield": Global Gateway (public), Isolated Tenant Fortress (per-schema), Intelligence/Analytics Mesh (de-identified aggregate).

---

## Part 6: World-Class Blueprint Index (Nothing Missed)

| Blueprint area | In plan / Roadmap | Notes |
|----------------|-------------------|--------|
| Schema-per-tenant, onboarding, master table list, migration runner | In plan (Part 0) | Locked in. |
| Country/region, module vs feature center, region coverage, branding, education systems, forms, admission number | In plan (Part 1, 4) | Q&A + actions. |
| Dashboard catalog | In plan (Part 2b, 4.9) | DashboardTemplate, TenantLayoutAssignment, Configuration Hub. |
| Workflow catalog | In plan (Part 2c, 4.10) | WorkflowTemplate/FlowRegistry, TenantWorkflow, Command Center, engine. |
| Full blueprint checklist (4.1–4.10) | In plan (Part 3.4) | Core infra, module mapping, audit, autonomy, schema specifics, audit trail, compliance/GSOC, communication, financial, other. |
| Deep-dive execution | In plan (Part 5) | 8-step process; REPORTS/AUDIT_LOG.md; Day 1 / Master architecture. |
| Trigger-based immutable audit trail | In plan (Part 4.11, 4.6) | Gap; action listed. |
| Feedback → product backlog | In plan (4.4) | Gap; tag by region/module, roadmap visibility. |
| Staging/sandbox schema | In plan (4.7) | Gap; optional. |
| Legacy import wizard | In plan (4.10) | Add to roadmap. |
| Interoperability (LTI, OneRoster, webhooks, developer portal) | In plan (4.10) | Document and implement in phases. |
| Testing (synthetic data, migration dry-run) | In plan (4.10) | Add. |
| Crisis & DR | In plan (4.10) | Document and implement. |
| Accreditation & evidence | In plan (4.10) | Add to roadmap. |
| Research hub (anonymized) | In plan (4.10) | Optional; document. |
| PODs (Privacy Obligation Documents) | In plan (4.7) | Gap; automated PODs per local law (FERPA, LGPD); add to roadmap. |
| Three platform layers (Marketing, Superadmin, Tenant) | In plan (4.8) | Marketing Engine; Superadmin/Ecosystem Controller; Tenant/White-Label Views — document and implement. |
| Marketing page & public site (full audit) | In plan (4.11, Part 4.13) | All sections from visitor-facing page; nav (About, Features, Blog, Contact); post-enrollment revenue, blog, footer; tie to MARKETING_PUBLIC_SURFACE_BACKLOG. |
| School discovery & tenant login workflow | In plan (4.11) | Find your school → /discover/, /find/ → tenant subdomain; document and audit. |
| Marketing CMS (headless / content layer) | In plan (4.11) | Content for marketing copy, blog, pricing; marketing team edits without deploy. |
| Marketing analytics & A/B testing | In plan (4.11) | Conversion funnels; A/B for hero and CTAs; per MARKETING_PUBLIC_SURFACE_BACKLOG Wave 4. |
| Public API gateway & Developer Portal | In plan (4.10, 4.11) | Open Architecture promise; auth, rate limits, versioned APIs; document. |
| Marketing demo environment (try-it sandbox) | In plan (4.11) | Optional; read-only interactive demo on marketing site. |
| Post-enrollment revenue (Events, Online Courses, Alumni) | In plan (4.11) | School Events (ticketing, venue, sponsors); Online Courses LMS; Alumni/Endowment; add to product roadmap. |
| Blog / News ("Topics of leading faculties") | In plan (4.11) | Blog module for marketing site; CMS-backed. |
| Clean Architecture & SOLID (audit criteria) | In plan (Part 3.1, 5) | REPORTS/AUDIT_LOG.md section; Cursor prompt includes "Clean Architecture and SOLID". |
| GSOC (God-View, threat detection, financial integrity) | In roadmap (brief) | Build out super-admin toggle; enhance impossible travel, bulk export. |
| Universal grading engine (GradingScales, formula builder, GPA) | In roadmap (brief) | Extend metadata-driven rubrics; tenant-configurable formula. |
| Intelligent timetable | Not yet | Blueprint: AI/constraint-solver; school-week by region. |
| Global payment gateway (195 currencies, DCC, local acquiring) | In plan (4.9) | Multi-currency, FX, DCC; document 195-country strategy. |
| Tax & compliance (VAT/GST, nexus, FATCA, GloBE) | In plan (4.9) | Gap; document; tax API. |
| Triple-match reconciliation | In plan (4.9) | Gap. |
| Global Talent & Verification Engine | Not yet | Blueprint: teacher verification, credentials, recruitment. |
| Student health & safety (transport, medical alerts, safe-dismissal) | Not yet | Blueprint: RFID, medical profiles, lockdown. |
| AI learning & curriculum mapping | Not yet | Blueprint: digital twin, mastery graph, cross-walk. |
| Unified communication & marketplace | Not yet | Blueprint: omnichannel, K-12 translation, store. |
| Predictive facility & resources | Not yet | Blueprint: digital twin, IoT, asset lifecycle. |
| Executive BI & growth dashboard | Not yet | Blueprint: A-ROI, predictive enrollment. |
| Crisis & DR (detailed) | Not yet | Blueprint: triple-lock, multi-region, crisis schooling. |
| AI professional development | Not yet | Blueprint: virtual coach, PD pathways. |
| 100-year records & archiving | Not yet | Blueprint: decentralized storage, W3C VCs. |
| UI/UX (GSOC God-View, Command K, role layers) | Not yet | Blueprint: God-View UI, marketing/superadmin/tenant. |
| Widget library (Triple-A, Global Pulse, At-Risk Sentinel) | Not yet | Blueprint: adaptive widgets. |
| Pricing & subscription engine | Not yet | Blueprint: tiered, tax nexus, ASC 606. |
| Simplicity & workflows (one thing per page, progressive disclosure) | Not yet | Blueprint: role-specific simple workflows. |
| Zero-friction admission (5-min journey, magic link, OCR) | Not yet | Blueprint: identity spark, document snap, one-tap pay. |
| Teacher command center | Not yet | Blueprint: 10-min day, visual seating, AI inbox. |
| Equity & accessibility (low-bandwidth, neuro-diverse) | Not yet | Blueprint: adaptive UI, offline vault. |
| Legal & regulatory sentinel | Not yet | Blueprint: data residency shift, purge engine, whistleblower. |
| Library & digital assets | Not yet | Blueprint: resource sharing, DRM. |
| Alumni & endowment | Not yet | Blueprint: alumni network, fundraising CRM. |
| Migration engine (4-phase, dry-run, checksum) | In plan (4.10) | Discovery, Mapping, Pilot, Big Bang; idempotent; rollback under 60s. |
| Launch command center | Not yet | Blueprint: mass provisioning, war room. |
| Preview & feature toggles | Not yet | Blueprint: staging-as-a-service, canary. |
| Super-admin toggle center (grid, health pulse) | Not yet | Blueprint: full UI spec. |
| Health & service (AIOps, RCA, workflow designer) | Not yet | Blueprint: tenant vitality, service desk. |
| Strategic forecasting (5-year oracle) | Not yet | Blueprint: Monte Carlo, what-if. |
| Accreditation (continuous, evidence harvester) | Not yet | Blueprint: compliance sentinel, inspector portal. |
| Research hub (detailed, differential privacy) | Not yet | Blueprint: federated query, insights sandbox. |
| Master architecture & tech stack (three-layer shield) | In plan (Part 5 step 8) | Gateway (public), Tenant Fortress (per-schema), Intelligence Mesh; provisioner, middleware, sentinel, command UI. |
| Day 1 development checklist | In plan (Part 5 step 8) | Master Control, Tenant Provisioner, schema-aware middleware, Security Sentinel, Command Center UI. |

---

## Summary

- **Part 0:** Schema-per-tenant is the config (locked in). Document; build OnboardingService, Master Table List, migration runner. **Isolation = schema only;** optional RLS only as defense-in-depth.
- **Part 1:** Country/region → RegionConfig picker; module vs feature center documented; region coverage via seed + verify; branding = SiteSettings vs School + BrandSettings; education systems in RegionConfig + EducationSystemProfile; forms → catalog dropdowns + "Other"; admission number → configurable generation.
- **Part 2:** Strengths (multi-tenancy, **schema-per-tenant**, region/i18n, features, audit, Celery, API, docs). Weaknesses (no DB audit triggers, partial i18n, UX gaps, cache keys, role normalization; schema-per-tenant locked in, onboarding/master list/migration runner still to build). **Part 2b:** Dashboard catalog (DashboardTemplate, TenantLayoutAssignment, Configuration Hub). **Part 2c:** Workflow catalog (WorkflowTemplate/FlowRegistry, TenantWorkflow, Command Center, engine).
- **Part 3:** Deep-dive (REPORTS/AUDIT_LOG.md, module/workflow mapping, automate checks, existing docs). Blueprint table. **3.3:** Schema-per-tenant locked in; complete via OnboardingService, master list, migration runner. **3.4:** Full blueprint checklist (4.1–4.11). **4.11:** Marketing page & public site — full audit of visitor-facing page (all sections, nav, post-enrollment revenue, blog, CMS, analytics, school discovery, Public API, demo).
- **Part 4:** 13-item prioritized action list (config through deep-dive; item 13 = marketing page & public site).
- **Part 5:** Deep-dive execution (8 steps); step 8 = Day 1 / Master architecture (three-layer shield, provisioner, middleware, sentinel, command UI).
- **Part 6:** World-class blueprint index (every area; In plan / In roadmap / Not yet).

This plan is the **single source of truth**. Nothing is missed; all blueprint areas are either in the plan or explicitly marked in the index for future phases.
