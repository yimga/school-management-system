# Runtime Resolvers and Contract Tests

**Purpose:** §3.2 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Document resolver inventory and runtime contract tests. Nothing deferred.

**Status:** DONE — resolvers registered; contract tests exist and are run in pre_deploy_gate.

---

## 1. Resolver inventory

Source: `apps/platform_runtime/resolver_registry.py` (RESOLVER_ENTRY_POINTS). All tenant-facing behavior must resolve through these or helpers that consume them.

| Resolver | Implementation | Notes |
|----------|----------------|-------|
| RuntimeResolver | `apps.platform_runtime.runtime_resolver.build_tenant_runtime` | Full tenant runtime; precedence order in runtime_resolver steps 1–10 |
| SchemaResolver | `apps.metadata` (entity/field catalog; schema in .services) | Entity/field catalog |
| LayoutResolver | `apps.siteconfig` (layouts, forms, role homes) | Layouts, forms, role homes |
| BrandingResolver | `apps.platform_runtime.runtime_resolver._step7_branding` | Theme, colors, branding |
| BlueprintResolver | `apps.platform_runtime.runtime_resolver._step4_blueprint` | Blueprint pack assignment |
| PolicyResolver | `apps.policies.resolver.get_effective_policy` | Policy bundle |
| WorkflowResolver | `apps.siteconfig.workflow_resolver.for_action` | Workflow pack per action |
| DashboardResolver | `apps.siteconfig.dashboard_resolver.for_role` | Dashboard pack per role |
| EntitlementResolver | `apps.platform_runtime.runtime_resolver._step6_flags_entitlements` | Flags/entitlements |
| IntegrationResolver | `apps.platform_runtime.runtime_resolver._step10_integrations_marketplace` | Integrations catalog |
| LocalizationResolver | `apps.platform_runtime.runtime_resolver._step3_registry_context` | Region/locale/registry |

Helpers (consume runtime or platform defaults): `get_effective_site_settings`, `get_effective_flags`, `get_effective_flags_for_school`, `get_effective_feature_control_settings`, `get_effective_offline_runtime_settings`, `get_effective_support_contact_settings`, `get_effective_branding`, `get_effective_dashboard`, `get_effective_policy`, `get_effective_locale`, `get_effective_workflow` — in `apps/platform_runtime/helpers.py`.

---

## 2. Runtime contract

- **Contract shape:** `apps/platform_runtime/contracts.TenantRuntime` — typed contract for per-request tenant runtime. Compilation order enforced in `runtime_resolver.build_tenant_runtime` (steps 1–10).
- **Precedence:** Seven-level order (platform default → registry → blueprint → policy → entitlement → tenant override → sandbox). See `docs/runtime_precedence.md`.

---

## 3. Contract tests

| Test module | Coverage |
|-------------|----------|
| `apps/platform_runtime/tests/test_runtime_contract.py` | Runtime shape, compilation order, precedence, get_effective_site_settings prefers RuntimeDefaults, get_effective_flags_for_school, feature/offline/support settings, INTEGRATION_CATALOG |
| `apps/platform_runtime/tests/test_precedence.py` | Precedence chain matches north-star order |
| `apps/platform_runtime/tests/test_tenant_isolation_and_identity.py` | Precedence order has seven levels |

**CI:** `pre_deploy_gate.sh` runs targeted hardening tests including `apps.platform_runtime.tests.test_precedence` and platform_runtime contract tests.

---

## 4. Runtime inspector

- **Module:** `apps.platform_runtime.runtime_inspector` — uses `build_tenant_runtime` and `TenantRuntime` for admin/observability inspection. UI for "why enabled?" and source tracing can be built on this.

---

## 5. Completion gate (§3.2)

- [x] Resolvers documented and registered (resolver_registry.py + this doc).
- [x] Runtime contract tests exist and run in CI.
- [ ] Remove tenant-facing fallback logic outside runtime (ongoing per site_settings_usage_inventory).

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §3.2.*
