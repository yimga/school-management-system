# apps/brand_experience

> Themes, logos, palettes, and portal look/feel — plus the ExperienceTemplate
> marketplace that tenants install them through.

**Tenancy:** SHARED (public schema; per-tenant rows are scoped by an explicit `school` reference)
**Scale:** 8 models · 4 migrations · 12 test modules · ~3.7k LOC

## What this app owns

Brand Experience is the bounded context for how RunMyCampus *looks* to a given
tenant: brand profile and settings, theme packs for portal/admin/teacher/parent
surfaces, design templates, the compiled per-tenant PWA manifest, and the
operator-facing control-plane brand tokens. `resolvers.get_unified_theme_tokens`
is the single entry point portal, dashboard, and admin all read, so every surface
shares one design system rather than each inventing its own token names.

The decision a newcomer must understand is that **this app is mid-extraction from
`apps.siteconfig`, and its models are split into two kinds**. Five of the eight —
`BrandProfile`, `BrandSettings`, `DesignTemplate`, `GlobalBrandRegistry`,
`ThemePack` — are **proxy models over legacy siteconfig tables** (note their
`siteconfig_*` table names). They exist so new code can `import from
apps.brand_experience` today while data ownership migrates out of siteconfig.
The other three are first-class here. `PlatformGlobalBranding` is the
authoritative singleton for global branding; the slim siteconfig settings row
remains a *compatibility write surface* that syncs into it, and
`get_effective_site_settings` merges this row over the legacy copy.

The second decision: **templates are packs, not a parallel lifecycle**.
ExperienceTemplates live as `PackContract` entries in
`platform_runtime.pack_contract.EXPERIENCE_TEMPLATE_PACKS` so they inherit
preview / simulate / impact / apply / rollback / audit for free.
`experience_templates.py` holds only the template-*specific* overlay metadata
that does not belong on a generic pack: layout family, country/language coverage,
palette hints, accessibility floor, mobile posture, discovery tags.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `PlatformGlobalBranding` | `brand_experience_platformglobalbranding` | Singleton (pk=1). Authoritative platform-wide branding + report defaults: backgrounds, logo, favicon, theme pack refs, default report styles. First-class here. |
| `TemplateAssignment` | `brand_experience_templateassignment` | Per-school template assignment. OneToOne extension on `packages.InstalledPackage` — adds `template_key` + customizations without displacing the pack lifecycle record. |
| `TemplateAuditEvent` | `brand_experience_templateauditevent` | Append-only forensic trail for template lifecycle (preview / apply_requested / applied / rolled_back / customized). |
| `BrandProfile` | `siteconfig_brandprofile` | Tenant brand profile. **Proxy** over the legacy siteconfig table. |
| `BrandSettings` | `siteconfig_brandsettings` | Tenant brand settings. **Proxy.** |
| `DesignTemplate` | `siteconfig_designtemplate` | Reusable document/experience templates. **Proxy.** |
| `ThemePack` | `siteconfig_themepack` | Portal/admin/teacher/parent/student theme packs. **Proxy.** |
| `GlobalBrandRegistry` | `siteconfig_globalbrandregistry` | Globally seeded branding assets. **Proxy** (platform-scope, no `school`). |

All eight declared models are listed.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| URLs | `browse`, `detail`, `preview`, `compare`, `customize`, `apply`, `rollback`, `local_catalog`, `ai_recommend` | Tenant marketplace under `/school/studio/templates/*` (`urls_template_marketplace`) |
| Module | `resolvers` | `get_unified_theme_tokens(school, request)` — the shared token entry point |
| Module | `services` | `apply_palette(...)`, `install_brand_assets(...)` |
| Module | `experience_templates` | Overlay registry; layout families 1..10 |
| Module | `template_ai_recommender` | Gateway-routed recommender with deterministic rules fallback |
| Module | `platform_global_branding` | The singleton model + image/SVG validation |
| Module | `branding_singleton_sync` | Mirrors the legacy siteconfig row <-> `PlatformGlobalBranding` |
| Module | `pwa_manifest` | `compile_manifest(...)` — W3C manifest from white-label wizard inputs |
| Module | `control_plane_brand_vars` | Operator (manager-host) CSS custom properties |
| Module | `experience_packs` | Resolves + rolls back a school's experience pack |

No celery tasks, no management commands. The **operator** template surface is not
here: it lives under `/configuration/experience-templates/*` and reuses
`platform_runtime.views_administration.pack_*` directly.

**Partial by design:** `design_studio.py` is explicitly a stub. It resolves
`layout_metadata` from an `ExperiencePack` when one exists and otherwise returns
a minimal `{key, variant, sections: []}` structure. The layout-builder UI it
anticipates is not built. Do not present Design Studio as a delivered feature.

## Before you change this

- **Do not add fields to the five proxy models.** A proxy cannot add columns —
  the table belongs to `apps.siteconfig`. New brand columns go on
  `PlatformGlobalBranding` (or a new first-class model here), which is the
  direction of the extraction. `models.py` imports from siteconfig *submodules*
  (`models_global_experience`, `models_tooling`) rather than `siteconfig.models`
  specifically to avoid a circular import — brand_experience loads early in app
  setup. Keep those imports narrow.
- **`PlatformGlobalBranding` is a singleton at pk=1** and is read as
  `.filter(pk=1).first()`. Never create a second row. Writes to the legacy slim
  settings row sync *into* this one via `branding_singleton_sync`; if you add a
  field that must survive the migration off siteconfig, add it to
  `_BRANDING_MIRROR_FIELDS` too or the two rows silently diverge.
- **`TemplateAuditEvent` is append-only, enforced.** It uses the
  `AppendOnlyModelMixin` + `AppendOnlyManager` pattern and raises
  `AppendOnlyDeleteError`. Do not add an edit or delete path.
- **`TemplateAssignment` composes with `InstalledPackage`, it does not replace
  it.** The pack lifecycle record stays canonical. If you find yourself writing
  install/rollback logic here, you are duplicating `apps.packages.engine` — the
  marketplace views delegate to `preview_pack` / `simulate_pack` /
  `analyze_pack_impact` / `apply_pack` for exactly this reason, and no lifecycle
  code lives in this app.
- **`tenant_safe_only=True` is a tenancy boundary, not a filter preference.** The
  tenant marketplace views enforce it so operator-only templates can never appear
  in a tenant catalog. Removing it leaks the operator surface to schools.
- **AI calls must route through `services.ai_helpers`.** `template_ai_recommender`
  never imports `services.ai_gateway` directly — an architectural boundary scanner
  enforces this. The recommender also validates registry membership before
  returning, so it **never fabricates a template key**; keep that check if you
  change the AI path.
- **`services.py` helpers are deliberately no-op-friendly**: they tolerate
  `school is None` and missing models, log at DEBUG, and return silently. That is
  so CI-only callers without the full domain stack still land data in
  `cockpit_payload` via the wizard writer. The cost is that a real failure is
  quiet — do not assume "no exception" means "the write happened".
- `pwa_manifest.compile_manifest` exists because a wizard resolver called it
  inside a `try/except` and the module did not exist — the step silently skipped
  compiling for real. It is idempotent, tenant-scoped to the passed `school`, and
  must never raise into the wizard. Preserve all three properties.
