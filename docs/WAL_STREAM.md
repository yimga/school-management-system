# WAL Stream — RunMyCampus v4.00.0

The canonical SOT for the browser→Redis→Celery WAL outbox.

## Why it exists

The 8:00 AM "Mark All Present" thundering-herd of 35-40 individual REST
writes per teacher was the documented backend bottleneck. The WAL stream
collapses that into ONE delta payload, flushed over a persistent WSS, and
drained by pooled Celery workers under RLS context.

## Wire path

```
                 IndexedDB outbox (static/js/rmc-wal-stream.js)
                       │
                       │  persistent WSS /ws/wal/
                       ▼
        Channels consumer (apps/wal_stream/consumers.py)
                       │
                       │  XADD rmc.wal.<tenant_hash>
                       ▼
            Redis Streams  (always)        Kafka  (optional)
                       │                       │
                       ▼                       ▼
       Celery drain_tenant_stream (apps/wal_stream/tasks.py)
                       │
                       │  rls_school(school_id) context
                       ▼
       Per-domain writers (apps/wal_stream/writers.py)
       ├── attendance      -> AttendanceRecord.objects.bulk_create
       ├── grade           -> OfflineMarkEntry.objects.bulk_create
       ├── billing_charge  -> Invoice.objects.create (sequential)
       ├── communication_send -> Message.objects.bulk_create
       └── audit_event     -> MigrationCloudAuditEvent.objects.record (chain)
```

## At-least-once + dedupe

Each envelope carries a client-issued ``txn_id``. The drainer keeps a 24h
SISMEMBER set per tenant_hash so retries are safe. The browser only
advances vector_clock + creates a new txn_id after server ACK.

## Beat schedule

`wal-stream-drain-fanout` (every 30s) walks Redis with `XLEN rmc.wal.*`
and queues `drain_tenant_stream(tenant_hash)` only for tenants that have
non-empty streams.

## Optional Kafka mirror

Set `KAFKA_BOOTSTRAP_SERVERS=host:9092,host:9092` and install `aiokafka`.
The consumer mirrors every validated envelope to topic
``rmc.wal.<tenant_hash>``. Mirror failure logs WARNING and never blocks
the Redis Streams path.

## Operator runbook

* Inspect queue depth: `redis-cli XLEN rmc.wal.<tenant_hash>`
* Force drain: `python manage.py shell -c "from apps.wal_stream.tasks import drain_tenant_stream; drain_tenant_stream('<tenant_hash>')"`
* Investigate dedupe: `redis-cli SCARD rmc.wal.dedupe.<tenant_hash>`
* Tenant hash: `python -c "import hashlib;print(hashlib.sha256(b'<school_uuid>').hexdigest()[:12])"`

## Tests + gates

* `scripts/scan_rest_attendance_writes.py` bans direct ORM writes against
  `AttendanceRecord` / `GradeEntry` / `BillingCharge` from `apps/*`
  (excluding `apps/wal_stream/` + management commands).
