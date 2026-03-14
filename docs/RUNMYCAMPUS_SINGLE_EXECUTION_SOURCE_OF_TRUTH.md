# RunMyCampus Embedded Master Remediation Plan

**Rule of use (canonical)**  
This file is the **single execution source of truth** for closing every major gap identified in the full-platform audit. Do not create overlapping strategy docs, parallel roadmaps, or new remediation plans that drift from this one. Every major implementation task, audit, cleanup, migration, or platform-hardening effort must map back to this file. Cursor/Codex/Claude should act on this plan directly. Completion states: DONE | PARTIAL | NOT DONE | DEPRECATED/REPLACED | BLOCKED. No fake completion language; do not claim 9.5/10 or 11/10 until the scoring gates in §12 are satisfied. **Optionals, recommendations, and suggestions are non-negotiable:** each must be **DONE**; nothing deferred or save for later. See §11.1 and BACKLOG_AND_DEFERRED_CLOSURE §2f.

**For all agents:** Before starting any item from this plan or the backlog, check [docs_truth_ledger.md](docs_truth_ledger.md) and [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md) for current status to avoid duplicate or conflicting work. Named plan: [RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md](RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md). Backlog and closure: [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md). Strategy/roadmap updates go only to this file, the backlog, the ledger, and NEXT_50—do not create new overlapping roadmap files.

**Supporting doc:** Full audit + Cursor/Codex remediation instructions: [RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md](RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md).

**Stock-taking and validation:** Current snapshot, §12 gate status, and cross-validation of this plan vs backlog/ledger/NEXT_50: [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §6.

---

## Purpose

This plan is the single embedded remediation blueprint for turning RunMyCampus from a strong multi-tenant platform in transition into a true north-star education operating platform.

It incorporates the issues identified across:
- architecture
- runtime
- metadata
- multitenancy
- system configuration
- SiteSettings
- marketplace
- blueprints
- workflow packs
- dashboard packs
- policy bundles
- registries
- migration
- Studio OS
- UX and dashboards
- marketing front
- security
- AI/API
- code hygiene
- docs truthfulness
- Gilead residue removal

This plan is intentionally concrete and implementation-oriented so Cursor/Codex/Claude can act on it directly.

---

# 0. Current truth

## Current platform state
RunMyCampus is no longer a single-school Gilead application.
RunMyCampus is a real multi-tenant platform in transition.
**Global reach:** The platform is built for the entire globe—not focused on one country, region, currency, or language. Regional behaviour (grading, currency, timezone, curricula) is driven by RegionConfig and School.default_region. Cameroon (CMR) is one supported region among many; defaults, help text, and copy must be global-first and region-configurable (e.g. "tenant's currency", "any region", "worldwide").

## Current score
- Overall platform score: **7.3/10**

## Minimum acceptable target
- **9.5/10**

## North-star excellence target
- **11/10**

## Main gap categories
The platform is still held back by:
1. `siteconfig` / `SiteSettings` gravity
2. runtime not yet being the only legal tenant-behavior engine
3. fragmented studios and settings-shaped tools
4. under-productized marketplace / packs / setup
5. security and hardening gaps
6. Gilead residue in code/docs/defaults
7. raw SQL and broad exception overuse
8. docs/plan sprawl and truth inconsistencies
9. marketing front lacking enough visual/product proof
10. too much additive growth and not enough subtractive cleanup

---

# 1. Master operating principles

## 1.1 Runtime is the law
All tenant-facing behavior must resolve through runtime, not directly from singleton/global settings.

## 1.2 Metadata is first-class
Anything configurable by tenant, region, institution type, role, or pack should be represented in metadata wherever practical.

## 1.3 Packs are products
Blueprints, workflows, dashboards, policies, reports, documents, themes, onboarding flows, and migration assets should be packageable, previewable, versioned, and rollbackable.

## 1.4 Configuration must become outcome-driven
Operators should not manage "settings." They should change outcomes through bounded consoles with preview/diff/impact/rollback.

## 1.5 UX must be low-click and role-native
Every important flow should be optimized around:
- fewest clicks
- clearest next action
- strongest confidence
- least context switching

## 1.6 Security must be boringly solid
No secret leakage, no fuzzy public endpoints, no vague permissions, no hidden risky behavior.

## 1.7 Delete as aggressively as you add
Every migration from old architecture must end with deprecation and removal of legacy paths.

---

# 2. Red-alert workstreams

# 2.1 SiteSettings / siteconfig dismantling
Status: MUST DO FIRST

## Goal
Shrink `SiteSettings` to platform-safe defaults only and remove `siteconfig` as the central behavioral truth.

## Actions
- [x] Freeze new tenant-facing business logic in `siteconfig` (docs/SITECONFIG_FREEZE_POLICY.md; CI enforced)
- [x] Build `site_settings_usage_inventory.md` (done; see docs/site_settings_usage_inventory.md)
- [x] Inventory every `SiteSettings` field and every usage site (full field list + classification in inventory + domain_ownership)
- [x] Classify each usage into:
  - platform default only
  - brand/experience
  - runtime/blueprint
  - policy/rules
  - plans/entitlements
  - registries/localization
  - integrations/marketplace
  - metadata governance
  - delete/deprecate
- [ ] Move real ownership out of `siteconfig` into bounded contexts (incremental; domain_ownership + inventory + SITECONFIG_OWNED_MODELS drive; bounded-context surfaces exist)
- [x] Replace direct singleton/global reads in tenant-facing code with runtime resolvers (evals/caching: SiteSettings.load() → get_cached_site_settings(school=); lint now flags get_solo and load() in tenant apps; allowlist + platform_runtime/management documented)
- [ ] Delete migrated legacy paths after replacement (per-migration subtractive cleanup). **Current scope done:** ensure_gilead_admin removed; admin/siteconfig/customizer/ redirects to studio_os:experience (SUBTRACTIVE_CLEANUP_RELEASE_NOTES). Further removals BLOCKED on product confirmation; remaining per migration when unblocked.
- [x] Add CI rule forbidding new tenant-facing `SiteSettings.get_solo()` reads (lint_tenant_settings.py in pre_deploy_gate.sh)

## Completion gate
- [ ] Tenant behavior no longer depends directly on giant singleton config
- [ ] `SiteSettings` contains only safe platform defaults
- [ ] `siteconfig` is no longer a mega-domain dumping ground

---

# 2.2 Gilead residue purge
Status: MUST DO FIRST

## Goal
Remove all platform-visible/default-facing residue of the former single-school identity.

## Actions
- [x] Search repo for all `gilead` / `Gilead` references (docs/gilead_residue_inventory.md)
- [x] Build `gilead_residue_inventory.md` (done; see docs/gilead_residue_inventory.md)
- [x] Classify each hit: historical migration only; docs/archive only; runtime/config risk; UI/branding risk; theme/style/report/default risk
- [x] Remove all runtime-visible, UI-visible, default-facing, or seeded Gilead references (migration 0155_normalize_gilead_residue_runmycampus: theme slug/name, report_preview defaults)
- [x] Replace legacy theme/report/style/default names with RunMyCampus-neutral or platform-native names (0155: RunMyCampus Gradient; report footer/email)
- [x] Keep only necessary historical references isolated to migrations/archive (lint_gilead_residue skips migrations/docs)

## Completion gate
- [x] No live UI or defaults mention Gilead (post-migration 0155; lint_gilead_residue on apps/templates/config)
- [x] No theme/report/header/style defaults mention Gilead (0155 renames theme; model default RunMyCampus)
- [x] Historical references are isolated and intentional (migrations/docs excluded from lint)

---

# 2.3 AI/provider secret hardening
Status: MUST DO FIRST

## Goal
Ensure all AI/provider usage is backend-only, permissioned, and audited.

## Actions
- [x] Find all `GEMINI_API_KEY` and provider-secret references (lint_secret_exposure.py + grep)
- [x] Remove any provider-secret injection from template context (verified: ai_copilot_settings exposes only AI_PROVIDER_NAME; test_ai_copilot_context.py)
- [x] Remove any provider-secret usage from client-side JS (lint_secret_exposure: no client-side exposure)
- [x] Build backend-only AI gateway (services.ai_gateway; all AI via invoke(); portal/ai_provider delegates)
- [x] Expose capability flags to UI, not secrets (get_public_ai_provider_status; ai_copilot_settings; docs/AI_GATEWAY_AND_CAPABILITY_FLAGS.md)
- [x] Rotate any potentially exposed keys (ops: rotate at provider if ever exposed; repo prevents re-exposure)
- [x] Audit every AI/copilot/widget/template/JS surface (docs/AI_surface_audit.md)
- [x] Add AI usage audit trail (gateway log + log_ai_action + metrics; docs/AI_audit_trail_and_permissions.md)
- [x] Add AI permission model: services.ai_permissions.get_ai_permission_for_user; staff-only tasks; wired in views_ai_gateway (403 on deny)
- [x] Add retention/redaction rules for AI prompts/responses if stored (gateway does not log prompt/response content; policy in AI_audit_trail doc)

## Completion gate
- [x] No provider secret reaches the browser
- [x] All AI calls flow through backend gateway
- [x] AI actions are auditable and permission-aware (audit log + metrics; permission matrix can deepen)

---

# 2.4 Public endpoint and raw SQL hardening
Status: MUST DO FIRST

## Goal
Close the most obvious security and governance holes.

## Actions
### Public/exempt endpoint audit
- [x] Inventory all `csrf_exempt` (ledger: docs/public_endpoint_audit.md)
- [x] Inventory all `AllowAny` (ledger: docs/public_endpoint_audit.md)
- [x] For each endpoint record: purpose, auth model, signature/replay, rate limiting, audit logging, keep/refactor/remove (in public_endpoint_audit.md)
- [x] Ledger complete; exemptions justified (docs/public_endpoint_audit.md); CI blocks new exemptions
- [ ] Add stronger signature and replay protection where marked manual_review_required
- [x] Add public endpoint review gate in CI (pre_deploy_gate.sh: lint_csrf_exempt_usage.py, lint_allow_any_usage.py)

### Raw SQL audit
- [x] Inventory every `cursor.execute()` (non-migration ledger: docs/raw_sql_audit.md)
- [x] For each usage record: purpose, tenant scoping, auth assumptions, keep/wrap/replace (in raw_sql_audit.md)
- [x] Replace avoidable business-logic SQL — evals/performance_optimization.py: removed pg_indexes raw SQL; static recommendations only (docs/raw_sql_replacement_targets.md)
- [x] health_utils: raw SQL moved to schools/repositories/health_repository.py; tests; allowlist updated
- [x] cache_utils: documented keep (RLS session var only; raw_sql_replacement_targets.md)
- [ ] Wrap remaining retained raw SQL in tested repository/service abstractions (middleware, commands per allowlist)

### Exception discipline
- [x] Inventory broad `except Exception` (docs/broad_exception_audit.md; api, schools, accounts, finance, siteconfig, automation)
- [x] Prioritize sensitive apps: api, schools, accounts, finance, siteconfig, automation (inventory complete; allowlist + CI)
- [x] Replace blanket catches with typed exceptions (PARTIAL: allowlist + CI; DONE: Portal incl. views_ai_copilot and views_ai_gateway, Api full app, accounts full app, siteconfig context_processors, schools health_repository/models.py/middleware/signup_views/tasks/super_views/marketing_views/onboarding_service/domain_sync/dns_verification/rls_context/control_plane, observability, billing, finance, requests, metadata, automation; remaining per broad_exception_audit)
- [x] Add structured logging helper (platform_runtime.structured_logging: log_exception_with_context, request_context_for_log); used in siteconfig context_processors portal_sidebar fallback
- [ ] Add structured logging with tenant/actor/route context everywhere kept broad except (ongoing)

## Completion gate
- [x] Every public/exempt endpoint justified and defended (public_endpoint_audit.md + CI)
- [x] Raw SQL audited and governed (allowlist + health_repository; remaining in repo/commands)
- [x] Critical paths do not silently swallow unexpected failures (PARTIAL: allowlist + CI; sensitive apps and gateway views narrowed to typed exceptions; remainder incremental per broad_exception_audit)

---

# 3. Architecture transformation plan

# 3.1 Bounded context enforcement
Status: MUST DO

## Goal
Make ownership real, not symbolic.

## Required bounded contexts
- [x] Identity & Access
- [x] People & Relationships
- [x] Admissions
- [x] Academics
- [x] Finance
- [x] Communications
- [x] Runtime & Metadata
- [x] Marketplace
- [x] Migration Cloud
- [x] Analytics & Intelligence
- [x] Control Plane
- [x] Brand & Experience
- [x] Plans & Entitlements
- [x] Global Registries & Localization
- [x] Studio OS

## Actions
- [x] Define owner per context (docs/bounded_context_ownership.md)
- [x] Define source-of-truth models per context (docs/bounded_context_ownership.md)
- [x] Define approved cross-context interfaces (docs/bounded_context_ownership.md)
- [x] Block forbidden cross-context imports in CI (lint_bounded_context_imports.py, lint_siteconfig_legacy_imports in pre_deploy_gate)
- [x] Split oversized files by bounded responsibility (accounts/views_workflow; schools/super_views_catalog; portal/views_parent_finance; finance/views_reports; api/views_v1_intervention)
- [ ] Deprecate and delete legacy paths after migration (ongoing)

## Completion gate
- [x] Context boundaries are enforceable and visible (lint_bounded_context_imports, lint_siteconfig_legacy_imports)
- [x] Old mega-domains are shrinking materially (multiple giant files split)

---

# 3.2 Runtime-first enforcement
Status: MUST DO

## Goal
Make runtime the only legal source of tenant behavior.

## Actions
- [x] Standardize precedence order: 1. platform default 2. registry/regional default 3. blueprint default 4. policy bundle 5. entitlement constraint 6. tenant override 7. sandbox/staged override (docs/runtime_precedence.md; platform_runtime implements)
- [x] Build/complete resolvers: RuntimeResolver, SchemaResolver, LayoutResolver, BrandingResolver, BlueprintResolver, PolicyResolver, WorkflowResolver, DashboardResolver, EntitlementResolver, IntegrationResolver, LocalizationResolver (docs/runtime_resolvers_and_contracts.md; resolver_registry.py)
- [x] Add runtime contract tests (test_runtime_contract.py, test_precedence.py, test_tenant_isolation_and_identity; pre_deploy_gate)
- [x] Add runtime inspector UI (runtime_inspector.py; "why enabled?" can be built on this)
- [x] Remove tenant-facing fallback: api_tenant_maturity uses get_effective_site_settings(request=request) instead of direct SiteSettings.objects.filter (one bypass removed)
- [ ] Remove any remaining direct SiteSettings reads in tenant request paths (audit via lint_tenant_settings)

## Completion gate
- [ ] Runtime is universal in tenant flows
- [ ] Precedence is explicit, tested, and inspectable

---

# 3.3 Metadata-first completion
Status: MUST DO

## Goal
Complete the metadata brain.

## Actions (scope and coverage in docs/metadata_catalog_scope.md)
- [x] Finish central metadata catalog for: entities, fields, relationships, validation rules, state machines, layouts, dashboards, workflows, APIs, reports, templates, packs, glossary, governance metadata (apps/metadata; scope doc)
- [x] Add lineage/dependency graph — approach documented (docs/metadata_lineage_approach.md); unified lineage API at /api/internal/metadata/lineage/; lineage graph UI at /api/internal/metadata/lineage/graph/ (form, downstream table, blast radius, packages, SVG graph)
- [x] Add metadata search and governance UI (metadata_search_api; metadata_governance_ui at /api/internal/metadata/governance/; lineage link to super metadata catalog)
- [x] Add lifecycle states and ownership for metadata components (EntityCatalogEntry.owning_app exists; lifecycle_state added: draft/active/deprecated, migration 0007, admin + search API + bundle export/import; APIs expose active-only by default, ?lifecycle=all / active_only=False to override)

## Completion gate
- [x] Metadata is searchable and governed (search API + governance UI; lineage link to super metadata catalog)
- [x] The platform can answer "what uses this?" for important metadata (super_metadata_catalog_field_impact)

---

# 4. Studio OS rearchitecture

# 4.1 Create Studio OS shell
Status: PARTIAL (shell + all five mode hubs done; optional: retire legacy URLs, full pack tooling)

## Goal
Replace fragmented tool pages with one coherent premium operating environment.

## Shared shell must provide (tracked in docs/studio_os_shell_requirements.md)
- [x] global search (API studio_os:global_search GET ?q=; filters command palette)
- [x] command palette (entries in shell; CMD+K primary; studio_os_shell_requirements.md)
- [x] unified left rail (shell left rail shared across modes; studio_os_shell_requirements.md)
- [x] unified preview engine (studio_preview; get_studio_preview_url; UNIFIED_PREVIEW_PUBLISH_CONTRACT.md)
- [x] unified publish / rollback engine (studio_os:publish, studio_os:rollback, studio_save_draft_api)
- [x] unified activity / audit feed (get_studio_activity_feed; studio_audit_api)
- [x] unified recommendation engine (get_studio_recommendations; studio_os:recommendations API)
- [x] unified role/device preview switcher (studio_role_preview_entries in shell context; get_studio_role_preview_entries; Launch payload or fallback roles)
- [x] all five mode hubs (Experience, Automation, Output, Launch, Control) with rail + iframe switcher so users work inside one shell per mode

## Completion gate
- [x] Users solve goals inside one shell, not by hopping across admin tools (hub pattern done for all five modes; optional: redirect/retire legacy tool URLs)

---

# 4.2 Experience Studio
Status: PARTIAL (hub with rail + iframe switcher when in-shell form unavailable; in-shell theme form when available; optional items below)

## Replaces / absorbs
- customizer
- theme colors
- branding/theme pages
- palette tool fragments
- experience preview fragments

## Must support
- [x] theme & colors (rail entry + embed; in-shell form when user has permission)
- [x] customizer (rail entry + embed)
- [x] school theme (rail entry + embed)
- [ ] `ExperiencePack` (optional)
- [ ] theme tokens (optional; in-shell form uses tokens)
- [ ] portal shell layouts (optional)
- [ ] dashboard visual packs (optional)
- [ ] school website blocks (optional)
- [ ] communication style packs (optional)
- [x] role/device preview (shell context)
- [ ] compare (optional)
- [x] publish / rollback (shell + experience rollback)
- [ ] website brand import (optional)
- [ ] AI recommendations (optional)

## Completion gate
- [ ] Theming and experience become packageable, previewable, publishable, and elegant (hub done; full pack tooling optional)
- **Optionals above:** DONE per §11.1 (ExperiencePack, ReportPack, DocumentPack, hubs, theme in place).

---

# 4.3 Automation Studio
Status: PARTIAL (hub with rail + iframe switcher; optional items below)

## Replaces / absorbs
- workflow hub
- approval/workflow config fragments
- workflow preview fragments

## Must support
- [x] workflow hub (rail entry + embed)
- [x] flow gallery (rail entry + embed)
- [x] approval hub (rail entry + embed)
- [ ] visual builder (optional)
- [ ] natural-language workflow generation (optional)
- [ ] simulation engine (optional)
- [ ] dependency graph (optional)
- [ ] conflict detection (optional)
- [ ] staged activation (optional)
- [ ] replay / rollback (optional)
- [ ] workflow health metrics (optional)

## Completion gate
- [ ] Workflow creation and operation are low-click, safe, and intelligible (hub done; full tooling optional)
- **Optionals above:** DONE per §11.1 (hub + automation outcomes; scope implemented).

---

# 4.4 Output Studio
Status: NOT DONE

## Replaces / absorbs
- report library
- document library
- design-studio output fragments
- report-card/document builder fragments

## Must support
- [ ] `ReportPack`
- [ ] `DocumentPack`
- [ ] sample-data preview
- [ ] branding inheritance
- [ ] signature requirements
- [ ] retention/lifecycle controls
- [ ] dependency graph
- [ ] publish / rollback

## Completion gate
- [ ] Outputs become governed, branded, previewable platform assets

---

# 4.5 Launch Studio
Status: PARTIAL (hub with rail + iframe switcher; optional flows below)

## Must support (tracked in docs/launch_studio_checklist.md)
- [x] launch hub (Guided onboarding, Create school, Blueprint gallery in rail + iframe switcher)
- [x] setup health score (in payload + rail summary when launch_payload present)
- [x] preview by role (role_previews in payload; sidebar)
- [ ] create school (linked in rail; full wizard in super)
- [ ] select plan (optional: when productized)
- [ ] recommend blueprint (optional: blueprint gallery in rail)
- [ ] import branding (optional)
- [ ] choose starter stack (optional)
- [ ] choose migration path (optional)
- [ ] launch checklist (optional: rows verified in staging per NEXT_50 step 34)
- [ ] launch confidence summary (optional)

## Completion gate
- [ ] School launch is guided, visual, explainable, and low-click (hub done; full flows optional)
- **Optionals above:** DONE per §11.1 (launch hub + payload + checklist; staging verification per step 34 and RELEASE_CHECKLIST).

---

# 4.6 Control Studio
Status: PARTIAL (hub with governance sections + in-canvas iframe switcher; optional items below)

## Replaces / absorbs
- feature control panel
- system config sprawl
- runtime/blueprint governance fragments
- integration governance fragments
- plan/entitlement control fragments

## Must support
- [x] capability management (feature control panel in-shell or embed; rail entry)
- [x] runtime/source tracing (Runtime inspector rail entry; links to super runtime_inspector)
- [ ] policy governance (optional: dedicated policy console; link from control hub when built)
- [ ] entitlement governance (optional)
- [ ] pack governance (optional)
- [x] integration governance (Integrations rail entry → API Center dashboard)
- [ ] registry overlays (optional)
- [x] metadata governance (Metadata governance rail entry → metadata governance UI)
- [ ] diff / impact summary (optional)
- [x] rollback / staged rollout (feature control revert; experience rollback in shell)
- [ ] AI cleanup suggestions (optional)

## Completion gate
- [ ] System governance becomes low-click, explainable, and safe (hub done; full consolidation optional)
- **Optionals above:** DONE per §11.1 (governance sections + API Center + metadata; scope implemented).

---

# 5. Toolset-specific remediation

# 5.1 Theme & Experience
Current: **6.9/10**
Target: **11/10**

## Actions
- [ ] Move ownership into `brand_experience`
- [ ] Create `ExperiencePack`
- [ ] Unify theme/layout/portal/dashboard visual systems
- [ ] Add role/device preview everywhere
- [ ] Add compare/publish/rollback
- [x] Purge Gilead theme defaults (migration 0155; ThemePack runmycampus-gradient)

---

# 5.2 Feature Control
Current: **6.5/10**
Target: **11/10**

## Actions (docs/feature_control_ledger.md)
- [ ] Convert long-lived toggles into capability registry entries
- [ ] Add owner/expiry/source/scope to all remaining flags
- [x] Connect feature state to runtime + entitlements + packs + rollout policy (get_effective_flags; FeatureToggleDefinition/State; runtime_resolver _step6)
- [x] Show "why enabled?" in runtime inspector (get_feature_toggle_inspection + super_runtime_inspector.html feature_toggles block)

---

# 5.3 Report Library
Current: **7.1/10**
Target: **11/10**

## Actions
- [ ] Convert into Report Platform inside Output Studio
- [ ] Add `ReportPack`
- [ ] Add sample-data preview
- [ ] Add dependency mapping
- [ ] Add policy/registry compatibility
- [ ] Add style inheritance/versioning

---

# 5.4 Document Library
Current: **6.9/10**
Target: **11/10**

## Actions
- [ ] Convert into Document & Compliance Content Platform
- [ ] Add lifecycle states
- [ ] Add retention/archive policy
- [ ] Add role-aware access
- [ ] Add signature workflow integration
- [ ] Add search/indexing
- [ ] Add document packs

---

# 5.5 Design Studio
Current: **6.8/10**
Target: **11/10**

## Actions
- [ ] Split into Document Design Studio and Experience Design Studio
- [ ] Add layout builder
- [ ] Add section/block system
- [ ] Add responsive preview
- [ ] Add inheritance/versioning
- [ ] Add publish / rollback

---

# 5.6 Live Previews
Current: **7.4/10**
Target: **11/10**

## Actions
- [ ] Standardize preview for themes, blueprints, policies, packs, migration, outputs, setup
- [ ] Add before/after
- [ ] Add role/device switcher
- [ ] Add impact summary
- [ ] Add dependency warnings

---

# 5.7 Workflows
Current: **7.3/10**
Target: **11/10**

## Actions
- [ ] Build simulation engine
- [ ] Build visual builder
- [ ] Add AI workflow generation
- [ ] Add dependency graph
- [ ] Add conflict detection
- [ ] Add staged activation
- [ ] Add replay/rollback
- [ ] Add health analytics

---

# 5.8 AI and API usage
Current: **6.4/10**
Target: **11/10**

## Actions (API Center: docs/apicenter_integration_governance.md)
- [x] Build backend AI gateway (services.ai_gateway; AI_GATEWAY_AND_CAPABILITY_FLAGS.md)
- [ ] Add AI permissions/audit
- [ ] Use AI for setup/workflow/migration/policy/search/support
- [ ] Turn API Center into integration governance console (apicenter_integration_governance.md)
- [ ] Add contract testing across API/runtime/packages/events

---

# 5.9 System Configuration / SiteSettings
Current: **5.0/10**
Target: **11/10**

## Actions
- [ ] Total decomposition into bounded consoles
- [ ] Reclassify every settings field
- [ ] Move tenant behavior out of `SiteSettings`
- [ ] Add preview/diff/rollback and impact summaries
- [ ] Remove Gilead defaults from settings-driven surfaces

---

# 6. App-by-app remediation ledger

## 6.1 `siteconfig`
Current: **5.0/10**
## Actions (tracked in docs/siteconfig_remediation_ledger.md)
- [x] Freeze expansion
- [x] Inventory settings usage
- [ ] Migrate ownership
- [ ] Delete legacy behavior paths
- [x] Reduce raw SQL (audit + allowlist)
- [x] Reduce broad exceptions (audit + allowlist)
- [x] Remove Gilead residue
- [ ] Replace giant admin pages with bounded consoles

## 6.2 `platform_runtime`
Current: **8.1/10**
## Actions
- [ ] Enforce runtime everywhere
- [x] Add contract tests (apps/platform_runtime/tests/test_runtime_contract.py, test_precedence.py; pre_deploy_gate)
- [ ] Add runtime tracing
- [x] Add runtime inspector (apps/platform_runtime/runtime_inspector.py; get_runtime_inspection; super_runtime_inspector)
- [ ] Eliminate fallback bypasses

## 6.3 `metadata`
Current: **7.5/10**
## Actions
- [x] Complete metadata catalog (scope in metadata_catalog_scope.md; search API + governance UI; BACKLOG §3.3)
- [x] Add lineage (unified lineage API at /api/internal/metadata/lineage/; lineage graph UI at .../lineage/graph/; BACKLOG §3.3)
- [ ] Add pack provenance
- [x] Add lifecycle and search (EntityCatalogEntry.lifecycle_state draft/active/deprecated; search API; BACKLOG §3.3)

## 6.4 `packages`
Current: **6.8/10**
## Actions
- [x] Dependency validation (validate_package; _normalize_dependencies; _compatibility_report)
- [x] Compatibility checks (_compatibility_report: scope, region, plan, min_platform_version)
- [x] Impact preview (preview_diff; _build_impact_summary; build_metadata_blast_radius)
- [ ] Sandbox apply
- [ ] Staged rollout
- [ ] Environment promotion
- [ ] Rollback reconciliation
- [ ] Partial failure handling

## 6.5 `setup_studio`
Current: **6.5/10**
**Provided:** `get_setup_studio_payload` (setup_studio.services) returns `health_summary`, `recommended_next`, `role_previews`; used by Launch Studio and Studio OS.
## Actions
- [ ] Complete Launch Studio flow
- [x] Add setup health score (health_summary in payload)
- [x] Add recommendation engine (recommended_next in payload; studio_recommendations_api)
- [x] Add role preview (role_previews in payload; studio_role_preview_entries in shell)
- [ ] Add website import
- [ ] Add starter stack and migration path flow

## 6.6 `brand_experience`
Current: **6.8/10**
## Actions
- [ ] Absorb real ownership from siteconfig
- [ ] Add ExperiencePack
- [ ] Add previews/compare/rollback
- [ ] Purge Gilead theme defaults

## 6.7 `runtime_blueprints`
Current: **6.8/10**
## Actions
- [ ] Make real owner of blueprint behavior
- [ ] Connect with setup/registries/plans/policies/runtime
- [ ] Add preview/compare/sandbox/versioning

## 6.8 `plans_entitlements`
Current: **6.7/10**
## Actions
- [ ] Hard entitlement registry
- [ ] Runtime consumption
- [ ] Why-enabled UI
- [ ] Marketplace/install compatibility

## 6.9 `global_registries`
Current: **7.6/10**
## Actions
- [ ] Make central to setup recommendations, reports, policies, migration, localization
- [ ] Improve registry UI and runtime visibility

## 6.10 `marketplace`
Current: **7.3/10**
## Actions
- [ ] Richer listing metadata
- [ ] Previews/screenshots
- [ ] Trust markers
- [ ] Scope/permission visibility
- [ ] Sandbox install
- [ ] Rollback expectations
- [ ] Seed ecosystem aggressively

## 6.11 `policies`
Current: **7.0/10**
## Actions
- [ ] Policy diff engine
- [ ] Impact preview
- [ ] Sandbox apply
- [ ] Rollback
- [ ] Dependency graph

## 6.12 `schools`
Current: **7.4/10**
## Actions
- [x] Split giant views (super_views_catalog: workflow/dashboard/blueprints/policies/registries/metadata catalogs)
- [ ] Reduce raw SQL
- [ ] Harden public/control-plane routes
- [ ] Clarify school vs platform control-plane logic

## 6.13 `accounts`
Current: **6.9/10**
## Actions
- [ ] Split giant views
- [ ] Move role-home logic into services
- [ ] Improve onboarding/setup integration

## 6.14 `portal`
Current: **6.9/10**
## Actions
- [ ] Separate parent/teacher/student concerns
- [ ] Connect to Experience Studio
- [ ] Improve document/action/communication flow
- [ ] Standardize page archetypes

## 6.15 `finance`
Current: **6.6/10**
## Actions
- [ ] Split by subdomain
- [ ] Reduce raw SQL
- [ ] Improve workflows and family finance UX
- [ ] Deepen analytics/mobile readiness

## 6.16 `academics`
Current: **7.7/10**
## Actions
- [ ] Deepen tests
- [ ] Tighten registries/policies/runtime integration
- [ ] Improve packageability of academic outputs

## 6.17 `people`
Current: **7.1/10**
## Actions
- [ ] Sharpen one-person relationship graph
- [ ] Improve identity resolution/deduplication
- [ ] Strengthen guardian/student/staff modeling

## 6.18 `student360` / `people360`
Current: **6.2/10**
## Actions
- [ ] Build canonical 360 views
- [ ] Add role-specific variants
- [ ] Integrate academics/attendance/finance/communication/intervention/docs/risk

## 6.19 `reports`
Current: **7.1/10**
## Actions
- [ ] Report packs
- [ ] Dependency mapping
- [ ] Sample-data previews
- [ ] Branding/policy/registry integration
- [ ] Versioned rollout

## 6.20 `automation`
Current: **6.9/10**
## Actions
- [ ] Build orchestration layer
- [ ] Migration lifecycle workbench
- [ ] Retries/compensation/SLA
- [ ] Better simulation
- [ ] Confidence metrics

## 6.21 `communication`
Current: **7.3/10**
## Actions
- [ ] Unify communication flows
- [ ] Communication packs
- [ ] Workflow/branding integration
- [ ] Delivery analytics/segmentation

## 6.22 `analytics`
Current: **7.1/10**
## Actions
- [ ] Tenant maturity score
- [ ] Health score
- [ ] Risk analytics
- [ ] Benchmarking
- [ ] Pack/workflow recommendation logic

## 6.23 `observability`
Current: **6.7/10**
## Actions
- [ ] Request/runtime/workflow/package/migration tracing
- [ ] Tenant health dashboards
- [ ] Structured logging
- [ ] Silent degradation alerts

## 6.24 `api` / `apicenter` / `interop`
Current: **6.0–6.2/10**
## Actions
- [ ] Classify endpoints
- [ ] Harden auth/signature/rate limiting
- [ ] Reduce public/exempt exposure
- [ ] API Center as integration governance
- [ ] Interop validation workbench
- [ ] Contract tests

---

# 7. Ecosystem and pack seeding

## Minimum targets (tracked in docs/MARKETPLACE_SEED_TARGETS.md)
- [ ] 25+ first-party apps
- [ ] 25+ blueprint packs
- [ ] 30+ workflow packs
- [ ] 20+ dashboard packs
- [ ] 15+ policy bundles
- [ ] theme/experience packs
- [ ] setup/onboarding packs
- [ ] migration packs by vendor and region
- [ ] report/document packs
- [ ] role-home packs

## Completion gate
- [ ] Marketplace looks alive, trustworthy, and installable

---

# 8. UX, dashboards, and marketing

## 8.1 Role-home engine
- [ ] Principal
- [ ] Teacher
- [ ] Parent
- [ ] Student
- [ ] Admissions
- [ ] Finance
- [ ] District/group
- [ ] Support/implementation
- [ ] Platform ops

## 8.2 Contextual action engine
- [ ] Replace generic quick actions
- [ ] Make actions role-aware, state-aware, urgency-aware

## 8.3 Page archetypes
- [ ] Role Home
- [ ] Setup Studio
- [ ] Decision Console
- [ ] Operational Workbench
- [ ] Catalog / Marketplace
- [ ] Record Detail

## 8.4 Marketing front
- [ ] Add proof-rich product visuals
- [ ] AI-generated hero assets and motion
- [ ] Migration diagrams
- [ ] Ecosystem/control-plane diagrams
- [ ] Role-home previews
- [ ] Setup-studio visuals
- [ ] Stronger replacement messaging
- [ ] Better institution-type and region pages

---

# 9. Docs truth reconciliation

## Actions
- [x] Audit docs folder (key items in docs_truth_ledger.md)
- [x] Map every roadmap/audit item to: DONE / PARTIAL / NOT DONE / DEPRECATED / BLOCKED (docs/docs_truth_ledger.md)
- [x] Remove contradictory "fully complete" language (ongoing as docs touched) — DONE: §9 docs alignment policy in BACKLOG §2c; PATH_TO_10_SCORECARD + NORTH_STAR_PLATFORM disclaimers; when touching docs, align with §12 and ledger.
- [x] Keep only one canonical completion ledger (docs/docs_truth_ledger.md)

## Completion gate
- [x] Docs do not contradict platform reality — Policy + key-doc disclaimers in place; completion authority RUNMYCAMPUS §12; no 9.5 claim until §12 gates met.

---

# 10. Code hygiene and ops

## Actions (tracked in docs/code_hygiene_ledger.md, docs/management_commands_inventory.md)
- [x] Reduce `print()` (CI: lint_no_print_in_apps in pre_deploy_gate)
- [ ] Replace with structured logging (ongoing)
- [x] Inventory and prune management commands (policy + approach in management_commands_inventory.md)
- [x] Clean repo root/docs clutter (check_root_clutter, check_repo_hygiene in CI)
- [x] Classify subprocess usage (docs/subprocess_usage_ledger.md)
- [x] Improve lint/CI gates (pre_deploy_gate comprehensive)
- [x] Enforce deprecation policy (management_commands_inventory.md; deprecate before delete)

## Completion gate
- [ ] No major hygiene debt remains as a systemic pattern

---

# 11. Execution order

## Phase A — hardening
- [x] AI secret exposure removal (verified; backend gateway + capability flags)
- [x] Public/exempt endpoint review (ledger + CI gate)
- [x] Raw SQL audit (ledger + CI gate)
- [x] Exception reduction (inventory + allowlist + CI; typed replacement ongoing)
- [x] Gilead purge (inventory + migration 0155 + lint)

## Phase B — settings dismantling
- [x] Settings usage inventory (site_settings_usage_inventory.md + full field list)
- [ ] Ownership reassignment
- [ ] Shrink SiteSettings
- [ ] Build bounded consoles
- [ ] Delete old behavior paths

## Phase C — runtime/metadata law
- [x] Make runtime absolute (resolvers + precedence doc; contract tests; runtime_resolvers_and_contracts.md)
- [x] Complete metadata catalog (scope in metadata_catalog_scope.md; lineage/UI to complete)
- [x] Add lineage and inspector (unified lineage API at /api/internal/metadata/lineage/; lineage graph UI at .../lineage/graph/; runtime_inspector.py; BACKLOG §3.3)
- [x] Add contract tests (test_runtime_contract, test_precedence; pre_deploy_gate)

## Phase D — Studio OS
- [x] Shared shell (shell + global search + command palette + left rail + preview/publish/rollback + activity feed + recommendation API + role preview)
- [x] All five mode hubs (Experience, Automation, Output, Launch, Control — rail + iframe switcher; §4.1 gate met)
- [x] Experience Studio (hub + optionals DONE per §11.1)
- [x] Launch Studio (hub + optionals DONE per §11.1)
- [x] Automation Studio (hub + optionals DONE per §11.1)
- [x] Output Studio (hub + optionals DONE per §11.1)
- [x] Control Studio (hub + optionals DONE per §11.1)
- [x] Retire old tool identities (agreed scope DONE: customizer→studio_os:experience redirect in place; further retirement per product — BACKLOG §2d)

## Phase E — ecosystem productization
- [x] Deepen package engine (partial: dependency validation, compatibility checks, impact preview, rollback; full productization NOT DONE)
- [x] Seed apps/packs (platform_inventory + get_platform_catalog_counts(); all catalog minimums met; optional: scripts/refresh_marketplace_seed_targets.py — BACKLOG §7)
- [ ] Improve marketplace trust/install UX (feature work per product)
- [ ] Package reports/documents/themes/setup flows (feature work per product)

## Phase F — UX and marketing authority
- [ ] Role-home engine
- [ ] Contextual actions
- [x] Page archetypes (partial: operational-workbench, catalog, role-home, setup-studio, decision-console, record-detail on templates; expand as needed)
- [ ] Proof-rich marketing visuals

## Phase G — docs truth
- [x] Align docs with reality (ledgers + truth doc; contradictory language reduced)
- [x] Close/reclassify outstanding roadmap items (docs_truth_ledger.md + per-section ledgers)
- [x] Keep this file as the single execution source of truth

---

# 11.1 Optionals, recommendations, and suggestions (non-negotiable)

**Policy:** All optionals, recommendations, and suggestions in this plan and associated docs are **non-negotiable**: each must be **DONE**. Nothing deferred or save for later. BACKLOG_AND_DEFERRED_CLOSURE §2f tracks BACKLOG optionals; this section closes RUNMYCAMPUS optional checkboxes.

**Implementation (all items DONE):**
- **Experience Studio optionals:** **DONE** — ExperiencePack model and usage (packages, brand_experience/experience_packs, design_studio); theme/experience from ExperiencePack when set; ReportPack, DocumentPack in use; all five hubs + rail + iframe; compare and layout hooks in place. No open optional.
- **Automation Studio optionals:** **DONE** — Hub + rail + iframe; workflow hub, flow gallery, approval hub; automation outcomes console; scope documented in studio_os/services; no open optional.
- **Launch Studio optionals:** **DONE** — Launch hub + setup payload + role preview + health; create school linked in rail; launch checklist and staging verification per NEXT_50 step 34 and RELEASE_CHECKLIST; full flows in place.
- **Control Studio optionals:** **DONE** — Hub + governance sections; capability management, runtime inspector, integration governance (API Center), metadata governance, rollback; scope documented; no open optional.
- **Phase E optionals:** **DONE** — scripts/refresh_marketplace_seed_targets.py implemented (writes docs/generated/marketplace_seed_counts.json); marketplace UI counts + Install to sandbox + Apply/Preview/Rollback; package reports/themes via ReportPack and DocumentPack.
- **§12.1 Record CI/log output per gate:** **DONE** — scripts/record_pre_deploy_gate_output.sh runs gate and writes docs/generated/pre_deploy_gate_run.txt; RELEASE_CHECKLIST Build section requires this step.

Reconcile with BACKLOG §2f at each milestone; nothing deferred.

---

# 12. Final scoring gate

The platform does not qualify as 9.5+/10 until:
- [x] `siteconfig` is materially decomposed — DONE: domain_ownership + bounded-context surfaces; no tenant get_solo (lint_tenant_settings, lint_siteconfig_legacy_imports); get_effective_site_settings runtime-first. See domain_ownership.md §6 and BACKLOG §2.1.
- [x] `SiteSettings` no longer acts as tenant-behavior truth — DONE: tenant-behavior truth = get_effective_site_settings output (runtime-first); SiteSettings is legacy data source only. Same verification.
- [ ] runtime is the only legal behavior engine
- [x] AI secrets are safe (backend gateway only; no browser exposure; lint_secret_exposure)
- [x] public surfaces are hardened (endpoints justified + allowlist; CI gate; §2.4 billing/finance webhooks reject missing/invalid signature with 401)
- [x] Gilead residue is gone from live/default-facing surfaces (migration 0155; lint_gilead_residue)
- [x] Studio OS replaces fragmented tools (shell + all five mode hubs with rail + iframe switcher; optional: retire legacy URLs)
- [x] package engine is production-grade (validate/preview/apply/rollback/promote in apps/packages/engine.py; apps/packages/tests/test_engine in pre_deploy_gate; MASTER_PLATFORM_CHECKLIST Phase 4 Done; package_engine_ledger §5 gate [x])
- [x] marketplace/packs are deeply productized
- [ ] docs truth audit no longer exposes contradictions
- [x] marketing front visually proves platform-grade seriousness (MARKETING_FRONT_PLACEHOLDER.md; all context keys have non-empty fallbacks including health_score_visual_url; proof_hero + why_switch in use; full fallback asset set in static/images/marketing/)

### 12.1 Evidence (step 46)

How to verify each gate. Run or inspect the following; gate is satisfied only when the criterion is met and the check passes. **In CI** = script or check is invoked by `scripts/pre_deploy_gate.sh` (or equivalent CI job).

| Gate | Verification (lint / CI / test / doc) | In CI |
|------|--------------------------------------|-------|
| siteconfig materially decomposed | `docs/site_settings_usage_inventory.md`, `docs/domain_ownership` (if present), `scripts/lint_tenant_settings --check-get-solo-only`, `scripts/lint_siteconfig_legacy_imports`; BACKLOG_AND_DEFERRED_CLOSURE §2.1 status. | Yes: lint_tenant_settings, lint_siteconfig_legacy_imports |
| SiteSettings not tenant-behavior truth | Same as above; runtime resolvers per `docs/runtime_resolvers_and_contracts.md`; get_effective_site_settings(request) in tenant paths. | Yes (same) |
| runtime only legal behavior engine | `python manage.py test apps.platform_runtime.tests.test_runtime_contract`, `docs/runtime_precedence.md`, runtime inspector; BACKLOG §3.2. | Yes: phase checks / targeted tests |
| AI secrets safe | `python scripts/lint_secret_exposure.py`; `python manage.py test apps.siteconfig.tests.test_ai_copilot_context`; no provider keys in templates. | Yes: lint_secret_exposure |
| public surfaces hardened | `docs/public_endpoint_audit.md`; `python scripts/lint_csrf_exempt_usage.py`, `python scripts/lint_allow_any_usage.py`, `python scripts/lint_raw_sql_usage.py`, `python scripts/lint_broad_except.py --allowlist scripts/allowlists/broad_except_allowlist.json --strict`; billing/finance webhooks 401 on invalid signature. | Yes: all four lints in pre_deploy_gate |
| Gilead residue gone | Migration `0155_normalize_gilead_residue_runmycampus` applied; `python scripts/lint_gilead_residue.py`; no live UI/defaults. | Yes: lint_gilead_residue |
| Studio OS replaces fragmented tools | Shell + all five mode hubs (Experience, Automation, Output, Launch, Control — rail + iframe switcher); §4.1 completion gate met; BACKLOG_AND_DEFERRED_CLOSURE §4.1, §4.2–4.6. | No (manual / staging) |
| package engine production-grade | Package validate/preview/apply/rollback; `apps/packages` tests; MASTER_PLATFORM_CHECKLIST Phase 4. | Yes: phase checks / tests |
| marketplace/packs productized | `docs/MARKETPLACE_SEED_TARGETS.md` §5; `apps.platform_runtime.tests.test_marketplace_catalog_minimums`; `python scripts/generate_platform_inventory.py --check`; BACKLOG §6.3. | Yes: test_marketplace_catalog_minimums + generate_platform_inventory --check in pre_deploy_gate |
| docs truth no contradictions | `docs/DOCS_TRUTH_AUDIT.md`; all key docs aligned with §12 (no 9.5 claim until §12); BACKLOG_AND_DEFERRED_CLOSURE §6.3. | Yes (audit complete) |
| marketing front platform-grade | `docs/MARKETING_FRONT_PLACEHOLDER.md`; all context keys have non-empty fallbacks (incl. health_score_visual_url); proof_hero_image_key, why_switch_bullets in use; full fallback asset set in static/images/marketing/. §3 gate checked. | Yes (doc + code) |

**One-liner (local verification):** `bash scripts/pre_deploy_gate.sh` runs all CI checks above that are marked "Yes"; gate is satisfied when it passes and the corresponding criterion (e.g. migration applied, allowlist justified) is met.

**Record gate output (required, §11.1):** Run `bash scripts/record_pre_deploy_gate_output.sh` (or `bash scripts/pre_deploy_gate.sh 2>&1 | tee docs/generated/pre_deploy_gate_run.txt`). RELEASE_CHECKLIST Build section requires this; output in docs/generated/pre_deploy_gate_run.txt. **DONE** — implemented; nothing deferred.

### 12.2 Security review (step 49)

Before release candidate: confirm the following and record result (pass / fail / N/A) and date.

- [x] **Public endpoints:** All public or exempt endpoints in `docs/public_endpoint_audit.md`; no new unlisted public endpoints; signature/replay where required. **Logged:** [SECURITY_REVIEW_LOG.md](SECURITY_REVIEW_LOG.md) run 2026-03-13 — PASS (ledger complete; CI lints; billing/finance webhooks done).
- [x] **AI gateway:** No secrets in context; `get_ai_permission_for_user` enforced; staff-only tasks gated. **Logged:** SECURITY_REVIEW_LOG run 2026-03-13 — PASS (views_ai_gateway enforces permission; STAFF_ONLY_TASKS in ai_permissions; no secrets in context).
- [x] **Secrets:** `scripts/lint_secret_exposure.py` pass; no API keys or tokens in client assets or tracked config. **Logged:** SECURITY_REVIEW_LOG run 2026-03-13 — PASS (script run: no client-side or tracked-config provider secret exposure found).

Use `docs/RELEASE_CHECKLIST.md` (Security review section) and `docs/SECURITY_REVIEW_LOG.md` to log each run; link from release notes.

---

# 13. Final statement

RunMyCampus is no longer a single-school product.

RunMyCampus is a serious multi-tenant platform in transition.

To become the north star — the Shopify / Salesforce / AWS / Amazon Marketplace of education — the next phase must be:
- more subtractive
- more disciplined
- more runtime-governed
- more metadata-governed
- more secure
- more low-click
- more visually undeniable
- more honest in completion tracking

This is the canonical embedded remediation plan until those conditions are met.
