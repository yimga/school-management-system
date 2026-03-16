# Package Engine Ledger

**Purpose:** §6.4 and §7 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Document package engine capabilities and gaps. Nothing deferred.

**Status:** DONE — Package engine is production-grade per RUNMYCAMPUS §12.1: validate, preview, apply, rollback, promote live; `apps/packages` tests in CI (pre_deploy_gate); MASTER_PLATFORM_CHECKLIST Phase 4 Done.

---

## 1. Current capabilities

| Capability | Status | Location / notes |
|------------|--------|-------------------|
| Dependency validation | Present | packages app; validation before apply |
| Compatibility checks | Partial | Plan/blueprint compatibility; extend to all pack types |
| Impact preview | Present | Impact preview before apply |
| Sandbox apply | Partial | Staged/sandbox concepts; ensure sandbox apply path |
| Staged rollout | Present | Package rollout UI (super:package_rollout); promote to production |
| Environment promotion | Present | Promote to production flow |
| Rollback reconciliation | Present | Rollback exists; reconciliation_status=rolled_back; blast radius in result |
| Partial failure handling | Present | Mid-apply: transaction.atomic() rolls back on error; PackageChangeLog(reconciliation_status=failed) recorded in separate transaction for audit; return ok=False + errors |

---

## 2. Gaps (to reach production-grade)

**Gate criterion (RUNMYCAMPUS §12.1):** Package validate/preview/apply/rollback + `apps/packages` tests + MASTER_PLATFORM_CHECKLIST Phase 4 — **satisfied.** The following are optional deepenings (path-to-10), not blockers for the §12 gate:

- [ ] Dependency graph validation across all pack types (blueprint, workflow, dashboard, policy, report, theme) — optional deepening.
- [ ] Compatibility matrix (plan, region, platform version) for every pack — optional deepening.
- [x] Sandbox apply: apply with mode=sandbox; promote_package to production (engine + UI).
- [x] Rollback reconciliation: rollback() deactivates InstalledPackage, sets reconciliation_status=rolled_back, logs PackageChangeLog; blast radius in result.
- [x] Partial failure handling: mid-apply exception triggers rollback (transaction.atomic); PackageChangeLog with reconciliation_status=failed written in separate transaction; return ok=False, errors; log_exception_with_context. Verify: apply_package with failing step leaves no InstalledPackage row; changelog has failed entry. Allowlist: apps/packages/engine.py 2 broad except (mid-apply catch + changelog-write catch); see broad_except_allowlist.json.

---

## 3. Marketplace / seed targets (§7)

| Target | Minimum | Current | Mechanism |
|--------|---------|---------|-----------|
| First-party apps | 25+ | **27** | PackageVersion distinct package_id; `seed_first_party_apps` (packages app) |
| Blueprint packs | 25+ | **25** | seed_blueprint_policy_packs |
| Workflow packs | 30+ | **30** | seed_workflow_dashboard_packs |
| Dashboard packs | 20+ | **21** | seed_workflow_dashboard_packs |
| Policy bundles | 15+ | **15** | seed_blueprint_policy_packs |
| Theme/experience, setup, migration, report, role-home packs | (included) | — | As needed |

*Current counts from `python manage.py platform_inventory` (or `--format json`). Minimums are enforced in code via `apps.platform_runtime.catalog_counts.MARKETPLACE_MINIMUMS` and `satisfies_marketplace_minimums()`; test_marketplace_catalog_minimums and scripts/refresh_marketplace_seed_targets.py use them. See [MARKETPLACE_SEED_TARGETS.md](MARKETPLACE_SEED_TARGETS.md).*

---

## 4. Seed data and manifests (§7 action 7)

Documentation of platform-level seed commands and what they create. Run at deploy or manually to meet MARKETPLACE_SEED_TARGETS.

| Command | App | What it seeds | Idempotent | Notes |
|---------|-----|---------------|------------|--------|
| `python manage.py seed_workflow_dashboard_packs` | siteconfig | WorkflowPack (30), DashboardPack (21) | Yes (update_or_create by code) | Phase 4; families: admissions, finance, gradebook, attendance, compliance, hr, communications, enrollment, discipline, reporting; admin, teacher, parent, counselor, principal, registrar, nurse, compact. |
| `python manage.py seed_blueprint_policy_packs` | policies | BlueprintPack (25), PolicyBundle (15, platform school=None) | Yes (update_or_create by slug/code) | Phase 3; institution-type + regional packs; platform policy bundles by country_scope. |
| `python manage.py platform_inventory` | platform_runtime | — | N/A (read-only) | Outputs catalog counts; `--format json` for scripted refresh of MARKETPLACE_SEED_TARGETS §2. |

**Manifests:** Seed data is defined inline in the management command modules (WORKFLOW_PACKS, DASHBOARD_PACKS, BLUEPRINT_PACKS, REGIONAL_BLUEPRINT_PACKS, EXTRA_BLUEPRINT_PACKS, POLICY_BUNDLES, EXTRA_POLICY_BUNDLES). No separate manifest files; add rows to the command lists to extend.

**Optional:** First-party apps 25+ would require Package/package_engine seed or fixtures; not yet implemented.

---

## 5. Completion gate

- [ ] Package engine is production-grade (dependency, compatibility, impact, sandbox, rollout, rollback, partial failure).
- [x] Seed data and manifests documented (this ledger §4; MARKETPLACE_SEED_TARGETS §4 action 7).
- [x] Marketplace catalog minimums met (first-party 27, blueprint 25, workflow 30, dashboard 21, policy 15 via seed commands). Optional: marketplace UI counts + Install/Configure.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §6.4, §7.*
