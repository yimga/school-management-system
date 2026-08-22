# Runbooks index

**Purpose:** Index of runbooks for major failure modes and operations. Each runbook should be updated when procedures change.

## Incident response (start here in an outage)

| Topic | Doc | Notes |
|-------|-----|--------|
| Live incident | docs/INCIDENT_RUNBOOK.md | First-15-minutes: assess via `/healthz/`, declare + assign IC, check "what changed" (auto-deploy OFF, stale SW cache, CI not gating), communicate on the status page, mitigate → roll back / restore, resolve + postmortem. |

## Deploy and rollback

| Topic | Doc | Notes |
|-------|-----|--------|
| Deploy | Render/platform docs | Release command: `migrate --noinput && seed_render_users`. |
| Rollback | Platform docs | Revert deploy; DB migrations are forward-only — document rollback strategy per migration. |
| Fresh DB | docs/FRESH_DB_FIX.md | DB_FILE, clean SQLite path. |

## Sovereign / offline edge boxes

| Topic | Doc | Notes |
|-------|-----|--------|
| **TLS certificate — onboarding decision** | docs/EDGE_TLS_RUNBOOK.md | The school chooses `off` / `selfsigned` / `provided` (any CA) / `acme`, and can change later in either direction. Do this WITH the school before go-live. Without a certificate the origin is not a secure context, so WebCrypto is withheld and offline PIN / local mode cannot be enabled on any browser — "Local access could not be enabled on this browser" is the URL, not the browser. Gilead runs `selfsigned`. |
| Getting a name onto the LAN | docs/EDGE_LAN_HOSTNAME_DNS.md | Prerequisite for a certificate that asserts a hostname rather than only an IP. |
| Getting a new build to the box | docs/EDGE_UPDATE_PIPELINE.md | Image digest + compatibility floor; nothing ships while CI cannot start a job. |
| Sync operations | docs/EDGE_SYNC_OPERATIONS.md, docs/EDGE_CLOUD_SYNC_OPERATOR_RUNBOOK.md | Bundles, holds, parity. |
| Cloud/box drift | `manage.py deployment_parity --against <url>` | MUST_MATCH / MAY_DIFFER / MUST_DIFFER; `RMC_EDGE_TLS_MODE` is MAY_DIFFER and reported so an operator can see which certificate a school chose. |
| Is this box ready? | `manage.py check_edge_readiness --strict` | Blocks go-live on an unrecognised TLS mode, a missing/expired certificate, a certificate that omits an address the box answers at, HSTS on a LAN certificate, and the cookie-flag lockout. |

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
