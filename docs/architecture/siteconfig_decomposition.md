# Siteconfig Decomposition Plan

**Goal:** Kill the siteconfig mega-domain by decomposing into bounded subdomains. Runtime is the law; tenant behavior lives in runtime/metadata, not in a single SiteSettings singleton.

## 4.1 Target subdomains (decomposition)

| Subdomain | Ownership | Source-of-truth | Scope | Notes |
|-----------|-----------|-----------------|-------|--------|
| **brand_experience** | siteconfig (brand) | ThemePack, BrandingResolver, brand_registry | Tenant / blueprint | Logo, colors, themes, portal/marketing appearance |
| **runtime_blueprints** | siteconfig (runtime) | Blueprint, BlueprintResolver, models_runtime_blueprints | Platform / regional / tenant | Blueprint definitions, versioning, active blueprint per tenant |
| **policies_rules** | policies + siteconfig | Policy bundles, PolicyResolver, get_effective_policy | Platform / pack / tenant | RLS, workflow approval, feature flags derived from policy |
| **plans_entitlements** | siteconfig / billing | Plan, EntitlementResolver, feature gates | Platform / tenant | Plans, entitlements, module composition |
| **global_registries** | siteconfig / registries | Country, Locale, Calendar, GradingScale, EducationSystem, RegionalConfig | Platform / regional | Country profiles, locale, calendar, terminology, compliance pack |
| **integrations_marketplace** | marketplace + communication | Integration, Provider, webhooks, marketplace models | Platform / tenant | Providers, connectors, scopes, marketplace listings |
| **metadata_catalog** | siteconfig (catalog) | Schema metadata, experience metadata, governance (Phase 8) | Platform / regional / tenant | Entities, fields, layouts, navigation, versioning |
| **support_feedback** | siteconfig | GlobalSupportTicket, ProductFeedback, feature_control | Platform / tenant | Support queue, feedback, feature control panel |

Existing app mapping (current state):

- **siteconfig** today holds: SiteSettings (mega), ThemePack, DashboardWidget, WorkflowTemplate, Blueprint, RegionalConfig, integrations, support, feedback. These are reclassified into the subdomains above; code can remain in `apps/siteconfig` initially with clear module boundaries (e.g. `siteconfig.brand`, `siteconfig.runtime_blueprints`, `siteconfig.registries`).
- **policies** app: policy models and PolicyResolver.
- **registries** app: country/locale/calendar-style registries where they exist.
- **marketplace** app: marketplace listings and provider/app catalog.

## 4.2 Shrink SiteSettings

- **Reclassify every SiteSettings field** into: (a) platform-safe defaults only, (b) tenant behavior → runtime/metadata/blueprint, (c) regional → global_registries/RegionalConfig, (d) pack behavior → blueprint/workflow/dashboard/policy.
- **Keep in SiteSettings only:** platform-safe defaults (e.g. feature flags that are platform-wide, not tenant-facing), and fields required for bootstrap before runtime is available. All tenant-facing behavior must resolve through RuntimeResolver / BlueprintResolver / PolicyResolver / EntitlementResolver.
- **Migration strategy:** Add new resolvers or metadata tables as needed; backfill from SiteSettings; deprecate direct SiteSettings use in tenant-facing flows (already enforced by lint_tenant_settings and allowlist).

## 4.3 Config UX redesign (target consoles)

- **Brand & Experience Console:** branding, themes, logo, colors, portal/marketing preview.
- **Runtime & Blueprint Console:** active blueprint, pack install/disable, versioning, compatibility.
- **Policy & Rules Console:** policy bundles, RLS, workflow approval rules, feature control.
- **Marketplace & Integration Console:** providers, connectors, installed apps, scopes.
- **Plans & Entitlements Console:** plan selection, entitlements, module composition.
- **Global Registries & Localization Console:** country, locale, calendar, terminology, grading scale, education system.

These can be implemented as control-plane views that read/write the appropriate subdomain models and resolvers.

## 4.4 Config safety

- Preview before applying major config; diff views; staged rollout where needed; rollback for high-impact; audit logs for privileged config mutations. See orchestration_layer.md and exception_discipline.md. Event catalog and MigrationRun/rollback patterns apply to config changes where appropriate.

## Implementation order

1. Document and enforce module boundaries within siteconfig (brand, runtime_blueprints, registries, support_feedback).
2. Reclassify SiteSettings fields in a spreadsheet or doc; move tenant-facing defaults into runtime/blueprint/policy.
3. Add Config UX consoles incrementally (start with Runtime & Blueprint, then Brand & Experience).
4. Add preview/diff/rollback for high-impact config (blueprint apply, policy bundle, major branding).
