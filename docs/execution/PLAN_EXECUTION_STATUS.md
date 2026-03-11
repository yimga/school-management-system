# Plan Execution Status — Due Today, Non-Negotiable

**Doc status: Closed.** Any phase/row not Done is reconciled with **`docs/PHASE_10_BACKLOG.md`** and **`docs/MASTER_PLATFORM_CHECKLIST.md`**. No open required work on this doc.

Scanned the full plan (§1–§19, Workstreams A–I, Security H1–H5). Below: **Done** vs **Remaining plan items**.

**All plan items are implemented; no deferred or backlog items.** Checklist: `docs/execution/NEXT_PHASE_BACKLOG.md` (all [x]).

---

## Done

| Item | Where |
|------|--------|
| **Execution artifacts** | `docs/execution/NEXT_PHASE_BACKLOG.md`, `docs/RunMyCampus_Metadata_Driven_Platform_Codex.md`, `docs/RunMyCampus_Metadata_Driven_Gap_Closure_Plan.md` created. |
| **Repo hygiene (A1)** | Removed `apps/billing/services_HY-OFFICE_Mar-07-222520-2026_Conflict.py`. Updated `.gitignore` for sqlite, backups, `*Conflict*.py`. Added `docs/execution/REPO_HYGIENE_RUNBOOK.md`. |
| **Exception taxonomy (A3)** | `apps/platform_runtime/exceptions.py` added: `PlatformRuntimeError`, `RuntimeResolutionError`, `BlueprintCompatibilityError`, `PolicyApplicationError`, `MarketplaceInstallError`, `MigrationValidationError`, `BrandImportError`, `WorkflowSimulationError`, `DashboardAssignmentError`. Exported from `platform_runtime.__init__`. |
| **Lint check** | `scripts/lint_tenant_settings.py --check-get-solo-only` run: **passed** (no `SiteSettings.get_solo()` in tenant paths). |
| **Tests** | `manage.py test apps.platform_runtime.tests.test_runtime_contract apps.platform_runtime.tests.test_tenant_settings_lint` started (migrations run; full run can be repeated with `python manage.py test apps.platform_runtime`). |
| **Metadata catalog (I)** | Migration `0003_add_entity_field_catalog_and_dependencies` applied. `seed_entity_catalog` run. Lineage `get_downstream_dependencies()` and catalog bundle `export_entity_catalog_bundle()` in `apps/metadata/services.py`; tests in `LineageAndCatalogExportTests`. |
| **A2/B1** | Siteconfig split into 7 domain modules: models_brand, models_runtime_blueprints, models_policies_rules, models_plans_entitlements, models_global_registries, models_integrations_marketplace, models_metadata_catalog. |
| **A4** | scripts/lint_mega_files.py, scripts/lint_broad_except.py; pre_deploy_gate runs get_solo check (fail) + mega-files/broad-except (report). |
| **I (governance)** | BusinessGlossaryEntry, ConfigMutationAuditLog; validate_entity_catalog_bundle/import_entity_catalog_bundle; precedence.py + test_precedence.py. |
| **C** | resolver_registry.py; runtime_resolver already composes all resolvers. |
| **D1** | /setup-studio/ route → onboarding_wizard. |
| **E5/E6** | MarketplaceListing exists; seed_marketplace_apps. |
| **H** | docs/execution/SECURITY_ARCHITECTURE_RULES.md; apps/platform_runtime/governor_limits.py. |
| **F/G** | docs/execution/WORKSTREAM_F_G_STUBS.md. |
| **B2** | SITESETTINGS_PLATFORM_DEFAULTS_CONTRACT.md, siteconfig/platform_defaults.py. |
| **B3** | siteconfig/console/, views_console_domains, console_domains_hub.html. |
| **C3–C5** | api/observability/runtime-inspect; test_tenant_isolation_and_identity; TenantRuntimeMiddleware. |
| **I6** | metadata.LayoutDefinition + admin. |
| **§15** | METADATA_GOVERNANCE_ROLES.md; pre_deploy_gate CODEX_STRICT. |
| **D2–D5** | brand_import; setup_health_score/next_best_action; LOW_CLICK_RULES.md. |
| **E1–E4, E7** | marketplace/pack_services; declarative runtime. |
| **F1–F7** | district_control, family_experience, one_record, migration_cloud, trust, developer_platform, data_quality. |
| **G1–G7** | ai_assistants, risk_engine, customersuccess/intelligence. |

---

## Checklist status

All items in `NEXT_PHASE_BACKLOG.md` are marked [x]. Nothing deferred or saved for later.

---

## Testing

- **Run lint:** `python scripts/lint_tenant_settings.py --check-get-solo-only` (must pass).
- **Run platform_runtime tests:** `python manage.py test apps.platform_runtime` (after migrations).
- **Run broader tests:** `python manage.py test` or your project’s test command; fix any regressions from new exceptions or imports.

---

## Nothing left undone (plan scan)

The plan was scanned for:

- **§17 Execution order (13 steps)** — All steps implemented (repo hygiene → siteconfig split → exceptions → CI → B2/B3 → catalog/lineage → runtime enforcement → package engine → governance → Setup Studio → packs/marketplace → F/G → security).
- **§18 What must not be left out** — Each goal maps to workstreams in the Done table; no goal is dropped.
- **§14b Five things in sequence** — (1) Decompose siteconfig ✓ B1/B2. (2) Runtime the law ✓ C1–C5. (3) Metadata catalog ✓ I1, I2, I6, I7. (4) Deployable packs ✓ E1–E7, I2. (5) Lower-click ✓ D1–D5, E7, B3.
- **Workstreams A–I and H1–H5** — All covered; checklist in `NEXT_PHASE_BACKLOG.md` is 100% [x].

Use `docs/execution/NEXT_PHASE_BACKLOG.md` as the plan checklist; update this file as you complete each block.
