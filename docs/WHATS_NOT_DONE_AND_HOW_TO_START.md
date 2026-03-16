# What’s Not Done — and How to Start

**Source:** Every `- [ ]` in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) (SOT). Items marked N/A are in [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md); they still count as “not done” until implemented or formally closed.

**Total unchecked:** ~100 items across §4.5, §5, §6, §7, and Phase H. **Phase III §6.1–§6.24:** All addressed in SOT ([x] or N/A); remaining unchecked is mainly §4.5, §5, §7, Phase H.

**Doc cross-check:** To stay on track, use the checklist in SOT §11.3 (SOT, PATH_TO_100_PERCENT_EXECUTION_PLAN, NA_REGISTER, BACKLOG §6, docs_truth_ledger, LEGACY_PATH_INVENTORY, SUBTRACTIVE_CLEANUP_RELEASE_NOTES, this file). Every change must be **visible after deployment** (UI, API, or documented behavior); see SOT §11.3.

---

## 1. What is NOT done (by section)

### §4.5 Launch Studio
- [ ] **Select plan** — required when plans are productized; N/A until then.

### §5.1 Theme & Experience
- [ ] Move ownership into `brand_experience`
- [ ] Unify theme/layout/portal/dashboard visual systems

### §5.2 Feature Control
- [ ] Convert long-lived toggles into capability registry entries
- [ ] Add owner/expiry/source/scope to all remaining flags

### §5.3 Report Library
- [ ] Convert into Report Platform inside Output Studio
- [ ] Add style inheritance/versioning

### §5.4 Document Library
- [ ] Convert into Document & Compliance Content Platform

### §5.5 Design Studio
- [ ] Split into Document Design Studio and Experience Design Studio
- [ ] Add layout builder, section/block system, responsive preview
- [ ] Add inheritance/versioning, publish/rollback

### §5.7 Workflows
- [ ] Simulation engine, visual builder, AI workflow generation
- [ ] Dependency graph, conflict detection, staged activation
- [ ] Replay/rollback, health analytics

### §5.8 AI and API
- [ ] Add AI permissions/audit (beyond current gateway)
- [ ] Use AI for setup/workflow/migration/policy/search/support
- [ ] Turn API Center into integration governance console
- [ ] Add contract testing across API/runtime/packages/events

### §5.9 System Configuration
- [ ] Total decomposition into bounded consoles
- [ ] Reclassify every settings field
- [ ] Add preview/diff/rollback and impact summaries

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
- [ ] Make real owner of blueprint behavior
- [ ] Connect with setup/registries/plans/policies/runtime
- [ ] Add preview/compare/sandbox/versioning

### §6.8 plans_entitlements
- [ ] Hard entitlement registry
- [ ] Runtime consumption (EntitlementResolver)
- [ ] Why-enabled UI
- [ ] Marketplace/install compatibility

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

---

*Cross-reference: SOT §11.2, PATH_TO_100_PERCENT_EXECUTION_PLAN.md, NA_REGISTER_PATH_TO_100.md.*
