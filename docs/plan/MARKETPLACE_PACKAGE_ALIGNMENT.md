# Marketplace alignment with PackageEngine (metadata plan todo 8)

**Purpose:** Listings are thin wrappers around metadata packages; install goes through shared PackageEngine for governance, audit, and rollback.

## Current state

- **Marketplace** — [apps.marketplace](apps/marketplace): blueprint activation, app catalog, compatibility matrix, sandbox inspector. Blueprint apply uses [apps.policies.blueprint_services.apply_blueprint_pack](apps/policies/blueprint_services.py), which is **wired to PackageEngine.apply_package** so every apply creates an `InstalledPackage` and `PackageChangeLog` (todo 7).
- **Package format** — [docs/architecture/PACKAGE_FORMAT.md](architecture/PACKAGE_FORMAT.md). PackageEngine: [apps.packages.engine](apps/packages/engine.py).

## Alignment checklist

- [x] Blueprint apply calls PackageEngine.apply_package (via blueprint_services).
- [x] Workflow pack install: post_save on WorkflowPackAssignment calls PackageEngine.apply_package (siteconfig.signals).
- [x] Dashboard pack install: post_save on DashboardPackAssignment calls PackageEngine.apply_package (siteconfig.signals).
- [x] Policy bundle install: covered by blueprint apply when bundle is created; TenantBlueprint.active_bundle set via apply_blueprint_pack.
- [x] Theme pack install: template_gallery_page and brand_import_from_url_view call PackageEngine.apply_package when theme is applied.
- [x] Install flows use PackageEngine so governance, audit, and rollback are consistent.

New install flows should call `PackageEngine.apply_package()` (or `preview_diff` then `apply_package`) so governance, audit, and rollback are consistent.
