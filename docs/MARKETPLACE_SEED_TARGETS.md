# Marketplace Seed Targets (§7)

**Purpose:** §7 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Minimum pack/app counts so the marketplace looks alive, trustworthy, and installable.

**Status:** §3 completion gate satisfied; §12 gate MET when catalog minimums test + generate_platform_inventory --check in CI (see §5).

---

## 1. Minimum targets (from plan)

| Category | Minimum | Notes |
|----------|---------|--------|
| First-party apps | 25+ | Installable from marketplace; versioned |
| Blueprint packs | 25+ | School type / region blueprints |
| Workflow packs | 30+ | Approval, notification, automation |
| Dashboard packs | 20+ | Role-based dashboard templates |
| Policy bundles | 15+ | Grading, attendance, finance policies |
| Theme/experience packs | (included) | Theme packs, brand kits |
| Setup/onboarding packs | (included) | Guided flows, checklists |
| Migration packs | (by vendor/region) | Data migration templates |
| Report/document packs | (included) | Report templates, document packs |
| Role-home packs | (included) | Role-specific home layouts |

---

## 2. Current state (filled from catalog)

Run: `python manage.py platform_inventory` (text) or `python manage.py platform_inventory --format json` for scripted §2 refresh. Optional: `python scripts/refresh_marketplace_seed_targets.py` writes `docs/generated/marketplace_seed_counts.json` (with `_refreshed_at` timestamp); script validates minimums and exits 1 if not met. Minimums are defined in `apps.platform_runtime.catalog_counts.MARKETPLACE_MINIMUMS` (single source; must match this doc §1).

**Last refreshed:** 2026-03-13 (after seed_workflow_dashboard_packs + seed_blueprint_policy_packs; all catalog minimums met).

| Category | Current count | Minimum | Source |
|----------|---------------|---------|--------|
| First-party apps | **27** | 25+ | PackageVersion distinct package_id (`seed_first_party_apps`) |
| Blueprint packs | **25** | 25+ | runtime_blueprints.BlueprintPack (catalog) |
| Workflow packs | **30** | 30+ | siteconfig.WorkflowPack |
| Dashboard packs | **21** | 20+ | siteconfig.DashboardPack |
| Policy bundles | **15** | 15+ | policies.PolicyBundle |

*Counts from `platform_inventory`. All minimums met: first-party apps via `seed_first_party_apps`; blueprint, workflow, dashboard, policy via seed_blueprint_policy_packs + seed_workflow_dashboard_packs. Optional: script can parse `platform_inventory --format json` to sync this table.*

---

## 3. Completion gate (§7)

- [x] All minimum targets met or exceeded.
- [x] Marketplace UI shows counts and "Install" / "Configure" for each pack (counts via get_platform_catalog_counts on governance_console, app_catalog, tenant_app_catalog, blueprint_marketplace; Install to sandbox + Apply/Preview/Rollback in place).
- [x] Seed data and manifests documented in package_engine_ledger.

---

## 4. Action items (nothing left behind)

| # | Action | Owner / mechanism | Status |
|---|--------|-------------------|--------|
| 1 | First-party apps: reach 25+ (PackageVersion distinct package_id) | `python manage.py seed_first_party_apps` (packages app) | **DONE** (2026-03-13; 27 distinct package_id) |
| 2 | Blueprint packs: +10 (15 → 25+) | policies.BlueprintPack seed data or management command | **DONE** (seed_blueprint_policy_packs 2026-03-13) |
| 3 | Workflow packs: +23 (7 → 30+) | siteconfig.WorkflowPack seed data or management command | **DONE** (seed_workflow_dashboard_packs 2026-03-13) |
| 4 | Dashboard packs: +14 (6 → 20+) | siteconfig.DashboardPack seed data or management command | **DONE** (seed_workflow_dashboard_packs 2026-03-13) |
| 5 | Policy bundles: +5 (10 → 15+) | policies.PolicyBundle seed data or management command | **DONE** (seed_blueprint_policy_packs 2026-03-13) |
| 6 | Marketplace UI: show counts and Install/Configure per pack | get_platform_catalog_counts(); governance_console, app_catalog, tenant_app_catalog, blueprint_marketplace | **DONE** (counts in UI; Install to sandbox + Apply/Preview/Rollback) |
| 7 | Document all seed data and manifests in package_engine_ledger | Doc update when each seed is added | **DONE** (package_engine_ledger.md §4 + §3 table 2026-03-13) |

*When an action is completed, mark Status as DONE and reference the commit or doc. §5–§7 toolset/app actions and ecosystem seeding map here.*

---

## 5. §12 gate: marketplace/packs deeply productized

**RUNMYCAMPUS §12 and BACKLOG §6.3.** The gate is **MET** when all of the following hold:

- **§3 completion gate** above is satisfied (all [x]: minimums met, marketplace UI counts and Install/Configure, seed data documented).
- **Marketplace UI counts and Install/Apply/Preview/Rollback** are **required** (not optional): counts via `get_platform_catalog_counts()` on governance_console, app_catalog, tenant_app_catalog, blueprint_marketplace; Install to sandbox + Apply/Preview/Rollback in place.
- **Catalog minimums test** passes: `apps.platform_runtime.tests.test_marketplace_catalog_minimums` asserts `get_platform_catalog_counts()` meets MARKETPLACE_SEED_TARGETS minimums (25+ first-party apps, 25+ blueprint packs, 30+ workflow packs, 20+ dashboard packs, 15+ policy bundles). Test is in `scripts/pre_deploy_gate.sh` (TARGETED_HARDENING_TESTS); it seeds the test DB via setUpModule then asserts.
- **`python scripts/generate_platform_inventory.py --check`** runs in CI (pre_deploy_gate).

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §7, §12.*
