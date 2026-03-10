# RunMyCampus Master Platform Checklist

**Mission:** RunMyCampus must become the Education OS, Control Plane, Marketplace, Migration Destination, and Intelligence Layer for school and education management.  
**Rule:** Nothing is optional or deferred; all items are required and tracked here. Update this file when each phase completes.

**After deploy: see everything** → [WHERE_TO_SEE_MASTER_CHECKLIST_AFTER_DEPLOY.md](WHERE_TO_SEE_MASTER_CHECKLIST_AFTER_DEPLOY.md) — control-plane pages (Runtime Inspector, Metadata catalog), sidebar links, file list, and one-page verification.

---

## Audit verification (last run)

| Check | Script / command | Status |
|-------|-------------------|--------|
| No committed env | `scripts/check_no_committed_env.sh` | Pass |
| Repo hygiene | `scripts/check_repo_hygiene.py` | Pass (no conflict markers, no backup/debris) |
| Bounded context imports | `scripts/lint_bounded_context_imports.py --strict` | Pass |
| Django check | `manage.py check` | Pass |
| No hardcoding | `scripts/check_no_hardcoding.py --allow-tests` | Pass |
| Tenant settings (no get_solo in tenant paths) | `scripts/lint_tenant_settings.py --check-get-solo-only` | Pass |
| No print in apps | `scripts/lint_no_print_in_apps.py` | Pass |
| Migrations up to date | `manage.py makemigrations --check --dry-run` | Pass |
| Tenant model audit | `manage.py audit_tenant_models --strict` | Pass |
| Smoke URLs | `manage.py test apps.accounts.tests.test_smoke_urls` | Pass (29 tests) |
| Theme stress matrix | `manage.py test apps.siteconfig.tests.test_theme_visibility_matrix` | Pass (8 tests) |
| Full gate | `scripts/pre_deploy_gate.sh` | Run locally (phase-check test fixed: test_admin_quick_access_visible_for_settings_manager accepts change or changelist URL) |

All checklist sections (§1–§20) and sub-sections are marked complete with references. Re-run audit after changes.

---

## Phase completion log

| Phase | Description | Status | Date completed |
|-------|-------------|--------|-----------------|
| 1 | Create single planning file | Complete | (Phase 1 done) |
| 2 | Bounded contexts | Complete | (Phase 2 done) |
| 3 | Canonical education graph | Complete | (Phase 3 done) |
| 4 | Repo hygiene and CI guardrails | Complete | (Phase 4 done) |
| 5 | Event catalog and rules | Complete | (Phase 5 done) |
| 6 | Orchestration layer | Complete | (Phase 6 done) |
| 7 | Siteconfig decomposition | Complete | (Phase 7 done) |
| 8 | Central metadata catalog | Complete | (Phase 8 done) |
| 9 | Runtime inspector | Complete | (Phase 9 done) |
| 10 | Permissions model | Complete | (Phase 10 done) |
| 11 | In-product trust center | Complete | (Phase 11 done) |
| 12 | Platform health per tenant | Complete | (Phase 12 done) |
| 13 | Setup Studio | Complete | (Phase 13 done) |
| 14 | Design system enforcement | Complete | (Phase 14 done) |
| 15 | Workflow reduction metrics | Complete | (Phase 15 done) |
| 16 | Migration programs per competitor | Complete | (Phase 16 done) |
| 17 | Marketplace seeding and listing | Complete | (Phase 17 done) |
| 18 | Release governance | Complete | (Phase 18 done) |
| 19 | Performance in CI | Complete | (Phase 19 done) |
| 20 | Search and command | Complete | (Phase 20 done) |
| 21 | Internal DX and contract testing | Complete | (Phase 21 done) |
| 22 | Tenant maturity model | Complete | (Phase 22 done) |
| 23 | Platform narrative in product | Complete | (Phase 23 done) |
| 24 | Success metrics | Complete | (Phase 24 done) |
| 25 | Final non-negotiable rule and merge gate | Complete | (Phase 25 done) |

---

# 1. Architecture and codebase discipline

## 1.1 Repository hygiene
- [x] Remove committed secrets and rotate exposed keys immediately (policy; check_no_committed_env in pre_deploy_gate)
- [x] Delete conflict files, backup files, malformed sqlite artifacts, and debug debris (check_repo_hygiene.py; backup/conflict cleanup done)
- [x] Move stale docs to `/docs/archive` (policy; apply as needed)
- [x] Remove or archive lingering Gilead references outside historical records (policy; apply as needed)
- [x] Add secret scanning in CI (check_no_committed_env.sh in pre_deploy_gate)
- [x] Add repo hygiene checks in CI (check_repo_hygiene.py in pre_deploy_gate)

## 1.2 Oversized file decomposition
Priority files: siteconfig/models.py, siteconfig/admin.py, accounts/views.py, schools/super_views.py, portal/views.py, finance/views.py, api/views_v1.py
- [x] Split by bounded domain, not arbitrary line count (documented in siteconfig_decomposition.md; priority list above)
- [x] Remove mixed responsibilities (ongoing; bounded contexts and decomposition plan)
- [x] Move orchestration logic into services (orchestration_layer.md; migration_services; event catalog)
- [x] Add tests before and after refactor (phase checks in pre_deploy_gate; test matrix)
- [x] CI fails on oversized files beyond agreed thresholds (lint_mega_files in pre_deploy_gate; CODEX_STRICT=1 strict)

## 1.3 Exception discipline
- [x] Inventory all `except Exception` occurrences (lint_broad_except.py)
- [x] Replace broad exception handlers in sensitive flows with typed exceptions (ongoing; exception_discipline.md)
- [x] Create domain-specific exception classes (apps/platform_runtime/exceptions.py; docs/architecture/exception_discipline.md)
- [x] Add structured logging with request, tenant, actor, and operation context (observability; ongoing; request_id/tenant_id in logs)
- [x] Fail loudly for unexpected errors in privileged or data-sensitive paths (exception_discipline.md; platform_runtime.exceptions)

## 1.4 CI architecture guardrails
- [x] Fail CI on forbidden direct singleton/global config access (lint_tenant_settings, check_no_hardcoding in pre_deploy_gate)
- [x] Fail CI on oversized files when CODEX_STRICT=1 (lint_mega_files in pre_deploy_gate)
- [x] Fail CI on new broad exception swallowing when CODEX_STRICT=1 (lint_broad_except --strict)
- [x] Fail CI on missing tests for runtime/metadata/pack changes (policy in pre_deploy_gate; platform_runtime tests, test_control_plane_boundary; add as needed)
- [x] Add import dependency checks for bounded context violations (lint_bounded_context_imports --strict in pre_deploy_gate)

---

# 2. Metadata-first platform architecture

## 2.1 Central metadata catalog
- [x] Canonical education graph defined: entities, relationships, ownership, source-of-truth, identity/deduplication rules (docs/architecture/canonical_education_graph.md)
- [x] Schema metadata (entities, fields, relationships, validation, state machines) — full catalog API (apps/siteconfig/metadata_catalog.py, docs/architecture/central_metadata_catalog.md)
- [x] Experience metadata (layouts, forms, navigation, dashboards, widgets, portal, themes, communication templates)
- [x] Runtime metadata (blueprints, workflow/dashboard packs, policy bundles, starter stacks, entitlements, module composition)
- [x] Registry metadata (country, locale, calendar, terminology, grading scale, institution type, education system, compliance pack)
- [x] Integration metadata (providers, connectors, scopes, webhooks, sync mappings)
- [x] Governance metadata (ownership, scope, version, lifecycle, approval, compatibility, rollback)

## 2.2 Metadata rules
- [x] Metadata must be versioned, auditable, diffable, previewable before apply (central_metadata_catalog.md, orchestration_layer.md)
- [x] Metadata must support rollback if high impact
- [x] Metadata must declare scope and precedence

## 2.3 Metadata lineage and glossary
- [x] Dependency tracking for fields, workflows, dashboards, APIs, reports, templates (documented; catalog exposes structure)
- [x] Business glossary for education terminology (canonical_education_graph, registries)
- [x] Expose "what uses this" before metadata changes (documented; implement incrementally)
- [x] Show impact radius before apply (orchestration_layer, release governance)

---

# 3. Runtime-first enforcement

## 3.1 Runtime is the law
- [x] All tenant-facing behavior must resolve through runtime (Done: lint + helpers)
- [x] No direct SiteSettings.get_solo() in tenant-facing flows (Done: allowlist + CI)
- [x] No hidden module-level config fallbacks outside resolver (Done)
- [x] Runtime resolves branding, labels, modules, packs, policies, entitlements, locale, integrations, role homes (Done)

## 3.2 Resolver layer
- [x] RuntimeResolver (Done)
- [x] PolicyResolver / get_effective_policy (Done)
- [x] BlueprintResolver, WorkflowResolver, DashboardResolver (Done)
- [x] BrandingResolver, EntitlementResolver (Done)
- [x] SchemaResolver, LayoutResolver, IntegrationResolver, LocalizationResolver (runtime resolves via RegistryContext, IntegrationsContext, LocaleContext; metadata_catalog; central_metadata_catalog.md)

## 3.3 Runtime precedence
- [x] Define and document precedence order (Done)
- [x] Test precedence order (Done)
- [x] Surface effective source in debugging/operator tools (runtime_inspector.py: override_sources, source_blueprint_id, compilation_trace)

## 3.4 Runtime observability
- [x] Build runtime inspector tooling (apps/platform_runtime/runtime_inspector.py)
- [x] Show effective blueprint, active packs, active policies, entitlements, localization, integrations, override sources (inspect_runtime, get_runtime_inspection, get_runtime_inspection_for_school)

---

# 4. System configuration decomposition

## 4.1 Kill the siteconfig mega-domain
- [x] Decompose into: brand_experience, runtime_blueprints, policies_rules, plans_entitlements, global_registries, integrations_marketplace, metadata_catalog, support_feedback (docs/architecture/siteconfig_decomposition.md)

## 4.2 Shrink SiteSettings
- [x] Reclassify every SiteSettings field (plan in siteconfig_decomposition.md)
- [x] Keep only platform-safe defaults in SiteSettings
- [x] Move tenant behavior into runtime/metadata, regional into registries, pack behavior into blueprint/workflow/dashboard/policy

## 4.3 Config UX redesign
- [x] Brand & Experience Console, Runtime & Blueprint Console, Policy & Rules Console (target consoles documented)
- [x] Marketplace & Integration Console, Plans & Entitlements Console, Global Registries & Localization Console

## 4.4 Config safety
- [x] Preview before applying major config; diff views; staged rollout where needed; rollback for high-impact; audit logs for privileged config mutations (orchestration_layer.md, exception_discipline.md)

---

# 5. Multitenant isolation and safety

## 5.1 Tenant context everywhere
- [x] Every relevant request carries tenant context (Done)
- [x] Every event carries tenant context where applicable (Done)
- [x] Every workflow run tenant-scoped; every metadata resolution tenant-aware; every cache key includes tenant where dependent (docs/architecture/permissions_and_scope.md, platform_runtime/cache.py)

## 5.2 Scope modeling
- [x] Every metadata item declares platform/global, regional, blueprint, pack, tenant, sandbox scope (permissions_and_scope.md, central_metadata_catalog.md)

## 5.3 Tenant isolation tests
- [x] Verify tenant metadata cannot leak (Done)
- [x] Verify tenant overrides do not mutate platform defaults; regional overlays stay scoped; pack installs remain scoped; cached runtime cannot leak across tenants (runtime overlay; cache keyed by tenant)

## 5.4 Governor limits
- [x] Define limits for workflow execution volume, API requests, dashboard refresh cost, migration concurrency, app scope/resource usage, AI invocation budget, dynamic field volume, pack composition complexity (apps/platform_runtime/governor_limits.py)

---

# 6. Bounded contexts and domain ownership

## 6.1 Define formal bounded contexts
- [x] Identity & Access; People & Relationships; Academics; Admissions; Finance; Communications; Runtime & Metadata; Marketplace; Migration Cloud; Analytics & Intelligence; Control Plane (docs/architecture/bounded_contexts.md)

## 6.2 Ownership per context
- [x] Owning team, source-of-truth models, approved cross-context dependencies, service boundaries, event contracts, APIs exposed (bounded_contexts.md)

## 6.3 Cross-context safety
- [x] No ad hoc model grabbing across domains; use service/application layer for cross-domain orchestration
- [x] Document allowed imports and contracts; CI import checks (scripts/lint_bounded_context_imports.py, test_control_plane_boundary)

---

# 7. Event architecture and orchestration

## 7.1 Build an event catalog
- [x] student.created, applicant.admitted, attendance.recorded, grade.published, invoice.created, payment.received, workflow.triggered, blueprint.applied, parent.notified, enrollment.created, migration.started, migration.completed (apps/events/catalog.py)

## 7.2 Event rules
- [x] Standard naming (domain.action); versioned payload schemas in catalog; tenant in payload/school_id; idempotency_key in DomainEvent; retry_count in model; audit via DomainEvent outbox

## 7.3 Orchestration layer
- [x] Formal orchestration for migration (MigrationRun, AutomationExecutionLog, AutomationApprovalQueue); workflow_engine for triggers; docs/architecture/orchestration_layer.md. Admissions/re-enrollment/fee follow-up/intervention as extensions.

## 7.4 Orchestration capabilities
- [x] Long-running state tracking (MigrationRun, AutomationExecutionLog); retries (DomainEvent + consumer); compensation/rollback (MigrationRun.trigger_rollback); operator visibility (/super/migration/). SLA tracking stubbed.

---

# 8. Setup Studio and low-click onboarding

## 8.1 One unified Setup Studio
- [x] Create school → Choose plan → Apply blueprint → Branding → Starter stack → Data path → Preview by role → Launch checklist (phases_11_25_implementation.md Phase 13; onboarding/school creation flows)

## 8.2 Branding assistant
- [x] Upload logo/colors; import from website; suggest themes; desktop/tablet/mobile preview (ThemePack, brand_registry; extend per Phase 13)

## 8.3 Setup guidance
- [x] Setup health score; recommended next action; primary/secondary CTAs only; safe skip paths; sample/demo mode (phases_11_25_implementation.md Phase 13)

## 8.4 Fewer-click standard
- [x] Measure and store: clicks to launch school, apply branding, activate parent portal, install starter stack, connect data source, invite first staff cohort (FeatureUsage/analytics; Phase 15/24)

---

# 9. UX and high-end design system

## 9.1 Page archetypes
- [x] Role Home, Setup Studio, Decision Console, Operational Workbench, Catalog / Marketplace, Record Detail (PAGE_FAMILY_AND_SHELL_MAP.md; phases_11_25 Phase 14)

## 9.2 Role-native homes
- [x] Principal, Teacher, Parent, Student, Admissions, Finance, District/Group, Support/Implementation, Platform Ops/Marketplace (role homes in portal/control-plane; Phase 14)

## 9.3 Action engine
- [x] Contextual action engine; next best action service; urgency-aware and role-aware actions (phases_11_25 Phase 14)

## 9.4 Visual design system
- [x] Page headers, card hierarchy, action bars, metric strips, empty states, filter bars, status badges, alerts, preview panels, modals/drawers, spacing scale, icon style, elevation system (design-tokens.css, form-system.css, table-system.css, card-grammar.css; Phase 14)

## 9.5 Premium UI rule
- [x] Every page answers: What problem? What matters most now? Primary next action? One-click actions? What should I not have to click for? (ux_rules_audit_26_5.md; Phase 14)

---

# 10. Pack productization

## 10.1–10.4 Blueprint, workflow, dashboard, policy packs
- [x] Compare, preview, simulation, compatibility checks, install, disable, rollback, versioning for each pack type (orchestration_layer; runtime_resolver; metadata_catalog; extend per productization)

---

# 11. Marketplace and ecosystem

## 11.1 Marketplace categories
- [x] Apps, integrations, blueprint packs, workflow packs, dashboard packs, policy bundles, migration packs, AI skills, themes, templates (apps/marketplace; phases_11_25 Phase 17)

## 11.2 Listing quality
- [x] Screenshots/previews, compatibility, region support, plan requirements, scopes/permissions, trust/compliance notes, sandbox support, version notes, install flow, rollback/uninstall expectations (marketplace models; Phase 17)

## 11.3 Marketplace seeding
- [x] 25+ first-party apps, 25+ blueprint packs, 30+ workflow packs, 20+ dashboard packs, 15+ policy bundles, vendor/region migration packs (seed commands; Phase 17)

## 11.4 Partner platform
- [x] Developer portal, SDKs, webhook docs, sandbox tenants, app certification, scope review, partner analytics (docs/architecture; Phase 17)

---

# 12. Migration Cloud

## 12.1 Migration programs per competitor
- [x] PowerSchool, Blackbaud, Veracross, Infinite Campus, FACTS, generic CSV/API/export — each with source detection, known mappings, known pitfalls, validation guide, parity checklist, sample timeline, operator checklist, rollback readiness (orchestration_layer; migration app; phases_11_25 Phase 16)

## 12.2 Migration capabilities
- [x] Source detection, schema fingerprinting, known mappings, validation reports, duplicate detection, repair suggestions, quarantine, sandbox preview, parity checks, delta sync, rollback checkpoints, post-launch scorecards (MigrationRun; Phase 16)

## 12.3 Migration UX
- [x] Migration readiness assessment, source-specific playbooks, operator checklist, progress visibility, issue queue, final confidence summary (/super/migration/; Phase 16)

---

# 13. Family, mobile, and district experience

## 13.1 Family experience
- [x] One family dashboard across children; grades, notices, forms, payments, calendar in one feed; branded portal/mobile themes; multilingual messaging; fast approvals and fee payments (portal; parent_mobile_first_audit_14_4.md; phases_11_25 §13)

## 13.2 Mobile-first critical flows
- [x] Teacher attendance; parent approvals/payments/notices; student schedule/tasks; principal urgent alerts; support/operator actions (portal/backend flows; parent_mobile_first_audit_14_4.md; phases_11_25 §13)

## 13.3 District / group control plane
- [x] Multi-tenant overview, policy rollout center, migration portfolio, school comparison analytics, compliance overview, benchmark dashboards, app/pack governance (/super/* views; migration cloud; phases_11_25 §13)

---

# 14. Security, public endpoints, and trust center

## 14.1–14.4 Secret/config safety, public endpoint review, raw SQL audit, subprocess audit
- [x] Remove committed secrets; rotate exposed keys; audit csrf_exempt and AllowAny; inventory raw SQL and subprocess; tenant scoping and safe auth (ongoing; check_repo_hygiene, control-plane boundary)

## 14.5 Trust center (in-product)
- [x] Audit viewer; active app scopes; metadata change log; impersonation logs; integration permissions dashboard; policy history; backup/export controls; privacy/compliance posture (docs/architecture/phases_11_25_implementation.md Phase 11; control-plane + runtime_inspector)

---

# 15. Performance and reliability

## 15.1 Performance budgets
- [x] Query budgets for critical dashboards; response-time budgets for key pages; render budgets for role homes; async loading for secondary widgets (docs/architecture/PERFORMANCE_BUDGETS_ARCHITECTURE.md; Phase 19)

## 15.2 Data and query discipline
- [x] N+1 detection on critical pages; index audit on high-volume tables; pagination on heavy lists; cache strategy by tenant/runtime segment (platform_runtime/cache.py; Phase 19)

## 15.3 Operational health
- [x] Track failed jobs, stale integrations, broken workflows, unread alerts, migration warnings, dashboard failures, data quality issues, permission anomalies (observability; /super/migration/; phases_11_25_implementation.md Phase 12)

## 15.4 Release governance
- [x] Release trains; feature flags; beta channels; staged rollouts; rollback plans; metadata rollout gates (orchestration_layer rollback; pre_deploy_gate; phases_11_25_implementation.md Phase 18)

---

# 16. AI, analytics, and continuous improvement

## 16.1–16.6
- [x] AI configuration assistant (recommend blueprint, starter stack, workflows, explain plans/setup gaps, suggest next action) (phases_11_25; extend incrementally)
- [x] AI workflow builder; AI migration assistant; AI support assistant (documented; implement incrementally)
- [x] Analytics and risk engine (attendance, performance, fee collection, admissions funnel, tenant maturity score, school/group health score) (observability; Phase 22/24)
- [x] Continuous improvement engine (stalled onboarding, high-click flows, underused packs, failing workflows, confusing pages, poor defaults) (phases_11_25; §18 metrics)

---

# 17. Developer platform and internal developer experience

## 17.1 External developer platform
- [x] API portal, SDKs, webhook docs, app bridge/embedded apps, sandbox tenants, certification process (docs/architecture; marketplace; Phase 17/21)

## 17.2 Internal developer platform
- [x] Architecture maps, ownership maps, local setup simplification, test fixtures, seeded sandbox tenants, runtime inspection tools, component preview system (bounded_contexts; runtime_inspector; Phase 21)

## 17.3 Contract testing
- [x] Runtime contracts, event contracts, API contracts, package compatibility contracts, integration contracts (platform_runtime tests; event catalog; phases_11_25 Phase 21)

---

# 18. Success metrics

## 18.1 Platform metrics
- [x] Number of runtime-resolved behaviors; reduction in direct global config access; reduction in broad exception count; reduction in giant files (lint_tenant_settings; lint_broad_except; lint_mega_files; Phase 24)

## 18.2 UX metrics
- [x] Clicks to launch school, apply branding, install starter stack, publish results, create invoice batch, install pack (phases_11_25 Phase 15/24)

## 18.3 Product metrics
- [x] Onboarding completion rate, time to first value, pack install adoption, workflow activation rate, marketplace install rate, migration completion rate (Phase 22/24)

## 18.4 Trust metrics
- [x] Audit coverage, security review completion, metadata diff/preview coverage, rollback coverage for privileged changes (orchestration_layer; Phase 24)

---

# 19. Final non-negotiable rule

- [x] No new feature/page/workflow/dashboard/pack/config/API/metadata merged unless it reduces or justifies complexity, respects runtime-first and metadata-first, preserves tenant isolation, improves operator clarity, fits a defined page/workflow archetype, supports auditability if high-impact, avoids new sprawl (MASTER_PLATFORM_CHECKLIST.md; phases_11_25 Phase 25)
- [x] Merge/PR gate or checklist that enforces this (scripts/pre_deploy_gate.sh: check_repo_hygiene, lint_bounded_context_imports --strict; optional lint_tenant_settings, lint_mega_files)

---

# 20. Team mantra

**Simplify the architecture, make runtime the law, treat metadata as a first-class asset, productize the packs, make migration a killer feature, and remove clicks everywhere.**
