# Path to 100% — Execution Plan for All Unchecked SOT Items

**Authority:** This document is the implementation plan for every remaining `- [ ]` item in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). It is referenced by SOT §11.2.

**Rule:** For each unchecked item, either (1) **Implement** it and then mark `[x]` in the SOT, or (2) document it as **N/A** with owner, date, and justification, and record that in the SOT (e.g. "N/A — see PATH_TO_100_PERCENT_EXECUTION_PLAN.md §…"). No item remains unchecked without one of these actions.

**Execution order:** Phase II → Phase III → Phase IV → Phase V. Within each phase, follow the order below. Dependencies (e.g. §6.1 before §6.6 ownership) are noted where relevant.

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
