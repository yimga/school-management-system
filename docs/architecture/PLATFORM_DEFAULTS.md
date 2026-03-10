# Platform defaults (metadata plan todo 2)

**Purpose:** Single place for platform-wide, non-tenant-specific default values. No tenant-specific branches; use resolvers for tenant context.

## Where platform defaults live

- **SiteSettings.get_solo()** — Singleton for site-wide config (grading, locale, region). Used when no tenant context. See [SITESETTINGS_INVENTORY.md](security/SITESETTINGS_INVENTORY.md).
- **get_platform_defaults()** — [apps/platform_runtime/helpers.py](apps/platform_runtime/helpers.py) returns a small dict of platform defaults (e.g. default grading keys, default locale). Used by resolvers when building tenant runtime.
- **get_effective_site_settings(school=school)** — Prefer this in tenant-facing code instead of `SiteSettings.get_solo()` so region/tenant overrides apply.

## Future: dedicated PlatformDefaults model

When decomposing siteconfig further, a dedicated `PlatformDefaults` or `SiteDefaults` model can hold only platform-wide values (no tenant FK). New behavior should be added there; existing `SiteSettings` fields are gradually deprecated in favor of registry/resolver-backed metadata.
