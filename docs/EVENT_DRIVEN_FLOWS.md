# Event-driven flows

**Pillar 5 — durable log:** `emit_platform_event()` writes to **`platform_runtime.PlatformEventLog`** for every catalog event type. See `apps/platform_runtime/events.py`.

| Flow | Pattern |
|------|---------|
| Pack apply / rollback | Engine calls `emit_platform_event` → row in `PlatformEventLog` |
| Other catalog events | Same table (`payment_received`, `migration_*`, …) |
| Tenant migration | Provisioning + tasks; emit when wired |
| Scheduled reports | Celery + `ScheduledReportRunner` |

**Next:** worker column `processed_at` for replay; outbound webhooks from log.
