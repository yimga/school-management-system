# Metadata Catalog Scope

**Purpose:** §3.3 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Define central metadata catalog scope and current coverage. Nothing deferred.

**Status:** PARTIAL — catalog in place; lineage and governance UI to be completed.

---

## 1. Catalog scope (required)

| Area | Description | Current coverage |
|------|-------------|------------------|
| entities | Entity types (school, student, invoice, etc.) | apps/metadata: EntityCatalog, EntityFieldCatalog, dependencies |
| fields | Fields per entity, types, validation | EntityFieldCatalog, seed_entity_catalog |
| relationships | Entity relationships | Dependencies / usage_registry |
| validation rules | Validation rules per field/entity | In models/catalog |
| state machines | State machines for workflows/entities | apps/metadata/state_machine.py |
| layouts | Layout definitions | migrations 0005_add_layout_definition |
| dashboards | Dashboard metadata, lineage | dashboard_resolver lineage registration |
| workflows | Workflow metadata, lineage | workflow_resolver |
| APIs | API endpoints, contracts | INTEGRATION_CATALOG, API Center |
| reports | Report templates, lineage | Report templates, runtime_blueprints |
| templates | Template metadata | In catalog / siteconfig |
| packs | Blueprint/workflow/dashboard/policy packs | packages app, lineage |
| glossary | Business glossary | seed_business_glossary, GlossaryTerm |
| governance metadata | Ownership, lifecycle, audit | changelog, config audit (migration 0004); catalog APIs expose active lifecycle only by default (?lifecycle=all / active_only=False to include draft/deprecated) |

---

## 2. Lineage / dependency graph

- **Current:** usage_registry (apps/metadata/usage_registry.py), package payload registration, dashboard_resolver lineage registration. "What uses this?" for some objects.
- **To complete:** Lineage for workflows, dashboards, reports, APIs, templates, packs in one searchable/governance UI; lifecycle states and ownership for metadata components.

---

## 3. Metadata app location

- **App:** `apps/metadata` — models (EntityCatalog, EntityFieldCatalog, GlossaryTerm, LayoutDefinition, etc.), services, usage_registry, state_machine, changelog, admin, seed commands (seed_entity_catalog, seed_business_glossary).
- **Tests:** apps/metadata/tests (test_services, test_usage_registry_helpers).

---

## 4. Completion gate (§3.3)

- [x] Central metadata catalog scope documented; entities, fields, relationships, layouts, glossary, governance present.
- [ ] Lineage/dependency graph complete for workflows, dashboards, reports, APIs, templates, packs.
- [x] Metadata search and governance UI added (governance at /api/internal/metadata/governance/; search API).
- [x] Lifecycle states and ownership for EntityCatalogEntry (draft/active/deprecated; migration 0007; API + governance + bundle; catalog search/export/super catalog expose active-only by default). Other components as needed.

---

**§9 alignment:** Completion authority is RUNMYCAMPUS §12; no platform score (9.5/10) claimed until §12 gates are met. See [docs_truth_ledger.md](docs_truth_ledger.md).

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §3.3.*
