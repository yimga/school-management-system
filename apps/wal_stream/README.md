# apps/wal_stream

> The write-ahead-log offline rail: absorbs the browser outbox over a WebSocket,
> ships it to Redis Streams, and drains it into the DB from Celery.

**Tenancy:** SHARED (public schema; this app owns no tables — the writers it dispatches to reach into each tenant's rows under an RLS context)
**Scale:** 0 models · 0 migrations · 2 test modules · ~2.1k LOC

## What this app owns

`wal_stream` exists to kill one specific bottleneck, documented in the app's own
`__init__.py`: the 8:00 AM "Mark All Present" thundering herd, where a teacher's
roll-call turned into 35-40 individual REST writes at the exact moment every
other teacher did the same. This app collapses that into ONE compressed delta
payload and a single async flush.

It owns the whole path from browser to row:

```
browser Dexie outbox
  -> static/js/rmc-wal-stream.js (persistent WSS)
  -> /ws/wal/  (consumers.WalStreamConsumer)   [validate only, NEVER touches the DB]
  -> Redis Stream  rmc.wal.<tenant_hash>       [immediate ship, at-least-once]
  -> Celery drain_fanout -> drain_tenant_stream
  -> writers.dispatch()  under rls_school(school_id)
  -> optional Kafka sink when KAFKA_BOOTSTRAP_SERVERS is set
```

The defining decision is the **split between the socket and the writer**. The
consumer validates the envelope and pushes it onto a backpressure-safe queue —
that is all. Every DB write happens later, in a pooled Celery worker. That is
what lets the socket absorb a flash flood without holding a connection open per
teacher, and it is why this app declares no models: it is a transport, and the
rows it eventually writes belong to `academics`, `communication`, and friends.

Seven domains are registered in `writers._REGISTRY`: `attendance`,
`teacher_attendance`, `grade`, `communication_send`, `thread_message_create`,
`announcement_create`, `audit_event`. Anything else is rejected at the socket.

## Key models

**None — this app declares no Django models and ships no migrations.** That is
deliberate. Its durable state lives entirely in Redis, under six keys per
tenant: `rmc.wal.<hash>` (the stream), `.dedupe.` (24h `txn_id` set),
`.attempts.` (retry counter hash), `.deadletter.` (poison-pill review stream),
`.conflict.` (refused stale offline writes), and `.lock.` (per-tenant drain
lock). The rows it ultimately writes are owned by the target apps, reached
through `writers.dispatch()`.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| WebSocket | `/ws/wal/` | `routing.websocket_urlpatterns`, wired into `config/routing.py`; ASGI/Daphne only |
| HTTP | `wal_websocket_http_stub` | 426 fallback so WSGI-served `/ws/wal/` does not 302 to login (`views_http.py`) |
| Celery task | `wal_stream.drain_fanout` | Beat every 30s (`CELERY_BEAT_SCHEDULE`); scans Redis, queues a drainer only for non-empty streams |
| Celery task | `wal_stream.drain_tenant_stream` | Drains up to 64 envelopes for one `tenant_hash` |
| Module | `consumers` | Envelope validation + ship; never touches the DB |
| Module | `writers` | Per-domain `apply_<domain>` appliers + `dispatch` |
| Function | `tasks.purge_streams_for_school` | Offboarding hook — deletes all six Redis keys for a tenant |
| Function | `tasks.record_wal_conflicts` | Records refused stale offline writes for operator review |

This app has no `urls.py` and no management commands.

## Before you change this

- **`tenant_hash` is `sha256(str(school.id))[:12]` — nothing else.** This exact
  derivation appears in `consumers.connect`, `tasks._resolve_school_id_from_hash`,
  and `tasks.purge_streams_for_school`, and it must stay identical in all three.
  The client once hashed `window.location.host` instead; the server rejected
  every real-browser envelope as `tenant_mismatch` and **the entire offline rail
  was dead on arrival** (`cf6607530`). The client now reads the server-derived
  value out of the offline config island. The server tolerates an *absent*
  `tenant_hash` (it stamps its own authoritative one) but never a *wrong* one —
  keep both halves of that contract.
- **Never trust `school_id` from the client.** `_apply_envelope` resolves the
  school server-side from the hash and stamps it onto the envelope. Several
  writers use `bulk_create`, which bypasses `save()`, so without that stamp the
  `school` FK lands NULL.
- **`_ids_in_school` is not redundant with RLS.** Writers re-validate every
  client-supplied FK against the bound tenant, because `rls_school()` is a no-op
  under django-tenants schema mode and some referenced models have no row-level
  policy of their own. Do not delete it as "belt and braces".
- **The per-tenant drain lock is load-bearing.** The `sismember`→`sadd` dedupe is
  check-then-act, so two overlapping drains double-apply every non-idempotent
  domain (`announcement_create`, `communication_send`, `grade`, `audit_event`).
  The lock serializes drains; it deliberately fails *open* on a Redis error so a
  lock hiccup cannot stall draining entirely.
- **Dead-lettering is a poison-pill guard, not a nicety.** Without the
  `_MAX_APPLY_ATTEMPTS` bound, one permanently-failing envelope is never `xdel`'d
  and is redelivered forever — head-of-line blocking for that tenant's whole
  stream. Envelopes are scrubbed of credential-ish keys before they land in the
  dead-letter stream, so it never becomes a plaintext secret store.
- **Redis holds unsynced PII.** Queued attendance, grades, and messages live in
  these streams. A schema/row purge that skips `purge_streams_for_school` leaves
  tenant data behind after a "permanent" delete.
- **Stale offline writes are refused, not dropped.** `_partition_stale_upserts`
  does last-writer-wins by *capture* time, and the loser goes to
  `rmc.wal.conflict.<hash>` for review. Clients that send no `captured_at` (older
  builds) fall back to plain last-write-wins by design — do not make the absence
  of capture metadata an error.
- Ship paths are best-effort by contract: a Redis or Kafka hiccup must never
  close the WebSocket. The client retries, and `txn_id` + `vector_clock` dedupe
  protect against double-apply.
- The `consumers.py` header still names `tasks.drain_wal_batch`; the task is
  actually `drain_tenant_stream`. The prose is stale, the wire path is not.
