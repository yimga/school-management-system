# RunMyCampus Migration Cloud Connectors

## Purpose

Secure, authorized migration from a school's **current** platform into RunMyCampus — not scraping. This layer **extends** existing Migration Cloud (`MigrationBundle`, intake adapters, accelerators, landers, `migration_center.py`, `MigrationCloudAuditEvent`) rather than replacing it.

## Flow

```text
School authorizes migration
  → source URL + method (API token / OAuth / export / manual)
  → verify authorization + connection
  → discover entities (counts + samples only)
  → preview / stage / map fields
  → validate data quality + quarantine
  → import (creates MigrationBundle, landers apply path)
  → audit every step
  → purge one-time credentials (default)
```

## Models (`apps.migration_cloud.models_connectors`)

| Model | Role |
|-------|------|
| `MigrationConnectorProfile` | Platform-wide vendor registry + certification |
| `MigrationSourceConnection` | Tenant-scoped authorized source |
| `MigrationDiscoveryRun` | Discovery report (no import) |
| `MigrationStagingBatch` | Staged entity payload reference + quality score |
| `MigrationFieldMapping` | Source → destination mapping |
| `MigrationQuarantineItem` | Invalid/duplicate rows |
| `MigrationImportRun` | Import execution + idempotency |
| `MigrationAuditEvent` | School-scoped workflow audit (no secrets) |

## Credential handling

- **Default:** `memory_only` — credentials in process memory, purged after import/revoke.
- **Optional:** `encrypted_vault` via `EncryptedBinaryField` (Fernet shim).
- **Never:** plaintext passwords in DB, logs, audit metadata, or generated docs.
- **Username/password path:** one-time use; prefer OAuth, API token, CSV export, OneRoster, Ed-Fi.

## Connector adapters (`apps.migration_cloud.connectors`)

- `ConnectorAdapter` interface: `verify_connection`, `discover_capabilities`, `extract_entity`, `normalize_entity`.
- **API-first rule:** official APIs and exports before browser automation.
- **Browser rule:** Companion extension in operator's authenticated tab only; no MFA/CAPTCHA bypass.
- Certification levels: `placeholder` → `file_export_only` → `api_experimental` → `pilot_verified` → `production_ready`.
- Only `generic_csv_export` is `production_ready` in repo without live vendor API proof.

## Routes

| Audience | Base path |
|----------|-----------|
| Tenant setup | `/school/setup/migration-cloud/` |
| Operator | `/super/migration/connectors/` |
| Operator dashboard | `/super/migration/connectors/operator/` |

## Audit

- `MigrationAuditEvent` — wizard-queryable, metadata sanitized.
- `MigrationCloudAuditEvent` — tamper-evident chain (`connector.*` event types mirrored).

## Rollback posture

- Import tracks `rollback_snapshot_reference` and created/updated counts.
- Categories: `safe_revert`, `manual_review`, `not_reversible`, `external_unchanged`.
- No destructive rollback without confirmation; source platform never modified.

## Import pipeline (gap closeout)

1. Staged rows persist on `MigrationStagingBatch.staged_rows`.
2. `connector_bundle_bridge.write_staging_csv` → `BundleIngestionService.ingest` (FILE_UPLOAD).
3. `advance_bundle` → `apply_bundle` (supports `dry_run_apply` for safe rehearsal).

## Integration points

- **Preview/mapping/quality:** `apps.platform_runtime.migration_center`
- **Bundle apply:** `MigrationBundle` + orchestrator/landers (existing)
- **Vendor CSV layout:** `apps.migration_cloud.accelerators.*`
- **Companion live extract:** `companion-extension/` (separate security boundary)

## Verifiers

```bash
python manage.py test apps.migration_cloud.tests.test_source_connection_security
python scripts/generate_migration_connector_discovery.py
python manage.py seed_migration_connector_profiles
```
