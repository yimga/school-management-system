# Signed roster change webhook (district)

**Not** Clever/ClassLink. Allows districts to receive push notifications when roster changes.

- **Endpoint:** `POST /api/v1/oneroster/roster-webhook/` (or tenant-scoped variant).
- **Headers:** `X-Roster-Webhook-Signature: sha256=<hmac>` over raw body; `X-Roster-Webhook-Timestamp` for replay window.
- **Secret:** `school.settings["oneroster_webhook_secret"]` or ServiceIntegration metadata.
- **Payload:** `{ "event": "enrollment.changed", "sourcedId": "...", "dateLastModified": "ISO8601" }`.

Verify signature before processing; return 200 after enqueueing sync job.
