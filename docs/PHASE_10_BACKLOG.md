# Phase 10 Backlog

**Purpose:** Work closed from the REMAINING_WORK table and tracked here for future implementation. Nothing in this file is required for 9.5/10; all items are Path-to-10 (to reach 10/10) or siteconfig migration completion.

**Rule:** When an item is implemented, move it to "Done" in this file and add a one-line note; optionally remove from this backlog once shipped.

**Done (Path-to-10 executed):** Performance budget script; platform events; empty-state rollout complete; governor limits; governance 9.1. **Phase 10 implementation in progress:** 1.1 done; 1.2 started (RuntimeDefaults + backfill + resolver overlay); 2.1 started (siteconfig models_ai); 4.1 runners + process_orchestration_runs; 7.1 marketing_ai wired into hero/video; 8.1 webhook list + API keys stub; 10.2 FeatureToggleState.expires_at; 10.9 lint_tenant_settings already gates get_solo. See MASTER_PLATFORM_CHECKLIST and GIANT_FILE_DECOMPOSITION.md.

---

## Siteconfig ownership migration

- **1.1** Identify owned models: assign each siteconfig model (SiteSettings, ThemePack, FeatureControlAudit, etc.) to target bounded context. **Done:** `docs/SITECONFIG_OWNED_MODELS.md` + `apps/siteconfig/owned_models_registry.py` (`get_target_app_for_model`, `OWNED_MODELS_TARGET`).
- **1.2** State-safe migrations: Django migrations to move tables/FKs; backfill; switch reads to resolver; deprecate direct SiteSettings for tenant behavior. **Started:** `apps/platform_runtime` app + `RuntimeDefaults` model; `get_effective_site_settings` overlays RuntimeDefaults.payload when present; `backfill_runtime_defaults` command; migration 0001_runtimedefaults.
- **1.3** Delete legacy paths: remove deprecated accessors and old tables/columns; enforce via CI (lint_tenant_settings --check-get-solo-only already fails on new tenant get_solo).

## Architecture

- **2.1** Giant-file decomposition: split siteconfig/models.py, accounts/views.py, schools/super_views.py, portal/views.py, finance/views.py, api/views_v1.py; enforce file-line thresholds in CI. **Started:** siteconfig AI → `models_ai.py`; accounts migration hub → `views_migration.py`, rollover → `views_rollover.py` (re-exported from `views.py`); schools migration/sync-repair → `super_views_migration.py` (re-exported from `super_views.py`). Remaining: portal/views, finance/views, api/views_v1.

## Runtime & multitenancy

- **3.1** Governor limits enforcement: wire real usage counters; enforce limits in code; expose in runtime inspector. **Done:** API requests per minute wired to tenant throttle cache; runtime inspector shows usage; other counters (workflow, dashboard refresh, etc.) remain placeholder until instrumented.

## Event & orchestration

- **4.1** Orchestration layer: long-running process support (admissions, re-enrollment, migration, fee follow-up, approval chains) with state, retries, compensation, SLA visibility, operator workbench. **Started:** `apps/orchestration` app with `ProcessDefinition`, `OrchestrationRun` models; operator workbench at `/super/orchestration/`; admin registered.

## UX

- **5.1** Apply empty-state component to all catalog/workbench/list pages (component done; rollout incremental). **Done:** Rollout complete. All catalog/list/workbench surfaces use `components/dashboard_empty_state.html` where applicable: tenant app catalog, tenant installed apps, payroll dashboard, finance reports, evals compliance_dashboard/school_ranking, marketplace (compatibility_matrix, blueprint_marketplace, sandbox_inspector, governance_console, incident_dashboard, installation_health), accounts migration_run_list, schools (super_policies_catalog, super_control_health, super_migration_cloud, super_migration_profile_registry, super_pulse), reports (annual_report, promotion_preview), analytics (at_risk_dashboard, master_sheet, dashboard), customersuccess support_copilot, school_events event_hub, siteconfig (template_gallery, module_market).

## Marketing

- **7.1** Category-grade AI visuals: ship AI-generated hero images/videos; migration/setup/ecosystem visuals; integrate into marketing; keep asset governance. **Done (wiring):** `get_marketing_ai_asset_url()` used in `marketing_views.py` for hero_dashboard_image_url and hero_video_url; `hero_video` added to MARKETING_AI_ASSET_KEYS; settings/env override for AI-generated URLs.

## Developer platform

- **8.1** External dev platform: public API portal (docs, keys, quotas); webhook docs and subscription UI; SDKs; app certification; partner sandbox and scope review. **Done (UI + keys CRUD):** API portal docs (`/api-center/docs/`), webhook docs with subscription list (`/api-center/webhooks/`), API keys list/create/revoke (`/api-center/keys/`) with `APIKey` model (tenant-scoped, prefix + hash, one-time secret display); apicenter views and templates. Remaining: quotas display/enforcement, webhook create/edit subscription UI, SDK/cert/sandbox stubs.

## Governance

- **9.1** Management command rationalization: delete obsolete commands; document and own operational commands; expose critical ops via control-plane UI (index done: docs/management_commands_index.md). **Done:** Index in MANAGEMENT_COMMANDS_INDEX.md; ensure_gilead_admin is deprecated alias (points to ensure_default_tenant_admin); obsolete-command rationalization complete; expose ops via control-plane UI remains future enhancement.

## Toolsets

- **10.1** Theme & Experience: ExperiencePack as packageable unit; runtime-only theme resolution; compare/rollback. **Started:** `ExperiencePack` model in `apps/packages/models.py`.
- **10.2** Feature Control: single capability registry with expiry; surface "why this feature is on" in runtime inspector. **Done (inspector):** Runtime inspector shows "Feature toggles (why on)" with key, is_enabled, source, expires_at from FeatureToggleState; `get_feature_toggle_inspection(school)` in platform_runtime.runtime_inspector. FeatureToggleState.expires_at already in place.
- **10.3** Report Library: ReportPack model; preview with seeded sample data; dependency mapping. **Started:** `ReportPack` model in `apps/reports/models.py`.
- **10.4** Document Library: lifecycle states; retention rules; document packs; search/indexing. **Started:** `DocumentPack` model in `apps/packages/models.py` (lifecycle_states, retention_rule JSON); migration 0004_documentpack.
- **10.5** Design Studio: split document vs experience design; layout metadata and layout builder. **Started:** `apps/brand_experience/design_studio.py` stub (`get_layout_metadata`, `get_document_layout_schema`).
- **10.6** Live Previews: central preview service; side-by-side before/after; preview by role/device/tenant. **Started:** `apps/platform_runtime/live_preview.py` stub (`get_preview_url`).
- **10.7** Workflows: simulation with impact counts; workflow marketplace cards; versioning and replay. **Started:** `run_workflow_simulation(definition_code, payload, school)` in `apps/orchestration/runners.py` (returns impact_count/steps stub).
- **10.8** AI & API: API contracts and contract tests; AI action audit trail. **Started:** `AIActionAuditLog` model in `apps/platform_runtime/models.py`; migration 0002_aiactionauditlog.
- **10.9** System Config: migrate remaining get_solo() to runtime; shrink allowlist toward zero; CI fails on new tenant-facing get_solo. **Done (CI):** `scripts/lint_tenant_settings.py --check-get-solo-only` already fails CI for new get_solo in tenant apps; allowlist in SITESETTINGS_GET_SOLO_ALLOWLIST.md; 1.2 RuntimeDefaults provides migration path.

---

**Single source of truth for completion:** `docs/MASTER_PLATFORM_CHECKLIST.md`. This backlog is for tracking only.
