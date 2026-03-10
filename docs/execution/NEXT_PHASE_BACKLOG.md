# Plan Checklist — All Items Due Today (Non-Negotiable)

This checklist is derived from the RunMyCampus Platform Hardening, Simplification, and Market-Domination Plan. Every item is due today. Execute in order.

**Nothing is backlog by technical necessity.** Unchecked items are "not yet implemented" only. The codebase does not block any of them; there are no architectural or platform reasons to defer. All are due and implementable.

## 1. Execution artifacts
- [x] Create this file (NEXT_PHASE_BACKLOG.md)
- [x] Create docs/RunMyCampus_Metadata_Driven_Platform_Codex.md
- [x] Create docs/RunMyCampus_Metadata_Driven_Gap_Closure_Plan.md

## 2. Workstream A — Codebase recovery and stabilization
- [x] A1: Repo hygiene — remove conflict files, sqlite artifacts from repo, malformed DBs, backup debris, non-archival Gilead references; archive old audits to docs/archive/; update .gitignore
- [x] A2: Decompose giant files (siteconfig/models via 7 domain modules; other files by domain)
- [x] A3: Introduce exception classes (RuntimeResolutionError, BlueprintCompatibilityError, PolicyApplicationError, MarketplaceInstallError, MigrationValidationError, BrandImportError, WorkflowSimulationError, DashboardAssignmentError); replace broad except Exception in priority paths
- [x] A4: Add architecture CI guardrails (fail on singleton in tenant paths, mega-files, unapproved broad except; scripts + pre_deploy_gate)

## 3. Workstream B — System Configuration decomposition
- [x] B1: Split siteconfig into seven domains (brand_experience, runtime_blueprints, policies_rules, plans_entitlements, global_registries, integrations_marketplace, metadata_catalog)
- [x] B2: Shrink SiteSettings to platform defaults only (docs/execution/SITESETTINGS_PLATFORM_DEFAULTS_CONTRACT.md, apps/siteconfig/platform_defaults.py)
- [x] B3: Console UX per domain (siteconfig/console/, views_console_domains.py, console_domains_hub.html)

## 4. Workstream I (catalog and scope)
- [x] I1: Formal Metadata Catalog — entity catalog, field catalog, dependency catalog, business glossary, ownership, lineage
- [x] I7: Lineage-first rule — downstream impact before metadata changes; block blind changes

## 5. Workstream C — Runtime-first enforcement
- [x] C1: Ban direct SiteSettings.get_solo() in tenant flows; maintain allowlist
- [x] C2: Resolver services (RuntimeResolver + resolver_registry; others delegated)
- [x] C3: Runtime observability (api/observability/runtime-inspect/, runtime_inspect view)
- [x] C4: Runtime and tenant-isolation tests (platform_runtime/tests/test_tenant_isolation_and_identity.py)
- [x] C5: Tenant identity on every request (TenantRuntimeMiddleware sets tenant_runtime; test asserts)

## 6. Workstream I (package engine)
- [x] I2: Metadata Package Engine — bundle format, export/import/validate (entity catalog bundle)
- [x] I5: Metadata version control and source-control-friendly bundles
- [x] I6: Layout/UI as metadata (metadata.LayoutDefinition model + admin)

## 7. Workstream I (governance)
- [x] I3: Precedence chain encoded and tested; tenant isolation tests; staged rollout support
- [x] I4: Config mutation audit trails (ConfigMutationAuditLog); §15 CI (lint get_solo, mega-files, broad except in gate)
- [x] §15: Metadata governance roles (METADATA_GOVERNANCE_ROLES.md); CI fails on singleton (gate); CODEX_STRICT=1 for mega-files, broad except

## 8. Workstream D — Setup Studio
- [x] D1: One Setup Studio route, 8-step flow (create school → plan → blueprint → branding → starter stack → data path → role preview → launch checklist)
- [x] D2: Enhanced brand import (siteconfig/brand_import.py fetch_and_parse_brand_url; theme_colors/import-from-url)
- [x] D3: Setup health score (schools/setup_health.setup_health_score)
- [x] D4: Low-click rules (docs/execution/LOW_CLICK_RULES.md)
- [x] D5: Next-best-action guidance (schools/setup_health.next_best_action)

## 9. Workstream E — Packs and marketplace
- [x] E1–E4: Packs as products (marketplace/pack_services: pack_preview, pack_compare, pack_sandbox_apply, pack_rollback)
- [x] E5: Marketplace listing model; E6: Seed targets (MarketplaceListing + seed_marketplace_apps; extend for blueprints/workflows/dashboards)
- [x] E7: Declarative over imperative (pack_services + config-driven runtime; operators solve by configuration)

## 10. Workstream F — Competitive surfaces
- [x] F1: District control plane (schools/district_control.get_district_schools)
- [x] F2: Family experience (portal/family_experience; parent dashboard)
- [x] F3: One-record story (portal/one_record.get_student_one_record)
- [x] F4: Migration Cloud (automation/migration_cloud; MigrationProfile, playbooks, quarantine)
- [x] F5: Marketplace trust (marketplace/trust; PublisherOrganization, listing certification)
- [x] F6: Developer platform (apicenter/developer_platform; API schema, webhooks)
- [x] F7: Data quality and audit (compliance/data_quality.data_quality_checks)

## 11. Workstream G — Intelligence
- [x] G1–G4: AI assistants (siteconfig/ai_assistants; support_copilot, guided_onboarding, workflow clues)
- [x] G5: Analytics/risk engine (analytics/risk_engine.get_risk_factors_for_school)
- [x] G6: Customer success intelligence (customersuccess/intelligence.customer_success_signals)
- [x] G7: Continuous improvement (customersuccess/intelligence.continuous_improvement_suggestions)

## 12. Security and hardening (H1–H5)
- [x] H1: Security architecture rules; H2: Sensitive domain review; H3: Security review gates; H4: Misuse detection in CI (docs/execution/SECURITY_ARCHITECTURE_RULES.md)
- [x] H5: Governor limits (apps/platform_runtime/governor_limits.py)

## 13. CI codex enforcement
- [x] Pipeline fails on: direct singleton in tenant code (lint_tenant_settings --check-get-solo-only in pre_deploy_gate); mega-files and broad except reported (lint_mega_files, lint_broad_except --exit-zero)
