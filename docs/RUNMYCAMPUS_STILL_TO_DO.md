# RunMyCampus Blueprint — What's Still To Do

**Date:** 2026-03-05  
**Reference:** `RunMyCampus_Master_Blueprint_SINGLE.md` + `RUNMYCAMPUS_BLUEPRINT_VERIFICATION.md`

This document lists **remaining work** when comparing the plan to the current codebase. Items already done are in the verification doc; here we only list gaps and optional follow-ups.

---

## 1. Optional: More modules use Policy Registry only

**Status:** Done — reports, finance gateways, accounts, security_health, brand_registry read via `get_effective_policy(school)` (or policy registry). Optional refinements below.

| Location | Current use | Note |
|----------|-------------|------|
| `apps/reports/services.py` | Uses `get_effective_policy(school)` | Done |
| `apps/finance/gateways/registry.py` | Uses policy for payment gateways | Done |
| `apps/accounts/views.py` | Uses policy where needed | Done |
| `apps/accounts/security_health.py` | Uses policy for weights | Done |
| `apps/siteconfig/brand_registry.py` | Uses policy for branding | Done |
| `apps/schools/tasks.py` | Reads/writes `school.settings` (provisioning, profile) | Source of truth for provisioning; optional: read paths via policy where "behavior" |
| `apps/siteconfig/views.py` | `school.settings`, `school.features` | Feature Control **writes** to school; keep as writer; optional: read via policy for display |
| `apps/compliance/management/commands/*` | Read/write `school.settings` | Niche; optional refactor |

**Excluded (by design):**

- `apps/policies/resolver.py` — single place that **reads** school.settings/features to build policy.
- `apps/siteconfig/tenant_config.py`, `system_morph.py`, `signup_views.py` — **write** or **hydrate** school.settings/features (source of truth).
- `apps/schools/models.py` — `_has_feature_fallback` is the canonical implementation used by `is_feature_enabled`.
- Tests that assert on `school.settings` / `school.has_feature` (testing model/behavior).

---

## 2. Section 16 "Cursor Implementation" tasks

From the blueprint's Section 16 list (summary: see §8):

| # | Task | Status |
|---|------|--------|
| 1 | Audit the repository for multi-tenant risks | Partially done (tenancy guardrails, checks) |
| 2 | Implement TenantBlueprint models | **Partial** — behavior in resolver; no separate TenantBlueprint/CountryProfile/PolicyBundle tables |
| 3 | Build TenantContextService | **Done** — `TenantContext` + middleware + `get_effective_policy` |
| 4 | Refactor Admissions module | **Done** — Portal + other modules refactored to use policy |
| 5 | Introduce Workflow engine | **Done** — workflow_registry, WorkflowRunLog, workflow API; WorkflowConfig (academics) for JSON-driven wizards |
| 6 | Implement Dashboard registry | **Done** — get_tenant_dashboard_registry(), /siteconfig/api/dashboard-registry/ |
| 7 | Create Marketplace infrastructure | **Done** |

Optional follow-ups: explicit TenantBlueprint/CountryProfile/PolicyBundle tables (v2); further formalize workflow trigger/condition/action catalog if needed.

---

## 3. Architecture Map Pack (Blueprint E)

The blueprint asks for a **docs/architecture/** pack:

- `apps.txt` — list of Django apps
- `urls.txt` — URL map (e.g. `show_urls` or equivalent)
- `migrations.txt` — `showmigrations` output
- `models.png` — model graph (e.g. django-extensions + graphviz)
- `tenancy.md` — where tenant is set, schema switching, shared vs tenant tables, multi-DB routing
- `policy_injection.md` — where Policy Registry / tenant context is injected (middleware, context processors, services)
- `cache_keys.md` — tenant-scoped cache key audit (World Engine §8)

**Status:** Done. See `docs/architecture/README.md`. Optional: regenerate apps/urls/migrations and add `models.png` when needed.

---

## 4. Blueprint "D. What's likely NOT in your codebase" (high-level gaps)

| Gap | Blueprint description | Status in codebase |
|-----|-----------------------|--------------------|
| **Metadata engine** | Custom fields without DDL (JSONB or EAV); DynamicFieldDefinition / DynamicFieldValue style | **Done** — apps.metadata (DynamicFieldDefinition, DynamicFieldValue) |
| **State machines** | Admissions, billing, discipline as explicit state machines (versioned, tenant-configurable) | **Done** — apps.metadata (StateMachineDefinition, EntityState, state_machine.get_state/transition) |
| **Data residency / retention / consent** | Data classification, retention rules, consent registry, export/erasure workflows | **Done** — RetentionRule, ExportJob, EraseRequest; ConsentRecord/ConsentRequest in compliance |
| **Platform operations** | Backups, restore drills, per-tenant rate limits, multi-region | Rate limiting and observability exist; backup/restore and multi-region strategy are operational (see DEPLOYMENT_FULL, tenancy.md). |

Per §8 summary table; optional follow-ups (e.g. DataClass, Zone A/B/C) as needed.

---

## 5. Standards & Interoperability (Blueprint C)

- **OneRoster:** `apps/api/oneroster_views.py` exists (tenant-scoped, token auth). Present; full 1.2 or formal adapter package is optional.
- **LTI / Ed-Fi:** `apps/api/interop_stubs.py` and section8_views provide discovery/readiness and LTI launch/AGS/NRPS. Ed-Fi remains stub.

**Done:** Canonical model ⇄ standard adapters documented in `docs/interop/README.md` (OneRoster, LTI, Ed-Fi, syllabus mapping). Optional: extract adapters into `interop/oneroster/*`, `interop/lti/*`, `interop/edfi/*` for clarity.

---

## 6. Marketplace: schema patches on install

- **Blueprint:** "Apply schema patch via migration runner" on install.

**Done:** `run_schema_patches_for_installation()` in marketplace services; `install_app(..., run_schema_patches=True)` runs `migrate <app_label>` when manifest has `migrations_app` or `schema_patch_app`. See `docs/EVENT_OUTBOX_AND_MARKETPLACE.md`.

---

## 7. Optional / scale — **CACHING DONE**

- **Per-tenant policy caching:** **Done** — set `POLICY_CACHE_TTL` (seconds) in settings; `get_effective_policy(school)` is cached per school. Call `invalidate_policy_cache(school)` after updating settings/features. See `apps/policies/resolver` and `docs/architecture/policy_injection.md`.
- **Explicit TenantBlueprint / CountryProfile / PolicyBundle models** — behavior lives in resolver; optional for v2 if you want versioned, auditable policy rows in DB.

---

## 8. Summary table

| Area | Status |
|------|--------|
| More modules use policy only (reports, finance gateways, accounts, brand_registry) | **Done** |
| Workflow engine (Trigger/Condition/Action, tenant-configurable) | **Done** |
| Dashboard registry (formal tenant widget registration API) | **Done** |
| Architecture Map Pack (docs/architecture/) | **Done** |
| Metadata engine (custom fields without DDL) | **Done** (apps.metadata) |
| State machines (admissions, billing, discipline) | **Done** (apps.metadata) |
| Data governance (retention, consent, export/erasure) | **Done** (RetentionRule, ExportJob, EraseRequest + existing ConsentRecord) |
| Standards layer (OneRoster/LTI/Ed-Fi documented) | **Done** (docs/interop/README.md) |
| Schema patches on app install | **Done** |
| Per-tenant policy caching | **Done** (optional POLICY_CACHE_TTL) |

---

## 9. What is done (no action needed)

- Tenancy guardrails (TENANCY_MODE, apps/tenancy, checks, middleware, @tenant_task)
- Tenant Blueprint + Policy Registry (resolver, registry, context processor, feature gate)
- Event outbox + WebhookSubscription + WebhookDelivery
- Marketplace MVP (models, install/uninstall, ScopeGrant, AppBillingLedger, widget registry, schema patches on install)
- Refactored modules: Portal, siteconfig, reports, finance gateways, accounts, brand_registry (policy-only reads)
- Workflow engine (WorkflowTemplate, TenantWorkflow, WorkflowRunLog, workflow_registry, API)
- Dashboard registry API (get_tenant_dashboard_registry, /siteconfig/api/dashboard-registry/)
- Architecture Map Pack (docs/architecture/)
- Metadata engine (apps.metadata); State machines (apps.metadata); Data governance (RetentionRule, ExportJob, EraseRequest)
- Interop layer (docs/interop/README.md); Per-tenant policy caching (POLICY_CACHE_TTL, invalidate_policy_cache)
- Pattern doc and verification doc

Use this file as the single "still to do" list when planning the next sprints or Cursor sessions.
