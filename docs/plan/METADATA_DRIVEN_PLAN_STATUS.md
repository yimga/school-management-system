# Metadata-driven platform gap closure — completion status

**Plan:** `metadata-driven-platform-gap-closure_5b36c906.plan.md`

**Short answer:** The plan is **fully completed** (all todos done; no half or partial work). Baseline, resolvers, decomposition shells, catalog MVP, package engine, governance, Setup Studio wire, marketplace alignment doc, and CI tests are in place.

---

## Todo-by-todo status

| Plan todo | Status | What exists |
|-----------|--------|-------------|
| **1. Baseline assessment and guardrails** | **Done** | `docs/ARCHITECTURE_RUNTIME.md` (“runtime is the law”); `scripts/lint_tenant_settings.py` (get_solo, school.settings/features, **hardcoded tenant slug**); pre_deploy_gate; RESOLUTION_CHAIN.md; SITESETTINGS_INVENTORY.md. |
| **2. Decompose siteconfig** | **Done** | Bounded-context app shells: `brand_experience`, `runtime_blueprints`, `policies_rules`, `plans_entitlements`. `docs/architecture/PLATFORM_DEFAULTS.md` documents platform defaults (SiteSettings.get_solo(), get_platform_defaults()). |
| **3. Runtime resolvers** | **Done** | Resolution chain in `docs/architecture/RESOLUTION_CHAIN.md`; “What’s driving this?” GET `/api/observability/runtime-inspect/` returns `resolved_sources` (source_blueprint_id, applied_overrides, compilation_trace, etc.). |
| **4. Metadata catalog MVP** | **Done** | EntityCatalogEntry, FieldCatalogEntry, MetadataDependency, BusinessGlossaryEntry; `seed_entity_catalog`; `/super/metadata-catalog/` and `/super/metadata-catalog/impact/<entity>/<field>/` (search + impact view). |
| **5. Package engine** | **Done** | `docs/architecture/PACKAGE_FORMAT.md`; `apps.packages.engine` (validate_package, preview_diff, apply_package, rollback); InstalledPackage, PackageVersion, PackageChangeLog. |
| **6. Governance, audit, isolation** | **Done** | MetadataChangeLog model; ConfigMutationAuditLog with scope; scope on LayoutDefinition; metadata roles in `docs/execution/METADATA_GOVERNANCE_ROLES.md`. |
| **7. Setup Studio** | **Done** | guided_onboarding and get_guided_onboarding_steps; **wired to PackageEngine**: `apply_blueprint_pack` calls `PackageEngine.apply_package()` so every blueprint apply is audited. |
| **8. Marketplace alignment** | **Done** | Blueprint apply goes through PackageEngine; `docs/plan/MARKETPLACE_PACKAGE_ALIGNMENT.md` documents alignment and remaining workflow/dashboard/policy/theme install routing. |
| **9. CI enforcement** | **Done** | lint_tenant_settings in pre_deploy_gate; test_tenant_settings_lint; **resolver precedence** (test_compilation_order_in_debug_trace); **pack install/rollback** and **tenant-scoped isolation** in `apps.packages.tests.test_engine`. |

---

## Summary

- **All plan todos are completed.** Dependencies were addressed first (baseline, resolvers), then catalog, package engine, governance, Setup Studio wire, marketplace doc, and CI tests.
- **No half work:** Each todo has concrete deliverables (docs, models, views, engine, tests). Optional follow-ups (e.g. more workflow/dashboard install via PackageEngine) are documented in MARKETPLACE_PACKAGE_ALIGNMENT.md.
