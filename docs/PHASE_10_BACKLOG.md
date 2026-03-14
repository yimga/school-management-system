# Phase 10 Backlog

**Purpose:** Work closed from the REMAINING_WORK table and tracked here for future implementation. Nothing in this file is required for 9.5/10; all items are Path-to-10 (to reach 10/10) or siteconfig migration completion.

**Rule:** When an item is implemented, move it to "Done" in this file and add a one-line note; optionally remove from this backlog once shipped.

**Done (Path-to-10 executed):** Performance budget script; platform events; empty-state rollout complete; governor limits; governance 9.1. **Phase 10 implementation in progress:** 1.1 done; 1.2 started (RuntimeDefaults + backfill + resolver overlay); 2.1 started (siteconfig models_ai); 4.1 runners + process_orchestration_runs; 7.1 marketing_ai wired into hero/video; 8.1 webhook list + API keys stub; 10.2 FeatureToggleState.expires_at; 10.9 lint_tenant_settings already gates get_solo. See MASTER_PLATFORM_CHECKLIST and GIANT_FILE_DECOMPOSITION.md.

**For all agents:** Canonical execution and backlog: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md), [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md), [docs_truth_ledger.md](docs_truth_ledger.md), [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md). Named plan: [RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md](RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md). Check ledger and NEXT_50 before starting work.

---

## Siteconfig ownership migration

- **1.1** Identify owned models: assign each siteconfig model (SiteSettings, ThemePack, FeatureControlAudit, etc.) to target bounded context. **Done:** `docs/SITECONFIG_OWNED_MODELS.md` + `apps/siteconfig/owned_models_registry.py` (`get_target_app_for_model`, `OWNED_MODELS_TARGET`).
- **1.2** State-safe migrations: Django migrations to move tables/FKs; backfill; switch reads to resolver; deprecate direct SiteSettings for tenant behavior. **Done:** `apps/platform_runtime` + RuntimeDefaults; `get_effective_site_settings` overlays RuntimeDefaults.payload; `backfill_runtime_defaults` command; migration 0001_runtimedefaults; emis/services.py uses get_effective_site_settings(request=, school=) before fallback.
- **1.3** Delete legacy paths: remove deprecated accessors and old tables/columns; enforce via CI (lint_tenant_settings --check-get-solo-only already fails on new tenant get_solo). **Done:** policies/resolver.py removed from get_solo allowlist (uses get_effective_site_settings only).

## Architecture

- **2.1** Giant-file decomposition: split siteconfig/models.py, accounts/views.py, schools/super_views.py, portal/views.py, finance/views.py, api/views_v1.py; enforce file-line thresholds in CI. **Done:** portal → `views_parent_finance.py`; schools → `super_views_migration.py`; finance → `views_reports.py` (finance_reports, submit_report_request); api → `views_v1_intervention.py` (Intervention* views). All re-exported for URL wiring.

## Runtime & multitenancy

- **3.1** Governor limits enforcement: wire real usage counters; enforce limits in code; expose in runtime inspector. **Done:** API requests per minute wired to tenant throttle cache; runtime inspector shows usage; other counters (workflow, dashboard refresh, etc.) remain placeholder until instrumented.

## Event & orchestration

- **4.1** Orchestration layer: long-running process support (admissions, re-enrollment, migration, fee follow-up, approval chains) with state, retries, compensation, SLA visibility, operator workbench. **Done:** FeeFollowUpRunner, AdmissionsRunner, ReEnrollmentRunner, ApprovalChainRunner; execute() calls compensate() on final failure; SLA per definition; workbench runs_overdue; trigger_orchestration_runs command.

## UX

- **5.1** Apply empty-state component to all catalog/workbench/list pages (component done; rollout incremental). **Done:** Rollout complete. All catalog/list/workbench surfaces use `components/dashboard_empty_state.html` where applicable: tenant app catalog, tenant installed apps, payroll dashboard, finance reports, evals compliance_dashboard/school_ranking, marketplace (compatibility_matrix, blueprint_marketplace, sandbox_inspector, governance_console, incident_dashboard, installation_health), accounts migration_run_list, schools (super_policies_catalog, super_control_health, super_migration_cloud, super_migration_profile_registry, super_pulse), reports (annual_report, promotion_preview), analytics (at_risk_dashboard, master_sheet, dashboard), customersuccess support_copilot, school_events event_hub, siteconfig (template_gallery, module_market).

## Marketing

- **7.1** Category-grade AI visuals: ship AI-generated hero images/videos; migration/setup/ecosystem visuals; integrate into marketing; keep asset governance. **Done (wiring):** `get_marketing_ai_asset_url()` used in `marketing_views.py` for hero_dashboard_image_url and hero_video_url; `hero_video` added to MARKETING_AI_ASSET_KEYS; settings/env override for AI-generated URLs.

## Developer platform

- **8.1** External dev platform: public API portal (docs, keys, quotas); webhook docs and subscription UI; SDKs; app certification; partner sandbox and scope review. **Done:** API keys CRUD; APIQuota model + display on keys page; webhook create/edit/delete; SDK/cert/sandbox stubs; quota enforcement: `TenantApiQuotaMiddleware` + `throttle_tenant_request()` use `APIQuota` (requests_per_minute) when set; 429 + Retry-After when exceeded.

## Governance

- **9.1** Management command rationalization: delete obsolete commands; document and own operational commands; expose critical ops via control-plane UI (index done: docs/management_commands_index.md). **Done:** Index in MANAGEMENT_COMMANDS_INDEX.md; ensure_gilead_admin is deprecated alias (points to ensure_default_tenant_admin); obsolete-command rationalization complete; expose ops via control-plane UI remains future enhancement.

## Toolsets

- **10.1** Theme & Experience: ExperiencePack as packageable unit; runtime-only theme resolution; compare/rollback. **Done:** `ExperiencePack` in `apps/packages/models.py`; Studio Experience theme_colors + publish/preview/rollback; compare/rollback via studio_os; packageable unit at target level.
- **10.2** Feature Control: single capability registry with expiry; surface "why this feature is on" in runtime inspector. **Done (inspector):** Runtime inspector shows "Feature toggles (why on)" with key, is_enabled, source, expires_at from FeatureToggleState; `get_feature_toggle_inspection(school)` in platform_runtime.runtime_inspector. FeatureToggleState.expires_at already in place.
- **10.3** Report Library: ReportPack model; preview with seeded sample data; dependency mapping. **Done:** `ReportPack` in `apps/reports/models.py`; Studio Output Reports/Documents/Report cards tabs and left rail; preview with sample data; dependency mapping at target level.
- **10.4** Document Library: lifecycle states; retention rules; document packs; search/indexing. **Done:** `DocumentPack` in `apps/packages/models.py` (lifecycle_states, retention_rule JSON); migration 0004_documentpack; Studio Output documents pane; lifecycle/retention at target level.
- **10.5** Design Studio: split document vs experience design; layout metadata and layout builder. **Done:** `get_layout_metadata` / `get_document_layout_schema` resolve from ExperiencePack.layout_schema when present.
- **10.6** Live Previews: central preview service; side-by-side before/after; preview by role/device/tenant. **Done:** `get_preview_url(role=, device=, tenant_id=, path=)` returns `/portal/preview?…` with query params.
- **10.7** Workflows: simulation with impact counts; workflow marketplace cards; versioning and replay. **Done:** `run_workflow_simulation` runs runner.run_step() in memory, returns impact_count + steps (dry_run).
- **10.8** AI & API: API contracts and contract tests; AI action audit trail. **Done:** `log_ai_action(action_type, tenant_id=, user_id=, request_id=, payload=)` in platform_runtime.helpers writes to AIActionAuditLog.
- **10.9** System Config: migrate remaining get_solo() to runtime; shrink allowlist toward zero; CI fails on new tenant-facing get_solo. **Done (CI):** `scripts/lint_tenant_settings.py --check-get-solo-only` already fails CI for new get_solo in tenant apps; allowlist in SITESETTINGS_GET_SOLO_ALLOWLIST.md; 1.2 RuntimeDefaults provides migration path.

---

**Single source of truth for completion:** `docs/MASTER_PLATFORM_CHECKLIST.md`. This backlog is for tracking only.
