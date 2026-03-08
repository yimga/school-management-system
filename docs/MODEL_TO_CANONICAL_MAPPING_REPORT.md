# RunMyCampus Model-to-Canonical Mapping Report

**Date:** 2026-03-08  
**Reference:** `RunMyCampus_Canonical_Data_Object_Map.md`, `RunMyCampus_Model_to_Canonical_Mapping_Audit_Prompt.md`

---

## Purpose

This report maps the current Django model inventory to the canonical object families defined in the Canonical Data Object Map. It identifies KEEP, MERGE, SPLIT, EXTRACT, legacy, and delete actions and lists missing canonical objects.

---

## PART 1 — Current Model Inventory

Grouped by domain (from codebase inspection and TENANT_APPS / SHARED_APPS):

### Tenancy / institution

- **customers:** `Client` (TenantMixin), `Domain` (DomainMixin) — core tenant/domain.
- **siteconfig:** `SiteSettings`, `School`, and related (branding, dashboard, workflow config) — mix of platform and tenant; singleton pattern.
- **schools:** School-related, provisioning, marketing — shared/platform.
- **policies:** `PolicyBundle`, `TenantBlueprint`, `BlueprintPack` — platform configuration.
- **registries:** Registry-style models — platform configuration.

### People / identity

- **accounts:** User, roles, permissions — shared (auth).
- **people:** (TENANT_APP) — students, staff, guardians, assignments; core tenant data.

### Admissions

- **people:** Applicant, application workflows (if present) — tenant.
- **siteconfig:** Admission config — mix.

### Academics

- **academics:** (TENANT_APP) — courses, sections, terms, syllabi, curriculum — tenant.

### Assessments / grades

- **evals:** (TENANT_APP) — grades, gradebooks, report cards — tenant.

### Attendance / behavior

- **academics / people:** Attendance, behavior (if present) — tenant.

### Finance

- **finance:** (TENANT_APP) — fees, invoices, payments, aid — tenant.

### Communication

- **communication:** (TENANT_APP) — messaging, notifications — tenant.

### Documents

- **siteconfig / portal:** Documents, templates — mix.
- **reports:** (TENANT_APP) — report definitions, publishing — tenant.

### Workflows

- **siteconfig / automation / requests:** Workflows, requests — mix of platform and tenant.

### Marketplace / apps

- **marketplace:** App catalog, installations, blueprint marketplace — platform.

### Platform configuration

- **siteconfig:** SiteSettings, branding, dashboard palettes, feature flags — singleton.
- **platform_runtime:** Runtime resolution from blueprint, policy, registry — no DB models; resolver only.
- **compliance:** Compliance and access control — shared.
- **billing:** Billing for platform (trials, plans) — shared.

### Analytics / observability

- **analytics:** (TENANT_APP) — tenant analytics.
- **observability:** SLO, health — platform.

### Migration

- **schools / tenancy:** Provisioning, tenant creation — platform.

**Classification:** Core (Client, Domain, people, academics, finance, evals, communication, reports); Support (accounts, compliance, billing); Transitional (SiteSettings as singleton); Duplicate/Legacy (to be identified per model in Part 2).

---

## PART 2 — Canonical Mapping Table (Summary)

| Current model / area      | Canonical target (from map)     | Confidence | Action                    | Reasoning |
|---------------------------|----------------------------------|------------|---------------------------|-----------|
| Client, Domain             | Tenant / Organization, Domain   | High       | KEEP                      | Aligns with canonical tenant/domain. |
| School (siteconfig)        | Tenant or Campus                | Medium     | KEEP BUT RENAME / SPLIT   | Clarify Tenant vs Campus; separate identity from campus/branch. |
| SiteSettings               | Control-plane + tenant defaults | Low        | SPLIT / EXTRACT           | Singleton; split into control-plane only vs tenant-runtime defaults; tenant behavior → runtime/blueprint. |
| people (Student, Staff…)   | Person, Role Assignment         | High       | KEEP; align to Person      | Person as identity root; roles and assignments. |
| academics                  | Course, Section, Term, etc.     | High       | KEEP                      | Aligns with canonical academic structure. |
| finance                    | Invoice, Payment, Fee           | High       | KEEP                      | Aligns with canonical finance. |
| evals                      | Assessment, Grade               | High       | KEEP                      | Aligns with canonical assessment/grades. |
| PolicyBundle, Blueprint    | Policy, Blueprint (config)      | High       | KEEP                      | Canonical configurable layers. |
| marketplace (App, Install) | App, App Installation           | High       | KEEP                      | Aligns with canonical marketplace. |
| SiteSettings (tenant use)  | Tenant runtime / blueprint      | Medium     | EXTRACT CONFIGURABLE      | Move tenant-facing fields to tenant_runtime compilation. |

Full mapping for every model requires file-by-file inspection; the above gives the direction. Single-school residue: SiteSettings singleton used for tenant behavior. Multi-tenant risk: tasks without tenant context; global fallbacks.

---

## PART 3 — Missing Canonical Objects

From the Canonical Data Object Map, the following need stronger or explicit form:

1. **Person** as stable identity root (may exist in people; ensure one canonical Person model).
2. **Campus** as first-class entity (separate from Tenant where multi-campus).
3. **Role Assignment** (explicit link Person–Role–Tenant/Campus).
4. **App Installation** with granted scopes (marketplace may have; verify).
5. **Migration Profile** (for migration cloud).
6. **Provider Registry Entry** (extensible integrations).
7. **Document Version / Generated Artifact** separation (if not clear).
8. **Custom Field Definition / Custom Field Value** (metadata/custom fields).
9. **Workflow Run** as canonical cross-module process object.
10. **Guardian–Student Link** normalization (if multiple link types).

---

## Refactor Plan (Ordered)

1. **High:** Classify and split SiteSettings; stop tenant-facing get_solo(); route to tenant_runtime.
2. **High:** Ensure all tenant-app tasks run with tenant context.
3. **Medium:** Rename/split School vs Tenant vs Campus per canonical map.
4. **Medium:** Align people models to Person + Role Assignment.
5. **Medium:** Add missing canonical objects (Migration Profile, Provider Registry Entry, Workflow Run) where needed.
6. **Lower:** Extract configurable behavior from models into registries/blueprints/policies; mark legacy and delete-later where identified.

---

## Persistence

This report is the persisted output of the Model-to-Canonical Mapping Audit. Use it with the Canonical Data Object Map for implementation. High-priority refactors should be implemented or backlogged with clear ownership; see `PLATFORM_AUDIT_REMEDIATION_BACKLOG.md`.
