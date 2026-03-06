# Feature Flags and OpenFeature (Section 31.7)

How RunMyCampus resolves feature and capability flags. Single read path for modules; optional OpenFeature provider later.

**Ref:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md § 25.1, 31.7; policy_injection.md § Feature gate; REFINEMENT_AND_IMPLEMENTATION_ORDER.md Priority 3.

---

## 1. Current implementation

- **`is_feature_enabled(school, code)`** — `apps.schools.models`. Returns whether a feature (by code) is enabled for the school. Backed by merged policy: plan entitlements, addons, `school.features`, FeatureToggleState. Use for feature toggles (e.g. module on/off, beta features).
- **`can(school, capability)`** — `apps.schools.models`. Returns whether the school has a given capability (e.g. permission scope). Use for entitlement checks (e.g. "MODULE_X", limits).
- **`limits(school)`** — Returns dict of TenantQuotaLimit by limit_type for the school.

**Rule:** Modules must not read `school.features` or plan/addon data directly; use `is_feature_enabled(school, code)` and `can(school, capability)` only.

---

## 2. Where to use

- Views and API: before rendering or returning data that depends on a feature, call `is_feature_enabled(request.school, "feature_code")` or `can(request.school, "CAPABILITY")`.
- Templates: pass flags via context (e.g. from `global_env` or a dedicated context processor that uses the same functions).
- Services: receive `school` (or tenant context) and call `is_feature_enabled(school, code)` / `can(school, capability)`; do not read settings/features directly.

---

## 3. OpenFeature (optional future)

[OpenFeature](https://openfeature.dev) provides a vendor-neutral API for feature flags. To adopt without changing module behavior:

- Add an **OpenFeature provider** that resolves flags by calling the same backend as `is_feature_enabled(school, flag_key)`. The evaluation context would include `school_id` (or tenant identifier) so resolution remains per-tenant.
- Document in this file and in policy_injection.md that the provider reads from the same source as `is_feature_enabled` / `can()`. External systems (e.g. LaunchDarkly) could then sit behind the provider for runtime overrides without code deploy.
- Until then, the single read path remains `is_feature_enabled` and `can()`; no change required for compliance with Section 31.7.

---

## 4. Policy and caching

- Policy merge includes `features`; when POLICY_USE_BUNDLES is True, bundle policy_snapshot can set feature defaults.
- If POLICY_CACHE_TTL is set, the full policy (including effective features) is cached per school; call `invalidate_policy_cache(school)` after changing features or plan.

---

## References

- apps/schools/models.py — `is_feature_enabled`, `can`, `limits`
- policy_injection.md — Feature gate, OpenFeature note
- docs/architecture/REFINEMENT_AND_IMPLEMENTATION_ORDER.md — Priority 3 (OpenFeature optional)
