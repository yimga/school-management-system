# SiteSettings: Platform Defaults Only (B2)

**Contract:** SiteSettings holds **platform-wide defaults only**. Tenant-specific behavior must be resolved via runtime (request.tenant_runtime, get_effective_* helpers, School.settings/features where canonical). No tenant-facing code path may call SiteSettings.get_solo() for tenant behavior.

- **Platform defaults:** Single row (singleton) for global fallbacks (region, currency, feature flags default set, grading default).
- **Tenant overrides:** Stored on School, blueprint, plan, or policy bundle; resolved by RuntimeResolver and helpers.
- **Shrink in practice:** New settings that are tenant-specific go to School or domain models (brand, registries, integrations), not SiteSettings. SiteSettings fields that are purely tenant-overridable are deprecated for new use; read via get_effective_* only.

Implementation: `apps/platform_runtime/helpers.get_platform_defaults()` and `get_effective_*` are the canonical readers. Lint enforces no get_solo() in tenant paths.
