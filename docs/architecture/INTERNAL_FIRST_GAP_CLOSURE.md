# Internal-first / optional gap closure (what was missing)

Summary of remaining gaps identified and what was closed. All items below are treated as required (no deferrals).

## Closed in this pass

| Gap | Fix |
|-----|-----|
| **Event outbox not scheduled** | Added `process-event-outbox` to `CELERY_BEAT_SCHEDULE` (every 2 min, task `apps.events.process_event_outbox`). |
| **Notification queue not scheduled** | Added `process-outbound-message-queue` to `CELERY_BEAT_SCHEDULE` (every 2 min, task `communication.process_outbound_message_queue`). |
| **CI vulnerability check** | Added pip-audit step to `.github/workflows/smoke.yml`; build fails on reported vulnerabilities (waiver = fix or ticket). |

## Already in place (verified)

- **Event outbox consumer:** `apps.events.tasks.process_outbox_batch` and management command `process_event_outbox`; webhook dispatch via `queue_deliveries_for_event` / `dispatch_due_webhooks`.
- **Weather:** Behind feature flag `show_header_context_weather` (default off); no mandatory external dependency.
- **Exchange rate:** GET `/api/v1/finance/exchange-rate` implemented in `apps.api.views_v1`.

## Completed (all addressed)

- **SBOM in CI:** Added to `.github/workflows/smoke.yml`: install `cyclonedx-bom`, run `cyclonedx-py requirements requirements.txt -o sbom.json`, upload `sbom.json` as artifact (retention 90 days).
- **Control plane runbooks URL:** Documented in `.env.example` as `CONTROL_PLANE_RUNBOOKS_URL`; set in env when running control plane so health dashboard can link to incident runbooks.
- **pip-audit:** CI runs `pip-audit --desc`; build fails on reported vulnerabilities (fix with `pip-audit --fix` or version bumps, or waive with ticket).

## References

- `config/settings.py` — `CELERY_BEAT_SCHEDULE`
- `apps/events/tasks.py` — `process_outbox_batch`, `process_event_outbox_task`
- `apps/communication/tasks.py` — `process_outbound_message_queue`
- `docs/RUNBOOK_EVENT_OUTBOX.md`, `docs/RUNBOOK_NOTIFICATION_QUEUE.md`
- `docs/SECURITY_POLICY.md`, `docs/COMPATIBILITY.md`
