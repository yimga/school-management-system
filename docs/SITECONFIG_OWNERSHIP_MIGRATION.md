# Siteconfig Ownership Migration (Phase 2)

**Goal:** Move database and behavioral ownership out of `siteconfig` into bounded contexts so tenant behavior is resolved from runtime, registries, and packs—not from a single giant settings domain.

**Status:** In progress. Bounded-context import surfaces exist; DB ownership migration is tracked here.

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
