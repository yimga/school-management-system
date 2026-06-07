# Marketplace app manifest (platform)

Tenant and control-plane UIs merge JSON from `MarketplaceApp.manifest` with canonical keys via `apps.marketplace.manifest_schema.normalize_platform_manifest`.

## Canonical fields

| Field | Purpose |
| --- | --- |
| `app_key` | Stable id; defaults to `MarketplaceApp.slug`. |
| `name`, `version`, `category` | Display and sorting. |
| `publisher` | Slug string; `publisher_display_name` optional override for UI. |
| `required_plan` | Plan slug gate (school.plan). |
| `required_features` | Feature codes checked via entitlements / `school.has_feature`. |
| `required_commercial_tier` | Minimum commercial tier (alias `min_commercial_tier`). |
| `permissions`, `scopes` | Same merged list (OAuth-style codes); duplicates removed. |
| `dependencies` | Declared package / app dependencies (install impact). |
| `configurable` | Whether tenant may edit allow-listed keys. |
| `installable` | Catalog hint; listing approval still controls real installability. |
| `rollout_status` | `ga`, `beta`, or `internal` (supplements listing governance). |
| `pricing_type` | `free`, `paid`, `included_in_plan`, `enterprise`; normalized `pricing_kind` for chips. |
| `price_display`, `trial_available`, `billing_sku` | Monetization copy and Stripe SKU when paid. |
| `rollback_supported` | Whether rollback UX treats sandbox / prior version as safe. |
| `min_platform_version` | Minimum RunMyCampus platform semver (`config.settings.APP_VERSION`). Alias: `min_rmc_version`. |
| `tenant_editable_config_keys` | Allow-listed keys for tenant config POST. |
| `capability_bindings` | **Required (wave 1).** List of `{kind, target, mode}` declaring runtime effect on activate: `feature`, `package_id`, `widget`, `extension_hook`, `integration_adapter`, `workflow_trigger`. Inferred at seed via `apps/marketplace/capability_contract.py` when absent. |
| `enabled_features` | Feature codes flipped on sandbox → active (mirrors feature bindings). |
| `package_id` | Package engine id attempted on activate when `PackageVersion` payload exists. |

## Lifecycle and install state

Installations stamp `installed_catalog_version` on the `AppInstallation.config` JSON. When the catalog app version advances and the tenant re-installs, `previous_catalog_version` stores the prior stamp for rollback messaging.

Signals for cards and **Installed apps** are computed in `resolve_tenant_catalog_signals` (`state_machine`: available, installed, active, disabled, update_available, rollback_available, compatibility flags).

## Publisher pipeline

`MarketplaceListing.status` drives draft → pending_review → approved/rejected/suspended. Governance console surfaces certification and security review columns; badges on tenant catalog combine listing certification, security review, manifest rollout, and app kind.

## Billing

`app_purchase_intent` never completes a fake purchase: paid paths require Stripe configuration and `billing_sku`; otherwise the user is routed to Plan & entitlements or operator messaging.

## Validation (local / CI)

Fast artifact checks:

`python scripts/verify_marketplace_platform_mission.py`

`python scripts/verify_marketplace_app_capability_contract.py` (73 first-party apps)

`python scripts/verify_marketplace_catalog_10x_closure.py` (waves 1–8 bundle)

`python scripts/verify_marketplace_package_payload_parity.py` (73 catalog slugs ↔ PackageVersion)
`python scripts/verify_first_party_package_payload_parity.py` (27 legacy package IDs ↔ PackageVersion)
`python scripts/verify_marketplace_sandbox_embed_registry.py` (73-app sandbox iframe url_name registry)
`python scripts/verify_legacy_package_id_bindings.py` (catalog slug -> legacy package_id wiring)
`python scripts/verify_marketplace_catalog_package_coverage.py` (73 apps: legacy + catalog-native payloads)
`python scripts/verify_integration_adapter_credential_schema.py` (adapter credential field schemas)
`python scripts/verify_marketplace_integration_credentials_ui.py` (finance integration credential editor)

Seed packages after marketplace apps:

`python manage.py seed_marketplace_catalog_packages`
`python manage.py seed_first_party_apps` (legacy 27 IDs — non-empty payloads via `first_party_package_payloads.py`)

Full gate (includes billing tenant tests used by marketplace POST routes):

`python manage.py test apps.marketplace.tests apps.siteconfig.tests.test_billing_stripe_tenant --noinput`

Design / surface audits often run with marketplace work:

`python scripts/verify_design_system_phase2.py`

`python scripts/audit_luxury_ui_surface.py`

Platform kill test (spawns Django tests; on Windows use a unique `DJANGO_TEST_DB_FILE` or close processes holding `.django_test_dbs/*.sqlite3`):

`python scripts/run_kill_test.py`
