# Metadata-driven platform gap closure — completion status

**Plan:** `metadata-driven-platform-gap-closure_5b36c906.plan.md`

**Short answer:** The plan is **not** fully completed. Baseline and resolvers are largely in place; decomposition, metadata catalog MVP, package engine, governance, and full CI enforcement are only partial or not started.

---

## Todo-by-todo status

| Plan todo | Status | What exists | What’s missing |
|-----------|--------|-------------|----------------|
| **1. Baseline assessment and guardrails** | **Done (partial)** | SITESETTINGS_INVENTORY.md; `scripts/lint_tenant_settings.py` (flags SiteSettings.get_solo in tenant apps, school.settings/features); pre_deploy_gate runs it. Runtime helpers and resolver registry. | `docs/ARCHITECTURE_RUNTIME.md` (“runtime is the law”) not created; doc lives in docs/architecture/ARCHITECTURE_OVERLAY_AND_RUNTIME_CONSTITUTION.md and related runtime docs. |
| **2. Decompose siteconfig** | **Not done** | siteconfig remains the main app; platform_runtime.helpers and policies/resolver provide runtime layer. | No new bounded-context apps (brand_experience, runtime_blueprints, policies_rules, plans_entitlements, global_registries, integrations_marketplace, metadata_catalog). No SiteDefaults/PlatformDefaults. |
| **3. Runtime resolvers** | **Done (partial)** | `platform_runtime.resolver_registry`: RuntimeResolver, BlueprintResolver, PolicyResolver, BrandingResolver, LayoutResolver, etc. `get_effective_site_settings`, `get_effective_policy`, `get_effective_branding`, `get_effective_flags` used across many apps. Tenant flows migrated to resolvers. | Resolution chain (platform → registry → blueprint → policy → plan → tenant → sandbox) not fully formalized as a single precedence doc; observability “What’s driving this?” panel/endpoint not present. |
| **4. Metadata catalog MVP** | **Partial** | `metadata` app with DynamicFieldDefinition; entity/field catalog migrations and services. | No EntityDefinition / FieldDefinition / UsageReference / BusinessTerm as in plan. No management commands to seed from Django models or register UsageReference. No `/super/metadata-catalog/` or impact view. |
| **5. Package engine** | **Not done** | Blueprint/pack apply and marketplace flows exist. | No canonical package format under metadata/packages/. No PackageEngine with validate_package, preview_diff, apply_package, rollback. No InstalledPackage, PackageVersion, PackageChangeLog models. |
| **6. Governance, audit, isolation** | **Partial** | Policy and tenant isolation in place; some audit logging. | No central MetadataChangeLog; no metadata-level roles (Policy Steward, Registry Steward, etc.); no scope fields (global/region/blueprint/plan/tenant/sandbox) on metadata models. |
| **7. Setup Studio** | **Done (partial)** | Unified Setup Studio flow: guided_onboarding (three-column, progress rail, live preview, Next/Skip/Back); get_guided_onboarding_steps(); first-login checklist aligned; branding step. | Not wired to PackageEngine.apply_package(); no step models in a dedicated setup_studio app; brand import assistant not extended per plan. |
| **8. Marketplace alignment** | **Partial** | Marketplace listings and install flows exist. | Listings not refactored to thin wrappers around metadata packages; install not yet via shared PackageEngine. |
| **9. CI enforcement** | **Done (partial)** | lint_tenant_settings (get_solo, school.settings/features) in pre_deploy_gate; test_tenant_settings_lint. | No tests for resolver precedence, pack install/rollback, or tenant-scoped metadata isolation. |

---

## Summary

- **Completed / largely in place:** Baseline inventory and CI guardrails (1), runtime resolvers and migration of tenant flows (3), Setup Studio UX and flows (7), and basic CI enforcement (9).
- **Partial:** Metadata catalog (4), governance/audit (6), marketplace alignment (8).
- **Not started:** Full siteconfig decomposition into bounded-context apps (2), PackageEngine and package models (5).

To “complete” the plan you would: add ARCHITECTURE_RUNTIME.md (or point to existing runtime docs), implement the package engine and catalog MVP, add metadata governance/audit, refactor marketplace to packages, and add the remaining CI/metadata tests.
