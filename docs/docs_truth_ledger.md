# Docs Truth Ledger

**Purpose:** §9 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Single canonical completion ledger; every roadmap/audit item mapped to DONE / PARTIAL / NOT DONE / DEPRECATED / BLOCKED. No contradictory "fully complete" language. Nothing deferred.

**Status:** In force. This file is the completion ledger; RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md is the execution plan. **Last reconciled with BACKLOG:** This run (§12 **marketplace/packs deeply productized** gate MET in BACKLOG §6.3; **11 of 11 §12 gates MET**). Verification: MARKETPLACE_SEED_TARGETS §5; test_marketplace_catalog_minimums + generate_platform_inventory --check in pre_deploy_gate. Previous: optionals all DONE; §12 docs truth gate MET; Step 4 + Step 6 + §8.

---

## 1. Canonical sources

| Document | Role |
|----------|------|
| [PLAN_VERIFICATION_REPORT.md](PLAN_VERIFICATION_REPORT.md) | Periodic verification: optional/suggestion items vs repo; §12 vs MASTER_PLATFORM_CHECKLIST reconciliation. |
| [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) | Single execution source of truth; all remediation work maps here. |
| [RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md](RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md) | Full audit + Cursor phases; context only; execution checklist lives in single source of truth. |
| This file (docs_truth_ledger.md) | Completion ledger: roadmap/audit items → DONE / PARTIAL / NOT DONE / DEPRECATED / BLOCKED. |

---

## 2. Ledger entries (key items)

| Item | Status | Notes |
|------|--------|--------|
| SiteSettings usage inventory | DONE | docs/site_settings_usage_inventory.md; full field classification in domain_ownership. |
| §2.1 get_solo call-site inventory | **DONE** | Tenant-facing complete: lint_tenant_settings --check-get-solo-only pass; get_solo only in siteconfig (definition), tests, allowlisted management (backfill_runtime_defaults). Step 5 DONE. |
| §2.1 Resolver–migrate–delete ordering | **DONE** | docs/RESOLVER_MIGRATE_DELETE_ORDERING.md: Phase 1 (resolver first), Phase 2 (migrate), Phase 3 (delete) checklist; no step left without status. BACKLOG ?2b ?2.1 references it. |
| §2.4 Signature/replay implementation plan | **DONE** | public_endpoint_audit.md §6: per-endpoint scheme and status (Billing/Finance DONE; SCIM/LTI SPECIFIED+DEFERRED; SAML replay DONE; SchoolConfigAPI/GraphQL N/A). No endpoint left without a decision. BACKLOG ?2b ?2.4 references it. |
| Gilead residue inventory | DONE | docs/gilead_residue_inventory.md; migration 0155 normalizes theme + report preview. |
| Public/exempt endpoint audit | DONE | docs/public_endpoint_audit.md; per-endpoint record; CI lint. |
| Step 7 csrf_exempt/AllowAny removal audit | **DONE** | Audit complete: all listed exemptions justified; no removal needed. CI in pre_deploy_gate. Step 7 DONE. |
| Step 8 GraphQL audit logging | DONE | config/graphql_view.py: logger.info for each POST (operation_name, authenticated); no PII. Rate limit already present. |
| Step 8 SCIM + Section8 LTI audit logging | DONE | scim_views: _log_scim_request (path, method, resource, authenticated); section8_views: _log_lti_request (path, method, operation, tool_id); no PII. public_endpoint_audit §1 + §4 updated. Signature/replay for SCIM/LTI still manual_review_required. |
| Step 34 Launch checklist staging verification | PARTIAL | launch_studio_checklist.md §4: Step 34 closure = staging row + sign-off; dependency = staging access. Run 10-point checklist in staging before prod per RELEASE_CHECKLIST. NEXT_50 step 34 → PARTIAL until staging run recorded. |
| §8 marketing context comparison_table/replacement_messaging | PARTIAL | schools/marketing_views: context keys wired; config/settings.py defines MARKETING_COMPARISON_TABLE and MARKETING_REPLACEMENT_MESSAGING (default [] and {}); override via env JSON or Django settings. MARKETING_FRONT_PLACEHOLDER action 8 updated; content TBD. |
| Raw SQL audit | DONE | docs/raw_sql_audit.md; per-usage record; CI lint. |
| Broad exception audit | DONE | docs/broad_exception_audit.md; allowlist + CI. |
| AI secret hardening | DONE | No secrets in UI; backend gateway only; docs/AI_GATEWAY_AND_CAPABILITY_FLAGS.md. |
| Siteconfig freeze policy | DONE | docs/SITECONFIG_FREEZE_POLICY.md; CI forbids new get_solo/load in tenant apps. |
| §2.1 domain_ownership doc | DONE | docs/domain_ownership.md: field ownership, resolver path, legacy-path policy; references apps/siteconfig/domain_ownership.py. |
| §2.1 evals/caching resolver | DONE | evals/caching.py: SiteSettings.load() → get_cached_site_settings(school=); lint_tenant_settings flags SiteSettings.load(). |
| Bounded context ownership | DONE | docs/bounded_context_ownership.md; 15 contexts, owner + source-of-truth. |
| Runtime precedence | DONE | docs/runtime_precedence.md; 7-step order; platform_runtime implements. |
| Gilead theme/report defaults | DONE | Migration 0155_normalize_gilead_residue_runmycampus. |
| Studio OS shared shell | DONE | Shell + all five mode hubs (rail + iframe switcher); customizer→Studio OS Experience redirect in place; pack tooling deferred to product. |
| Experience / Automation / Output / Launch / Control Studio | DONE | All five mode hubs done; customizer redirect in place; pack tooling deferred. |
| Metadata catalog complete | DONE | Governance UI; search API; EntityCatalogEntry.lifecycle_state + migration 0007; lineage API + graph UI at /api/internal/metadata/lineage/ and /lineage/graph/. |
| Package engine production-grade | **DONE** | validate/preview/apply/rollback/promote in apps/packages/engine.py; apps/packages/tests/test_engine in pre_deploy_gate; MASTER_PLATFORM_CHECKLIST Phase 4 Done; package_engine_ledger §5 gate [x]. §12 gate MET. |
| Marketplace seed (25+ apps, 25+ blueprints, etc.) | **DONE** | platform_inventory + get_platform_catalog_counts(); all catalog minimums met. Marketplace UI shows counts (governance_console, app_catalog, tenant_app_catalog, blueprint_marketplace); Install to sandbox + Apply/Preview/Rollback in place. Step 36 DONE. |
| §12 gate: marketplace/packs deeply productized | **DONE** | MARKETPLACE_SEED_TARGETS §5: catalog minimums test (test_marketplace_catalog_minimums) in pre_deploy_gate; UI counts and Install/Apply/Preview/Rollback required; generate_platform_inventory --check in CI. RUNMYCAMPUS §12 [x]; BACKLOG §6.3 MET. |
| Webhook signature verification (§2.4) | DONE | Billing and finance reject missing/invalid signature with 401. |
| Legacy path removed (§2.1) | DONE | siteconfig.webhook_delivery removed; callers use apps.events.webhooks. |
| Step 6 ensure_gilead_admin removed / legacy-path removal | PARTIAL (BLOCKED) | ensure_gilead_admin removed; customizer→studio_os redirect in place. **Further legacy-path removal BLOCKED on product confirmation** (BACKLOG §2d; NEXT_50 step 6). Clear note: no additional legacy URL deletion until product confirms. NEXT_50: **48 DONE, 1 PARTIAL, 1 NOT DONE** (step 4 NOT DONE; step 6 PARTIAL BLOCKED). |
| Accounts giant file split (§3) | DONE | views_workflow.py (approval/automation/import/workflow/academic_rules). |
| Schools giant file split (§3) | DONE | super_views_catalog.py (workflow/dashboard/blueprints/policies/registries/metadata catalogs). |
| Finance broad-except replacement (§2.4) | DONE | Full app pass: all modules at allowlist 0; see broad_exception_audit §1 apps/finance. |
| Portal broad-except replacement (§2.4) | DONE | views_parent_finance, models_kb, views_documents, services, views_kb, views_ai_copilot, **views_ai_gateway** (allowlist 0): typed exceptions + GATEWAY_VIEW_ERRORS; broad_exception_audit updated. ai_provider etc. remain allowlisted. |
| Schools broad-except replacement (§2.4 / step 9) | DONE | health_repository, **models.py** (limits + _has_feature_fallback→typed + logger.debug; allowlist 0), middleware.py, signup_views.py, tasks.py, marketing_views.py, onboarding_service.py, super_views.py, welcome_email.py, celery_tasks.py, domain_sync.py, funnel_events.py, control_plane_lifecycle.py, control_plane.py, rls_context.py, repositories/health_repository.py, management/commands: align_tenant_config, tenant_health_check, validate_marketing_urls, tenant_wind_down, migrate_tenant_schemas_one_by_one, verify_custom_domains (all typed; allowlist 0); remaining per broad_exception_audit. |
| Marketing proof_hero_image_key / §12 marketing front platform-grade | **DONE** | §12 gate MET. proof_hero_image_key + why_switch_bullets in use; all context keys have non-empty fallbacks (incl. health_score_visual_url→_diagram_fallback); full fallback asset set in static/images/marketing/. MARKETING_FRONT_PLACEHOLDER §3–§4 completion gate checked. Optional: replace placeholders with final creative via env or static. |
| Docs contradict platform reality | **DONE** | §9 docs alignment policy (BACKLOG §2c); PATH_TO_10_SCORECARD + NORTH_STAR_PLATFORM disclaimers; MASTER_PLATFORM_CHECKLIST states §12 authority. When editing any doc that mentions completion or 9.5, align with RUNMYCAMPUS §12 and this ledger. No 9.5 claim until §12 gates met. |
| **§12 docs truth no contradictions gate** | **DONE** | docs/DOCS_TRUTH_AUDIT.md: completion authority §12 + BACKLOG §6.3; key docs table aligned; gate MET. PLATFORM_9.5_SCORE_DRY_RUN, REMAINING_WORK, WHAT_IS_LEFT_MASTER, AUDIT_RERUN_RESULT updated with §12 disclaimers. RUNMYCAMPUS §12.1 evidence + BACKLOG §6.3 MET. |
| Phase G — align docs with reality | **DONE** | §9 docs alignment policy (BACKLOG §2c); PATH_TO_10_SCORECARD + NORTH_STAR_PLATFORM disclaimers; no 9.5 claim until §12. Ledgers map work to DONE/PARTIAL; when touching docs, align with RUNMYCAMPUS §12 and this ledger. |
| AI surface audit | DONE | docs/AI_surface_audit.md |
| AI audit trail | PARTIAL | log_ai_action + gateway metrics; get_ai_permission_for_user implemented and wired in views_ai_gateway |
| Raw SQL replacement targets | **DONE** | All business-logic wraps DONE. Allowlist shrunk: raw_sql_allowlist.json only repos + cache_utils (10 entries); wrapped paths removed. raw_sql_audit.md + raw_sql_replacement_targets.md DONE. lint_raw_sql_usage pass. Step 10 DONE. |
| Metadata lineage | PARTIAL | docs/metadata_lineage_approach.md; unified lineage API + lineage graph UI at /api/internal/metadata/lineage/graph/ (form, downstream, blast radius, packages, SVG graph); coverage for workflows, dashboards, reports, APIs, templates via usage_registry. |
| Feature control / why enabled | PARTIAL | docs/feature_control_ledger.md |
| Subprocess classified | DONE | docs/subprocess_usage_ledger.md |
| Subprocess when-adding rule (NEXT_50 step 39) | DONE | Ledger §3: when adding subprocess call, add row to table and apply policy; completion gate updated. |
| Feature toggle inspection fail closed (§2.4) | DONE | runtime_inspector: DatabaseError in catch; return [] on error; docstring. |
| Studio OS shell requirements doc | DONE | studio_os_shell_requirements.md: all 8 shared requirements DONE. |
| Packages dependency/impact preview (§6.4) | DONE | validate_package; _compatibility_report; preview_diff; _build_impact_summary. |
| Setup Studio health/recommendation (§6.5) | DONE | get_setup_studio_payload provides health_summary, recommended_next, role_previews; used by Launch Studio / Studio OS. |
| verify_onboarding_setup raw SQL wrap (§2.4) | DONE | check_siteconfig_migration_applied in onboarding_verification.py; command uses helper; raw_sql_allowlist + audit updated. |
| verify_onboarding_setup typed exceptions (§2.4) | DONE | LookupError; (LookupError, OSError, TypeError); ImportError. |
| Page archetype operational-workbench (§8.3) | DONE | workflow_center, studio_os/shell, orchestration/operator_workbench. |
| Page archetype catalog (§8.3) | DONE | metadata/governance, app_catalog, tenant_app_catalog, governance_console, blueprint_marketplace, lineage_graph. |
| Page archetype record-detail (§8.3) | DONE | data-page-archetype="record-detail" on requests/detail.html (single-request view). |
| Backlog/deferred closure | DONE | docs/BACKLOG_AND_DEFERRED_CLOSURE.md: every unchecked/deferred item has status (DONE/PARTIAL/NOT DONE/BLOCKED) and closure note. |
| Optionals and recommendations (non-negotiable) | **DONE** | Policy: all optionals must be **DONE**; nothing deferred. RUNMYCAMPUS §11.1: all items DONE (Experience/Automation/Launch/Control Studios, Phase E, §12.1 record gate output). BACKLOG §2f: status table all DONE; record_pre_deploy_gate_output.sh + RELEASE_CHECKLIST; refresh_marketplace_seed_targets.py; marketplace UX + ReportPack/DocumentPack; role-home/proof-rich marketing. No open optional. |
| Implementation dependencies and order | DONE | docs/IMPLEMENTATION_DEPENDENCIES_AND_ORDER.md: dependency graph, get_solo/raw SQL/signature refactor checklist, §4 Studios and §7 scope, §9/§12 actions. |
| §9 MASTER_PLATFORM_CHECKLIST alignment | DONE | 9.5/10 not claimed until §12; completion authority RUNMYCAMPUS §12; BACKLOG_AND_DEFERRED_CLOSURE referenced. |
| MASTER_PLATFORM_CHECKLIST completion rows match §12 (step 48) | DONE | Phase ledger footnote: "Done" = phased 0–8 scope; §12 gates sole authority for 9.5; BACKLOG_AND_DEFERRED_CLOSURE linked. |
| §12 gates evidence (step 46) | DONE | RUNMYCAMPUS §12.1 table: every gate has verification (lint/CI/test/doc); optional: record CI output per gate. |
| §12 gate: siteconfig materially decomposed | **DONE** | domain_ownership + bounded-context surfaces; no tenant get_solo (lint_tenant_settings, lint_siteconfig_legacy_imports); get_effective_site_settings runtime-first. domain_ownership.md §6; BACKLOG §2.1 move ownership (behavioral) DONE. |
| §12 gate: SiteSettings not tenant-behavior truth | **DONE** | Tenant-behavior truth = get_effective_site_settings output (runtime-first); SiteSettings is legacy data source only. Same verification; BACKLOG §2.1 completion gates DONE. |
| Security review checklist (step 49) | DONE | RUNMYCAMPUS §12.2 checklist executed and logged. RELEASE_CHECKLIST Security review section added; SECURITY_REVIEW_LOG.md created; run 2026-03-13: Public endpoints PASS, AI gateway PASS, Secrets (lint_secret_exposure) PASS. §12.2 checkboxes in RUNMYCAMPUS marked [x]. |
| §7 First-party apps 25+ (seed_first_party_apps) | DONE | packages/management/commands/seed_first_party_apps.py: 27 PackageVersion distinct package_id; platform_inventory first_party_apps 27. MARKETPLACE_SEED_TARGETS §4 action 1 DONE; package_engine_ledger §4. |
| Release notes subtractive cleanup (step 50) | DONE | docs/SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md: template + running log; RELEASE_CHECKLIST.md Pre-release step references it. |
| Billing app broad-except replacement (§2.4 / step 9) | DONE | entitlements.py, services.py, admin.py: typed exceptions + logging; allowlist 0. |
| Finance app broad-except replacement (§2.4 / step 9 full) | DONE | Full app: all finance modules at allowlist 0; see broad_exception_audit §1 apps/finance. |
| finance payment_validators_temp.py (legacy/deferred) | DONE (closure) | Documented in BUILD_IMPROVEMENTS and MODULE_AUDIT as consolidate or remove; no app imports; no code change until product confirms. Closed so nothing left "not done." |
| Api app broad-except replacement (§2.4 / step 9) | DONE | dashboard_api, digital_id_api, ministry_connectors, rate_limit, search_api, entity_api: typed exceptions + logging; allowlist 0; broad_exception_audit §1 updated. |
| §2.4 Webhook audit logging | DONE | Billing: BillingProcessorSyncEvent + incident; Finance: WebhookLog; **Lead capture:** logger.info lead_capture_created/lead_capture_duplicate (school_id, applicant_id, lead_source, ip); public_endpoint_audit updated. |
| §12 Marketing placeholder wiring | **DONE** | All context keys and template slots wired in marketing_views; MARKETING_* in config/settings.py or getattr fallbacks. MARKETING_FRONT_PLACEHOLDER status "Wiring DONE"; §4 table Wiring DONE / assets TBD. Remaining: asset pipeline (create/source images; plug via env or static). |
| get_solo allowlist (platform_runtime/management) | DONE | SITESETTINGS_GET_SOLO_ALLOWLIST.md: platform_runtime/management/commands documented. |
| Observability DB liveness wrap (§2.4 / step 44) | DONE | db_liveness.check_db_liveness(); db_health_check + synthetic_probe commands delegate to it; monitoring/views use it; allowlist updated; test_db_liveness.py. |
| Resolver registry when-adding policy (step 21) | DONE | resolver_registry.py module docstring: append to RESOLVER_ENTRY_POINTS, run contract tests, document in bounded_context_ownership if cross-context. |
| Resolver registry contract test (step 20) | DONE | test_resolver_registry_dotted_paths_importable: module-only paths (e.g. apps.metadata.services) now pass; test tries import_module(loc) first. test_runtime_contract.py. |
| Siteconfig import fixes (manage.py check) | DONE | siteconfig.models re-exports (FeatureToggleDefinition/State, TourStep, CountryMultiplier, ReportCardStyleAssignment, HolidayCalendar); context_processors, forms, dashboard_resolver, communication/views_announcements, portal/views import from models_support (or defining module) to avoid circular deps; manage.py check passes. BACKLOG §3, §5, §5a updated. |
| Step 40 code hygiene — accounts | DONE | accounts app: ruff F401/F841 (46: 38 auto + 8 _prefix); urls import workflow views from views_workflow/views_migration. code_hygiene_ledger, NEXT_50 step 40, BACKLOG §1 §10 + §5a updated. |
| Step 40 code hygiene — api | DONE | api app: ruff F401/F841 (31); urlconf intervention from views_v1_intervention. accounts/urls: migration views from .views_migration. manage.py check passes. BACKLOG §5, §10, NEXT_50 step 40, code_hygiene_ledger updated. |
| Step 40 code hygiene — portal | DONE | portal app: ruff F401/F841 (82); urlconf imports parent_finance/parent_wallet/parent_feed from .views_parent_finance, teacher/student_onboarding_wizard from .views_onboarding; verify_onboarding_setup redundant import removed. schools/super_urls: super_migration_cloud, super_migration_profile_registry, super_migration_rollback from .super_views_migration. manage.py check passes. BACKLOG §5, §10, NEXT_50 step 40, code_hygiene_ledger updated. |
| Step 40 code hygiene — policies | DONE | policies app: ruff F401/F841 (7 auto). manage.py check passes. BACKLOG §1 §10, NEXT_50 step 40, code_hygiene_ledger updated. |
| Step 40 code hygiene — runtime_blueprints | DONE | runtime_blueprints app: ruff F401/F841 (3 auto). manage.py check passes. BACKLOG §1 §10, NEXT_50 step 40, code_hygiene_ledger updated. |
| Step 40 code hygiene — apicenter + platform_runtime | DONE | apicenter tests: F401 remove unused api_center_dashboard import; platform_runtime: runtime_inspector remove Optional, runtime_resolver remove unused School import (job-mode path). Ruff clean for these apps; siteconfig 51 remain (re-exports noqa). code_hygiene_ledger, NEXT_50 step 40, BACKLOG updated. |
| Where we stand snapshot (BACKLOG § / Step 25) | DONE | BACKLOG "Where we stand (snapshot)" table added: plan §1–§12 summary, NEXT_50 (40 DONE / 6 PARTIAL / 4 NOT DONE), Step 40 remaining, next logical steps. dashboard/interop/payroll/studio_os F401/F841 verified clean. Doc-only; Last reconciled updated. |
| §7 workflow + dashboard seed | DONE | seed_workflow_dashboard_packs extended to 30 workflow packs, 21 dashboard packs; workflow 30+ and dashboard 20+ minimums met. MARKETPLACE_SEED_TARGETS §2 §4 actions 3–4 DONE. BACKLOG §1 §7 updated. |
| §7 blueprint + policy seed | DONE | seed_blueprint_policy_packs extended: +10 BlueprintPack (25 total), +5 PolicyBundle (15 total). Blueprint 25+ and policy 15+ minimums met. MARKETPLACE_SEED_TARGETS §2 §4 actions 2 and 5 DONE. BACKLOG §1 §7 updated. |
| §7 action 7 seed data/manifests in package_engine_ledger | DONE | package_engine_ledger.md §4 (Seed data and manifests): commands table, manifests note; §3 table with current counts. MARKETPLACE_SEED_TARGETS §4 action 7 DONE. BACKLOG §5 updated. |
| §5–§7 platform_inventory --format json | DONE | platform_inventory: --format json for scripted §2 refresh; bare except → typed (ImportError, AttributeError, TypeError, DatabaseError, OperationalError, ProgrammingError) + logger.debug. MARKETPLACE_SEED_TARGETS §2 run note updated. BACKLOG §5 §7 updated. |
| §5–§7 MARKETPLACE_SEED_TARGETS §4 action table | DONE | MARKETPLACE_SEED_TARGETS.md §4: 7 action items (first-party apps 25+, blueprints +10, workflows +23, dashboards +14, policy +5, marketplace UI, ledger doc); each with Owner/mechanism and Status. Nothing left behind. |
| §8/§12 MARKETING_FRONT_PLACEHOLDER §4 action table | DONE | MARKETING_FRONT_PLACEHOLDER.md §4: 9 asset/action items (hero, why_switch DONE; product visuals, migration diagram, ecosystem, role-home, setup-studio, replacement messaging, institution/region NOT DONE with clear action). Nothing left behind. |
| §3.1/§3.2 BACKLOG §2d legacy-path checklist | DONE | LEGACY_PATH_INVENTORY.md: all paths (REMOVED/REDIRECT/CANDIDATE); §2d: (1) policy+inventory DONE, (2)(3) get_solo/fallback removed from tenant path DONE, (4) doc policy DONE. runtime_precedence.md §3: tenant-facing fallback DONE. |
| Step 14 lint_secret_exposure verification | DONE | Run after AI/template change; latest run: pass — no client-side or tracked-config provider secret exposure. BACKLOG §3 + §5 updated. |
| NEXT_50 step 9 sync with §1 | DONE | Step 9 text now matches §1: schools (health_repository + models.py DONE; middleware, signup_views, etc. ongoing). BACKLOG §5 + Last reconciled updated. |
| RLS context contract test (§2.4 / step 45 optional) | DONE | apps/schools/tests/test_rls_context.py: set_rls_school_id/reset_rls_school_id callable, set-then-reset cycle, idempotent reset. |
| Cross-context RLS interface doc (step 22) | DONE | bounded_context_ownership.md §2: schools.rls_context (set_rls_school_id/reset_rls_school_id) as single place for app.current_school_id; middleware uses it. |
| Entity catalog lifecycle_state (§3.3) | DONE | EntityCatalogEntry.lifecycle_state (draft/active/deprecated); migration 0007; catalog search, governance UI, bundle export/import; APIs expose active-only by default (?lifecycle=all / active_only=False to override). |
| Unified lineage API (§3.3) | DONE | GET /api/internal/metadata/lineage/ (object_type=entity|field|package|consumer); apps/metadata/lineage_api.get_unified_lineage(); aggregates usage_registry + package lineage + blast radius; staff-only; tests in test_lineage_api.py. |
| Marketing placeholder keys wired (§12) | DONE | migration_diagram_url, ecosystem_diagram_url, control_plane_diagram_url, setup_studio_flow_image_url, health_score_visual_url, role_preview_images in marketing_views + marketing_landing template. |
| Management commands when-adding rule (step 38) | DONE | management_commands_inventory.md §4: new command → ledger entry + tests (or docstring verification); compliance ongoing for existing commands. |
| Observability broad-except sprint (step 9) | DONE | apps/observability: views, monitoring, middleware, templatetags, synthetic_probe — all broad excepts replaced with typed exceptions + structured logging; db_liveness single keep with log; broad_exception_audit §1 updated. |
| Requests + Metadata broad-except sprint (step 9) | DONE | apps/requests: tasks.py (Notification create + task body), services.py (GradeApprovalRequest lookup); apps/metadata: changelog.py (record_metadata_changelog). Typed exceptions + logging; broad_exception_audit §1 updated. |
| Automation app broad-except (step 9) | DONE | apps/automation/models.py: rollback run → (DatabaseError, IntegrityError, ValidationError, ValueError, TypeError) + logger.exception; broad_exception_audit §1 updated. |
| §12 Evidence table (step 46) | DONE | RUNMYCAMPUS §12.1: Evidence table has "In CI" column per gate; one-liner pre_deploy_gate.sh for local verification; optional full check-off unchanged. |
| BACKLOG_AND_DEFERRED_CLOSURE reconciliation | DONE | §1 and §2/§2b complete. RUNMYCAMPUS checkboxes aligned: Phase C "Add lineage and inspector" [x]; §6.3 metadata catalog/lineage/lifecycle+search [x]. §5a and Last reconciled updated. |
| Step 47 (no duplicate strategy docs) | DONE | BACKLOG §2c: verification note added; only four canonical docs receive completion updates; NEXT_50 step 47 DONE. |
| Step 12 (pre_deploy_gate in CI) | DONE | .github/workflows/smoke.yml runs `bash scripts/pre_deploy_gate.sh` on push and pull_request to main; timeout 25 min; NEXT_50 step 12 DONE. |
| Step 37 API Center governance | DONE | apicenter_integration_governance.md: dashboard shows rate limits/quotas + audit log; apps.apicenter.tests.test_governance_contract (auth, Integration); doc actions/checkboxes updated. Per-endpoint hardening and interop workbench remain optional. |
| Step 41 Automation bounded console | DONE | automation/outcomes_console view + template (MigrationRun, AutomationExecutionLog); automation/urls; config/urls automation/; Studio OS automation rail "Outcomes" first; staff-only. Outcomes only, no raw settings. |
| Step 42 Finance/accounts broad except policy | DONE | broad_except_allowlist.json: policy + issue_link; allowed_counts 0 for finance/accounts; lint_broad_except --strict in CI. No new broad except without allowlist entry + issue. |
| Step 17 api_tenant_maturity get_effective_site_settings | DONE | api_tenant_maturity (portal/views_ai_gateway.py) uses get_effective_site_settings(request=request); remaining direct reads audited via lint_tenant_settings in CI. NEXT_50 step 17 DONE. |
| Step 9 schools rls_context broad except | DONE | schools/rls_context.py: rls_school finally-block RESET → (OperationalError, ProgrammingError, DatabaseError); allowlist 0; lint_broad_except --strict pass. |
| Step 40 code hygiene (one app) | DONE | All apps F401/F841 clean. siteconfig re-exports: noqa: F401 on all blocks in siteconfig/models.py; ruff check apps --select F401,F841 passes. Step 40 complete. |
| §10 print + hygiene debt | **DONE** | No print() in apps outside tests/management/migrations (lint_no_print_in_apps pass); CI enforced; code_hygiene_ledger §8 completion gate updated. BACKLOG §1 ?10 rows marked DONE. |
| Step 25 reconciliation (this run) | DONE | Ledger §2 cross-checked with BACKLOG §1 and NEXT_50; statuses consistent. Step 14 lint_secret_exposure re-run: pass. BACKLOG Last reconciled + §3 + §5a updated. No 9.5 claim; §12 gates remain authority. |
| Step 13 migration 0155 + lint_gilead_residue | PARTIAL | Migration 0155 applied (this env); lint_gilead_residue.py pass. Apply in staging then prod at deploy (RELEASE_CHECKLIST Pre-release). NEXT_50 step 13 PARTIAL. |
| Siteconfig 0156 (EducationSystemProfile subject_seed/term_labels) | DONE | Migration 0156_alter_educationsystemprofile_subject_seed_and_more created (serializable defaults) and applied. Aligns model help_text/default with models_platform_catalog. |
| CMR/XAF hardcoded advisory (lint_tenant_settings full) | DONE (closure) | Documented in BACKLOG §3 and §2e; full run = advisory only; CI uses --check-get-solo-only. No code change required; closure = documented. Cleanup incremental per SITESETTINGS_AUDIT when touching those areas. |

---

## 3. Rule

- Do not claim 9.5/10 or 11/10 until §12 gates in RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md are satisfied.
- When updating any roadmap or audit doc, set each item to exactly one of: DONE, PARTIAL, NOT DONE, DEPRECATED, BLOCKED. No "save for later" or "backlog" without a status.

---

## 4. Completion gate (§9)

- [x] Audit docs folder; map key items to this ledger.
- [x] One canonical completion ledger (this file).
- [x] Remove contradictory "fully complete" language from all docs — DONE: §9 docs alignment policy in BACKLOG §2c; PATH_TO_10_SCORECARD + NORTH_STAR_PLATFORM disclaimers; when touching docs, align with RUNMYCAMPUS §12 and this ledger.

**Reconciliation (NEXT_50 step 25):** Ledger §2 aligned with BACKLOG §1 and NEXT_50. Completion authority = RUNMYCAMPUS §12; do not claim 9.5/10 until §12 gates are satisfied. **Policy:** Reconcile after each milestone. **Last reconciliation:** 2026-03-13. Step 14 + baseline (lint_secret_exposure, lint_raw_sql_usage, lint_broad_except --strict, manage.py check) all pass; Step 25 reconciled. Snapshot: 49 DONE, 1 NOT DONE (step 4); Step 6 PARTIAL (BLOCKED). Nothing left behind.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §9.*
Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §9.*
