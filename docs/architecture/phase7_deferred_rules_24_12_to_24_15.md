# Phase 7: Deferred Rules 24.12–24.15

Implementation status for checklist items 24.12, 24.13, 24.14, 24.15.

---

## 24.12 — No third-party app direct schema freedom; extensions through contracts

**Rule:** Third-party/marketplace apps must not have direct schema freedom. Extensions are through declared contracts only.

**Implemented:**
- **Contract:** Schema changes only via manifest keys `migrations_app` or `schema_patch_app` (Django app label). No raw SQL or arbitrary migrations.
- **Restriction:** For **third-party** apps, schema patches run only if the declared app label is in the allowlist `THIRD_PARTY_SCHEMA_PATCH_ALLOWLIST` (settings). Empty by default = third-party apps cannot run schema patches. First-party apps may declare any in-repo app label.
- **Code:** `apps.marketplace.services.run_schema_patches_for_installation` checks app kind and allowlist before running migrate.
- **Documentation:** This doc; manifest contract documented in marketplace model help_text.

**Contract summary:** Apps extend via manifest (scopes, widgets, events_consumed/emitted, optional migrations_app); permission scopes and ScopeGrant; no direct DB access beyond API and declared contracts.

---

## 24.13 — Every workflow must degrade safely if downstream fails

**Rule:** Workflows (approval, automation, integrations) must not break the system when a downstream step fails.

**Implemented:**
- **workflow_resolver:** `for_action` already wraps TenantWorkflow lookup in try/except and returns `{}` on failure. `get_approval_workflow` now wrapped in try/except; on failure returns `{"type": "approval", "workflow_key": key, "approval_roles": [], "approver_ids": [], "approver_count": 0}` so callers get a safe empty-approver definition instead of 500.
- **workflow_engine.run_actions:** Each action execution wrapped in try/except; failed actions append `{"type": ..., "error": str(e)}` to results; workflow continues and logs; `run_workflow` still returns `ok: True` with partial `actions_run` (degraded outcome).
- **workflow_engine.run_workflow:** WorkflowRunLog create and SchoolProvisioningEvent.log_event already in try/except (log warning, continue). Conditions evaluation does not raise; action failures are isolated per action.
- **Documentation:** Safe degradation behavior documented in this doc and in workflow_resolver/workflow_engine docstrings.

---

## 24.14 — Every customization upgrade-safe

**Rule:** Tenant/admin customizations (policy overrides, workflow config, blueprint choices) must survive platform upgrades.

**Implemented:**
- **Policy/Blueprint:** PolicyBundle and BlueprintPack have `version`; TenantBlueprint points to a bundle. Upgrade path: apply a new BlueprintPack or create a new PolicyBundle with updated snapshot; point TenantBlueprint to it. No in-place mutation of historical bundles.
- **Workflow:** TenantWorkflow stores `overrides` (JSON); template reference is by FK. Template changes are additive (new template version or new code); overrides remain valid until explicitly migrated.
- **Documentation:** Upgrade-safety notes in this doc; recommend versioning custom config and avoiding destructive schema changes to customization storage.

**Recommendations:** When adding new policy keys or workflow actions, preserve backward compatibility (defaults for missing keys); avoid removing keys that tenants might have in overrides.

---

## 24.15 — Every admin config has preview, validation, rollback

**Rule:** Admin/config changes should support preview, validation, and rollback where feasible.

**Implemented:**
- **Migration wizard:** Dry-run (validate only) and scorecard before run; MigrationRun audit for rollback visibility (full rollback of last run deferred).
- **Blueprint apply:** Validation: `apply_blueprint_pack` checks pack is active; optional `preview_blueprint_pack(school, pack)` returns summary of what would be applied (policy keys, no DB write). Rollback: Revert by setting TenantBlueprint.active_bundle to a previous PolicyBundle (or null); documented in UI or admin.
- **Documentation:** Preview/validation/rollback patterns documented in this doc; admin UX for blueprint rollback (select previous bundle) can be added in manager.

**Existing:** Feature-flag and siteconfig changes in admin; marketplace governance (approve/reject). Preview/validation for complex config (e.g. policy JSON) can be extended incrementally.

---

## Optional environment variables

Set in `.env` or environment; see `config.settings` and `.env.example`.

| Variable | Purpose | Example |
|----------|---------|--------|
| `POLICY_USE_BUNDLES` | Use blueprint bundles in resolver (1/0). When 1, `get_effective_policy(school)` merges from `TenantBlueprint.active_bundle.policy_snapshot` when set. | `POLICY_USE_BUNDLES=1` |
| `POLICY_CACHE_TTL` | Per-tenant policy cache TTL in seconds; 0 = no cache. Reduces resolver load. | `POLICY_CACHE_TTL=300` |
| `THIRD_PARTY_SCHEMA_PATCH_ALLOWLIST` | Comma-separated Django app labels that third-party apps may use for schema patches (24.12). Empty = none. | `THIRD_PARTY_SCHEMA_PATCH_ALLOWLIST=my_extension_app` |
