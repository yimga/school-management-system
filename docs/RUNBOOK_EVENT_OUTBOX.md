# Runbook: Event outbox processing (required, non-optional)

Domain events are written to the `DomainEvent` outbox; consumers must process them. This runbook is required for operations.

## What it is

- **Model:** `apps.events.models.DomainEvent` (status: pending → processing → processed/failed).
- **Emit:** Service layer calls `apps.events.services.emit_event(event_type, payload, school_id=..., idempotency_key=...)`.
- **Consume:** A Celery task or cron job processes pending rows and dispatches to webhooks/handlers.

## How to process the outbox

1. **Task/cron:** Ensure the event consumer task runs on schedule (e.g. every minute or as a Celery beat task).
2. **Query:** Select rows with `status='pending'` (and optionally `retry_count < max_retries` for failed).
3. **Lock:** Set `status='processing'` (and optionally `processed_at` / `error_message`) in a transaction.
4. **Dispatch:** For each event, call the appropriate handler (webhook POST, internal service, notification).
5. **Complete:** Set `status='processed'` or `status='failed'` and `processed_at`, `error_message` if failed.
6. **Idempotency:** Use `idempotency_key` to avoid duplicate delivery; skip or dedupe in handlers.

## Failure handling

- On handler exception: set `status='failed'`, increment `retry_count`, set `error_message`; optionally re-queue for retry.
- **DLQ:** After `max_retries`, move to dead-letter (e.g. separate table or status='failed' with no further retries); alert and inspect.

## Where the consumer lives

- Check `apps.events.tasks` (or equivalent) for the task that processes `DomainEvent`; ensure it is registered in Celery beat or cron.
- If no task exists: add one that selects pending events, updates status, and calls webhook/handler logic.

## References

- `apps/events/models.py` — `DomainEvent`
- `apps/events/services.py` — `emit_event`
- `docs/architecture/domain_events.md`
