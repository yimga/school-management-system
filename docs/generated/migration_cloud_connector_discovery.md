# Migration Cloud connector discovery

Generated: 2026-05-20T02:38:52.251726+00:00

## Existing primitives (reuse)

- **bundle_lifecycle:** `apps.migration_cloud.models.MigrationBundle + MigrationArtifact`
- **intake_adapters:** `apps.migration_cloud.intake.* (file, archive, url, oauth, pdf, access, sql_dump)`
- **accelerators:** `apps.migration_cloud.accelerators.* (6 SIS vendors + OneRoster + canonical)`
- **landers:** `apps.migration_cloud.landers.* (24+ domains)`
- **preview_mapping:** `apps.platform_runtime.migration_center`
- **audit_chain:** `apps.migration_cloud.models_audit.MigrationCloudAuditEvent`
- **customer_intake:** `apps.migration_cloud.models_intake.MigrationIntakeRequest`
- **companion:** `companion-extension/ + companion_receiver.py`

## New connector layer

- **models:** `apps.migration_cloud.models_connectors`
- **services:** `['connector_credentials', 'connector_discovery', 'connector_mapping', 'connector_import', 'connector_bundle_bridge', 'connector_rollback', 'connector_audit']`
- **intake:** `['api_pull_intake', 'database_intake (sqlite)']`
- **adapters:** `apps.migration_cloud.connectors`
- **tenant_routes:** `/school/setup/migration-cloud/`
- **operator_routes:** `/super/migration/connectors/`

## Deferred

- Live vendor API pull (IntakeMethod.API_PULL Phase U9)
- DatabaseIntakeAdapter / EmailIntakeAdapter (Phase U7)
- OAuth Google Classroom connector (planned)
- Ed-Fi production connector (planned)
- FACTS/Skyward write paths (counsel-blocked in companion)
