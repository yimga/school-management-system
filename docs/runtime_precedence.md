# Runtime Precedence Order

**Purpose:** §3.2 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Standardize the order in which tenant-facing behavior is resolved. Nothing deferred.

**Status:** DONE — order documented and implemented in platform_runtime.

---

## 1. Standard precedence order

Tenant-effective value is resolved in this order (first non-null / applicable wins):

1. **Platform default** — System-wide fallback (e.g. `build_platform_default_site_settings()`).
2. **Registry / regional default** — Global registries (region, country, education profile) and regional overrides.
3. **Blueprint default** — Blueprint pack applied to the tenant (school type, region, plan).
4. **Policy bundle** — Policy bundle attached to the tenant (grade approval, MFA, features).
5. **Entitlement constraint** — Plan/entitlement caps and feature gates.
6. **Tenant override** — School-specific or runtime override (e.g. RuntimeDefaults, school.settings).
7. **Sandbox / staged override** — Preview or staged rollout overrides (e.g. preview mode, A/B).

---

## 2. Where it is implemented

- **Helpers:** `apps/platform_runtime/helpers.py`: `get_effective_site_settings()`, `get_effective_flags()`, `get_platform_defaults()`.
- **Models:** `apps/platform_runtime/models.RuntimeDefaults` holds tenant-effective snapshot; sync from SiteSettings with ownership filters.
- **Tests:** `apps/platform_runtime/tests/test_precedence.py` (and related) assert precedence behavior.
- **Resolvers:** Policies, registries, blueprints, and entitlements feed into the same order via runtime; no tenant-facing code should bypass runtime.

---

## 3. Completion gate (§3.2)

- [x] Precedence order standardized and documented.
- [x] Runtime resolution implemented in platform_runtime.
- [x] Tenant-facing fallback removed: no direct `SiteSettings.get_solo()` or `.load()` in tenant app code (lint_tenant_settings --check-get-solo-only); `get_effective_site_settings(request)` is runtime-first (RuntimeDefaults then platform record); fallback in helpers is platform-only, not tenant path.

**Optional (path to 10):** Shrink allowlist further by migrating allowlisted management commands to pass-through resolvers; see site_settings_usage_inventory.md and SITESETTINGS_GET_SOLO_ALLOWLIST.md.

---

**Tenant registry keys and compiled layers:** [RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md](RUNTIME_PRECEDENCE_AND_TENANT_REGISTRY_KEYS.md).

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §3.2.*
