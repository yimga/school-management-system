# Blueprint / policy / app / migration activation flows

**Purpose:** Document activation endpoints and UX so blueprint, policy, app install, and migration flows are productized and test-covered.

## Blueprint pack

- **Preview:** `apps.policies.blueprint_services.preview_blueprint_pack(school, pack)` — returns pack slug/name, policy_keys, current_bundle_id; no DB write.
- **Apply:** `apply_blueprint_pack(school, pack, applied_by=request.user)` — creates PolicyBundle, sets TenantBlueprint.active_bundle, invalidates policy cache.
- **Control-plane UX:** Marketplace views use preview then apply (e.g. super blueprint catalog); confirmation/rollback option should be explicit in UI.
- **Tests:** See `apps/policies/tests` and marketplace tests; add integration test that apply creates bundle and runtime reflects it.

## Policy bundle

- Policy is merged at runtime via `get_effective_policy(school)`; PolicyBundle stores snapshot when blueprint is applied. Rollback = set TenantBlueprint.active_bundle to previous bundle or clear.
- **Control plane:** Policy bundle application is visible where blueprint is applied; consider a "Policy history" or "Rollback" action in super dashboard.

## App installation (marketplace)

- **Lifecycle:** Install → Sandbox (pre-activation) → Activate. `activate_sandbox_installation(inst, activated_by=request.user)` in `apps.marketplace.services`.
- **Views:** `tenant_activate_installation`, `super_activate_sandbox` in marketplace/views.py; audit events emitted on install/uninstall/activate_sandbox.
- **Gaps:** Ensure first-party default blueprints/packs are seeded and visible; document how to add more.

## Migration Cloud

- **Entry:** `/super/migration/` (super_migration_cloud template). MigrationProfile and MigrationRun in `apps.automation.models`.
- **Gaps:** End-to-end wizard (select profile → map fields → run → verify), progress/status dashboard, rollback UX, per-tenant migration history. See Item 9 plan.

## References

- `apps/marketplace/views.py` (apply_blueprint_pack, tenant_activate_installation)
- `apps/policies/blueprint_services.py`
- `docs/SITECONFIG_DECOMPOSITION_PLAN.md`
