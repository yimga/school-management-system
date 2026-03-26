# Phase 7 — Runtime-first enforcement — checklist

**SOT:** Precedence + resolvers — [runtime_precedence.md](../runtime_precedence.md), [PHASE_6_RUNTIME_FIRST_ENFORCEMENT.md](../PHASE_6_RUNTIME_FIRST_ENFORCEMENT.md), [runtime_resolvers_and_contracts.md](../runtime_resolvers_and_contracts.md).

**Mandatory audit:** [PHASE_07_RUNTIME_FIRST_AUDIT.md](../phase_audit/PHASE_07_RUNTIME_FIRST_AUDIT.md) — **CLOSED** 2026-03-24.

**Mechanical gates:** `python scripts/verify_cursor_phase7_runtime_first.py` — **Granular (execution law):** `python scripts/verify_cursor_phase7_granular.py` (adds full tenant lints including `apps/studio_os` + `test_tenant_isolation_and_identity.py` + `schools/tests/test_super_views_runtime_ops.py`).

## Precedence

- [x] `apps/platform_runtime/precedence.py` — seven-layer `PRECEDENCE_ORDER`, aliases, `merge_by_precedence`, `describe_precedence_chain`
- [x] `docs/runtime_precedence.md` — narrative aligned with code
- [x] Feature-flag merge helper — `merge_feature_flags_by_runtime_precedence` (policy < tenant < sandbox for overlapping keys)

## Resolvers

- [x] `apps/platform_runtime/resolver_registry.py` — `RESOLVER_ENTRY_POINTS` includes Runtime, Branding, Blueprint, Policy, Workflow, Dashboard, Entitlement, Integration, Localization
- [x] `apps/platform_runtime/runtime_resolver.py` — `build_tenant_runtime`, 13-step `compilation_trace`
- [x] Policy — `apps.policies.resolver.get_effective_policy`
- [x] Workflow / dashboard — `apps.siteconfig.workflow_resolver`, `dashboard_resolver`

## Tenant behavior paths

- [x] `apps/platform_runtime/helpers.py` — `get_effective_site_settings`, flags, platform record helpers (runtime-first)
- [x] Phase 6 lints — no tenant `get_solo()` / forbidden ORM on touched trees (`verify_cursor_phase6_*`)

## Inspector / visibility

- [x] `apps/platform_runtime/runtime_inspector.py` — `inspect_runtime`, `get_runtime_inspection`, toggles / entitlements helpers
- [x] `templates/schools/super_runtime_inspector.html` + `super:runtime_inspector`
- [x] Linked from control outcome center, Studio Control rail, deep links, control plane nav

## Contract tests

- [x] `apps/platform_runtime/tests/test_precedence.py`
- [x] `apps/platform_runtime/tests/test_phase7_runtime_gate.py` — canonical precedence + required resolver names
- [x] `apps/platform_runtime/tests/test_runtime_contract.py` — `TenantRuntime` shape, compilation order, resolver registry importability, inspector precedence payload, integrations shape

## Validation

- [x] `python scripts/verify_cursor_phase7_runtime_first.py`
- [x] `python scripts/verify_cursor_phase7_granular.py`
- [x] `python -m pytest apps/platform_runtime/tests/test_phase7_runtime_gate.py apps/platform_runtime/tests/test_precedence.py apps/platform_runtime/tests/test_runtime_contract.py -q`

## Acceptance

- [x] Runtime authoritative on touched flows (aggregate runtime + helpers)
- [x] Precedence explicit, testable, inspectable
- [x] Fallback outside runtime removed from touched tenant paths (Phase 6 CI lints)
- [x] **Do not move to Phase 8** until `verify_cursor_phase7_granular.py` passes (superset of the narrow bundle)
