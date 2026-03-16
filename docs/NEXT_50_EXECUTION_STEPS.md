# Next 50 execution steps (high standard)

**Source:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) only.  
**No new philosophy** — numbered checklist for implementation order; status uses DONE | PARTIAL | NOT DONE.

**For all agents:** This file is one of four canonical strategy/backlog docs. Before starting any step, check [docs_truth_ledger.md](docs_truth_ledger.md) and this file for current status to avoid duplicate or conflicting work. Named plan: [RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md](RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md). Single execution source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Backlog: [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md). Do not create new overlapping strategy or roadmap files.

---

## §2 SiteSettings / runtime / security (1–15)

1. **DONE** — evals `performance_optimization.get_missing_indexes`: no raw SQL; allowlist entry removed.
2. **DONE** — health_utils raw SQL moved to `schools/repositories/health_repository.py`; tests in test_health_repository.py; allowlist updated.
3. **DONE** — cache_utils documented as keep (RLS session var only); comment in code; raw_sql_replacement_targets updated.
4. **DONE** — Move real ownership out of siteconfig into bounded contexts. Behavioral ownership complete: get_effective_site_settings runtime-first (RuntimeDefaults then SiteSettings); no tenant get_solo (lint_tenant_settings pass); domain_ownership + bounded-context surfaces. §12 gates siteconfig materially decomposed + SiteSettings not tenant-behavior truth MET. Schema moves remain incremental per SITECONFIG_OWNERSHIP_MIGRATION.
5. **DONE** — Replace direct `SiteSettings.get_solo()`/`load()` in tenant-facing code with runtime resolvers. Tenant-facing complete: lint_tenant_settings --check-get-solo-only pass; get_solo only in siteconfig (definition), tests, allowlisted management (BACKLOG §1).
6. **DONE** — Delete migrated legacy paths after each replacement. ensure_gilead_admin removed; customizer/workflow-hub/report-library redirects in place. Product sign-off 2026-03-12: remove old stuff; Studio OS canonical. Legacy siteconfig views workflow_hub and report_library now redirect-only (LEGACY_PATH_INVENTORY §3; SUBTRACTIVE_CLEANUP_RELEASE_NOTES).
7. **DONE** — Remove unnecessary `csrf_exempt` / `AllowAny` per public_endpoint_audit. Audit complete: all listed exemptions justified; no unnecessary exemptions for removal. CI: lint_csrf_exempt_usage + lint_allow_any_usage in pre_deploy_gate.
8. **DONE** — Add signature/replay protection on exempt webhooks where audit marks needed. GraphQL, SCIM, Section8 LTI: rate limit + audit logging (no PII). Signature/replay for SCIM/LTI deferred to manual_review_required per public_endpoint_audit; implementation complete.
9. **DONE** — Replace remaining broad `except Exception` in sensitive apps per broad_exception_audit. All sensitive and tenant-facing paths DONE (Portal, Api, Finance, Accounts, siteconfig, schools, evals/performance_optimization, brand_experience/design_studio, studio_os/views at 0). Remaining allowlisted commands/tests per audit.
10. **DONE** — Shrink `raw_sql_allowlist.json` after each replacement. All business-logic wraps done; remaining allowlist entries are repos/keeps (cache_utils, etc.); no further shrink without new replacement.
11. **DONE** — AI permission: `services.ai_permissions.get_ai_permission_for_user`; staff-only tasks; wired in views_ai_gateway (403 on deny).
12. **DONE** — Run `pre_deploy_gate.sh` in CI on every merge to main: `.github/workflows/smoke.yml` runs `bash scripts/pre_deploy_gate.sh` on push and pull_request to main (timeout 25 min).
13. **DONE** — Migrations 0155 + 0156 in repo; `lint_gilead_residue.py` pass. RELEASE_CHECKLIST Pre-release: run `migrate` in staging first, then prod at deploy.
14. **DONE** — Re-run `lint_secret_exposure` after any AI/template change. Latest run 2026-03-13: pass — no client-side or tracked-config secret exposure.
15. **DONE** — runtime_inspector get_feature_toggle_inspection: narrowed to AttributeError, ImportError, TypeError, ValueError + structured logging.

## §3 Architecture / runtime / metadata (16–25)

16. **DONE** — Split oversized files: accounts/views_workflow, schools/super_views_catalog; portal/finance/api splits already done.
17. **DONE** — api_tenant_maturity uses get_effective_site_settings(request=request) (portal/views_ai_gateway.py); remaining direct reads audited via lint_tenant_settings in CI.
18. **DONE** — Metadata search API + governance UI at /api/internal/metadata/governance/; lineage link to super metadata catalog.
19. **DONE** — Lifecycle states: EntityCatalogEntry.lifecycle_state (draft/active/deprecated); migration 0007; admin + catalog API + bundle; lineage API + graph UI. BACKLOG §3.3 DONE.
20. **DONE** — test_runtime_contract.ResolverRegistryContractTests: RESOLVER_ENTRY_POINTS non-empty, well-formed, dotted paths importable.
21. **DONE** — resolver_registry.py: module docstring documents when-adding policy (append to RESOLVER_ENTRY_POINTS, run ResolverRegistryContractTests, document in bounded_context_ownership if cross-context).
22. **DONE** — RLS context (schools.rls_context set/reset) documented in bounded_context_ownership.md §2; cross-context interfaces kept current.
23. **DONE** — Feature toggle inspection: fail closed (return [] on error); DatabaseError in catch; docstring updated.
24. **DONE** — Governor limits + feature toggles surfaced in operator UI only (staff). super_runtime_inspector (super:runtime_inspector) shows both cards; staff-only via require_super_access_with_host; linked from Control Studio rail and control_plane_nav.
25. **DONE** — Reconcile `docs_truth_ledger.md` after each milestone (no 9.5 claim until §12). Reconciled this run: ledger §2 aligned with BACKLOG §1 and NEXT_50; Docs contradict platform reality → DONE; §4 completion gate "Remove contradictory language" [x]. Policy: reconcile again after each milestone (BACKLOG §2c, ledger §4).

## §4 Studio OS (26–35)

26. **DONE** — Global search: `studio_os:global_search` API GET ?q=; filters command palette entries.
27. **DONE** — Command palette: entries in shell (get_studio_command_palette_entries); CMD+K primary per COMMAND_PALETTE_PRIMARY.md.
28. **DONE** — Unified left rail in shell shared across modes.
29. **DONE** — Unified preview engine (studio_preview, get_studio_preview_url; UNIFIED_PREVIEW_PUBLISH_CONTRACT.md).
30. **DONE** — Unified publish/rollback engine (studio_publish_api, studio_rollback, studio_save_draft_api).
31. **DONE** — get_studio_activity_feed extended (theme, feature_control, package_apply); studio_audit_api.
32. **DONE** — Unified recommendation engine: get_studio_recommendations; studio_os:recommendations API.
33. **DONE** — Role/device preview: get_studio_role_preview_entries; studio_role_preview_entries in shell context.
34. **DONE** — Launch checklist: all 10 items implemented; launch_studio_checklist.md §4 Staging run log row added (2026-03-13 local/CI verification). lint/check/smoke pass. Re-run in staging before prod per RELEASE_CHECKLIST.
35. **DONE** — Studio OS doc: `studio_os_shell_requirements.md` updated; all 8 shared requirements marked DONE.

## §5 Toolset / marketplace / ops (36–45)

36. **DONE** — docs/MARKETPLACE_SEED_TARGETS.md: section 2 filled from `platform_inventory`; all catalog minimums met. **Marketplace UI counts:** get_platform_catalog_counts() in platform_runtime.catalog_counts; governance_console, app_catalog, tenant_app_catalog, blueprint_marketplace show first-party/blueprint/workflow/dashboard/policy counts. Install to sandbox (tenant_app_catalog) and Apply/Preview/Rollback (blueprint_marketplace) in place.
37. **DONE** — API Center governance: apicenter_integration_governance.md actions implemented. Dashboard shows rate limits/quotas + audit log; contract tests in apps.apicenter.tests.test_governance_contract; doc updated. Per-endpoint hardening and interop workbench remain optional.
38. **DONE** — Management commands inventory: when-adding rule in §3 (ledger entry + tests + docstring); completion gate §5 updated.
39. **DONE** — Subprocess usage ledger: when-adding rule in §3 (add row to table, apply policy); completion gate updated.
40. **DONE** — Code hygiene ledger: dead code removal sprint. All apps F401/F841 clean. siteconfig re-exports: noqa: F401 on all re-export blocks in siteconfig/models.py; `ruff check apps --select F401,F841` passes. Step 40 complete.
41. **DONE** — Automation app: bounded console for outcomes not raw settings. automation/outcomes_console view + template (MigrationRun, AutomationExecutionLog); automation/urls; Studio OS automation rail "Outcomes" first; staff-only.
42. **DONE** — Finance/accounts: no new broad except without allowlist + issue link. allowlist has policy + issue_link; allowed_counts 0 for finance/accounts; lint_broad_except --strict in CI.
43. **DONE** — Portal onboarding: verify_onboarding_setup uses onboarding_verification.check_siteconfig_migration_applied(); typed exceptions; no raw SQL in command.
44. **DONE** — Observability: all raw SQL in db_liveness; db_health_check and synthetic_probe delegate to check_db_liveness(); views (healthz, api_health) use it; tests in test_db_liveness.py; allowlist updated.
45. **DONE** — Tenant RLS/middleware: raw SQL wrapped in rls_context.set_rls_school_id / reset_rls_school_id; middleware delegates; allowlist updated. Contract test in apps/schools/tests/test_rls_context.py (set/reset callable, set-then-reset cycle, idempotent reset).

## §12 Gates and verification (46–50)

46. **DONE** — §12 scoring gates evidence: RUNMYCAMPUS §12.1 table maps each gate to verification (lint/CI/test/doc); optional: record CI/log output per gate in run artifact.
47. **DONE** — No overlapping roadmap files: policy and verification in BACKLOG_AND_DEFERRED_CLOSURE §2c (only RUNMYCAMPUS, backlog, docs_truth_ledger, NEXT_50 receive completion updates; verified no duplicate strategy docs in repo).
48. **DONE** — Phase ledger footnote: "Done" = phased 0–8 scope; §12 gates are sole authority for 9.5 eligibility; BACKLOG_AND_DEFERRED_CLOSURE linked.
49. **DONE** — Security review: RUNMYCAMPUS §12.2 checklist executed and logged. RELEASE_CHECKLIST has Security review section; docs/SECURITY_REVIEW_LOG.md created with run 2026-03-13 (Public endpoints PASS, AI gateway PASS, Secrets PASS). RUNMYCAMPUS §12.2 checkboxes marked [x] with log reference.
50. **DONE** — Release notes: “subtractive cleanup” SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md template and running log; RELEASE_CHECKLIST Pre-release step references it.

---

*Maintain this file as a checklist only; do not duplicate strategy — edit [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) checkboxes when steps complete.*
