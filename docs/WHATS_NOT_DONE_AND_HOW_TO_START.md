# What’s Not Done — and How to Start

**Source:** Every `- [ ]` in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) (SOT). Items marked N/A are in [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md); they still count as “not done” until implemented or formally closed.

**Total unchecked:** ~100 items across §4.5, §5, §6, §7, and Phase H. **Phase III §6.1–§6.24:** All addressed in SOT ([x] or N/A); remaining unchecked is mainly §4.5, §5, §7, Phase H.

**Doc cross-check:** To stay on track, use the checklist in SOT §11.3 (SOT, PATH_TO_100_PERCENT_EXECUTION_PLAN, NA_REGISTER, BACKLOG §6, docs_truth_ledger, LEGACY_PATH_INVENTORY, SUBTRACTIVE_CLEANUP_RELEASE_NOTES, this file). Every change must be **visible after deployment** (UI, API, or documented behavior); see SOT §11.3.

**Runtime-first / Phase 6:** SOT **§3.2** is **[x]** — **100% complete** (no partial). Evidence: `registry_snapshots.py` (entitlement + blueprint lifecycle + marketplace install registries), runtime inspector UI, `resolver_registry.py`, contract tests. [PHASE_6_RUNTIME_FIRST_ENFORCEMENT.md](PHASE_6_RUNTIME_FIRST_ENFORCEMENT.md) maps tasks to code.

**Reconciliation — §5 spine, Phase B, optional depth (authority: SOT §11.4):** In [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md), **§5.1–§5.9** toolset actions are **`[x]`** (repository spine). **Phase 5 ZIP** is **COMPLETE**. **Phase B physical migration:** **Batch 0 COMPLETE** (`0162_phase_b_slim_sitesettings` + `RuntimeDefaults.payload` bridge); **Batches 1+** are incremental and tracked in [SITECONFIG_OWNERSHIP_MIGRATION.md](SITECONFIG_OWNERSHIP_MIGRATION.md) (*Phase B batch progress*). **§5.x / §11.4 “full product” depth** (extra report SKUs, full diff UI, deeper simulation, full layout builder, etc.) is **optional release cadence** — not open PARTIAL gates. If a bullet below conflicts with the SOT, **the SOT wins**.

---

## 1. What is NOT done (by section)

### §4.5 Launch Studio
- [ ] **Select plan** — required when plans are productized; N/A until then.

### §5.1–§5.9 Toolset (summary)
- **SOT status:** All §5.x **Actions** lists are **`[x]`** in SOT §5 (spine + “when prioritized” notes for deeper product work).
- **Still incremental:** Phase B **Batches 1+** (move columns into bounded contexts) — not the same as unchecked §5 checkboxes.
- **Optional:** “Full” Report Platform, full config diff UI, full workflow builder depth, etc. — ship per **§11.4** product planning.

### §6.1 siteconfig
- [ ] Migrate ownership (continue SITECONFIG_OWNERSHIP_MIGRATION)
- [ ] Delete legacy behavior paths (per product sign-off)
- [ ] Replace giant admin pages with bounded consoles

### §6.2 platform_runtime
- [ ] Enforce runtime everywhere
- [ ] Add runtime tracing
- [ ] Eliminate fallback bypasses

### §6.4 packages
- [ ] Partial failure handling (deepen mid-apply handling)

### §6.5 setup_studio
- [ ] Complete Launch Studio flow

### §6.6 brand_experience
- [ ] Absorb real ownership from siteconfig
- [ ] Add previews/compare/rollback (theme/experience)
- [ ] Purge Gilead theme defaults (verify; 0155 done)

### §6.7 runtime_blueprints
- [x] Make real owner of blueprint behavior — **DONE** (runtime `_step4_blueprint`; `tenant_blueprint` accessor; inspector)
- [x] Connect with setup/registries/plans/policies/runtime — **DONE**
- [x] Preview/compare/sandbox/versioning — **DONE** (sandbox/preview flag merge + route; **blueprint_lifecycle** snapshot: pack version vs `PolicyBundle.applied_pack_version`, `pack_update_needed`; command `update_blueprint_bundles`)

### §6.8 plans_entitlements
- [x] Hard entitlement registry — **DONE** (`registry_snapshots.build_entitlement_registry_snapshot`; inspector **Entitlement registry** card; `EntitlementRegistrySnapshot` in `resolver_registry.py`)
- [x] Runtime consumption (EntitlementResolver) — **DONE** (`_step6_flags_entitlements`, `runtime.entitlements`)
- [x] Why-enabled UI — **DONE** (inspector + toggles + entitlements_why + canonical registry)
- [x] Marketplace/install compatibility — **DONE** (`marketplace_install_registry` snapshot from runtime step 10; inspector **Marketplace install registry** card)

### §6.9 global_registries
- [ ] Make central to setup recommendations, reports, policies, migration, localization
- [ ] Improve registry UI and runtime visibility

### §6.10 marketplace
- [ ] Richer listing metadata, previews/screenshots, trust markers
- [ ] Scope/permission visibility

### §6.11 policies
- [ ] Policy diff engine, impact preview
- [ ] Sandbox apply (policy bundle)
- [ ] Dependency graph

### §6.12 schools
- [ ] Reduce raw SQL, harden public/control-plane routes
- [ ] Clarify school vs platform control-plane logic

### §6.13 accounts
- [ ] Improve onboarding/setup integration

### §6.14 portal
- [ ] Connect to Experience Studio
- [ ] Improve document/action/communication flow

### §6.15 finance
- [ ] Reduce raw SQL (if any), improve workflows and family finance UX
- [ ] Deepen analytics/mobile readiness

### §6.16 academics
- [ ] Deepen tests, tighten registries/policies/runtime integration
- [ ] Improve packageability of academic outputs

### §6.17 people
- [ ] Sharpen one-person relationship graph
- [ ] Improve identity resolution/deduplication
- [ ] Strengthen guardian/student/staff modeling

### §6.18 student360 / people360
- [ ] Build canonical 360 views, role-specific variants
- [ ] Integrate academics/attendance/finance/communication/intervention/docs/risk

### §6.19 reports
- [ ] Report packs, dependency mapping, sample-data previews
- [ ] Branding/policy/registry integration, versioned rollout

### §6.20 automation
- [ ] Orchestration layer, migration lifecycle workbench
- [ ] Retries/compensation/SLA, better simulation, confidence metrics

### §6.21 communication
- [ ] Unify communication flows, communication packs
- [ ] Workflow/branding integration, delivery analytics/segmentation

### §6.22 analytics
- [ ] Tenant maturity score, health score
- [ ] Risk analytics, benchmarking
- [ ] Pack/workflow recommendation logic

### §6.23 observability
- [ ] Request/runtime/workflow/package/migration tracing
- [ ] Tenant health dashboards
- [ ] Structured logging (expand), silent degradation alerts

### §6.24 api / apicenter / interop
- [ ] Classify endpoints, harden auth/signature/rate limiting
- [ ] Reduce public/exempt exposure
- [ ] API Center as integration governance
- [ ] Interop validation workbench, contract tests

### §7 Ecosystem and pack seeding
- [ ] Minimum targets: 25+ apps, 25+ blueprints, 30+ workflows, 20+ dashboards, 15+ policy bundles, theme/setup/migration/report/role-home packs
- [ ] Completion gate: Marketplace looks alive, trustworthy, installable

### §11 Phase H (manual)
- [ ] Full codebase pass: links, buttons, dashboards, 404/500, UI/UX, responsive, framing, labeling, seeding
- [ ] After deployment: changes visibly seen and behave as intended
- [ ] Run full test suite and smoke/E2E; fix regressions

---

## 2. What we need to do to start getting things done

### Use the existing plan and order
- **Execution plan:** [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) — every item has an **Action** (Implement steps or N/A).
- **Order:** Phase III → Phase IV → Phase V (Phase II is done). Within each phase, work **app-by-app** in section order (§6.1, §6.2, …).

### Suggested starting sequence (high impact, lower risk)

1. **Pick one app and finish it**
   - Example: **§6.12 schools** — “Reduce raw SQL” (use [raw_sql_audit.md](raw_sql_audit.md)), “Harden public/control-plane routes” (use [public_endpoint_audit.md](public_endpoint_audit.md)), “Clarify school vs platform control-plane logic” (doc + split views if needed).
   - When done: mark the three §6.12 items `[x]` in the SOT and add a one-line note.

2. **One toolset slice**
   - Example: **§5.2 Feature Control** — “Convert long-lived toggles into capability registry entries” and “Add owner/expiry/source/scope to all remaining flags” (see [feature_control_ledger.md](feature_control_ledger.md)).
   - Unblocks “why enabled?” and control-plane clarity.

3. **One Phase H slice**
   - Run `python scripts/phase_h_audit.py --verbose` and fix **one** category (e.g. all pages missing `data-page-archetype`, or one app’s broken links).
   - Then run `python manage.py test apps.accounts.tests.test_phase_h_ux_verification` and fix any failures.

4. **Revisit N/A items when product prioritizes**
   - [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md) lists items deferred with owner and date. When product says “do X,” find X in the SOT and in the execution plan, implement it, then mark `[x]` and remove or update the N/A row.

### Concrete “start today” checklist
- [ ] Open [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) and pick **one** Phase III section (e.g. §6.12 schools).
- [ ] Open the SOT at that section and the linked ledgers (e.g. raw_sql_audit, public_endpoint_audit).
- [ ] Implement the first unchecked action for that section; mark it `[x]` in the SOT with a short note.
- [ ] Run `bash scripts/pre_deploy_gate.sh` to ensure nothing regressed.
- [ ] Repeat with the next action or next section.

### Where things live
| Need to… | Use |
|----------|-----|
| See every unchecked item with implement/N/A | [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) |
| See what’s deferred with owner/date | [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md) |
| Single source of truth (all checkboxes) | [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) |
| Phase H verification | [PHASE_H_UX_VERIFICATION.md](PHASE_H_UX_VERIFICATION.md), `scripts/phase_h_audit.py` |
| Raw SQL / public endpoints / feature control | [raw_sql_audit.md](raw_sql_audit.md), [public_endpoint_audit.md](public_endpoint_audit.md), [feature_control_ledger.md](feature_control_ledger.md) |
| **Unblock any N/A item** | [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md) — concrete steps and key files per category |
| **Declare plan done** | [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) "Release sign-off"; [launch_studio_checklist.md](launch_studio_checklist.md) §4 staging run |

---

*Cross-reference: SOT §11.2, PATH_TO_100_PERCENT_EXECUTION_PLAN.md, NA_REGISTER_PATH_TO_100.md.*
