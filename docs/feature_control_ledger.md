# Feature Control Ledger

**Purpose:** §5.2 "Convert long-lived toggles into capability registry entries" and "Show why enabled?" in the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).

**Status:** PARTIAL — FeatureToggleDefinition/State and get_effective_flags in use; runtime inspector deepens "why enabled?".

---

## 1. Current model

- **FeatureToggleDefinition / FeatureToggleState** — `apps/siteconfig` (owned_models_registry → platform_runtime); admin in siteconfig; scope school/platform.
- **get_effective_flags(request)** / **get_effective_flags_for_school(school)** — `apps/platform_runtime/helpers.py`; merges backend_feature_flags and toggles; used across accounts, api, dashboard, portal.
- **schools/feature_registry.py** — get_or_create definitions per key for school scope.

---

## 2. Actions

- [ ] Add owner/expiry/source/scope to all remaining ad-hoc flags (migrate to FeatureToggleDefinition where missing).
- [ ] Connect every long-lived toggle to runtime + entitlements + packs (runtime_resolver _step6_flags).
- [ ] Runtime inspector: surface "why enabled?" from TenantRuntime / flag source chain.

---

## 3. Completion gate (§5.2)

- [ ] All long-lived toggles in capability registry with owner/expiry/source/scope.
- [ ] Feature state connected to runtime + entitlements + packs + rollout policy.
- [ ] "Why enabled?" available in runtime inspector or equivalent.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §5.2.*
