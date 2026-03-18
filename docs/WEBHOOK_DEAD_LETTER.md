# Payment webhook dead-letter queue

After `WEBHOOK_DEAD_LETTER_FAILURE_THRESHOLD` (default **5**) **FAILED** logs for the same `provider` + `reference_id` within `WEBHOOK_DEAD_LETTER_WINDOW_HOURS` (default **24**), the next valid request is acknowledged with **HTTP 200** and status **DEAD_LETTER** so providers stop retrying.

- **Idempotency-Key** still deduplicates successful processing.
- Tune via Django settings or env-wrapped settings.
- **Replay:** Fix root cause, delete or archive dead-letter rows for that reference, resend webhook (or use provider replay).
