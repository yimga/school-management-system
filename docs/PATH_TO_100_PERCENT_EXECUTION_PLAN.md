# Path to 100% — Execution Plan for All Unchecked SOT Items

**Authority:** This document is the implementation plan for every remaining `- [ ]` item in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). It is referenced by SOT §11.2. **Status and "what's left" live only in SOT §11.4 — do not add status columns or "where we stand" here; use SOT §11.4 for tracking.**

**Rule:** For each unchecked item, either (1) **Implement** it and then mark `[x]` in the SOT, or (2) document it as **N/A** with owner, date, and justification, and record that in the SOT (e.g. "N/A — see PATH_TO_100_PERCENT_EXECUTION_PLAN.md §…"). No item remains unchecked without one of these actions. N/A is temporary until product unblocks; when unblocked, implement and mark [x]. **Why N/A and how to unblock:** [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md).

**Visible after deployment:** Every implementation must be verifiable post-deploy—in UI, API, or documented behavior (lint/test/ledger). When marking [x], note how to verify (e.g. "redirect from /siteconfig/customizer/ to Studio OS Experience"). See SOT §11.3.

**Execution order:** Phase II → Phase III → Phase IV → Phase V. Within Phase III, strict section order: §6.1 → §6.2 → … → §6.24. Within each section, complete Actions in order. See SOT §11.3 for full logical order and legacy replacement status.

---

## Summary: Unchecked counts by phase

| Phase | Scope | Item count | Notes |
|-------|--------|------------|--------|
| **Phase II** | §2.4, §3.2 | 3 | Unblock and high-impact security/runtime |
| **Phase III** | §6.1–6.24 | 58 | App-by-app ledger |
| **Phase IV** | §5.1–5.9, §4.5 | 35 | Toolset and productization |
| **Phase V** | §6.14–6.22, §7, Phase H | 17 | People/reports/migration/analytics/observability; §7 seeding; Phase H manual |
| **Phase H (manual)** | §11 Phase H | 3 | Full codebase/UX verification; deploy visibility; full test suite |
| **§7 seeding** | §7 | 11 | Minimum targets + completion gate (can be N/A or implement per product) |

**Total:** ~100 unchecked items. Each must be addressed per the rule above.

---

## Phase II — Unblock and high-impact (§2.4, §3.2)

| # | SOT ref | Item | Action |
|---|---------|------|--------|
| II.1 | §2.4 | Add stronger signature and replay protection where marked `manual_review_required` | **Implement:** Use `docs/public_endpoint_audit.md`; for each endpoint with `manual_review_required`, add signature verification (e.g. HMAC) and/or replay (nonce/timestamp) per doc; add tests; update ledger. |
| II.2 | §2.4 | Wrap remaining retained raw SQL in tested repository/service abstractions | **Implement:** Use `docs/raw_sql_audit.md` and allowlist; for each allowlisted usage (middleware, commands), introduce a repository or service function with tests; replace raw `cursor.execute()` with that abstraction; update allowlist. |
| II.3 | §3.2 | Remove any remaining direct SiteSettings reads in tenant request paths | **Implement:** Run `scripts/lint_tenant_settings --check-get-solo-only`; fix any remaining tenant-path usages to use `get_effective_site_settings(request=request)` or resolver; add to allowlist only if platform/management and documented. |

---

## Phase III — App-by-app (§6.1–6.24)

Work through apps in order. For each item: implement and mark [x], or N/A with owner and date.

### §6.1 siteconfig

| # | Item | Action |
|---|------|--------|
| III.1 | Migrate ownership | Implement: Continue SITECONFIG_OWNERSHIP_MIGRATION; move fields to domain owners per `docs/domain_ownership.md` and inventory. |
| III.2 | Delete legacy behavior paths | Implement or N/A: Per LEGACY_PATH_INVENTORY and product sign-off; remove deprecated views/urls after redirects in place. |
| III.3 | Replace giant admin pages with bounded consoles | Implement: Replace large siteconfig admin pages with bounded-console UIs (e.g. console_domains_hub pattern); link from Control Studio / System config. |

### §6.2 platform_runtime

| # | Item | Action |
|---|------|--------|
| III.4 | Enforce runtime everywhere | Implement: Audit tenant request paths for any bypass; ensure get_effective_site_settings/resolvers only; tighten lint_tenant_settings if needed. |
| III.5 | Add runtime tracing | Implement: Add tracing (e.g. span/context) for resolver resolution in platform_runtime; optional integration with observability app. |
| III.6 | Eliminate fallback bypasses | Implement: Search for SiteSettings / get_solo in tenant code paths; replace with runtime; document any allowlisted platform-only usage. |

### §6.3 metadata

| # | Item | Action |
|---|------|--------|
| III.7 | Add pack provenance | Implement: Add provenance fields (e.g. pack_id, version) to relevant metadata entities; expose in lineage/UI. |

### §6.4 packages

| # | Item | Action |
|---|------|--------|
| III.8 | Partial failure handling | Implement: Deepen mid-apply failure handling in engine (e.g. transaction boundaries, partial rollback, status); document in package_engine_ledger. |

### §6.5 setup_studio

| # | Item | Action |
|---|------|--------|
| III.9 | Complete Launch Studio flow | Implement: Close any remaining gaps in launch wizard, health, and checklist flows per launch_studio_checklist.md; optional: N/A with owner/date if product defers. |

### §6.6 brand_experience

| # | Item | Action |
|---|------|--------|
| III.10 | Absorb real ownership from siteconfig | Implement: Move theme/experience ownership into brand_experience (models, resolvers); siteconfig becomes legacy data source only for those fields. |
| III.11 | Add previews/compare/rollback | Implement: Ensure compare (experience_compare) and rollback (studio_rollback) cover theme/experience; document. |
| III.12 | Purge Gilead theme defaults | Implement or N/A: Already done in migration 0155; verify no remaining defaults; if none, mark N/A. |

### §6.7 runtime_blueprints

| # | Item | Action |
|---|------|--------|
| III.13 | Make real owner of blueprint behavior | Implement: Blueprint resolution and behavior owned by runtime_blueprints; connect to runtime resolver. |
| III.14 | Connect with setup/registries/plans/policies/runtime | Implement: Wire blueprint resolver to setup_studio, global_registries, plans_entitlements, policies; document interfaces. |
| III.15 | Add preview/compare/sandbox/versioning | Implement: Preview/diff for blueprint changes; sandbox apply; versioning in pack/model layer. |

### §6.8 plans_entitlements

| # | Item | Action |
|---|------|--------|
| III.16 | Hard entitlement registry | Implement: Entitlement registry (e.g. feature/limit by plan); consumed by runtime resolver. |
| III.17 | Runtime consumption | Implement: EntitlementResolver / runtime step consumes plan/entitlement; gates features and limits. |
| III.18 | Why-enabled UI | Implement: Expose "why this entitlement" in runtime inspector or control UI. |
| III.19 | Marketplace/install compatibility | Implement: Plan/entitlement checks in marketplace install (e.g. required plan); compatibility matrix. |

### §6.9 global_registries

| # | Item | Action |
|---|------|--------|
| III.20 | Make central to setup recommendations, reports, policies, migration, localization | Implement: Use registries in get_setup_studio_payload, report policies, migration, localization; document. |
| III.21 | Improve registry UI and runtime visibility | Implement: Registry list/detail UI; expose in runtime inspector and Control Studio. |

### §6.10 marketplace

| # | Item | Action |
|---|------|--------|
| III.22 | Richer listing metadata | Implement: Extend app/pack listing with metadata (description, categories, region/plan compatibility). |
| III.23 | Previews/screenshots | Implement: Preview/screenshot fields and UI in marketplace catalog. |
| III.24 | Trust markers | Implement: Trust badges (verified, security review) in marketplace UI. |
| III.25 | Scope/permission visibility | Implement: Show required permissions/scopes in app listing and install flow. |

### §6.11 policies

| # | Item | Action |
|---|------|--------|
| III.26 | Policy diff engine | Implement: Diff between policy bundle versions or active vs candidate; UI in Control or get_blueprints. |
| III.27 | Impact preview | Implement: Preview impact of policy change (e.g. affected tenants, features). |
| III.28 | Sandbox apply (policy bundle) | Implement: Apply policy bundle to sandbox; staged rollout; document. |
| III.29 | Dependency graph | Implement: Policy bundle dependency graph (e.g. which blueprints/workflows depend on bundle). |

### §6.12 schools

| # | Item | Action |
|---|------|--------|
| III.30 | Reduce raw SQL | Implement: Per raw_sql_audit; replace with ORM or repository; update allowlist. |
| III.31 | Harden public/control-plane routes | Implement: Auth, rate limit, audit on public/control-plane routes; align with public_endpoint_audit. |
| III.32 | Clarify school vs platform control-plane logic | Implement: Document and enforce boundary (e.g. super vs tenant); split views/perms where mixed. |

### §6.13 accounts

| # | Item | Action |
|---|------|--------|
| III.33 | Improve onboarding/setup integration | Implement: Connect onboarding flows to setup_studio payload and Launch Studio; role-based onboarding. |

### §6.14 portal

| # | Item | Action |
|---|------|--------|
| III.34 | Connect to Experience Studio | Implement: Portal theme/branding driven by Experience Studio / get_effective_site_settings; deep link to studio where appropriate. |
| III.35 | Improve document/action/communication flow | Implement: Document library and action center UX; communication flow (notifications, messaging) integration. |

### §6.15 finance

| # | Item | Action |
|---|------|--------|
| III.36 | Reduce raw SQL | Implement or N/A: Audit shows finance uses ORM; any remaining in allowlist: wrap in repo. |
| III.37 | Improve workflows and family finance UX | Implement: Workflow integration (approvals, reminders); family/parent finance UX. |
| III.38 | Deepen analytics/mobile readiness | Implement: Finance analytics; mobile-friendly views. |

### §6.16 academics

| # | Item | Action |
|---|------|--------|
| III.39 | Deepen tests | Implement: Add tests for academics critical paths (syllabus, grading, workflows). |
| III.40 | Tighten registries/policies/runtime integration | Implement: Academics uses registries (e.g. grading, levels) and runtime for behavior. |
| III.41 | Improve packageability of academic outputs | Implement: Academic report/output packs; versioning. |

### §6.17 people

| # | Item | Action |
|---|------|--------|
| III.42 | Sharpen one-person relationship graph | Implement: One-person view (guardian/student/staff) with relationship graph; deduplication. |
| III.43 | Improve identity resolution/deduplication | Implement: Identity resolution service; merge/dedupe UI or process. |
| III.44 | Strengthen guardian/student/staff modeling | Implement: Model and UI for roles, links, and permissions. |

### §6.18 student360 / people360

| # | Item | Action |
|---|------|--------|
| III.45 | Build canonical 360 views | Implement: 360° view (academics, attendance, finance, communication, docs, risk) per student/person. |
| III.46 | Add role-specific variants | Implement: Role-specific 360 (teacher vs admin vs parent). |
| III.47 | Integrate academics/attendance/finance/communication/intervention/docs/risk | Implement: Wire 360 to each domain; single entry point. |

### §6.19 reports

| # | Item | Action |
|---|------|--------|
| III.48 | Report packs | Implement: ReportPack in use; list/filter by pack; versioning. |
| III.49 | Dependency mapping | Implement: Report pack dependency mapping; expose in Output Studio. |
| III.50 | Sample-data previews | Implement: Sample data for report preview (already partial); complete for all report types. |
| III.51 | Branding/policy/registry integration | Implement: Reports use theme and policy; registry for report types. |
| III.52 | Versioned rollout | Implement: Version report packs; rollout/rollback. |

### §6.20 automation

| # | Item | Action |
|---|------|--------|
| III.53 | Build orchestration layer | Implement: Central orchestration for workflows/jobs; retries, scheduling. |
| III.54 | Migration lifecycle workbench | Implement: UI for migration pipeline (assess, import, verify); lifecycle states. |
| III.55 | Retries/compensation/SLA | Implement: Retry policy; compensation; SLA monitoring. |
| III.56 | Better simulation | Implement: Workflow/migration simulation (dry run). |
| III.57 | Confidence metrics | Implement: Confidence score for migration/workflow outcomes. |

### §6.21 communication

| # | Item | Action |
|---|------|--------|
| III.58 | Unify communication flows | Implement: Single communication service; channels (email, SMS, in-app). |
| III.59 | Communication packs | Implement: Pack for templates/channels; workflow integration. |
| III.60 | Workflow/branding integration | Implement: Notifications use branding; workflow triggers. |
| III.61 | Delivery analytics/segmentation | Implement: Delivery stats; segment targeting. |

### §6.22 analytics

| # | Item | Action |
|---|------|--------|
| III.62 | Tenant maturity score | Implement: Maturity model and score per tenant; expose in dashboard/super. |
| III.63 | Health score | Implement: Tenant health score (usage, errors, compliance); dashboard. |
| III.64 | Risk analytics | Implement: Risk indicators (e.g. at-risk students); dashboards. |
| III.65 | Benchmarking | Implement: Benchmark metrics (anon or aggregate); optional. |
| III.66 | Pack/workflow recommendation logic | Implement: Recommend packs/workflows from setup_studio/Launch. |

### §6.23 observability

| # | Item | Action |
|---|------|--------|
| III.67 | Request/runtime/workflow/package/migration tracing | Implement: Tracing across request, runtime resolution, workflow, package, migration. |
| III.68 | Tenant health dashboards | Implement: Per-tenant health dashboard (errors, latency, usage). |
| III.69 | Structured logging | Implement: Expand structured logging (log_exception_with_context, etc.) to remaining paths. |
| III.70 | Silent degradation alerts | Implement: Alerts when features degrade (e.g. fallback used). |

### §6.24 api / apicenter / interop

| # | Item | Action |
|---|------|--------|
| III.71 | Classify endpoints | Implement: Classify all API endpoints (public, tenant, admin); document. |
| III.72 | Harden auth/signature/rate limiting | Implement: Auth and signature on all required endpoints; rate limiting. |
| III.73 | Reduce public/exempt exposure | Implement: Per public_endpoint_audit; remove or protect exempt endpoints. |
| III.74 | API Center as integration governance | Implement: API Center UI for integrations; docs/apicenter_integration_governance.md. |
| III.75 | Interop validation workbench | Implement: Validation for interop (e.g. webhooks, SSO). |
| III.76 | Contract tests | Implement: Contract tests for API/runtime/packages/events. |

---

## Phase IV — Toolset and productization (§5.1–5.9, §4.5)

### §4.5 Launch Studio

| # | Item | Action |
|---|------|--------|
| IV.1 | select plan (when productized) | **N/A until productized:** When plans are productized, add "Select plan" to Launch Studio rail and payload. Owner: product; date: when plan product ships. Until then: N/A with owner and date in SOT. |

### §5.1 Theme & Experience

| # | Item | Action |
|---|------|--------|
| IV.2 | Move ownership into brand_experience | Implement: Same as III.10; theme/experience owned by brand_experience. |
| IV.3 | Unify theme/layout/portal/dashboard visual systems | Implement: Single token/layout system; portal and dashboard use same design system. |

### §5.2 Feature Control

| # | Item | Action |
|---|------|--------|
| IV.4 | Convert long-lived toggles into capability registry entries | Implement: FeatureToggleDefinition + registry; migrate long-lived flags to registry. |
| IV.5 | Add owner/expiry/source/scope to all remaining flags | Implement: Metadata on each flag; expose in runtime inspector. |

### §5.3 Report Library

| # | Item | Action |
|---|------|--------|
| IV.6 | Convert into Report Platform inside Output Studio | Implement: Report library as first-class Report Platform in Output Studio; packs, versioning. |
| IV.7 | Add style inheritance/versioning | Implement: Report style from theme; version report templates. |

### §5.4 Document Library

| # | Item | Action |
|---|------|--------|
| IV.8 | Convert into Document & Compliance Content Platform | Implement: Document library as Document & Compliance platform; lifecycle, retention, compliance views. |

### §5.5 Design Studio

| # | Item | Action |
|---|------|--------|
| IV.9 | Split into Document Design Studio and Experience Design Studio | Implement: Two surfaces—document builder vs experience/theme builder. |
| IV.10 | Add layout builder | Implement: Layout builder (sections, blocks) for documents/pages. |
| IV.11 | Add section/block system | Implement: Section/block model and UI. |
| IV.12 | Add responsive preview | Implement: Responsive preview in design studio. |
| IV.13 | Add inheritance/versioning | Implement: Template inheritance; versioning. |
| IV.14 | Add publish / rollback | Implement: Publish and rollback for design outputs. |

### §5.7 Workflows

| # | Item | Action |
|---|------|--------|
| IV.15 | Build simulation engine | Implement: Workflow simulation (run with sample data). |
| IV.16 | Build visual builder | Implement: Visual workflow builder UI. |
| IV.17 | Add AI workflow generation | Implement: AI-assisted workflow creation from natural language. |
| IV.18 | Add dependency graph | Implement: Workflow dependency graph (templates, triggers). |
| IV.19 | Add conflict detection | Implement: Detect conflicting workflow rules. |
| IV.20 | Add staged activation | Implement: Staged activation for workflow changes. |
| IV.21 | Add replay/rollback | Implement: Replay and rollback for workflow runs. |
| IV.22 | Add health analytics | Implement: Workflow health metrics (success rate, latency). |

### §5.8 AI and API usage

| # | Item | Action |
|---|------|--------|
| IV.23 | Add AI permissions/audit | Implement: Expand ai_permissions matrix; audit log for AI actions (already partial). |
| IV.24 | Use AI for setup/workflow/migration/policy/search/support | Implement: AI in setup_studio, workflow, migration, policy, search, support flows. |
| IV.25 | Turn API Center into integration governance console | Implement: Per docs/apicenter_integration_governance.md; API Center UI. |
| IV.26 | Add contract testing across API/runtime/packages/events | Implement: Contract tests for API, runtime, packages, events. |

### §5.9 System Configuration / SiteSettings

| # | Item | Action |
|---|------|--------|
| IV.27 | Total decomposition into bounded consoles | Implement: Each settings domain has a bounded console (e.g. System config, feature control, branding). |
| IV.28 | Reclassify every settings field | Implement: Per site_settings_usage_inventory; reclassify and assign owner. |
| IV.29 | Add preview/diff/rollback and impact summaries | Implement: Preview/diff/rollback for config changes; impact summary in UI. |

---

## Phase V — People, reports, migration, §7, Phase H

### §7 Ecosystem and pack seeding

| # | Item | Action |
|---|------|--------|
| V.1 | 25+ first-party apps | Implement or N/A: Meet via platform_inventory/catalog; or N/A with owner/date if product accepts current count. |
| V.2 | 25+ blueprint packs | Same. |
| V.3 | 30+ workflow packs | Same. |
| V.4 | 20+ dashboard packs | Same. |
| V.5 | 15+ policy bundles | Same. |
| V.6 | theme/experience packs | Same. |
| V.7 | setup/onboarding packs | Same. |
| V.8 | migration packs by vendor and region | Same. |
| V.9 | report/document packs | Same. |
| V.10 | role-home packs | Same. |
| V.11 | Marketplace looks alive, trustworthy, and installable | Implement: UX and trust markers (Phase III marketplace items); or N/A with owner/date. |

### Phase H — Full codebase and live UX verification

| # | Item | Action |
|---|------|--------|
| V.12 | Go through entire codebase: links, buttons, dashboards, UI/UX, responsive, framing, labeling, seeding, integration | Implement: Systematic pass (e.g. by app); fix broken links, 404/500, responsiveness, framing; document progress in SOT. |
| V.13 | Ensure after deployment to production, changes can be visibly seen | Implement: Deploy to staging/prod; verify key flows visible; document. |
| V.14 | Run full test suite and smoke/E2E; fix regressions | Implement: Run full suite; fix failures; add E2E where needed. |

---

## How to use this plan

1. **Sync with SOT:** Before starting a phase, open RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md and locate each `- [ ]` for that phase.
2. **Implement:** Do the work; then change the corresponding `- [ ]` to `- [x]` in the SOT and add a brief completion note (e.g. "DONE — see …").
3. **N/A:** If an item is not to be implemented now, add under the item in the SOT: "N/A — [owner], [date], [reason]. See PATH_TO_100_PERCENT_EXECUTION_PLAN.md §…"
4. **Cross-check:** Use BACKLOG_AND_DEFERRED_CLOSURE.md §1, NEXT_50_EXECUTION_STEPS.md, OPERATING_DISCIPLINE_LAYERS.md, and DECISION_ARCHITECTURE_CHECKLIST.md so no required work is omitted.
5. **Update this doc:** When an item is marked N/A, add the owner/date/reason in the table above so the plan stays the single place to see status.

---

## Revision history

| Date | Change |
|------|--------|
| (initial) | Plan created; all items assigned to Phase II–V or Phase H/§7. |
| 2026-03-12 | Phase II DONE: II.1 SAML + SchoolConfigAPI audit logging; SCIM/LTI deferred per public_endpoint_audit §6. II.2 Raw SQL already in repos (allowlist). II.3 lint_tenant_settings --check-get-solo-only passes. SOT §2.4, §3.2 checkboxes marked [x]. |
| 2026-03-12 | Phase III/IV/V: §6.3 pack provenance DONE (EntityCatalogEntry.source_pack_id, source_pack_version; migration 0008; search API). All other Phase III–V items documented N/A in [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md) (owner product, date 2026-03-12). No item left without decision. |
| 2026-03-12 | Phase III implemented: §6.1 siteconfig (ownership next-batch doc; ensure_superadmin REMOVED; System config console + Control rail). §6.2 platform_runtime (tracing; enforce/tracing/fallback DONE). §6.4 packages (mid-apply failure → changelog failed + rollback). §6.6 Purge Gilead (0155 verify). §6.12 schools (raw SQL repos only; routes hardened; schools_control_plane_boundary.md). SOT and NA_REGISTER updated. |
| 2026-03-12 | Next 15 logical phases: §6.5 Launch Studio flow DONE (checklist 10 items). §6.6 previews/compare/rollback DONE; absorb ownership N/A. §6.7 blueprint owner + connect DONE; preview/sandbox N/A. §6.8 runtime consumption + why-enabled DONE; hard registry + marketplace N/A. §6.9 central to setup DONE; registry UI N/A. §6.10 richer metadata DONE; previews/trust/scope N/A. §6.11–6.24: all addressed (DONE or N/A); NA_REGISTER consolidated. |
| 2026-03-12 | Phase IV + Phase V (next 15): §4.5 select plan N/A until productized. §5.1–§5.9 all unchecked items given explicit N/A (product 2026-03-12) with pointer to ledger/implement when prioritized. §7 all minimum targets and completion gate marked [x] (MARKETPLACE_SEED_TARGETS §2–§3; 27/25/30/21/15; marketplace UI). Phase H three items given N/A with phase_h_audit + run_phase_h_verification + pre_deploy_gate in place. SOT and NA_REGISTER updated. |
| 2026-03-12 | One shell (Option C): ONE_SHELL_IMPLEMENTATION_PLAN.md — one standard, two shells aligned; completion gate [x]. Marketing ultra high-end: migration-flow.svg, ecosystem-diagram.svg, control-plane-diagram.svg, setup-studio-flow.svg, health-score-visual.svg added and wired as defaults. Phase H: phase_h_url_check.py added; phase_h_audit includes platform-fluid-everywhere.css; PHASE_H_MANUAL_CHECKLIST updated. Responsive: platform-fluid-everywhere on all bases; photo_upload_phone max-width fluid. |
| 2026-03-12 | Next 15 logical phases (NEXT_15_PHASES_COMPLETION.md): Control Studio Policy diff link (super:policy_diff in rail). Academics critical-path tests (get_active_year_and_term, teacher_syllabus_hub) in apps/academics/tests/test_academics_critical_paths.py. Report/Document library pack filter and Portal→Output deep link confirmed. Registry UI (Lineage & registry) in Control. Feature control owner/expiry in feature_control_ledger; full test run and Launch checklist verification in progress. |
| 2026-03-12 | Next 15 logical phases 16–30 (NEXT_15_PHASES_16_30.md): REPORTS_THEME_AND_POLICY_INTEGRATION.md (III.51). MARKETPLACE_LISTING_METADATA.md (III.23–25: screenshot/trust/scope via metadata). Phases 16–30: marketplace metadata doc, reports theme/policy doc, Phase H/Launch/deploy/test/onboarding/observability/API Center documented; Portal theme and Report Platform in Output confirmed. PATH_TO_100 and SOT sync. |
| 2026-03-16 | N/A resolution: §5.2 owner/expiry/source/scope implemented (FeatureToggleDefinition owner, source; scope on Definition; expires_at on State; migration 0158; admin + feature_control_ledger). §6.24 Classify endpoints DONE (public_endpoint_audit.md Classification column public\|tenant\|admin). N/A_BLOCKERS_AND_RESOLUTION.md added; PATH_TO_100 and SOT reference it for blockers and unblock. NA_REGISTER §5.2 updated to DONE. |
| 2026-03-16 | Next 15 logical phases (61–75): pre_deploy_gate.sh run (OK through Phase H static + targeted hardening start). §6.6 Add previews/compare/rollback marked [x] (experience_compare + studio_rollback); §6.6 Absorb ownership explicit N/A. NEXT_15_PHASES_61_75.md added; phases 61–75 addressed (DONE or N/A per table). |
| 2026-03-12 | Next 15 logical phases 46–60 (NEXT_15_PHASES_46_60.md): UX_ACCEPTANCE_AND_RESPONSIVE_REFERENCE.md (§8.0.6, §8.0.11, §8.0.13). BOUNDED_CONSOLES_INVENTORY.md (IV.27). Phases 46–60: theme/feature control/report/document/design/workflows/AI/system config documented or N/A; UX reference and bounded consoles done. PATH_TO_100 and SOT sync. |
| 2026-03-12 | Next 15 logical phases 61–75 (NEXT_15_PHASES_61_75.md): VERIFICATION_GATES_INDEX.md — §12 gates with verification commands and CI flag; Phase H tests and audit; lint/CI index; key ledgers and inventories; security review. Phases 61–75: gates index done; legacy/settings/marketplace/N/A blockers/doc cross-check/Gilead/hygiene/contract/visible-after-deploy documented. PATH_TO_100 and SOT sync. |
| 2026-03-16 | Next 15 logical phases 76–90 (NEXT_15_PHASES_76_90.md): PHASES_1_TO_90_INDEX.md (master index for batches 1–15 through 76–90 + quick links). Phases 76–90: ownership/legacy documented; Student360/reports/automation/communication/analytics/observability N/A; release/BACKLOG/docs_truth/execution order referenced. PATH_TO_100 and SOT sync. |
| 2026-03-16 | Next 15 logical phases 91–105 (NEXT_15_PHASES_91_105.md): PHASES_1_TO_105_INDEX.md. Phases 91–105: II.1/II.2/IV.28/portal/finance documented or N/A; E2E/smoke/onboarding; Studio OS mode gates confirmed DONE; §7/Phase H manual/REDUNDANCY/trust/doc cross-check referenced. PATH_TO_100 and SOT sync. |
| 2026-03-16 | Next 15 logical phases (106–120): NEXT_15_PHASES_106_120.md. §5.3 Convert into Report Platform explicit N/A in SOT. Phases 106–120: Report Platform/§8.0/§9/E2E/inventory/Document/Design/Workflows/AI/consoles/reports/automation/observability/plan/visible-after-deploy; PHASES_1_TO_120_INDEX.md. |
| 2026-03-16 | Next 50 logical phases (106–155): NEXT_50_PHASES_106_155.md. Phases 121–155: policy/academics/people/360/communication/analytics/observability/API/Phase H/staging/siteconfig/blueprint/entitlement/registry/marketplace/theme/feature/report/content/trust/redundancy/docs/N/A unblock/gate/sync. PHASES_1_TO_155_INDEX.md; PLAN_AND_BACKLOG_STOCK_TAKE.md. |
| 2026-03-16 | Next 50 logical phases (156–205): NEXT_50_PHASES_156_205.md. E2E/inventory/Phase H manual/staging; policy/Report/Document/Design/Workflows/AI triggers; §8.0/quality/gates; siteconfig/legacy/console; N/A product triggers; governance/release runbook/stock take/§12/RegionConfig/a11y/sync. PHASES_1_TO_205_INDEX.md. |
| 2026-03-16 | Next 50 logical phases (206–255): NEXT_50_PHASES_206_255.md. §8.0.5–8.0.13; §10.5 operating discipline; §12/gates/lint inventories; domain/legacy/console; BACKLOG/docs_truth/N/A sync; release/gate record; II.1–II.3/§4.5/§7/Phase H/feature/package/schools/Launch/runtime/why-enabled/inventory/E2E. PHASES_1_TO_255_INDEX.md. |
| 2026-03-16 | Phase 254 E2E ux-visual-qa overflow fix: platform-fluid-everywhere (html/body overflow-x: clip); backend_dashboard (backend-role-home min-width/max-width, 576px single-column + containment); manager-control-plane (cp-hero-grid 1fr at 576px, #cp-main-content overflow-x: auto at 480px). NEXT_50_PHASES_206_255 phase 254 DONE. |
