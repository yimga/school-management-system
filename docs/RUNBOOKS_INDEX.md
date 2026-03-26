# Runbooks index

**Purpose:** Index of runbooks for major failure modes and operations. Each runbook should be updated when procedures change.

## Deploy and rollback

| Topic | Doc | Notes |
|-------|-----|--------|
| Deploy | Render/platform docs | Release command: `migrate --noinput && seed_render_users`. |
| Rollback | Platform docs | Revert deploy; DB migrations are forward-only — document rollback strategy per migration. |
| Fresh DB | docs/FRESH_DB_FIX.md | DB_FILE, clean SQLite path. |

## Failure modes

| Failure mode | Doc / location | Notes |
|--------------|----------------|-------|
| Tenant isolation concern | docs/CONTROL_PLANE_BOUNDARY_RULES.md | Control-plane vs tenant; no tenant data on manager host. |
| Migration failure | docs/MIGRATION_CLOUD_RUNBOOK.md | Migration cloud rollback, repair. |
| Auth / login | docs/PLATFORM_ACCESS_AND_CREDENTIALS.md | Admin, tenant admin, passwords. |
| SiteSettings / config | docs/SITESETTINGS_GET_SOLO_ALLOWLIST.md | Where get_solo is allowlisted. |
| Health / observability | apps/observability/ | /health/, /healthz/, db_health_check; healthz returns 500 on DB failure. |

## Event outbox and notifications (required)

| Topic | Doc | Notes |
|-------|-----|--------|
| Event outbox | docs/RUNBOOK_EVENT_OUTBOX.md | DomainEvent processing; consumer task; DLQ. |
| Notification queue | docs/RUNBOOK_NOTIFICATION_QUEUE.md | OutboundMessageQueue; retries; circuit breaker. |
| Storage/backup | docs/RUNBOOK_STORAGE_BACKUP.md | MEDIA_ROOT / S3 backup when production media used. |

## Operational discipline

- **Audit logs:** Retention and query — see compliance app and security_log_retention command.
- **Management commands:** docs/MANAGEMENT_COMMANDS_INDEX.md.
- **Platform apps single path:** docs/PLATFORM_APPS_PUBLIC_API.md.

## Implementation and improvements

| Topic | Doc | Notes |
|-------|-----|--------|
| SOT / §11.4 execution slices | docs/IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md | Verify-then-ship for **explicit SOT `[ ]`**, **§11.4** depth, PATH_TO **Action** rows, and Phase GAP; resumable via session state. **Status:** SOT **At a glance** + **§11.4**. |
| Improvements (gates, scroll, nav, a11y) | docs/IMPROVEMENTS_RUNBOOK.md | Execute steps 1.1–6.1 without interruption; session state in IMPROVEMENTS_RUNBOOK_SESSION_STATE.md. |

## References

- docs/MIGRATION_CLOUD_RUNBOOK.md
- docs/ACTIVATION_FLOWS.md
- docs/CONTROL_PLANE_BOUNDARY_RULES.md
- docs/PLATFORM_ACCESS_AND_CREDENTIALS.md
- docs/RUNBOOK_EVENT_OUTBOX.md
- docs/RUNBOOK_NOTIFICATION_QUEUE.md
- docs/RUNBOOK_STORAGE_BACKUP.md
