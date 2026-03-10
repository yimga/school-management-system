# Marketplace alignment with PackageEngine (metadata plan todo 8)

**Purpose:** Listings are thin wrappers around metadata packages; install goes through shared PackageEngine for governance, audit, and rollback.

## Current state

- **Marketplace** — [apps.marketplace](apps/marketplace): blueprint activation, app catalog, compatibility matrix, sandbox inspector. Blueprint apply uses [apps.policies.blueprint_services.apply_blueprint_pack](apps/policies/blueprint_services.py), which is **wired to PackageEngine.apply_package** so every apply creates an `InstalledPackage` and `PackageChangeLog` (todo 7).
- **Package format** — [docs/architecture/PACKAGE_FORMAT.md](architecture/PACKAGE_FORMAT.md). PackageEngine: [apps.packages.engine](apps/packages/engine.py).

## Alignment checklist

- [x] Blueprint apply calls PackageEngine.apply_package (via blueprint_services).
- [ ] Workflow pack install: route through PackageEngine.apply_package with package_type="workflow".
- [ ] Dashboard pack install: route through PackageEngine.apply_package with package_type="dashboard".
- [ ] Policy bundle install: route through PackageEngine.apply_package with package_type="policy".
- [ ] Theme pack install: route through PackageEngine.apply_package with package_type="theme".
- [ ] Marketplace listing models (BlueprintPackListing, etc.) reference package_id/version and install via PackageEngine.

New install flows should call `PackageEngine.apply_package()` (or `preview_diff` then `apply_package`) so governance, audit, and rollback are consistent.
