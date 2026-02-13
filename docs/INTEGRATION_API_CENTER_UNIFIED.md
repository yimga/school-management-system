# Unified Integration & API Center (One Module)

**Status: Implemented.** Current behavior is described in [API_CENTER_AND_INTEGRATIONS.md](./API_CENTER_AND_INTEGRATIONS.md).

## Goal

Merge the **siteconfig Integration** (plugin config: name, provider, enabled, config) and **apicenter APIService** (governance: kill switch, audit, rate limit, scopes) into **one model and one page** to:

- Remove redundancy (one “enabled” / kill switch, one name, one identity)
- Close gaps (no “Register in API Center” step; every integration is governable by default)
- Single list, single edit, single toggle with audit

## Design

### Single model: Integration (siteconfig)

**Kept (existing):** name, provider, enabled, config, updated_at

**Added (from APIService):**

| Field               | Type           | Purpose                          |
|---------------------|----------------|----------------------------------|
| slug                | SlugField      | Unique ID for toggle URL / keys  |
| category            | CharField      | Optional display (Payment, LMS…) |
| rate_limit_per_min  | PositiveInteger| Optional rate limit              |
| ip_whitelist        | JSONField      | Optional IP allowlist            |
| allowed_scopes      | JSONField      | Optional scopes                  |
| secret_key_hash     | TextField      | Optional key hash                |
| last_call_at        | DateTimeField  | Optional last use                |
| health_status       | CharField      | Optional health                  |
| pii_masking         | BooleanField   | Optional PII masking              |
| school              | FK(School)     | Optional tenant                  |
| created_at          | DateTimeField  | Creation time                    |

- **Single kill switch:** `enabled` on Integration. No separate APIService.is_active.
- **Audit:** APIAuditLog (apicenter) has FK to **Integration** instead of APIService. Toggle updates `Integration.enabled` and creates APIAuditLog(integration=…).

### Removed: APIService

- All governance fields live on Integration.
- APIAuditLog.integration replaces APIAuditLog.api_service.
- No “Register in API Center”; every Integration is on the API Center page by default.

### One page (API Center)

- Lists **Integrations** only (one table/cards).
- Each row: name, provider, enabled, optional governance summary, **Toggle** (with required reason) → updates Integration.enabled + APIAuditLog.
- Audit log below (integration, action, by, reason).
- “Add integration” can link to Configuration Engine (admin) or a simple form later.

### Gating

- `is_integration_allowed(integration)`:
  - If Feature Control `enable_api_center` is off → True (no gating).
  - Else → `integration.enabled` (single source of truth).

### Migration path

1. Add new fields to Integration; backfill slug for existing rows (e.g. `integration-{id}`).
2. APIAuditLog: add `integration` FK (null=True). Data migration: for each APIAuditLog, set integration from api_service.integration or create Integration from APIService; then drop api_service FK.
3. Drop APIService table.
4. Update all code (gating, views, admin, template) to use Integration only and APIAuditLog.integration.
