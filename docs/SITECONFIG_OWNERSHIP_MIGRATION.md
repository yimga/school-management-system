# Siteconfig Ownership Migration (Phase 2)

**Goal:** Move database and behavioral ownership out of `siteconfig` into bounded contexts so tenant behavior is resolved from runtime, registries, and packs—not from a single giant settings domain.

**Status:** **Phase 5 (repository) COMPLETE** — behavioral truth is runtime-first; bounded-context surfaces + CI gates + inventory/`domain_ownership` alignment. **Remaining:** **Phase B** below — state-safe Django migrations to move columns/tables off `SiteSettings` incrementally (ordering in [RESOLVER_MIGRATE_DELETE_ORDERING.md](RESOLVER_MIGRATE_DELETE_ORDERING.md)); does not reopen Phase 5 ZIP closure in the SOT.

## Done

- Bounded-context shell apps: `brand_experience`, `platform_runtime`, `plans`, `registries`, `marketplace`, `policies` provide canonical import surfaces.
- CI gate: `lint_siteconfig_legacy_imports.py` blocks new direct imports from legacy `apps.siteconfig.models_*` domain wrappers.
- Live app/test imports cut over to brand, runtime, plans, registries, marketplace, policies where applicable.
- Six unused legacy `apps/siteconfig/models_*` compatibility shims deleted.
- §2.1 resolver migration: `evals/caching.py` — `SiteSettings.load()` replaced with `get_cached_site_settings(school=)`; `lint_tenant_settings.py` now flags `SiteSettings.load()` in tenant apps; `docs/domain_ownership.md` added; allowlist includes `platform_runtime/management/`.
- Optional get_solo shrink: `backfill_runtime_defaults` uses `get_platform_site_settings_record(create=True)` instead of `SiteSettings.get_solo()`; get_solo remains only in `platform_runtime/helpers` (see SITESETTINGS_GET_SOLO_ALLOWLIST).

## Remaining

1. **Identify owned models** — **Done (1.1).**
   **Concrete move (example):** `theme_pack` / `admin_theme_pack` — resolved via runtime branding (get_effective_site_settings → RuntimeDefaults/branding); tenant-facing reads already use get_effective_site_settings. Legacy path to delete after verification: direct SiteSettings.theme_pack in any non-allowlisted tenant view (lint_tenant_settings enforces).  
   Full assignment in `docs/SITECONFIG_OWNED_MODELS.md`; Python registry in `apps/siteconfig/owned_models_registry.py` (`get_target_app_for_model`, `OWNED_MODELS_TARGET`). Every siteconfig model (models.py, models_dashboard.py, models_workflow.py) has a target bounded context.

2. **State-safe migrations**  
   Create Django migrations that move tables or add FK to new app without breaking existing code: e.g. add `runtime.Defaults` and backfill from `SiteSettings`; switch reads to resolver; then deprecate direct `SiteSettings` for tenant behavior.

3. **Delete legacy paths**  
   After all call sites use new surfaces, remove deprecated accessors and, where applicable, old tables or columns. Enforce via CI (no new tenant-facing `get_solo()` except allowlisted path-to-10).

4. **Deprecation markers**  
   Mark legacy access paths with `# DEPRECATED: use apps.platform_runtime.helpers.get_effective_site_settings` (or equivalent) and target removal date.

**Rule:** No new tenant behavior may be sourced from `SiteSettings` or other siteconfig singletons; use runtime resolvers and bounded-context services. See `docs/SITESETTINGS_GET_SOLO_ALLOWLIST.md` and `scripts/lint_tenant_settings.py --report-allowlisted`. **Ordering (nothing left behind):** [RESOLVER_MIGRATE_DELETE_ORDERING.md](RESOLVER_MIGRATE_DELETE_ORDERING.md) — resolver first, then migrate, then delete; phases 1–3 checklist.

---

## Phase B: Shrink SiteSettings (explicit plan)

**Goal:** SiteSettings eventually contains only **safe platform defaults**; all behavioral and tenant-facing fields move to bounded contexts and are read via runtime resolvers.

### Stay in SiteSettings (safe platform defaults only)

| Field | Reason |
|-------|--------|
| `maintenance_mode` | Platform-wide operational toggle; no tenant override. |
| `cache_rankings_interval_minutes` | Platform cache tuning; already mirrored to RuntimeDefaults where tenant override is needed; singleton default is sufficient. |

These are the only fields that remain as **safe platform defaults** in the singleton. All other fields are classified in `apps/siteconfig/domain_ownership.py` (EXACT_FIELD_OWNERS, PREFIX_FIELD_OWNERS) and have a target owner (brand_experience, runtime_blueprints, policies_rules, global_registries, marketplace_integrations, reports, documents, preview_platform, etc.).

### To migrate (by owner)

- **brand_experience:** site_name, tagline, theme_pack, admin_theme_pack, primary_color, favicon, custom_css, meta_description, etc. → resolve via runtime/branding; ownership in brand_experience.
- **runtime_blueprints:** admin_portal_stats_config, default_widgets_per_role, school_code, admission_number_*, etc. → RuntimeDefaults or blueprint resolver.
- **policies_rules:** backend_feature_flags, portal_features, grade_approval_enabled, require_mfa_*, etc. → get_effective_flags / policies resolver.
- **global_registries:** country, region, ministry, default_region, default_grading_scale → registries/runtime.
- **marketplace_integrations:** sms_provider, sms_api_key, email_from_address, whatsapp_*, etc. → integration config; no secrets in tenant path.
- **reports / documents / preview_platform / delete:** per domain_ownership; migrate or deprecate.

Shrink is **incremental**: each field move = add column (or model) in bounded context → backfill → resolver consumes it → stop reading from SiteSettings for that field. Full field list and classification: `site_settings_usage_inventory.md` §2.1 and `domain_ownership.py`.

---

## Phase B batch progress (execution tracker)

**Single tracker for physical schema work.** Does **not** reopen Phase 5 ZIP (repository behavioral gate stays COMPLETE). Ordering: [RESOLVER_MIGRATE_DELETE_ORDERING.md](RESOLVER_MIGRATE_DELETE_ORDERING.md).

| Batch | Scope | Status | Evidence |
|-------|--------|--------|----------|
| **0** | Slim `SiteSettings` row; behavioral keys in `RuntimeDefaults.payload`; dual read/write via `SiteSettings.__getattr__` / `_persist_runtime_payload_updates`; tenant truth = `get_effective_site_settings` | **COMPLETE** | Migration `siteconfig.0162_phase_b_slim_sitesettings`; `apps/siteconfig/models.py`; `verify_phase_5_siteconfig.py` |
| **1** | **brand_experience** — first-class singleton for platform theme packs, branding media, report-style defaults | **COMPLETE** | Model `PlatformGlobalBranding` (`apps/brand_experience/platform_global_branding.py`); migration `brand_experience.0002_platform_global_branding` + data backfill; `branding_singleton_sync.py`; `get_effective_site_settings` merge in `platform_runtime.helpers`; `SiteSettings.save` sync; tests `apps/brand_experience/tests/test_platform_global_branding.py`; `verify_phase_b_execution.py` after migrate |
| **2** | **policies_rules / runtime_blueprints / global_registries / marketplace_integrations** — owned payload in `RuntimeDefaults` | **COMPLETE (repo scope)** | `SiteSettings.save` → `runtime_sync_owners` → `RuntimeDefaults.sync_from_site_settings` for all domains on full save; scoped sync on partial `update_fields`; resolver read order in `_build_platform_site_settings_base` |
| **3** | **Drop** mirrored `SiteSettings` columns now duplicated in `PlatformGlobalBranding` | **COMPLETE** | Migration `siteconfig.0163_phase_b_batch3_drop_sitesettings_branding_columns` (data copy to `PlatformGlobalBranding(pk=1)` then `RemoveField`); theme/report writes via `SiteSettings.apply_theme_experience_state` / PGB; `ThemeColorsForm` virtual `ModelChoiceField`s for dropped FKs; `verify_phase_5_siteconfig.py` asserts `0163` artifact. |
| **4** | **design_studio** — `PlatformPhaseBDomainSnapshot` row `domain=design_studio` | **COMPLETE** | Payload from `SiteSettings.owned_payload(owner="design_studio")`; merged in `_build_platform_site_settings_base` before PGB; sync on `SiteSettings.save`; migration `platform_runtime.0007` + seed |
| **5** | **documents** — snapshot row | **COMPLETE** | Same pattern as batch 4 |
| **6** | **global_registries** — snapshot row | **COMPLETE** | Same pattern |
| **7** | **marketplace_integrations** — snapshot row (excludes `sms_api_key` from JSON) | **COMPLETE** | Secrets stay off snapshot; write path remains `SiteSettings` |
| **8** | **metadata_governance** — snapshot row | **COMPLETE** | Prefix-classified keys in `domain_ownership` |
| **9** | **plans_entitlements** — snapshot row | **COMPLETE** | Same pattern |
| **10** | **preview_platform** — snapshot row | **COMPLETE** | Same pattern |
| **11** | **reports** — snapshot row | **COMPLETE** | Report-style IDs still also flow through branding singleton where applicable |
| **12** | **runtime_blueprints** — snapshot row | **COMPLETE** | Blueprints / portal defaults / admission fields owned slice |
| **13** | **policies_rules** — snapshot row (portal flags, MFA, grade approval toggles, etc.) | **COMPLETE** | Last merge order **within** the snapshot combine step; globally **`RuntimeDefaults.payload` overrides snapshot keys** when both set. `get_effective_policy` backfills from `get_effective_site_settings`; `invalidate_all_tenant_policy_caches` on snapshot sync when `POLICY_CACHE_TTL` is set |

**Optional product depth (not Phase B):** Full Report Platform SKUs, full config diff UI, full workflow simulation productization, and similar items live under **SOT §11.4** “optional cadence” and **§5.x** “when prioritized” notes.

**Verification:** `python scripts/verify_phase_5_siteconfig.py` (artifacts 0162 + 0163 + 0002 + `0007_platform_phase_b_domain_snapshots`); `python scripts/lint_phase_b_batch3_sitesettings_fk_writes.py` (no `site.save(update_fields=[...])` / `SiteSettings.objects.create(..., theme_pack=...)` for removed FKs); after DB migrate, `python scripts/verify_phase_b_execution.py`; `pre_deploy_gate.sh` runs these. Targeted tests: `apps.brand_experience.tests.test_platform_global_branding`, `apps.platform_runtime.tests.test_phase_b_domain_snapshots`.
