# Siteconfig Ownership Migration (Phase 2)

**Goal:** Move database and behavioral ownership out of `siteconfig` into bounded contexts so tenant behavior is resolved from runtime, registries, and packs—not from a single giant settings domain.

**Status:** **Phase 5 (repository) COMPLETE** — behavioral truth is runtime-first; bounded-context surfaces + CI gates + inventory/`domain_ownership` alignment. **Phase B batches 0–13 (schema / snapshots) COMPLETE** in this repository — see the batch table below; migration artifacts are enforced by `scripts/verify_phase_5_siteconfig.py` (part of `scripts/verify_cursor_phase6_siteconfig_sitesettings.py`). **After migrate**, run `scripts/verify_phase_b_execution.py` on the target database. First-class tables per payload key and similar **§11.4** depth are **non-negotiable sequenced** work (SOT + execution log)—not an excuse to skip Phase 6 inventory/`domain_ownership` discipline.

## Done

- Bounded-context shell apps: `brand_experience`, `platform_runtime`, `plans`, `registries`, `marketplace`, `policies` provide canonical import surfaces.
- CI gate: `lint_siteconfig_legacy_imports.py` blocks new direct imports from legacy `apps.siteconfig.models_*` domain wrappers.
- Live app/test imports cut over to brand, runtime, plans, registries, marketplace, policies where applicable.
- Six unused legacy `apps/siteconfig/models_*` compatibility shims deleted.
- §2.1 resolver migration: `evals/caching.py` — `SiteSettings.load()` replaced with `get_cached_site_settings(school=)`; `lint_tenant_settings.py` now flags `SiteSettings.load()` in tenant apps; `docs/domain_ownership.md` added; allowlist includes `platform_runtime/management/`.
- **Non-negotiable** get_solo shrink path: `backfill_runtime_defaults` uses `get_platform_site_settings_record(create=True)` instead of `SiteSettings.get_solo()`; get_solo remains only in `platform_runtime/helpers` (see SITESETTINGS_GET_SOLO_ALLOWLIST).

## Phase 2 plan items (satisfied by Phase B + guardrails)

These original objectives are **addressed in-repo** (not a deferred backlog):

1. **Owned models** — `docs/SITECONFIG_OWNED_MODELS.md`, `apps/siteconfig/owned_models_registry.py`, `domain_ownership.py`; branding/theme paths via `get_effective_site_settings` and `PlatformGlobalBranding`.
2. **State-safe migrations** — `siteconfig.0162` / `0163`, `brand_experience.0002`, `platform_runtime.0007`, resolver-first reads per [RESOLVER_MIGRATE_DELETE_ORDERING.md](RESOLVER_MIGRATE_DELETE_ORDERING.md).
3. **Legacy path removal** — Mirrored branding columns dropped from `SiteSettings`; tenant `get_solo()` / `SiteSettings.objects` / `school.settings` guardrails in `lint_tenant_settings.py`; Batch 3 FK write lint.
4. **Deprecation discipline** — New work must use runtime helpers and bounded contexts; allowlists in `docs/SITESETTINGS_GET_SOLO_ALLOWLIST.md`.

**Rule:** No new tenant behavior may be sourced from `SiteSettings` or other siteconfig singletons; use runtime resolvers and bounded-context services. See `docs/SITESETTINGS_GET_SOLO_ALLOWLIST.md` and `scripts/lint_tenant_settings.py --report-allowlisted`. **Ordering (nothing left behind):** [RESOLVER_MIGRATE_DELETE_ORDERING.md](RESOLVER_MIGRATE_DELETE_ORDERING.md) — resolver first, then migrate, then delete; phases 1–3 checklist.

---

## Phase B: Shrink SiteSettings (explicit plan)

**Goal:** SiteSettings eventually contains only **safe platform defaults**; all behavioral and tenant-facing fields move to bounded contexts and are read via runtime resolvers.

### Stay on the `SiteSettings` **database row** (Phase B slim table)

| Column | Reason |
|--------|--------|
| `maintenance_mode` | Platform-wide operational toggle; real column on `siteconfig_sitesettings`. |
| `updated_at` | Row metadata. |

**No other product columns** live on `SiteSettings` after migration **0162** — behavioral keys were removed from the table and copied into `RuntimeDefaults.payload` (virtual reads via `SiteSettings.__getattr__`). **Regression guard:** `apps/siteconfig/sitesettings_slim_contract.py` + `scripts/verify_phase_b_execution.py` assert (1) the ORM only exposes `id`, `maintenance_mode`, `updated_at` as local concrete fields, and (2) when the `siteconfig_sitesettings` table exists, **introspected DB columns** match that same set (half-applied migrations or manual DDL).

### `cache_rankings_interval_minutes` (platform cache tuning)

- **Not** a column on `SiteSettings` after **0162** (removed with other behavioral fields).
- **Authoritative store:** first-class nullable column `RuntimeDefaults.cache_rankings_interval_minutes` (`platform_runtime` migrations **0004** / **0005**), edited in platform admin **Runtime defaults** alongside payload.
- **Read path:** `get_effective_site_settings` / `_build_platform_site_settings_base` prefers the RuntimeDefaults column when set; payload snapshot may still contain the key from historical merges.

All other logical fields remain classified in `apps/siteconfig/domain_ownership.py` (EXACT_FIELD_OWNERS, PREFIX_FIELD_OWNERS) with target owners (brand_experience, runtime_blueprints, policies_rules, global_registries, marketplace_integrations, reports, documents, preview_platform, etc.).

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

**Post–Phase B product depth (non-negotiable, sequenced):** Full Report Platform SKUs, full config diff UI, full workflow simulation productization, and similar items are **required** work under **SOT §11.4** and **§5.x**—executed in **scoped slices** with tests + [RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md) blocks; **not** skippable “optional cadence.” Align wording with SOT **§11.4 execution queue** subsection.

**Verification:** `python scripts/verify_phase_5_siteconfig.py` (artifacts 0162 + 0163 + 0002 + `0007_platform_phase_b_domain_snapshots`); `python scripts/lint_phase_b_batch3_sitesettings_fk_writes.py` (no `site.save(update_fields=[...])` / `SiteSettings.objects.create(..., theme_pack=...)` for removed FKs); after DB migrate, `python scripts/verify_phase_b_execution.py`; `pre_deploy_gate.sh` runs these. Targeted tests: `apps.brand_experience.tests.test_platform_global_branding`, `apps.platform_runtime.tests.test_phase_b_domain_snapshots`.
