# Domain ownership (§2.1)

**Purpose:** Single reference for SiteSettings field ownership and target bounded contexts. Used by §2.1 (move ownership out of siteconfig), `site_settings_usage_inventory.md`, and CI (`lint_tenant_settings`, `lint_siteconfig_legacy_imports`).

**Phase 5 / §2.1:** Repository gate **MET** — classification lives in code; tenant reads use runtime resolvers only; aggregated verification: `python scripts/verify_phase_5_siteconfig.py` (also in `pre_deploy_gate.sh`).

**Source of truth (code):** `apps/siteconfig/domain_ownership.py` — `classify_site_settings_field()`, `EXACT_FIELD_OWNERS`, `PREFIX_FIELD_OWNERS`, `OWNERSHIP_DOMAINS`.

---

## 1. Ownership domains

Every SiteSettings field is classified into one of:

| Domain | Target bounded context / app |
|--------|------------------------------|
| safe_platform_default | Platform singleton only; no tenant-facing read |
| brand_experience | brand_experience, platform_runtime (resolver) |
| runtime_blueprints | platform_runtime, packages |
| policies_rules | policies, platform_runtime (get_effective_flags) |
| plans_entitlements | plans_entitlements |
| global_registries | global_registries |
| marketplace_integrations | marketplace, integrations |
| reports | reports |
| documents | documents |
| design_studio | design_studio |
| preview_platform | preview_platform |
| metadata_governance | metadata |
| delete | Deprecate / stop reading in tenant paths |

---

## 2. Field classification

- **Exact owners:** See `EXACT_FIELD_OWNERS` in `apps/siteconfig/domain_ownership.py` (e.g. `site_name`, `theme_pack`, `backend_feature_flags`, `cache_rankings_interval_minutes` → brand_experience, policies_rules, safe_platform_default).
- **Prefix rules:** See `PREFIX_FIELD_OWNERS` (e.g. `theme_*`, `report_*`, `finance_*` → brand_experience, reports, policies_rules).
- **Run:** `python scripts/generate_platform_inventory.py` for current field list and owner counts.

---

## 3. Resolver path (tenant-facing reads)

- Tenant code must **not** call `SiteSettings.get_solo()` or `SiteSettings.load()`.
- Use `get_effective_site_settings(request=..., school=...)` or `get_cached_site_settings(school=...)` (automation/tasks) from `apps.platform_runtime.helpers` and `apps.automation.helpers`.
- CI: `scripts/lint_tenant_settings.py --check-get-solo-only` flags `get_solo()` and `load()` in tenant apps.

---

## 4. Legacy path deletion

Legacy paths (deprecated accessors, re-exports) are **deleted per-migration** after replacement is live and verified. See `docs/SITECONFIG_OWNERSHIP_MIGRATION.md` and `docs/SITECONFIG_OWNED_MODELS.md` for model→app targets and migration order.

---

## 5. Next incremental (Step 4 — move ownership)

- **Done (this run):** `cache_rankings_interval_minutes` moved to `RuntimeDefaults` as first-class column (migration 0004). Resolver `_build_platform_site_settings_base` uses it when set; `sync_from_site_settings` / `backfill_runtime_defaults` backfill from SiteSettings. evals/caching continues to read via `get_effective_site_settings` (unchanged).
- **Next concrete move:** Add more SiteSettings fields to `RuntimeDefaults` as first-class columns (same pattern: migration, backfill in sync_from_site_settings, apply in _build_platform_site_settings_base). Order by dependency (see `RESOLVER_MIGRATE_DELETE_ORDERING.md`). Next batch: theme/experience-related fields (e.g. `theme_pack`, `primary_color`) per domain_ownership brand_experience; implement when product unblocks.
- **Inventory:** Keep `site_settings_usage_inventory.md` and `apps/siteconfig/domain_ownership.py` in sync when adding or reclassifying fields.
- **Rule:** No new `get_solo()`/`load()` in tenant code (CI); ownership move is additive (new column + resolver) then subtractive (stop reading old) per field.

---

## 6. §12 gate satisfaction (siteconfig materially decomposed / SiteSettings not tenant-behavior truth)

**When are these two gates MET?**

- **siteconfig materially decomposed:** (a) Every SiteSettings field classified to an ownership domain (domain_ownership.py + this doc). (b) Bounded-context surfaces exist (platform_runtime, brand_experience, policies, etc.). (c) No tenant-facing code uses `SiteSettings.get_solo()` or `.load()` — enforced by `lint_tenant_settings --check-get-solo-only`. (d) `get_effective_site_settings(request=..., school=...)` is the only tenant-facing API for site settings; it is runtime-first (RuntimeDefaults then SiteSettings). (e) `lint_siteconfig_legacy_imports` blocks new direct imports from legacy siteconfig domain wrappers.
- **SiteSettings not tenant-behavior truth:** Tenant-behavior *truth* is the output of `get_effective_site_settings` (runtime-first). SiteSettings is the legacy data source used by the resolver when RuntimeDefaults is not populated; it is not the authority for tenant behavior. Verification: same lints + runtime_precedence.md + test_runtime_contract.

**Verification:** Run `python scripts/verify_phase_5_siteconfig.py`, `lint_tenant_settings --check-get-solo-only`, and `lint_siteconfig_legacy_imports`; all must pass. See BACKLOG_AND_DEFERRED_CLOSURE §6.3 and RUNMYCAMPUS §12.1.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.1.*
