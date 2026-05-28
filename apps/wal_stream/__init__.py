"""WAL stream app (v4.00.0).

Receives compressed delta payloads from the browser WAL outbox over a
persistent WebSocket, validates them, and ships them onto Redis Streams
for pooled Celery writers. An optional Kafka sink lights up when
``KAFKA_BOOTSTRAP_SERVERS`` is configured.

Why this exists: the 8:00 AM "Mark All Present" thundering-herd of 35-40
individual REST writes was the documented backend bottleneck. This app
collapses that into ONE delta payload + a single async flush.
"""

default_app_config = "apps.wal_stream.apps.WalStreamConfig"
