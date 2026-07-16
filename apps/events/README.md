# apps/events

> The transactional outbox for domain events, plus the webhook subscription and
> delivery runtime that fans them out to tenants.

**Tenancy:** SHARED (public schema; rows carry `school_id` and/or `schema_name` for tenant routing rather than living in a tenant schema)
**Scale:** 4 models · 8 migrations · 10 test modules · ~3.9k LOC

## What this app owns

Events is how the rest of the platform says "this happened" without knowing or
caring who is listening. A service emits `student.created` inside its own
transaction; this app durably records it and later fans it out to webhook
subscribers, in-process subscribers, notifications, and automation.

The architecture is the **transactional outbox** pattern, and the reason for it is
the reason to be careful with it. `emit_event()` writes a `DomainEvent` row in the
*same database transaction as the business operation that caused it*. If the
business write rolls back, the event vanishes with it; if it commits, the event is
durably queued. There is no window in which a student exists but the event does
not, and no window in which an event fires for a student that was never saved. A
separate consumer (Celery task or cron) picks up pending rows and does the actual
delivery — which is exactly why delivery must never be attempted inline.

Two rules follow from this and are stated in the module docstrings. First, **emit
from the service layer only** — `models.py` and `services.py` both say so, and
`services.py` names the alternative it is rejecting: "no model signals chaos". An
event emitted from a signal fires on fixture loads, cascades, and admin edits, and
carries no intent. Second, the event catalog is **code-backed**: `catalog.py` holds
the naming convention (`domain.action`), the required payload keys, the retry
policy, and the schema version for every event type.

## Key models

All 4 models:

| Model | Table | Purpose |
| --- | --- | --- |
| `DomainEvent` | `events_domainevent` | The outbox itself: one row per emitted event. UUID PK, `event_type`, `schema_version`, JSON `payload`, tenant context (`school_id` and/or `schema_name`), and a **unique** `idempotency_key`. Status: pending → processing → processed / failed |
| `WebhookSubscription` | `events_webhooksubscription` | A tenant- or platform-managed endpoint that wants domain events |
| `WebhookDelivery` | `events_webhookdelivery` | One delivery attempt of one event to one subscription: `http_status`, `scheduled_for`, `retry_count` against `max_attempts` (default 4), error text. Status: pending → sent / delivered / failed |
| `EventSystemRemediationAudit` | `events_eventsystemremediationaudit` | Append-only audit trail for DLQ retries and operator disposition |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `services` | `emit_event()` — the front door. Appends to the outbox in the caller's transaction |
| Module | `bus` | `publish()` (preferred for new code, same implementation) plus `subscribe()` / `dispatch_internal_subscribers()` for in-process handlers |
| Module | `catalog` | `EVENT_CATALOG`: naming, required/optional payload keys, retry policy, schema version |
| Module | `webhooks` | Signing (`sign_payload`), delivery, and retry backoff |
| Module | `event_contract` | `domain_event_to_contract()` — stable operator-facing serialization |
| Module | `replay_ops` | Clones an event into a **new pending row**; never mutates the original |
| Module | `remediation_ops` | DLQ querysets and operator remediation for domain + platform deliveries |
| Module | `legacy_bridge` / `checks` | Detects surviving `siteconfig` webhook subscriptions; raises system check `events.W001` |
| Celery | `process_event_outbox_task` | Sweeps pending outbox rows |
| Celery | `process_webhook_deliveries_task` | Sends due deliveries |
| Command | `process_event_outbox` | Manual/cron equivalent of the outbox sweep |
| Command | `process_webhook_deliveries` | Manual/cron equivalent of the delivery sweep |
| Command | `replay_domain_events` | Operator replay |
| Command | `sync_legacy_webhooks_to_events` | Copies legacy subscriptions onto the canonical stack |
| Command | `retire_legacy_webhooks` | Syncs **and deactivates** legacy producers — what `events.W001` asks you to run |
| URL | `event_console`, `event_dlq_console`, `event_analytics_console`, `event_domain_detail`, `event_platform_detail`, `event_replay` | Operator consoles |

## Before you change this

- **Emit from the service layer, inside the business transaction. Never from a
  model signal.** Both `models.py` and `services.py` state this, and `services.py`
  explains the rejection ("no model signals chaos"). Emit *after* the business
  operation succeeds, in the same atomic block.
- **Never deliver inline.** The outbox exists so the caller's transaction is not
  coupled to somebody else's HTTP endpoint being up. `emit_event()` writes a row
  and returns; delivery belongs to the consumer.
- **`DomainEvent.idempotency_key` is `unique` across the whole table**, and
  `emit_event` coerces a falsy key to `None` (NULL) so unkeyed events don't collide
  on empty string. If you start passing a key, make sure it is genuinely unique per
  logical event — a reused key raises `IntegrityError` at emit time, inside the
  caller's transaction, and will roll back the business write with it.
- **The outbox sweep is written for a single worker.**
  `process_event_outbox_batch` selects pending rows with a plain `filter(...)` and
  then flips status to `processing` — there is no `select_for_update(skip_locked=True)`.
  Two concurrent sweepers can therefore pick up the same row. What limits the blast
  radius is that `queue_deliveries_for_event` looks up an existing
  `(subscription, domain_event)` delivery before creating one, so a double sweep
  tends to reuse the delivery rather than duplicate it — but do not treat that as a
  concurrency guarantee. If you scale the sweep out, add real row claiming first.
- **Replay clones, it does not re-fire.** `clone_domain_event_for_operator_replay`
  creates a *new pending row* and stamps `payload._replay_meta` (source event id,
  actor, timestamp) for audit. The docstring is explicit that it "never mutates
  `src`". Preserve both properties: the original event is history, and a replayed
  event must be traceable to the operator who replayed it.
- **Two event stacks coexist, and this one is not automatically the only
  authority.** `apps.platform_runtime` has its own event bus and
  `EventWebhookDelivery`; `remediation_ops` deliberately queries both DLQs, and
  `replay_ops` notes that platform-runtime replay stays on
  `platform_runtime.event_bus.replay_event`. Likewise, legacy
  `siteconfig.WebhookSubscription` rows may still be live: the `events.W001` system
  check fires while they exist, and its hint says to run `retire_legacy_webhooks`
  "before treating `apps.events` as the only delivery authority". Do not assume
  single-stack until that check is clean.
- **Webhook retries are bounded and back off on a fixed ladder** —
  `RETRY_BACKOFF_SECONDS = (60, 300, 3600)` then `RETRY_BACKOFF_FALLBACK = 21600`,
  against `max_attempts` (default 4). A delivery that exhausts attempts is DLQ, not
  a retry loop: `domain_dead_letter_filter()` defines DLQ as
  `status=failed AND retry_count >= max_attempts`, and unresolved DLQ rows are those
  with a null `operator_resolution`.
- **Payloads are signed over canonical JSON.** `canonical_json_bytes` sorts keys and
  strips whitespace before HMAC, and the result rides in `X-Webhook-Signature`. If
  you change the serialization, every subscriber's signature check breaks — the
  bytes signed and the bytes sent must be the same bytes.
- **Add new event types to `EVENT_CATALOG`.** `catalog.py` requires it under strict
  mode, and the catalog is where the required payload keys and `schema_version` are
  declared. An event type that only exists at a call site has no contract.
- Outbox and delivery sweeps are **cross-tenant by design** and carry explicit
  `tenant-isolation-allow` markers with review dates. That exemption is scoped to
  these sweeps; it is not a licence to drop `school_id` scoping in new queries here.
