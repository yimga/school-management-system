# Feature gate and per-school modules

This document describes how path-based feature gating and per-school module toggles work, and how to enable/disable modules for a school.

## FEATURE_GATE_PATH_MAP

**Location:** `apps/schools/middleware.py`

`FEATURE_GATE_PATH_MAP` is a dictionary mapping **URL path prefixes** (or exact paths) to **feature codes**. When a request matches a path in this map, the system checks whether the current school has that feature enabled; if not, the middleware returns **403 Forbidden**.

### Current mapping

| Path prefix | Feature code |
|-------------|--------------|
| `/portal/design-studio/` | `design_studio` |
| `/portal/features/inventory/` | `inventory` |
| `/portal/features/library/` | `library` |
| `/portal/features/transport/` | `transport` |
| `/portal/features/canteen/` | (add when route exists) |

### How it works

1. **FeatureGatekeeperMiddleware** runs after tenant resolution (so `request.school` is set).
2. For each `(prefix, code)` in `FEATURE_GATE_PATH_MAP`, the middleware checks if `request.path` equals the prefix or starts with `prefix` (with a trailing slash).
3. If it matches, it calls `is_feature_enabled(school, code)` (see `apps/schools/models.py`).
4. If the feature is not enabled, the middleware returns 403 (JSON for API requests, HTML for browser).

### Adding a new gated path

1. Add an entry to `FEATURE_GATE_PATH_MAP` in `apps/schools/middleware.py`, e.g. `"/portal/features/canteen/": "canteen"`.
2. Ensure the feature code exists in the feature registry or in `School.features` / plan / addons so `is_feature_enabled` can resolve it.

---

## feature_registry (FEATURE_REGISTRY)

**Location:** `apps/schools/feature_registry.py` (and `apps/siteconfig` for FeatureToggleDefinition)

The **feature registry** is the list of modules that can be enabled per school. It is used by:

- **Module market / Grading & language / Site Settings** to show which modules a school can turn on.
- **is_feature_enabled(school, code)** to determine if a school has a module (via plan, addons, `School.features`, or FeatureToggleDefinition).

### Registry contents (FEATURE_REGISTRY)

Defined in `apps/schools/feature_registry.py` as `FEATURE_REGISTRY`: a list of `ModuleSpec` dicts with `code`, `name`, `description`, and optional `price`. Examples:

- `library` — Library management and book lending
- `transport` — School bus and transport fee management
- `canteen` — Canteen and meal plans
- `parent_chat` — Direct messaging with parents
- `cahier_de_texte` — Homework and class diary
- `offline_mode` — Offline sync (requires global Feature Control)
- `alumni` — Alumni network
- `dormitory` — Boarding and dorm management

### How modules are enabled for a school

1. **Plan:** If the school has a `plan` with `included_features`, those codes are enabled.
2. **Addons:** `school.addons` (list of feature codes) can add more.
3. **School.features:** JSON field on `School`, e.g. `{"library": true, "transport": false}`.
4. **FeatureToggleDefinition:** Seeded from `FEATURE_REGISTRY`; per-school toggles stored in TenantSystem / SystemFeature or equivalent (see `apps/siteconfig`).
5. **Billing waiver:** If `school.billing_type` is `COMPLIMENTARY` or `MANUAL_OVERRIDE`, all features are granted.

---

## Admin / config UI to enable or disable modules per school

- **Django Admin:** Edit the **School** and set the `features` JSON field (e.g. `{"library": true}`), or use plan/addons.
- **Module market (if enabled):** In the portal, **Site Settings** or **Grading & language** may expose a “Modules” or “Module market” view that lists modules from `get_available_modules()` and lets admins enable/disable them for the current school. This uses `FeatureToggleDefinition` and tenant config.
- **Super-admin:** When creating or editing a school (super dashboard), you can assign a plan or set addons/features so that the school has the correct modules.

Backend and portal **respect these flags**: the sidebar and nav can hide links for disabled modules; the **FeatureGatekeeperMiddleware** returns 403 for gated paths when the feature is not enabled.

---

## Tests

- `apps/schools/tests/test_plan_and_feature_gate.py` — Tests plan/addon/feature resolution and middleware 403 behaviour.
- `apps.schools.tests.test_feature_registry` — Run via `scripts/pre_deploy_gate.sh` (CI).

---

## Quick reference

| What | Where |
|------|--------|
| Path → feature code map | `apps/schools/middleware.py` → `FEATURE_GATE_PATH_MAP` |
| Is feature enabled? | `apps/schools/models.py` → `is_feature_enabled(school, code)` |
| List of modules | `apps/schools/feature_registry.py` → `FEATURE_REGISTRY`, `get_available_modules()` |
| Middleware | `apps/schools/middleware.py` → `FeatureGatekeeperMiddleware` |
| Module market UI | `apps/siteconfig/views.py` (e.g. `get_available_modules`), Site Settings / Customizer |
