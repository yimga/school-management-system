# Admin Registry Technical Note

## Summary

The platform and tenant Django admin sites no longer share a single registry. Each has its own model set:

- **Tenant admin** (`tenant_admin_site`): Used on tenant host at `/admin/`. Shows only **tenant-only** and **both** models (school-scoped data and shared config).
- **Platform admin** (`platform_admin_site`): Used on manager host at `/admin/`. Shows only **platform-only** and **both** models (platform config, catalogs, migration, observability, etc.).

## How registration works

In `config/admin.py`:

- `register_tenant_admin(model, admin_class)` — Registers the model only on `tenant_admin_site`.
- `register_platform_admin(model, admin_class)` — Registers the model only on `platform_admin_site`.
- `register_both(model, admin_class, platform_admin_class=None)` — Registers on both sites. Use `platform_admin_class` if you need a different ModelAdmin for the platform backoffice.

The backward-compatible alias `admin_site = tenant_admin_site` remains so code that imports `admin_site` still gets the tenant site. New app admin modules should use the explicit helpers above.

## Adding a new model

1. Decide ownership from the [Admin vs Super Responsibility Matrix](ADMIN_VS_SUPER_RESPONSIBILITY_MATRIX.md):
   - **Tenant-only:** Per-school data (users, academics, finance, etc.) → `register_tenant_admin(Model, ModelAdmin)`.
   - **Platform-only:** Manager-only data (e.g. School, migration runs, observability, billing platform) → `register_platform_admin(Model, ModelAdmin)`.
   - **Both:** Catalog/config used by platform backoffice and tenant config (e.g. ThemePack, ReportTemplate) → `register_both(Model, ModelAdmin)`.

2. In your app’s `admin.py`, import the helper from `config.admin` and call it (do not use `admin_site.register(...)` for new models unless you explicitly want tenant-only and keep the alias).

3. If the model is used in a template or view that assumes “the” admin site, ensure the code uses the correct site (e.g. `tenant_admin_site` or `platform_admin_site`) or gets the site from context (e.g. `context['site']` in admin templates).

## Code that assumed a single registry

- **Theme studio tests** (`apps/siteconfig/tests/test_theme_studio.py`): Use `tenant_admin_site._registry` when asserting on SiteSettings/ThemePack admin, since those models are on the tenant site (and on both).
- **Admin extras templatetags** (`apps/observability/templatetags/admin_extras.py`): Already use the admin site from template context (`context.get('site', default_admin_site)`), so they work with either site’s registry.

## Permission rule

**Super view/governance access does not imply admin raw edit.** Access to `/super` (Control Plane) is enforced separately from access to `/admin` (Platform Backoffice). Platform admin `has_permission()` requires manager host + staff + superuser. Tenant users must never reach platform `/admin` or `/super`; tenant admin is only available on tenant host.

## Deep links and empty states

- **From /super:** Where an expert needs to edit a raw record, add an "Open in Admin" (or "Edit in backoffice") link to the specific changelist/edit URL in `/admin/`. Do not make `/admin` the primary path for governance.
- **Empty states / CTAs:** Prefer "Manage in Control Plane" (or "Open Control Plane") with links to the correct `/super` path (e.g. `/super/blueprints/`, `/super/policies/`) instead of "Go to admin to manage X". For maintenance-only flows, link to `/admin` and label as "Platform Backoffice" or "Configuration Engine".

## References

- Responsibility matrix: `docs/ADMIN_VS_SUPER_RESPONSIBILITY_MATRIX.md`
- Plan: `.cursor/plans/admin_vs_super_boundary_hardening_*.plan.md`
