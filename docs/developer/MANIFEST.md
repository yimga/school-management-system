# Marketplace app manifest

Canonical normalization and validation live in `apps/marketplace/manifest_schema.py`. JSON stored on `MarketplaceApp.manifest` is merged with authoritative fields from the app row (`slug`, `name`, `version`).

## Core keys

| Key | Type | Description |
| --- | --- | --- |
| `app_key` | string | Filled from `MarketplaceApp.slug` if omitted |
| `version` | string | Prefer semantic versions for update/rollback signals |
| `permissions` / `scopes` | string[] | Declarative API scopes; sensitive scopes may require elevated approval |
| `required_features` | string[] | Tenant feature codes (`School.has_feature`); all must be present |
| `required_plan` | string | Exact `Plan.slug` match when set |
| `required_commercial_tier` | string | One of `free`, `pro`, `enterprise` (alias: `min_commercial_tier`) |
| `pricing_type` | string | `free`, `paid`, `included_in_plan` (display only; no in-repo card capture) |
| `price_display` | string | Human-readable label |
| `upgrade_message` | string | Shown when the app is blocked by entitlements |
| `dependencies` | string[] | Declared app/package dependencies (governance / impact preview) |
| `rollback_supported` | bool | UX hint for rollback-friendly installs |
| `tenant_editable_config_keys` | string[] | Allowlisted config keys the tenant may POST-merge |

## Lifecycle

1. **Catalog** — approved `MarketplaceListing` surfaces the app.
2. **Sandbox install** — `AppInstallation` with `install_phase=sandbox`.
3. **Activate** — promotion to `active` (entitlements re-checked).
4. **Rollback (basic)** — remove sandbox install via Installed apps, or uninstall active app; metadata packs use governed pack rollback (`siteconfig` pack surfaces).

## Permissions

Scope codes are classified for UI (`classify_scope_access`: read / write / admin). **Runtime enforcement** remains in API policy and middleware, not in the manifest alone.

## Versioning

`installation.config.installed_catalog_version` records the catalog version at install time. When `MarketplaceApp.version` increases, the tenant catalog shows **Update available**. Downgrade/revert of live catalog version is an operator workflow; uninstall remains the supported tenant rollback for app installs.
