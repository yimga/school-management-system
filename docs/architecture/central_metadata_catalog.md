# Central Metadata Catalog

**Goal:** One metadata-first platform with a single catalog covering schema, experience, runtime, registry, integration, and governance metadata. All metadata is versioned, auditable, diffable, and previewable where high-impact.

## 2.1 Catalog categories

| Category | Contents | Source-of-truth | Scope |
|----------|----------|-----------------|--------|
| **Schema metadata** | Entities, fields, relationships, validation, state machines | canonical_education_graph + schema registry (future) | Platform / tenant |
| **Experience metadata** | Layouts, forms, navigation, dashboards, widgets, portal, themes, communication templates | siteconfig (ThemePack, DashboardWidget, portal config), workflow_registry | Platform / blueprint / tenant |
| **Runtime metadata** | Blueprints, workflow/dashboard packs, policy bundles, starter stacks, entitlements, module composition | siteconfig (Blueprint, WorkflowTemplate), policies, plans | Platform / regional / tenant |
| **Registry metadata** | Country, locale, calendar, terminology, grading scale, institution type, education system, compliance pack | registries app, siteconfig (RegionalConfig) | Platform / regional |
| **Integration metadata** | Providers, connectors, scopes, webhooks, sync mappings | siteconfig (Integration), communication, marketplace | Platform / tenant |
| **Governance metadata** | Ownership, scope, version, lifecycle, approval, compatibility, rollback | Pack/blueprint versioning, orchestration_layer | Platform / pack / tenant |

API surface: `apps.siteconfig.metadata_catalog` — `get_schema_metadata()`, `get_experience_metadata()`, `get_runtime_metadata()`, `get_registry_metadata()`, `get_integration_metadata()`, `get_governance_metadata()`. Optional tenant/school filter for tenant-scoped slices.

## 2.2 Metadata rules

- **Versioned:** All pack and blueprint metadata has a version; catalog API returns version where applicable.
- **Auditable:** Privileged metadata mutations are logged (audit logs); high-impact config supports rollback (orchestration_layer.md).
- **Diffable / previewable:** Before applying blueprint/pack or major config, diff and preview are supported (orchestration_layer, siteconfig_decomposition).
- **Scope and precedence:** Metadata declares platform / regional / blueprint / pack / tenant scope; precedence order is documented in runtime resolver and TENANCY_AND_DEFAULTS.

## 2.3 Metadata lineage and glossary

- **Dependency tracking:** Fields, workflows, dashboards, APIs, reports, templates can declare dependencies; "what uses this" is exposed before metadata changes (implemented incrementally; catalog API can expose dependency placeholders).
- **Business glossary:** Education terminology is centralized in registries (terminology pack) and canonical_education_graph; glossary is documented in bounded_contexts and canonical_education_graph.
- **Impact radius:** Before apply, show impact radius (which tenants, which roles, which features) where applicable; operator checklist in migration and release governance.
