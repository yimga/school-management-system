# Site Settings and system config wiring

Part 1 Q&A (branding). Single source of truth for **site-level** vs **tenant-level** configuration.

## Site-level (global)

- **SiteSettings** ([apps/siteconfig/models.py](../apps/siteconfig/models.py)) — singleton (django-solo or single row). Holds: primary_color, accent_color, logo, theme_pack, school_code, admission_number_mode/pattern/strategy/template, country (free-text), region (free-text), backend_feature_flags, default_language, and many other global defaults.
- **RegionConfig** — one per country; currency, timezone, grading_scale, term_count_per_year, etc.
- **EducationSystemProfile** — per region/country; term labels, grading, subject seed.
- Canonical **school location** for display/config is **School.default_region** (FK to RegionConfig). Prefer that over SiteSettings.country/region; sync or deprecate free-text where appropriate.

## Tenant-level (per school)

- **School** ([apps/schools/models.py](../apps/schools/models.py)) — logo_url, primary_color, accent_color, timezone, default_region (FK to RegionConfig), settings (JSON), features (JSON).
- **BrandSettings** (Phase F, if present) — optional per-tenant overrides.
- When `request.school` is set (tenant context), tenant branding (School + BrandSettings) **overrides** site-level for that request. CSS variables and theme are applied per tenant host (subdomain or custom domain).

## Wiring

- **Feature Control** ([apps/siteconfig/views_feature_control.py](../apps/siteconfig/views_feature_control.py)) toggles SiteSettings.backend_feature_flags and per-school modules.
- **Module vs feature center:** See [FEATURE_GATE_AND_MODULES.md](FEATURE_GATE_AND_MODULES.md).
- **School location:** Use School admin "School location" fieldset (default_region, compliance_region, timezone); pick from RegionConfig.

## Tenant alignment (uniform configuration)

To align a tenant (e.g. Gilead) with the codebase’s configuration **without changing name, slug, or subdomain**:

1. **Run the alignment command** (safe to re-run):
   ```bash
   python manage.py align_tenant_config
   ```
   Default target is `gilead-school`. This will:
   - Set **default_region** to `RegionConfig.get_default()` (e.g. CMR) if missing.
   - Set **country_code** (ISO alpha-2) from the region when blank.
   - Sync **timezone** from the region.
   - Persist **tenant_compiled_config** (and related keys) so policy/layers are in sync.
   - Sync **School.features** from the module manifest.

2. **Optional:** Use a specific region or another tenant:
   ```bash
   python manage.py align_tenant_config --slug gilead-school --region USA
   python manage.py align_tenant_config --slug other-school
   ```

3. **Optional:** Preview only (no writes):
   ```bash
   python manage.py align_tenant_config --dry-run
   ```

4. **Site-level:** Ensure **SiteSettings.backend_feature_flags** matches the default shape (e.g. `enable_super_admin_ui`) via Feature Control or admin; the command does not change SiteSettings.
