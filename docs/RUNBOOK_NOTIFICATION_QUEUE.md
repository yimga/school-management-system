# Runbook: Notification queue (OutboundMessageQueue) (required, non-optional)

Outbound WhatsApp/SMS messages are queued in `OutboundMessageQueue` and sent by a worker. This runbook is required for operations.

## What it is

- **Model:** `apps.communication.models.OutboundMessageQueue` (status: pending, retrying, sent, failed).
- **Channels:** WhatsApp, SMS (and optionally push via same queue or separate path).
- **Task:** `communication.process_outbound_message_queue` (Celery) processes pending and retrying rows.

## How to run the worker

1. **Celery:** Ensure the task `communication.process_outbound_message_queue` is run on a schedule (e.g. every 1–2 minutes via Celery beat).
2. **Per-school:** The task can be invoked with `school_id=...` for a single school or without for all schools.
3. **Limit:** Default `limit=50` per run; increase if backlog grows.

## Retry and failure behaviour

- **Retries:** Each row has `retry_count`; after 3 failures, status is set to `failed`.
- **Retrying:** Rows with status `retrying` are picked up again on the next run.
- **Idempotency:** `idempotency_key` is passed to SMS provider to avoid duplicate sends.
- **DLQ:** Rows that remain `failed` after max retries are effectively dead-lettered; alert and inspect.

## Health checks

- Monitor count of `pending` + `retrying`; if it grows without bound, investigate provider (SMS/WhatsApp) config or rate limits.
- Check `error_message` on failed rows for provider errors (credentials, timeout, etc.).

## References

- `apps/communication/models.py` — `OutboundMessageQueue`
- `apps/communication/tasks.py` — `process_outbound_message_queue`
- `apps/communication/notification_service.py` — `send_sms`, `send_whatsapp`
