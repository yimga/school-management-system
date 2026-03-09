# Canonical Data Objects — Implementation Mapping

**Purpose:** Map the canonical object names from the Model-to-Canonical report to concrete RunMyCampus models and APIs. Use this for audits and when adding new canonical entities.

---

## Implemented canonical objects

| Canonical object | RunMyCampus implementation | Location |
|------------------|----------------------------|----------|
| **Migration Profile** | `MigrationProfile` | `apps.automation.models.MigrationProfile` — platform registry of migration connector profiles (CSV/XLSX, students/finance/grades, generic SIS). Seeded by `seed_migration_profiles`; used by migration cloud at `/super/migration/`. |
| **Migration Run** | `MigrationRun` | `apps.automation.models.MigrationRun` — per-tenant migration execution; links to MigrationProfile; supports rollback via `trigger_rollback`. |
| **Workflow Run** | `WorkflowRunLog` | `apps.siteconfig.models_workflow.WorkflowRunLog` — canonical cross-module workflow execution log. Used by workflow engine for audit and debugging. |
| **Provider Registry Entry** | `Integration` | `apps.siteconfig.models.Integration` — extensible provider/integration registry (SMS, payment, etc.). Single kill switch and optional governance. For a dedicated “Provider Registry” table, extend or alias from Integration. |
| **Policy Bundle** | `PolicyBundle` | `apps.policies.models.PolicyBundle` — snapshot of merged policy per school; versioned; used for rollback. |
| **Blueprint Pack** | `BlueprintPack` | `apps.policies.models.BlueprintPack` — catalog of installable blueprint packs; has `version`; applying creates PolicyBundle and sets TenantBlueprint. |

---

## Optional / future

| Canonical object | Status |
|------------------|--------|
| **Campus** | Not implemented. When needed: add `Campus` model (FK to School). See SCHOOL_TENANT_CAMPUS_CANONICAL.md. |
| **Person** (single identity root) | people app has StudentProfile, Staff, etc.; align to single Person + roles when refactoring. |
| **Document Version / Generated Artifact** | Clarify in reports/documents if needed. |
| **Custom Field Definition / Value** | Metadata/custom fields; implement when productised. |

---

**See also:** `MODEL_TO_CANONICAL_MAPPING_REPORT.md`, `SCHOOL_TENANT_CAMPUS_CANONICAL.md`.
