# Governance: Feature Toggles, Migration Cloud, Pack Versioning

**Purpose:** Document platform governance capabilities and target state for feature toggles (control-plane), migration cloud, and pack versioning so the backlog is actionable.

## Feature toggles

### Current

- **SiteSettings.backend_feature_flags** (JSON): Platform/backend flags such as `enable_super_admin_ui`, `block_promotion_if_outstanding_returns`, etc. Stored in single global SiteSettings row; effective scope is platform-wide. Feature Control panel in siteconfig allows editing.
- **FeatureToggleDefinition / FeatureToggleState** (siteconfig): Tenant-scoped toggles for A/B and rollout; used for tenant-level features.
- **default_backend_feature_flags()**: Defaults in code; new flags added there and in Feature Control UI.

### Target (control-plane only)

- **Platform-wide flags** that must not be overridden per tenant (e.g. "maintenance mode", "super admin UI enabled") can remain in SiteSettings.backend_feature_flags (single row) or move to a dedicated **platform_flags** table or env-only config for strict separation. Current single-row SiteSettings is acceptable for now; document that backend_feature_flags are platform-level, not tenant overridable.

## Migration cloud

### Current

- **Super view:** `/super/migration/` (super_migration_cloud) for migration profiles, runs, parity, rollback.
- **Migration services:** Registry-aware validation and run execution (siteconfig.migration_services, etc.).

### Target

- **Migration cloud UI:** Already present; enhance with runbooks (docs) and clearer rollback flows.
- **Runbooks:** Document in docs/ or runbook repo: how to run a migration, how to rollback, how to verify parity. Link from migration cloud UI.

## Pack versioning and rollback

### Current

- Blueprints and policies can be applied to schools; versioning is not yet formal (no version field or rollback to previous version).

### Target

- **Pack versioning:** Add version to blueprint/policy pack definitions; record which version is applied per school. **Rollback:** Allow operator to revert a school to a previous pack version from control plane. Design in architecture doc; implement when prioritised.

## Status

- **Done:** Documented current vs target; backend_feature_flags are platform-level; migration cloud UI exists; pack versioning/rollback is design-next.
- **Next:** Add runbooks for migration/rollback; design pack version schema and rollback API.
