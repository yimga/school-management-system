# apps/metadata

> Custom fields without migrations, the catalog of what every entity and field
> on the platform *is*, and the lineage that answers "what uses this?" and
> "which rows produced this number?".

**Tenancy:** SHARED (public schema; tenant-scoped rows carry an explicit
`school` FK, and platform-wide definitions use `school=None`)
**Scale:** 12 models · 16 migrations · 12 test modules · ~5.7k LOC

## What this app owns

Metadata is how a school adds a field the platform never shipped — an Aadhaar
reference, a house name, a bus-lane code — **without anyone running a
migration**. A `DynamicFieldDefinition` declares the field against an entity
type; a `DynamicFieldValue` stores one value for one entity. That is the EAV
core, and everything else in this app exists because EAV alone is not
governable.

So the app also owns the **catalogs** (`EntityCatalogEntry` /
`FieldCatalogEntry` — what a "student" or an "invoice" is, and what each of its
fields is, including the sensitivity tier that `apps.policies.dlp` redacts on),
the **glossary** that maps an education term to its technical metadata, a
minimal tenant-configurable **state machine** engine, layout-as-metadata, and
two distinct kinds of **lineage**.

The defining design decision is in the name of the safety module: **no DDL,
ever, on a request path**. `ddl_safety.py` pattern-matches `ALTER TABLE` /
`ADD COLUMN` / `DROP TABLE` and friends and raises `MetadataDdlForbiddenError`.
A tenant adding a custom field must never mutate the schema — because on a
multi-tenant platform that is a lock, a deploy hazard, and a per-tenant schema
drift all at once. The escape hatch is not "sometimes DDL is fine"; it is that
governed preview/rollback flows live in
`apps.platform_runtime.metadata_governance`.

The second decision is the newer one and worth understanding: the app already
answered *design-time* lineage ("what dashboards/workflows/policies use this
field?") via `MetadataDependency` + `lineage_api`. It could not answer the
*record-level* question — which Evaluation rows produced this report-card
average? The platform's most consequential numbers were its least traceable.
`DerivedValueLineage` closes that, and it is deliberately honest about
precision: inputs are recorded at `row` granularity (explicit PKs) or `scope`
granularity (a queryset descriptor) depending on what the computation actually
supports, and the row says which.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `DynamicFieldDefinition` | `metadata_dynamicfielddefinition` | Declares a custom field on an entity type — the no-DDL core |
| `DynamicFieldValue` | `metadata_dynamicfieldvalue` | One custom field value for one entity (no DDL on core models) |
| `EntityCatalogEntry` | `metadata_entitycatalogentry` | Catalog entry for a logical entity (student, invoice, attendance_record) |
| `FieldCatalogEntry` | `metadata_fieldcatalogentry` | Catalog entry for a field — carries the sensitivity tier the PDP/DLP reads |
| `MetadataDependency` | `metadata_metadatadependency` | Design-time lineage edge from a consumer (dashboard, workflow, policy, API, template, integration) |
| `DerivedValueLineage` | `metadata_derivedvaluelineage` | Record-level provenance: which inputs produced a persisted derived value |
| `BusinessGlossaryEntry` | `metadata_businessglossaryentry` | Business-first glossary: education term → technical metadata |
| `StateMachineDefinition` | `metadata_statemachinedefinition` | Minimal versioned, tenant-configurable state machine definition |
| `EntityState` | `metadata_entitystate` | Current state of an entity within a state machine |
| `LayoutDefinition` | `metadata_layoutdefinition` | Layout/UI as metadata: widget keys, order, options |
| `MetadataChangeLog` | `metadata_metadatachangelog` | Central audit trail for metadata object changes |
| `ConfigMutationAuditLog` | `metadata_configmutationauditlog` | Audit trail for privileged metadata/config mutations |

All 12 declared models are listed.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| URL | `metadata_governance`, `metadata_lineage`, `metadata_lineage_graph`, `metadata_search` | The governance/lineage UI — staff-only |
| Module | `ddl_safety` | `contains_forbidden_ddl` + the `MetadataDdlForbiddenError` guard |
| Module | `services` | `entity_type_for`, `set_dynamic_field_value` and the EAV read/write core |
| Module | `dynamic_forms` | Renders `DynamicFieldDefinition` rows as real Django form fields (`dyn_` prefix) |
| Module | `lineage_api` | Unified aggregation of usage registry + package lineage + blast radius |
| Module | `usage_registry` | `register_usage()` / `get_lineage_consumers()` — call it where dashboards/workflows/policies resolve |
| Module | `state_machine` | Get current state, transition by event |
| Module | `country_eav_catalog` | Country-specific field definitions injected at runtime, no migration |
| Module | `dynamic_field_reconciliation` | Pure functions mapping legacy siteconfig typed EAV ↔ metadata JSON EAV |
| Management command | `seed_entity_catalog`, `seed_business_glossary`, `seed_dynamic_field_recipes` | Catalog/glossary seeding |
| Management command | `sync_siteconfig_dynamicfields_to_metadata` | Legacy migration path |

No Celery tasks. `apps.py::ready()` does real work: it imports signals and
registers four admins through `config.admin.register_both` (both the tenant and
platform admin sites — a plain `@admin.register` only reaches
`django.contrib.admin.site`, so console domain links that reverse the tenant
admin would 404).

## Before you change this

- **Never emit DDL on a request or worker path.** This is the app's reason for
  existing, it is enforced by `ddl_safety.py` + `test_metadata_no_ddl_safety`,
  and the correct answer to "but I need a real column" is a governed change set
  via `apps.platform_runtime.metadata_governance` (`build_metadata_change_set` →
  `analyze_metadata_impact` → `preview_metadata_change_set`), not a bypass.
- **`school=None` means platform-wide, not "unscoped".** Definitions with a null
  school are inherited by every tenant and may be overridden per school (see
  `country_eav_catalog`). Do not write a query that treats a null school as a bug
  to be backfilled — and do not forget the null branch when filtering, or tenants
  silently lose their inherited fields.
- **Check the lineage before you change or retire a field.** That is what
  `usage_registry.get_lineage_consumers()` and `lineage_api` are for — impact
  preview and rollback safety. A field with dashboard/workflow/policy consumers
  is not free to remove, and this app is the only thing that can tell you.
- **`register_usage()` must be called where consumers are defined**, not where
  they are rendered. If a new dashboard/workflow/policy resolves a field without
  registering, the lineage silently under-reports and the next person's "nothing
  uses this" check is wrong.
- **`DerivedValueLineage` writes are best-effort and must never block the compute
  path.** A lineage failure must not fail a report card. Keep it that way.
- **The lineage/governance surfaces are staff-only** (`lineage_api`'s docstring
  says so explicitly) — they expose cross-tenant blast radius by design.
- **`siteconfig_dynamicfield_bridge.connect_siteconfig_dynamicfield_dual_write`
  is an intentional no-op.** The legacy `siteconfig_dynamicfield*` models and
  tables were removed in Batch 14 Phase 5b; the function survives only so the
  `metadata.apps` wiring stays stable. Do not "implement" it — delete-or-keep is
  a wiring decision, not a missing feature.
- **`dynamic_field_reconciliation` is pure functions, no DB.** It is testable
  precisely because of that. Adding a query to it breaks the contract its tests
  rely on.
