# Platform Workflow Code-Truth Inventory (Phase 0)
_Generated 2026-05-22T12:21:14Z by `scripts/audit_workflow_code_truth_inventory.py`._

Code-truth inventory of every Django URL configuration in this repo (6 root URLconfs + every apps/*/*urls*.py) and the per-app rollup of views, forms, services, models, templates, tests, README/howto, and AI/feedback/help cross-references. Read-only filesystem walk; no Django startup. Phase 1 (classification by audience / primary action / click count) builds on this artifact, not on it.

## Summary

- URL configs scanned: **49** (43 per-app + 6 root)
- Total `path(...)`/`re_path(...)` route declarations: **1909** (1872 named, 37 unnamed)
- Total `include(...)` chains: **90**
- Apps scanned: **50**
- Apps with routes: **27** | with tests: **43** | with templates: **31**
- Apps with help template: **4** | with AI hook: **18** | with feedback import: **6**
- Apps reachable from operator (manager_urls): **13**
- Apps reachable from tenant (tenant_urls): **22**
- Apps reachable from public (public_urls): **3**
- Apps reachable from api (api_urls): **1**
- Apps reachable from docs (docs_urls): **1**

## Surface totals (root URLconfs)

| Surface | Root URLconf | Direct routes | Reachable apps |
|---|---|---:|---:|
| operator | `config/manager_urls.py` | 71 | 13 |
| tenant | `config/tenant_urls.py` | 93 | 22 |
| public | `config/public_urls.py` | 250 | 3 |
| api | `config/api_urls.py` | 7 | 1 |
| docs | `config/docs_urls.py` | 4 | 1 |
| default | `config/urls.py` | 261 | 24 |

## Per-app rollup

| App | Routes | Tests | Surfaces | Help? | AI? | FB? | Tmpl dirs | Workflow tmpls |
|---|---:|---:|---|:-:|:-:|:-:|---:|---:|
| `api` | 222 | 94 | operator,tenant,public,api,default |   | ✓ |   | 0 | 0 |
| `schools` | 180 | 355 | operator,default | ✓ | ✓ | ✓ | 1 | 14 |
| `siteconfig` | 129 | 320 | operator,tenant,default |   | ✓ | ✓ | 1 | 20 |
| `accounts` | 121 | 101 | operator,tenant,public,docs,default |   | ✓ |   | 1 | 14 |
| `portal` | 120 | 149 | operator,tenant,default | ✓ | ✓ | ✓ | 1 | 13 |
| `migration_cloud` | 92 | 136 | operator,tenant,default |   | ✓ |   | 1 | 5 |
| `studio_os` | 48 | 74 | operator,tenant,default |   | ✓ |   | 1 | 15 |
| `platform_runtime` | 45 | 403 | operator,tenant,default |   | ✓ |   | 1 | 20 |
| `analytics` | 29 | 63 | tenant,default |   | ✓ |   | 1 | 0 |
| `finance` | 28 | 105 | tenant,default |   | ✓ |   | 1 | 2 |
| `compliance` | 26 | 46 | tenant,default |   |   |   | 1 | 1 |
| `apicenter` | 23 | 26 | operator,tenant,public,default | ✓ | ✓ |   | 1 | 1 |
| `evals` | 22 | 22 | tenant,default |   |   |   | 1 | 5 |
| `feedback` | 22 | 31 | operator,tenant,default | ✓ |   | ✓ | 1 | 0 |
| `marketplace` | 19 | 78 | tenant,default |   | ✓ |   | 1 | 10 |
| `communication` | 15 | 29 | tenant,default |   | ✓ |   | 1 | 5 |
| `integrations_marketplace` | 15 | 30 | default |   |   |   | 1 | 0 |
| `automation` | 11 | 42 | operator,tenant,default |   | ✓ |   | 1 | 0 |
| `reports` | 11 | 19 | tenant,default |   |   |   | 1 | 3 |
| `academics` | 10 | 12 | tenant,default |   |   |   | 1 | 2 |
| `orchestration` | 8 | 6 | default |   |   |   | 1 | 0 |
| `events` | 6 | 19 | tenant |   |   |   | 1 | 1 |
| `payroll` | 6 | 6 | tenant,default |   |   |   | 1 | 1 |
| `sales` | 5 | 4 | operator |   |   |   | 1 | 1 |
| `metadata` | 4 | 16 | operator,default |   |   |   | 1 | 0 |
| `requests` | 3 | 4 | tenant,default |   |   |   | 1 | 3 |
| `school_events` | 3 | 0 | tenant |   |   |   | 1 | 0 |
| `billing` | 0 | 20 | — |   |   |   | 0 | 0 |
| `brand_experience` | 0 | 8 | — |   |   |   | 0 | 0 |
| `customers` | 0 | 2 | — |   |   |   | 0 | 0 |
| `customersuccess` | 0 | 4 | — |   |   | ✓ | 1 | 1 |
| `dashboard` | 0 | 20 | — |   | ✓ |   | 0 | 0 |
| `global_registries` | 0 | 0 | — |   |   |   | 0 | 0 |
| `interop` | 0 | 6 | — |   |   |   | 0 | 0 |
| `locale` | 0 | 0 | — |   |   |   | 0 | 0 |
| `observability` | 0 | 17 | — |   | ✓ | ✓ | 1 | 1 |
| `packages` | 0 | 6 | — |   |   |   | 0 | 0 |
| `people` | 0 | 19 | — |   | ✓ |   | 1 | 3 |
| `plans_entitlements` | 0 | 0 | — |   |   |   | 0 | 0 |
| `policies` | 0 | 8 | — |   |   |   | 0 | 0 |
| `policies_rules` | 0 | 0 | — |   |   |   | 0 | 0 |
| `registries` | 0 | 2 | — |   |   |   | 0 | 0 |
| `runtime_blueprints` | 0 | 0 | — |   |   |   | 0 | 0 |
| `schoolops` | 0 | 18 | — |   |   |   | 1 | 1 |
| `security` | 0 | 33 | — |   |   |   | 0 | 0 |
| `setup_studio` | 0 | 4 | — |   | ✓ |   | 0 | 0 |
| `social_media` | 0 | 4 | — |   |   |   | 0 | 0 |
| `student360` | 0 | 0 | — |   |   |   | 1 | 0 |
| `sync_engine` | 0 | 4 | — |   |   |   | 0 | 0 |
| `tenancy` | 0 | 18 | — |   |   |   | 0 | 0 |

## Honest gaps (signals, not classifications)

Phase 0 only flags _signals_. Classification (strong vs broken vs missing how-to) is Phase 1.

**Framing:** an app with zero routes and zero `urls.py` is NOT a defect. Many apps in this repo are model-only / service-only and surface through other apps' views. Those are listed in the **Service-only apps** section below, not in gaps.

### `routes_without_help_or_ai_signal` (12 apps)

  `academics`, `compliance`, `evals`, `events`, `integrations_marketplace`, `metadata`, `orchestration`, `payroll`, `reports`, `requests`, `sales`, `school_events`

### `routes_without_tests` (1 apps)

  `school_events`

### `templates_without_tests` (2 apps)

  `school_events`, `student360`

### `views_present_but_no_urls_file_check_inclusion` (5 apps)

  `customersuccess`, `observability`, `people`, `schoolops`, `student360`

### `workflow_templates_without_feedback_hook` (18 apps)

  `academics`, `accounts`, `apicenter`, `communication`, `compliance`, `evals`, `events`, `finance`, `marketplace`, `migration_cloud`, `payroll`, `people`, `platform_runtime`, `reports`, `requests`, `sales`, `schoolops`, `studio_os`

### `workflow_templates_without_help` (20 apps)

  `academics`, `accounts`, `communication`, `compliance`, `customersuccess`, `evals`, `events`, `finance`, `marketplace`, `migration_cloud`, `observability`, `payroll`, `people`, `platform_runtime`, `reports`, `requests`, `sales`, `schoolops`, `siteconfig`, `studio_os`

## Service-only apps (informational)

23 apps have no `*urls*.py` and no `path(...)` declarations. These are model / service / task layers that surface through other apps' views:

  `billing`, `brand_experience`, `customers`, `customersuccess`, `dashboard`, `global_registries`, `interop`, `locale`, `observability`, `packages`, `people`, `plans_entitlements`, `policies`, `policies_rules`, `registries`, `runtime_blueprints`, `schoolops`, `security`, `setup_studio`, `social_media`, `student360`, `sync_engine`, `tenancy`


## Related existing inventories (cross-reference)

- `docs/generated/academic_operations_workflow_audit.json` (3,607 bytes)
- `docs/generated/admin_config_domain_route_matrix.json` (11,555 bytes)
- `docs/generated/ai_center_platform_inventory.json` (10,851 bytes)
- `docs/generated/ai_tenant_studio_audit_first_inventory.json` (4,123 bytes)
- `docs/generated/control_plane_sweep_routes.json` (95,621 bytes)
- `docs/generated/end_to_end_app_route_inventory.json` (477 bytes)
- `docs/generated/orchestrator_code_truth_inventory.json` (9,021 bytes)
- `docs/generated/platform_inventory.json` (48,225 bytes)
- `docs/generated/platform_workflow_code_truth_inventory.json` (67,100 bytes)
- `docs/generated/portal_tenant_sweep_routes.json` (44,473 bytes)
- `docs/generated/route_click_targets.json` (13,882 bytes)
- `docs/generated/route_surface_audit.json` (7,155,179 bytes)
- `docs/generated/shell_surface_inventory_ledger.json` (7,232 bytes)
- `docs/generated/studio_os_code_truth_inventory.json` (6,534 bytes)
- `docs/generated/workflow_click_reduction_audit.json` (3,776 bytes)

## Phase 0 deferred (next waves)

- Workflow classification by audience (operator / tenant admin / teacher / parent / student / support / partner) — Phase 1
- Primary-action / next-best-action / blocker identification per workflow — Phase 1
- Current vs ideal step count per workflow — Phase 1
- How-to coverage gap classification (strong / usable / fragmented / broken / missing) — Phase 1
- Contextual information tag coverage audit — Phase 3
- AI workflow assistant coverage audit — Phase 8

**Verdict:** `PHASE_0_INVENTORY_READY`
