# Siteconfig Ownership Migration (Phase 2)

**Goal:** Move database and behavioral ownership out of `siteconfig` into bounded contexts so tenant behavior is resolved from runtime, registries, and packs—not from a single giant settings domain.

**Status:** In progress. Bounded-context import surfaces exist; DB ownership migration is tracked here.

## Done

- Bounded-context shell apps: `brand_experience`, `platform_runtime`, `plans`, `registries`, `marketplace`, `policies` provide canonical import surfaces.
- CI gate: `lint_siteconfig_legacy_imports.py` blocks new direct imports from legacy `apps.siteconfig.models_*` domain wrappers.
- Live app/test imports cut over to brand, runtime, plans, registries, marketplace, policies where applicable.
- Six unused legacy `apps/siteconfig/models_*` compatibility shims deleted.

## Remaining

1. **Identify owned models** — **Done (1.1).**  
   Full assignment in `docs/SITECONFIG_OWNED_MODELS.md`; Python registry in `apps/siteconfig/owned_models_registry.py` (`get_target_app_for_model`, `OWNED_MODELS_TARGET`). Every siteconfig model (models.py, models_dashboard.py, models_workflow.py) has a target bounded context.

2. **State-safe migrations**  
   Create Django migrations that move tables or add FK to new app without breaking existing code: e.g. add `runtime.Defaults` and backfill from `SiteSettings`; switch reads to resolver; then deprecate direct `SiteSettings` for tenant behavior.

3. **Delete legacy paths**  
   After all call sites use new surfaces, remove deprecated accessors and, where applicable, old tables or columns. Enforce via CI (no new tenant-facing `get_solo()` except allowlisted path-to-10).

4. **Deprecation markers**  
   Mark legacy access paths with `# DEPRECATED: use apps.platform_runtime.helpers.get_effective_site_settings` (or equivalent) and target removal date.

**Rule:** No new tenant behavior may be sourced from `SiteSettings` or other siteconfig singletons; use runtime resolvers and bounded-context services. See `docs/SITESETTINGS_GET_SOLO_ALLOWLIST.md` and `scripts/lint_tenant_settings.py --report-allowlisted`.
