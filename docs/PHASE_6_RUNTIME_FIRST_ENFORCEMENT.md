# Phase 6 — Runtime-first enforcement (execution map)

**Canonical plan:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **§3.2**. This document maps the **Phase 6 agenda** (precedence, resolvers, fallbacks, inspector, tests) to repository artifacts so execution status is unambiguous.

**Status (engineering):** §3.2 completion gate is **[x]** in the SOT — runtime is the legal tenant behavior engine for standardized paths, with CI enforcement and inspectability.

---

## 1. Goal

**Make runtime the only legal tenant behavior engine** on tenant-facing paths: resolve behavior through `build_tenant_runtime` / `request.tenant_runtime` and `get_effective_*` helpers — not ad-hoc `SiteSettings.get_solo()` or unconstrained `school.settings` reads in tenant apps.

---

## 2. Task 1 — Standardize precedence

| Layer (your list) | Code / doc |
|-------------------|------------|
| Platform default | `precedence.PRECEDENCE_ORDER[0]`; platform defaults in `runtime_resolver` + `build_platform_default_site_settings` |
| Regional / registry default | `registry_default`; `_step3_registry_context` (LocalizationResolver) |
| Blueprint default | `blueprint_default`; `_step4_blueprint` (BlueprintResolver) |
| Policy bundle | `policy_bundle`; `get_effective_policy` + policy step in runtime |
| Entitlement constraint | `entitlement_gate`; `_step6_flags_entitlements` (EntitlementResolver) |
| Tenant override | `tenant_override`; school settings / runtime flags merged in resolver + helpers |
| Staged / sandbox override | `sandbox_override`; route preview/sandbox in `RouteContext` + `RUNTIME_COMPILATION_ORDER.md` §Override |

**Single chain:** `apps/platform_runtime/precedence.py` (`PRECEDENCE_ORDER`, `merge_by_precedence`, `describe_precedence_chain`).  
**Narrative:** [runtime_precedence.md](runtime_precedence.md), [architecture/RESOLUTION_CHAIN.md](architecture/RESOLUTION_CHAIN.md), [RUNTIME_COMPILATION_ORDER.md](architecture/RUNTIME_COMPILATION_ORDER.md).

---

## 3. Task 2 — Build / complete resolvers

Registry: `apps/platform_runtime/resolver_registry.py` → `RESOLVER_ENTRY_POINTS`.

| Resolver | Primary implementation |
|----------|-------------------------|
| **RuntimeResolver** | `runtime_resolver.build_tenant_runtime` |
| **BrandingResolver** | `runtime_resolver._step7_branding` |
| **BlueprintResolver** | `runtime_resolver._step4_blueprint` |
| **PolicyResolver** | `apps.policies.resolver.get_effective_policy` |
| **WorkflowResolver** | `apps.siteconfig.workflow_resolver.for_action` |
| **DashboardResolver** | `apps.siteconfig.dashboard_resolver.for_role` |
| **EntitlementResolver** | `runtime_resolver._step6_flags_entitlements` |
| **IntegrationResolver** | `runtime_resolver._step10_integrations_marketplace` |
| **LocalizationResolver** | `runtime_resolver._step3_registry_context` |
| **SchemaResolver** | `apps.metadata` (catalog / schema services) — bounded context, not a single function |
| **LayoutResolver** | `apps.siteconfig` (layouts, role homes, forms) |

**Also:** `apps/policies/resolvers.py` exposes façade resolvers (e.g. `TenantBlueprintResolver`, `BrandingResolver`) used by policy/dashboard/workflow flows; runtime compilation remains the single per-request aggregate.

Detail table: [runtime_resolvers_and_contracts.md](runtime_resolvers_and_contracts.md).

---

## 4. Task 3 — Remove tenant-facing fallback outside runtime (touched paths)

- **CI:** `scripts/lint_tenant_settings.py` (`--check-get-solo-only`) — tenant apps must not use `SiteSettings.get_solo()` / `.load()` for behavior.
- **Helpers:** `get_effective_site_settings`, `get_effective_flags_for_school`, etc. in `apps/platform_runtime/helpers.py` — runtime-first; platform singleton only where documented.
- **Ongoing:** Any *new* tenant path must use runtime helpers or `request.tenant_runtime`; track stragglers via `site_settings_usage_inventory.md` / audits.

---

## 5. Task 4 — Runtime inspector

- **Core:** `apps/platform_runtime/runtime_inspector.py` — `inspect_runtime`, `get_runtime_inspection`, `get_runtime_inspection_for_school`, `get_feature_toggle_inspection`, `entitlements_why`.
- **UI:** `super:runtime_inspector` — `templates/schools/super_runtime_inspector.html` (blueprint, packs, trace, toggles, governor limits, **entitlement_registry**, **blueprint_lifecycle**, **marketplace_install_registry**).
- **Precedence in payload:** `precedence_chain`, `feature_flags_merge_order`.
- **Registries:** `registry_snapshots.py` — entitlement registry, blueprint pack/bundle versioning, marketplace install list.

---

## 6. Task 5 — Contract tests (precedence + isolation)

| Test module | Role |
|-------------|------|
| `apps/platform_runtime/tests/test_precedence.py` | Seven-level order, aliases, `merge_by_precedence` |
| `apps/platform_runtime/tests/test_runtime_contract.py` | `TenantRuntime` shape, 13-step `compilation_trace`, helpers, `ResolverRegistryContractTests` |
| `apps/platform_runtime/tests/test_tenant_isolation_and_identity.py` | Identity / isolation aligned with runtime model |
| `apps/platform_runtime/tests/test_tenant_settings_lint.py` | Fails if tenant apps regress to `get_solo` |

**Gate:** `pre_deploy_gate.sh` → `TARGETED_HARDENING_TESTS` includes `test_precedence`, `test_tenant_isolation_and_identity`, `test_tenant_settings_lint`, `test_runtime_contract` (among others).

---

## 7. Acceptance criteria (mapped)

| Criterion | Evidence |
|-----------|----------|
| Runtime authoritative on touched paths | §3.2 actions + lint + helpers |
| Precedence explicit and testable | `precedence.py` + `test_precedence.py` + docs |
| Runtime inspectable | `runtime_inspector` + super UI + `precedence_chain` in payload |

---

## 8. Phase closure

Phase 6 is **closed at 100%**. Further platform work (e.g. shrinking `get_solo` allowlists, richer marketing UX) is tracked under **SOT §2.1 / §12** and [runtime_precedence.md](runtime_precedence.md) optional notes — **not** partial completion of Phase 6.

---

---

## 9. Line-by-line verification (agenda ↔ evidence)

Sweep against the external Phase 6 checklist; all rows satisfied.

| # | Agenda item | Verified in repo |
|---|-------------|------------------|
| **1** | Platform → regional/registry → blueprint → policy → entitlement → tenant → staged/sandbox | `precedence.PRECEDENCE_ORDER` + labels; `runtime_precedence.md` §1 (narrative aligned with “higher overrides lower”); `merge_feature_flags_by_runtime_precedence`; inspector `precedence_chain` + `feature_flags_merge_order` |
| **2** | Nine resolvers + schema/layout | `resolver_registry.RESOLVER_ENTRY_POINTS`; implementations per §3 table; `ResolverRegistryContractTests` importable paths |
| **3** | Remove tenant fallbacks on touched paths | `lint_tenant_settings.py` in `pre_deploy_gate.sh`; `test_tenant_settings_lint`; helpers runtime-first (`get_effective_site_settings`, etc.); stragglers = inventory docs only |
| **4** | Runtime inspector | `runtime_inspector.inspect_runtime`; super template + `entitlement_registry` / `blueprint_lifecycle` / `marketplace_install_registry` |
| **5** | Contract tests precedence + isolation | `test_precedence.py`, `test_runtime_contract.py`, `test_tenant_isolation_and_identity.py`, `test_tenant_settings_lint` — **all** in `pre_deploy_gate.sh` targeted hardening list |

*Do not duplicate this as a second execution plan; extend **RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md** §3.2 and this map only.*
