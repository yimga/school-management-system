# Platform `/admin/` → control plane (`/super/`) — system configuration

**Purpose:** Document how **SiteSettings**, **system configuration**, and related fleet surfaces are decoupled from raw Django admin on the **manager host**, and where the canonical operator UX lives.

**Single execution reference:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.1 (SiteSettings / siteconfig dismantling).

## Principles

1. **Manager host (`platform_admin_site`):** Primary flows use **`/super/`** (control plane) and **`siteconfig:console_domains_hub`** (System config). Platform `/admin/` is **deep maintenance** raw model CRUD, not the default operator path.
2. **SiteSettings:** Registered only on **tenant** admin (`register_tenant_admin`). It does **not** appear on platform `/admin/`. On the manager host, links resolve via `apps.siteconfig.staff_navigation` to **`super:site_settings_list`** / **`super:site_settings_edit`**.
3. **Plans & catalog models** that have super CRUD are intentionally **not** registered on platform admin where noted in app `admin.py` (e.g. `plans_entitlements`).

## Full bridge coverage (platform changelists)

Every **`register_platform_admin`** surface (and **`register_both`** models that also appear on platform admin) for **siteconfig**, **integrations_marketplace**, **runtime_blueprints**, **global_registries**, **packages**, **brand_experience**, **platform_runtime**, **automation**, **observability** — plus related catalog rows — has a **`super:admin_bridge`** entry in **`apps/schools/super_admin_bridge_registry.py`**.

- **`PLATFORM_ADMIN_BRIDGE_ORDER`** — display order on **Platform operator hub** (Admin-tagged tiles).
- **`PLATFORM_ADMIN_BRIDGES`** — `bridge_key` → `admin:…_changelist` + labels.
- **Tests:** `test_platform_admin_bridge_registry_order_matches_bridges` and `test_admin_bridge_redirects_to_platform_changelists` assert **ORDER ↔ BRIDGE keys** match and each bridge **302** matches the resolved admin path (dynamic path-tail check).

Operators can open any covered platform changelist **without hardcoding `/admin/` paths** — use  
`reverse("super:admin_bridge", kwargs={"bridge_key": "<slug>"})`.

## UX: banners on platform backoffice

When `is_manager_host` is true (platform admin), changelist templates under **`admin/siteconfig/`** and **`admin/global_registries/`** show a short banner with links to the control plane, System config, and relevant super lists.

## Quick map (operator → super / System config)

| Concern | Canonical surface |
|--------|-------------------|
| Fleet dashboard & curated links | `super:platform_operator_hub`, `super:dashboard` |
| Bounded “System config” console | `siteconfig:console_domains_hub` |
| Site settings (manager) | `super:site_settings_list`, `super:site_settings_edit` |
| Regions, grading, plans, feature toggles (catalog) | `super:regions_list`, `super:grading_list`, `super:plans_list`, `super:feature_toggles_list` |
| AI posture (regional clusters, upgrade flows) | `super:ai_model_hub`, `super:global_ai_version` |
| **All platform admin changelist bridges** | `super:admin_bridge` + `super_admin_bridge_registry` |

## Related docs

- [RUNBOOK_ADMIN_TO_SUPER_MIGRATION.md](RUNBOOK_ADMIN_TO_SUPER_MIGRATION.md)
- [CONTROL_PLANE_AND_PLATFORM_ADMIN.md](CONTROL_PLANE_AND_PLATFORM_ADMIN.md)
- `apps/siteconfig/staff_navigation.py`
