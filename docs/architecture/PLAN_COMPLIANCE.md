# RunMyCampus Full Implementation Plan — Compliance Checklist

This document tracks the implementation status of each phase from the RunMyCampus Full Implementation Plan. Use it to confirm nothing was missed and to prioritize follow-up work.

---

## Phase 1: Runtime Contract and Compilation Order ✅

| Item | Status |
|------|--------|
| Typed sections in contracts.py (tenant, route, registry, blueprint, policy, branding, flags, entitlements, workflows, dashboards, integrations, marketplace, compliance, locale, security, modules, debug) | Done |
| Strict compilation order 1–13 in runtime_resolver.build_tenant_runtime | Done |
| cache.py: request-scope cache, per-tenant cache, invalidation | Done |
| runtime.debug (source blueprint/policy IDs, overrides, warnings, compilation trace) | Done |
| build_tenant_runtime_for_tenant(tenant, mode="job") | Done |
| Tests (test_runtime_contract.py) | Done |
| Doc (RUNTIME_COMPILATION_ORDER.md) | Done |

---

## Phase 2: Global Registries Completion and Governance ✅

| Item | Status |
|------|--------|
| DocumentTypeRegistry, FeeCategoryRegistry, GradeScaleRegistry | Done |
| Country/Currency fields (default_calendar_family, writing_direction, thousands_separator_style, etc.) | Done |
| Registry services (get_education_levels_for_country, get_document_types, get_fee_categories, get_grade_scale_families, etc.) | Done |
| ensure_document_type_seed, ensure_fee_category_seed, ensure_grade_scale_seed; ensure_registry_baseline() | Done |
| Runtime step 3: registry context (document_types, fee_categories, grade_scale_families, etc.) | Done |
| Control-plane: super_registries_overview (all registry types, counts, Manage links) | Done |
| Seed: seed_platform_registries calls ensure_registry_baseline | Done |

---

## Phase 3: Blueprint Packs and Policy Bundles ✅

| Item | Status |
|------|--------|
| BlueprintPack model completion (code, family, institution_type, supported_country_scope, etc.) | Done |
| PolicyBundle model completion (code, country_scope, blueprint_compatibility, precedence_weight, etc.) | Done |
| BlueprintCompatibilityRule, PolicyCompatibilityRule, TenantPolicyOverride, ScheduledPolicyOverride | Done |
| Runtime: blueprint and policy resolution in build_tenant_runtime | Done |
| Seed: seed_blueprint_policy_packs (blueprint + policy families) | Done |
| Control-plane: super_blueprints_catalog, super_policies_catalog | Done |
| Blueprint detail / policy diff viewer | Done (policy diff at super/policy-diff/) |

---

## Phase 4: Workflow Packs and Dashboard Packs ✅

| Item | Status |
|------|--------|
| WorkflowPack, WorkflowPackAssignment; WorkflowTemplate.workflow_pack | Done |
| DashboardPack, DashboardPackAssignment; DashboardTemplate.dashboard_pack | Done |
| Runtime step 8: resolve from WorkflowPackAssignment when present, else legacy workflow_resolver | Done |
| Runtime step 9: resolve from DashboardPackAssignment when present, else legacy dashboard_resolver | Done |
| Seed: seed_workflow_dashboard_packs (workflow + dashboard pack families) | Done |
| Control-plane: super_workflow_packs_catalog, super_dashboard_packs_catalog | Done |
| WorkflowPackVersion, WorkflowSimulationRun, WidgetRegistryItem, simulation/preview studio | Deferred (models/tooling can be added later) |

---

## Phase 5: SiteSettings and Runtime Bypass Remediation ✅ (foundation)

| Item | Status |
|------|--------|
| Audit table (SITESETTINGS_AUDIT.md) | Done |
| Helper shims (helpers.py: get_effective_branding, get_effective_dashboard, get_effective_policy, get_effective_locale, get_effective_workflow) | Done |
| Dashboard context: use request.tenant_runtime for site_id and flags when present | Done |
| Config tenant_urls: api_schema_ui flags from runtime when present | Done |
| Portal, communication, payroll, automation, remaining apps refactor | Deferred (use helpers in follow-up) |
| CI/lint patterns to flag SiteSettings.get_solo() in tenant code | Documented in SITESETTINGS_AUDIT; no automated check yet |

---

## Phase 6: Admissions as First Canonical Module ✅ (foundation)

| Item | Status |
|------|--------|
| runtime.modules.admissions (step 12) with education_levels, required_documents, numbering_strategy, workflow, etc. | Done |
| admissions_services.py (get_admissions_config, get_education_levels_for_admissions, get_required_documents, get_numbering_strategy, get_admissions_workflow) | Done |
| Onboarding wizard: create_school_wizard uses registries (country, subdivisions, education levels, etc.) | Done |
| Full AdmissionNumberService, AdmissionDocumentPolicyService, etc. | Stubs / use admissions_services helpers |
| People/portal admission forms and views refactored to runtime only | Pattern and slice done: Form_view_refactor_guide.md; portal site_name refactored; rest refactor when touching code |
| Test matrix across blueprint families | Documented (test_matrix_by_blueprint.md); test with real School fixture added (test_runtime_from_real_school_fixture) |

---

## Phase 7: Gradebook/Evals as Second Canonical Module ✅ (foundation)

| Item | Status |
|------|--------|
| runtime.modules.gradebook (step 12) | Done |
| runtime_gradebook.py (get_gradebook_config, get_pass_mark, get_grading_family, get_publish_workflow) | Done |
| Evals views/forms refactored to use only runtime | Same pattern as portal: use get_effective_flags/get_site_display_name when touching; Form_view_refactor_guide.md |
| Tests for grading/publish across blueprint families | Runtime-by-fixture test added; extend with grading fixtures when needed |

---

## Phase 8: Finance, Communication, Portal, Reports, Payroll, People ⚠️

| Item | Status |
|------|--------|
| Pattern documented: resolve from runtime.policy.*, runtime.integrations, runtime.workflows | Done (helpers + runtime shape) |
| Per-module refactor (finance, communication, portal, reports, payroll, people) | Pattern done: Form_view_refactor_guide.md; portal slice refactored; use get_site_display_name/get_effective_flags when touching code |

---

## Phase 9: Control Plane Completion and Separation ✅

| Item | Status |
|------|--------|
| Shell and routing (super/, control plane base, sidebar) | Done |
| Sections: Overview, Tenants, Blueprints, Policies, Workflows, Dashboards, Marketplace, Migration, Observability, Billing, Compliance, Analytics | Done (catalogs, tenant health, compliance overview, analytics overview, migration_cloud) |
| Tenant 360 + runtime inspector (super/tenants/<id>/360/) | Done |
| Policy diff viewer (super/policy-diff/?school_id=) | Done |
| Control-plane roles and permissions (own role system) | Deferred (access via require_super_access / superuser) |
| Support shadow/impersonation with audit | Existing support tools; full impersonation flow deferred |

---

## Phase 10: Integrations and Migration Cloud ✅ (foundation)

| Item | Status |
|------|--------|
| runtime.integrations from ServiceIntegration (payment_provider, messaging_channels, enabled_providers) | Done |
| migration_services.py stubs (map_education_level, map_fee_category, validate_migration_mapping, dry_run_import) | Done |
| Control-plane migration console (super/migration/) | Done |
| Formal IntegrationProvider model | ServiceIntegration used as provider registry |
| MigrationParityService, MigrationCutoverService, MigrationRollbackService | Stubs / extend migration_services |

---

## Phase 11: Marketplace and App Ecosystem ✅ (foundation)

| Item | Status |
|------|--------|
| MarketplaceContext in runtime (installed_apps, granted_scopes, widget_registry, etc.) | Done (contracts; step 10 returns empty MarketplaceContext) |
| Control-plane: app catalog, governance (super marketplace URLs) | Done |
| App types, scopes, installation lifecycle, compatibility | Existing in apps/marketplace; extend as needed |

---

## Phase 12: Hardcoding Eradication and Global Defaults ✅ (foundation)

| Item | Status |
|------|--------|
| Settings: REGION_CODE, DEFAULT_GRADING_SCALE, DEFAULT_CURRENCY no longer default to CMR/0-20/XAF | Done (empty default; set via .env) |
| TENANCY_AND_DEFAULTS.md (sweeps, CI, test matrix) | Done |
| Sweep A/B/C (constants, forms, conditionals) | Deferred |
| CI/lint scanner for DEFAULT_COUNTRY, SiteSettings.get_solo(), etc. | Implemented: `scripts/lint_tenant_settings.py` (SiteSettings.get_solo, DEFAULT_COUNTRY, hardcoded region/currency/grading); optional pre-commit/CI hook |
| Test matrix by blueprint family | Deferred |

---

## Phase 13: Analytics, Observability, Compliance ✅

| Item | Status |
|------|--------|
| Compliance overview (super/compliance/) | Done |
| Analytics overview (super/analytics/) | Done |
| runtime.compliance in resolver; enforcement in modules | Done (step 11) |
| Tenant health, pulse, usage (existing) | Done |
| Full analytics (adoption, workflow success, etc.) | Placeholder; wire to existing APIs as needed |

---

## Summary

- **Phases 1–5, 9–10, 12–13:** Implemented to the level described above; a few items are explicitly deferred (simulation studio, full refactors, CI script, test matrix).
- **Phases 6–7:** Config and service helpers in place; form/view refactors and test matrix deferred.
- **Phase 8:** Pattern and runtime shape in place; per-app refactor deferred.
- **Phase 11:** Runtime marketplace shape and control-plane URLs in place; app lifecycle details in existing marketplace app.

**Optional steps (implemented):**

1. **Seed workflow/dashboard packs:** Run `python manage.py seed_workflow_dashboard_packs` so control-plane catalog pages have data.
2. **Single-region .env:** For deployments that relied on old defaults, set in `.env`: `REGION_CODE=CMR`, `DEFAULT_GRADING_SCALE=0-20`, `DEFAULT_CURRENCY=XAF`. See `.env.example`.
3. **Refactor to runtime helpers:** Portal, evals, and finance now use `get_effective_flags(request)` from `apps.platform_runtime.helpers` for feature-flag reads where request is available. Remaining `SiteSettings.get_solo()` (e.g. for `site` in context) can be refactored to `get_effective_branding(request)` or runtime in follow-up.
4. **CI/pre-commit:** Run `python scripts/lint_tenant_settings.py` to flag `SiteSettings.get_solo()` in tenant apps and hardcoded CMR/XAF/0-20. Use `--exit-zero` to report without failing until more refactors are done.
5. **Tests by blueprint family:** `apps/platform_runtime/tests/test_runtime_by_blueprint_family.py` asserts `runtime.modules.admissions`, `runtime.modules.gradebook`, and `runtime.modules.finance` shape. Extend with real school/blueprint fixtures for full matrix.
