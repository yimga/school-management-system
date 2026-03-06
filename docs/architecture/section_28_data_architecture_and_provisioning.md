# Section 28 — Data Architecture and Provisioning

Phase 7: Single reference for tenant blueprint ownership, brand vs site, dashboard by role, workflow layers, app categories, module vs feature language, data architecture, external integrations, and schema provisioning.

---

## 28.1 — Tenant Blueprint ownership list

**The tenant (school) effectively “owns” or drives the following.** Sources: `School`, `SiteSettings` (when per-tenant), policy resolver `get_effective_policy(school)` / `get_tenant_blueprint(school)`, and tenant-scoped models.

| Ownership area | Where it lives | Notes |
|----------------|----------------|--------|
| **Identity** | School (name, slug, custom_domain, logo_url, primary_color, accent_color, etc.) | School model; branding fields. |
| **Institution metadata** | School, SiteSettings | Country, region, timezone, subdivision; name, type. |
| **Country/region** | School.country_code, default_region, subdivision; policy country_defaults | Resolver merges country into policy. |
| **Education levels** | Policy/blueprint, EducationLevelRegistry | Levels and terminology from blueprint/registry. |
| **Institution type(s)** | InstitutionTypeRegistry; policy | Tenant can have one or more types. |
| **Education system(s)** | EducationSystemRegistry; policy | Tenant systems (e.g. K–12, IB). |
| **Branding** | School (logo, colors), SiteSettings (theme pack, senders) | See 28.2 brand vs site. |
| **Dashboard/workflow assignments** | TenantLayoutAssignment (template per role), TenantWorkflow (active templates, overrides) | siteconfig.models_dashboard, models_workflow. |
| **Feature entitlements** | Plan + addons; School.features; FeatureToggleState; `can(school, code)` | apps.schools.models; billing. |
| **Policy overrides** | Policy bundle (tenant overrides); resolver merges platform ⊕ country ⊕ tenant | apps.policies.resolver. |
| **Numbering rules** | TenantAdmissionNumberPolicy; policy slice `admissions` | siteconfig; identifier_policy_service. |
| **Communication DNA** | SiteSettings (senders, channels); policy comms slice | Comms defaults and overrides. |
| **Compliance/retention** | Policy; TenantComplianceProfile (when present); AuditLog sensitivity | compliance, policies. |
| **Extension/app installations** | Marketplace AppInstallation, TenantInstalledApp (or equivalent) | marketplace; tenant-scoped app list. |

**Reference:** `docs/architecture/policy_injection.md`, `apps/policies/resolver.py` (`get_effective_policy`, `get_tenant_blueprint`), `docs/architecture/blueprint_registry_current_state.md`.

---

## 28.2 — Brand identity vs site experience (split)

**Clear split so product and UX can treat “brand” and “site” consistently.**

| Layer | Scope | Examples (where implemented or intended) |
|-------|--------|------------------------------------------|
| **Brand identity** | Name, logo, colors, typography, senders | School: name, logo_url, primary_color, accent_color. SiteSettings: theme pack, email/sms senders. Used for white-label, emails, PDFs, public-facing identity. |
| **Site experience** | Portal theme, dashboard family, density, nav, welcome, footer/header | Policy/context: portal theme key, dashboard template family (from TenantLayoutAssignment → DashboardTemplate), density (e.g. compact/comfortable), nav structure, welcome message, footer/header content. global_env / tenant_ctx in templates. |

**Implementation:** Brand fields on School and SiteSettings; site experience from `dashboard_resolver.for_role` (template + styling_overrides), policy (terminology, theme keys), and context processors. Document in UX/design system: “brand” = identity assets; “site” = layout, density, navigation, and portal chrome.

---

## 28.3 — Dashboard by role

**Roles that have (or will have) a dashboard family / template assignment.**

| Role | Code (TenantLayoutAssignment) | Dashboard family / notes |
|------|-------------------------------|---------------------------|
| Administrator | ADMIN | Backend admin dashboard; full widget set. |
| Leadership | LEADERSHIP | Executive/leadership view. |
| IT Admin | IT_ADMIN | IT-focused widgets. |
| Teacher | TEACHER | Classes, attendance, marks, lesson plans. |
| Student | STUDENT | Student portal dashboard. |
| Parent | PARENT | Parent portal; linked students. |
| Finance admin | — | Extend ROLE_CHOICES if needed; finance dashboard family. |
| Registrar | — | Extend ROLE_CHOICES if needed; registrar dashboard family. |
| Principal | — | Can map to LEADERSHIP or separate role. |
| Librarian | — | Extend ROLE_CHOICES if needed. |
| Transport manager | — | Extend ROLE_CHOICES if needed. |
| HR | — | Extend ROLE_CHOICES if needed. |
| Admissions officer | — | Extend ROLE_CHOICES if needed. |

**Current implementation:** `TenantLayoutAssignment.ROLE_CHOICES`: STUDENT, TEACHER, PARENT, ADMIN, LEADERSHIP, IT_ADMIN. Runtime: `dashboard_resolver.for_role(school, role)` → template + layout + theme. Additional roles (registrar, librarian, transport, HR, admissions, finance admin) are documented targets; add to ROLE_CHOICES and assign templates when those personas are onboarded.

**Reference:** `apps/siteconfig/models_dashboard.py` (TenantLayoutAssignment, DashboardTemplate), `apps/siteconfig/dashboard_resolver.py`, `docs/architecture/phase4_workflow_dashboard_hubs.md`.

---

## 28.4 — Workflow layers

**Three layers with clear guardrails.**

| Layer | Description | Implementation |
|-------|-------------|----------------|
| **Certified platform flows** | Built-in workflows (approval, form signature, automation) defined by WorkflowTemplate. | WorkflowTemplate (siteconfig.models_workflow); code and DB define triggers, conditions, actions. |
| **Tenant-selected variants** | Tenant activates/deactivates which templates are in use. | TenantWorkflow (school, template/code, is_active); workflow gallery: activate/deactivate, rollback (clear overrides). |
| **Tenant custom composition** | Tenant overrides (JSON) within guardrails — no arbitrary code. | TenantWorkflow.overrides; validation so tenants cannot break security, compliance, data integrity, financial posting, or audit. |

**Guardrails:** (1) Workflow definitions and approval chains from template + overrides only; no raw code from tenant. (2) Financial posting and audit events remain platform-controlled. (3) Validation on save (e.g. allowed keys, role IDs must exist). (4) Rollback clears overrides and reverts to template default.

**Reference:** `apps/siteconfig/models_workflow.py`, `apps/siteconfig/workflow_resolver.py`, `apps/siteconfig/workflow_engine.py`, `/siteconfig/workflow-gallery/`, `docs/architecture/phase4_workflow_dashboard_hubs.md`, `docs/architecture/phase7_deferred_rules_24_12_to_24_15.md`.

---

## 28.5 — App categories

**Documented categories for apps and extensions.**

| Category | Description | Examples |
|----------|-------------|----------|
| **Control / shared** | Platform and superadmin; shared schema; no tenant context. | Control plane UI, tenant list, billing console, blueprint registry admin, runbooks. |
| **Tenant-domain** | Tenant-scoped; run in tenant context (request.school / tenant schema). | Portal, evals, academics, people, finance, siteconfig (tenant settings), workflow/dashboard hubs. |
| **Platform support** | Shared services used by tenant-domain apps (APIs, jobs, search, messaging). | API Center, search API, Celery workers (with tenant context), notification delivery. |

Marketplace apps (Section 25.2) install into tenant-domain with permission scopes; control-plane can host “shared” apps that are not tenant-specific.

**Reference:** `docs/architecture/RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md` (Part F, ecosystem layer), Section 25.2, apps.txt / urls.txt.

---

## 28.6 — Module vs feature (consistent language)

**Definitions used platform-wide.**

| Term | Definition |
|------|------------|
| **Module** | A business capability area (bounded context). Examples: Admissions, Academics, Evals, Finance, People, Portal, Communication, Reports, Siteconfig. |
| **Feature** | A sub-capability or toggle within a module. Examples: “grade_approval”, “admission_number_editable”, “offline_mode”. Often exposed as a feature flag or policy key. |

**Usage:** Docs and code use “module” for the area (e.g. “Admissions module”); “feature” for the switch or sub-capability (e.g. `is_feature_enabled(school, "MODULE_EVALS")`, `can(school, "MODULE_X")`). Policy and blueprint use the same language so tenant config stays consistent.

---

## 28.7 — Data architecture

| Element | Specification | Current state |
|---------|---------------|---------------|
| **Public schema** | Tenants (Client), domains, users (shared auth), subscriptions, marketplace, blueprint registries, policy packs, feature flags, support/audit (control-plane). | RLS mode: single schema; schema-per-tenant: SHARED_APPS in public schema (e.g. customers, domains). See tenancy.md. |
| **Tenant schema** | tenant_&lt;slug&gt; or single schema with RLS; operational data (people, academics, finance, evals, portal, etc.). | django-tenants tenant schema or RLS-scoped tables; TenantDatabaseRouter for regional/dedicated DB. |
| **Append-only audit** | Audit logs append-only; queryable; exportable. | AuditLog (compliance.models_audit); create-only from app; query via admin/API. |
| **Object storage path** | `storage/<tenant-id-or-schema>/<module>/<entity>/<file>` (or tenant_uploads/…). | Documented in media_tenant_scope.md; _tenant_upload_to and tenant-prefixed callables; path pattern tenants/{school_id}/… or tenant_uploads/… . |
| **Search** | Control-plane index (de-identified) vs tenant-local / tenant-scoped. | GlobalSearchAPI filters by request.school (tenant-scoped); control-plane search separate. Section 25.3. |

**Reference:** `docs/architecture/tenancy.md`, `docs/architecture/media_tenant_scope.md`, `apps/compliance/models_audit.py`, `apps/api/search_api.py`.

---

## 28.8 — External integrations (drivers)

**Integration types as architectural drivers.** Policy/config picks defaults; health, failover, and fallback routing apply.

| Driver | Purpose | Current / planned |
|--------|---------|-------------------|
| **PaymentProvider** | Payments, invoices, refunds. | Finance models (Invoice, Payment); billing; external_reference. Provider abstraction can wrap Stripe/local gateways. |
| **MessagingProvider** | Email, SMS, push, WhatsApp, voice. | SiteSettings senders; comms module; fallback order (e.g. Push→WhatsApp→SMS→Voice) configurable per region/policy. |
| **LMSProvider** | LMS sync, course/grade export. | Integration config in siteconfig; LTI/OAuth (ExternalToolConfig, ServiceIntegration). |
| **GovtProvider** | Government returns, EMIS, reporting. | EMIS export; per-region defaults and reporting pipelines. |
| **IoTProvider** | Devices, attendance hardware, sensors. | Extension point; document when device integrations are added. |

**Health, failover, per-region:** Each driver should have health check, failover (e.g. secondary provider), and per-region default selection; policy or SiteSettings store active provider and region. Fallback routing (e.g. comms cascade) is configuration-driven.

**Reference:** `apps/siteconfig/models.py` (Integration, ExternalToolConfig, ServiceIntegration), `apps/finance`, `apps/communication`, `apps/emis`.

---

## 28.9 — Schema provisioning

| Requirement | Description | Current state |
|-------------|-------------|---------------|
| **Idempotent provisioning job** | Onboarding new tenant: create schema (or RLS scope), seed minimal data, set domains. Repeatable without duplicate work. | django-tenants create_tenant/create_schema; RLS mode: no schema create. Idempotent onboarding script or management command to be documented/standardized. |
| **Schema patch system for app installs** | Installing a marketplace app may add tables/columns; apply via versioned schema patches, not ad-hoc migrations. | Schema patches for app installs: document pattern (e.g. THIRD_PARTY_SCHEMA_PATCH_ALLOWLIST, versioned migrations in app bundle). |
| **Tenant-aware migration strategy with versioning** | Migrations run per tenant or once in RLS; version tracked; no cross-tenant locks. | Django migrations; django-tenants run migrations per schema; document versioning and order (e.g. shared first, then tenant). |

**Reference:** `docs/architecture/phase7_deferred_rules_24_12_to_24_15.md` (optional env for schema patch allowlist), config/settings (TENANT_APPS, SHARED_APPS), migrations.txt.

---

## Checklist summary

| Id | Done when |
|----|-----------|
| 28.1 | Tenant Blueprint ownership list documented (this doc). |
| 28.2 | Brand vs site split documented (this doc). |
| 28.3 | Dashboard by role listed; ROLE_CHOICES + extension path (this doc). |
| 28.4 | Workflow layers and guardrails documented (this doc). |
| 28.5 | App categories documented (this doc). |
| 28.6 | Module vs feature language documented (this doc). |
| 28.7 | Data architecture (public/tenant, storage, search, audit) documented (this doc + tenancy, media_tenant_scope). |
| 28.8 | External integration drivers and health/failover/fallback documented (this doc). |
| 28.9 | Schema provisioning (idempotent job, schema patch, tenant-aware migrations) documented (this doc). |
