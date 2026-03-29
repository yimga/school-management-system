# Feature gate, modules, and feature center

## Modules vs feature center

- **Modules** are product capabilities that can be enabled or disabled **per school** (e.g. library, transport, canteen). They are defined in [apps/schools/feature_registry.py](../apps/schools/feature_registry.py) and gated by [apps/schools/middleware.py](../apps/schools/middleware.py) via **`FEATURE_GATE_PATH_MAP`** (one capability per prefix) and **`FEATURE_GATE_PATH_ANY_OF`** (prefix allowed if **any** listed capability is enabled — report ministry, staff publish/promotion preview under **`/reports/publish/`** and **`/reports/promotion-preview/`** (coarse **`reports`** only), parent PDF downloads, report card builder/previews under `/siteconfig/reports/…`, **`/siteconfig/reports/scheduled/`**, **`/siteconfig/reports/download/`**, **`/siteconfig/reports/bulk-letters/`**, **`/api/v1/reports/adhoc`**, **`/api/v1/reports/scheduled`**, **`/api/v1/reports/regulatory-*`**, **`/api/v1/reports/emis`** (prefix match); see [BILLING_SKUS_ENTITLEMENTS.md](BILLING_SKUS_ENTITLEMENTS.md)). **`FEATURE_GATE_PATH_MAP`** resolution uses **`get_effective_policy`** when available, else **`is_feature_enabled(school, code)`**. **`FEATURE_GATE_PATH_ANY_OF`** uses **`is_plan_entitlement_feature_enabled`** (plan, addons, `School.features` only) so BASE_SCHOOL manifest modules such as **`reports`** do not bypass SKU-style gates.
- **Feature center (Feature Control)** is the **UI panel** where you toggle modules and global/site flags. It lives at [apps/siteconfig/views_feature_control.py](../apps/siteconfig/views_feature_control.py) — path `/siteconfig/feature-control/`. There you control both per-school **modules** and site-level flags stored in `SiteSettings.backend_feature_flags`.

So: **modules** = the capability model; **feature center** = the admin UI that changes those capabilities and site settings.

## Branding: site-level vs tenant-level

- **Site-level (global):** The singleton **SiteSettings** in [apps/siteconfig/models.py](../apps/siteconfig/models.py) holds `primary_color`, `accent_color`, `logo`, `theme_pack`, etc. This is the default branding when no tenant is in context.
- **Tenant-level:** [apps/schools/models.py](../apps/schools/models.py) defines **School** (`logo_url`, `primary_color`, `accent_color`) and optional **BrandSettings**. When `request.school` is set (tenant context), tenant branding overrides site-level. CSS variables and theme are applied per tenant host (subdomain or custom domain).

Summary: **Site** = SiteSettings; **Tenant** = School + BrandSettings. Document any new branding fields in this file or in SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING if you add a dedicated wiring doc.
