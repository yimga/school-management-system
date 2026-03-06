# Phase 6: App and Blueprint Marketplace

Scope and implementation status for checklist 11.2, 12.6.

## Goals

- **Blueprint marketplace:** Catalog of blueprint packs (e.g. Cameroon Francophone, UAE MoE+IB, UK GCSE/A-Level, US charter, technical/trade, faith-based) that can be applied to a school. Applying creates a PolicyBundle and sets TenantBlueprint.active_bundle so `get_effective_policy(school)` uses it when `POLICY_USE_BUNDLES=True`.
- **App marketplace:** Tenant/superadmin can discover and install approved apps for a school. Existing: MarketplaceApp, MarketplaceListing, AppInstallation, `install_app(school, app, ...)`. Phase 6 adds a discover/install UI.

## Implemented

### Blueprint pack catalog
- **BlueprintPack** model (`apps.policies.models`): slug, name, description, category, policy_snapshot (JSON), version, is_active, country_code, metadata. Control-plane catalog entry.
- **apply_blueprint_pack(school, pack, applied_by)** (`apps.policies.blueprint_services`): Creates PolicyBundle(school, policy_snapshot=pack.policy_snapshot), get_or_create TenantBlueprint(school), sets active_bundle, invalidate_policy_cache(school).
- **Blueprint marketplace UI:** Manager route `super:blueprint_marketplace` lists active packs; form to select school + pack and POST to apply. Templates: `marketplace/blueprint_marketplace.html`.

### App catalog UI
- **App catalog UI:** Manager route `super:app_catalog` lists installable listings (approved, not kill-switched); form to select school + app and POST to install. Uses existing `install_app(school, app, installed_by=request.user)`. Template: `marketplace/app_catalog.html`.

### Navigation
- Manager command-center / search catalog: entries for "Blueprint Marketplace" and "App Catalog" (Phase 6).
- Links from governance console, blueprint marketplace, and app catalog to each other and control plane.

## Touchpoints

- `apps.policies.models.BlueprintPack`, `apps.policies.blueprint_services.apply_blueprint_pack`
- `apps.policies.resolver`: when POLICY_USE_BUNDLES=True, resolver merges from TenantBlueprint.active_bundle.policy_snapshot
- `apps.marketplace.views`: blueprint_marketplace, app_catalog
- `apps.schools.super_urls`: marketplace/blueprints/, marketplace/apps/
- `config.manager_urls`: static_catalog entries for Blueprint Marketplace and App Catalog

## Deferred / later

- Tenant-facing "Get blueprints" / "Get apps" in tenant backend settings (optional; currently manager-only).
- Blueprint pack versioning and upgrade path (e.g. bump pack version, offer "Update bundle" for schools).
- Developer portal (developer.runmycampus) and public app/blueprint showcase (11.5).
