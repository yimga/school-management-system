# Admin gravity audit (generated)

**UTC** `2026-05-03T17:25:59.706325+00:00`  

| Metric | Value |
| --- | --- |
| approx `admin.site.register` calls | 0 |
| custom admin template files | 67 |
| product files w/ admin bridge hints | 59 |
| product files w/ `admin:metadata` references | 6 |
| approx product `admin.` reference lines (non-migration) | 477 |
| product views rendering `admin/*.html` | 0 |

## High-registration apps (3+ register calls, heuristic)

_None (threshold not met)._

## Control-plane replacement roadmap (repo-backed)

- **region_operator_matrices** (rank 1, shipped) — Region validation, comparison, and grading scale matrices
- **tenant_runtime_effective_settings** (rank 2, shipped) — Tenant runtime & effective site settings hub
- **feature_control_surface** (rank 3, shipped) — Feature toggles and control-plane audit (vs raw admin)
- **metadata_catalog_operator** (rank 4, shipped) — Metadata & lineage hub + entity catalog (admin remains for CRUD and config audit)
- **marketplace_operator_governance** (rank 5, shipped) — Marketplace governance and app catalog (control plane primary)
- **reports_bulk_export_surfaces** (rank 6, shipped) — Reports, bulk letters, and export (Studio + siteconfig, not admin lists)
- **workflow_automation_control_plane** (rank 7, shipped) — Workflow packs and automation Studio (operator entry vs model admin)
- **audit_rollback_staging_evidence** (rank 8, shipped) — Audit, rollback, staging evidence (feature audit + Control Studio; admin bridge fallback)
- **admin_gravity_artifact_themes** (rank 9, shipped) — Admin gravity theme hints in generated JSON (roadmap/strict/CP map)
- **metadata_dynamic_field_operator** (rank 10, shipped) — Dynamic field EAV operator (read-only triage; admin CRUD for definitions/values)

