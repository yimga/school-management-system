"""Channels consumer for the WAL outbox stream (v4.00.0).

Wire path:

  browser Dexie outbox
    -> static/js/rmc-wal-stream.js (persistent WSS)
    -> /ws/wal/ (this consumer)
    -> Redis Streams `rmc.wal.<tenant_hash>` (immediate ship)
    -> Celery worker pool drains via pgbouncer-wrapped connection pool
    -> optional Kafka sink when KAFKA_BOOTSTRAP_SERVERS is set

The consumer NEVER touches the DB directly. The point is to absorb the
flash-flood and push it onto a backpressure-safe queue. DB writes happen
in the Celery worker (``apps.wal_stream.tasks.drain_wal_batch``).

Payload contract (validated below):
  {
    "txn_id": "<uuid>",                # client-issued, server-verified dedupe key
    "vector_clock": int,               # monotonically-increasing per client
    "domain": "attendance"|"grade"|"...",
    "actions": [ { ... }, ... ],       # opaque to the consumer; validated downstream
    "tenant_hash": "<sha256[:12]>",    # client-asserted, server cross-checks
  }
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

logger = logging.getLogger(__name__)

_MAX_PAYLOAD_BYTES = 256 * 1024  # 256 KiB; covers ~2000 attendance rows compressed
_ALLOWED_DOMAINS: frozenset[str] = frozenset({
    "attendance",
    "teacher_attendance",
    "grade",
    "communication_send",
    "thread_message_create",
    "announcement_create",
    "audit_event",
})


class WalStreamConsumer(AsyncJsonWebsocketConsumer):
    """Single-tenant WebSocket WAL ingestor."""

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return
        if self.scope.get("school_access_denied") or not self.scope.get("school_id"):
            await self.close(code=4403)
            return
        school_id = str(self.scope["school_id"])
        self.tenant_hash = hashlib.sha256(school_id.encode("utf-8")).hexdigest()[:12]
        self.user_id = str(user.pk)
        await self.accept()

    async def receive_json(self, content: Any, **kwargs) -> None:
        if not isinstance(content, dict):
            await self.send_json({"ok": False, "error": "bad_payload"})
            return
        ok, reason = _validate(
            content,
            expected_tenant_hash=self.tenant_hash,
            expected_user_id=self.user_id,
        )
        if not ok:
            logger.warning("wal_stream.reject: %s", reason)
            await self.send_json({"ok": False, "error": reason, "txn_id": content.get("txn_id")})
            return
        # At-least-once: push the validated envelope onto Redis Streams.
        envelope = {
            "txn_id": content["txn_id"],
            "tenant_hash": self.tenant_hash,
            "user_id": self.user_id,
            "domain": content["domain"],
            "vector_clock": int(content["vector_clock"]),
            "actions": content["actions"],
            # When the offline write was CAPTURED on the device (epoch seconds).
            # Carried so upsert writers can do last-writer-wins by capture time
            # and refuse to clobber newer online state. None for older clients
            # (the writer then falls back to prior last-write-wins behavior).
            "captured_at": _coerce_captured_at(content.get("captured_at")),
            "received_at": time.time(),
        }
        await _ship_to_redis_stream(envelope)
        if getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", ""):
            await _ship_to_kafka(envelope)
        await self.send_json({"ok": True, "txn_id": content["txn_id"]})


def _coerce_captured_at(raw: Any) -> float | None:
    """Normalize the client-sent capture timestamp to epoch SECONDS.

    The client stores ``created_at`` as ``Date.now()`` (epoch MILLISECONDS).
    Accept a positive number and divide; reject anything else to None so a
    malformed value simply disables freshness checks for that envelope rather
    than corrupting the comparison.
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if raw <= 0:
        return None
    return float(raw) / 1000.0


def _validate(
    content: dict, *, expected_tenant_hash: str, expected_user_id: str | None = None
) -> tuple[bool, str]:
    txn_id = content.get("txn_id")
    if not isinstance(txn_id, str) or len(txn_id) < 8 or len(txn_id) > 64:
        return False, "bad_txn_id"
    vc = content.get("vector_clock")
    if not isinstance(vc, int) or vc < 0:
        return False, "bad_vector_clock"
    domain = content.get("domain")
    if domain not in _ALLOWED_DOMAINS:
        return False, "bad_domain"
    actions = content.get("actions")
    if not isinstance(actions, list) or not actions:
        return False, "no_actions"
    asserted_tenant = content.get("tenant_hash")
    if asserted_tenant and asserted_tenant != expected_tenant_hash:
        return False, "tenant_mismatch"
    # Shared-device defense: an outbox row stamped with the user who authored it
    # offline must not be shipped over a DIFFERENT user's authenticated socket.
    # Reject the mismatch so the row stays queued until the real author returns,
    # rather than being applied (and attributed) as the wrong user. Older clients
    # that don't stamp an author skip this check (backward compatible).
    author = content.get("author_user_id")
    if (
        author not in (None, "")
        and expected_user_id is not None
        and str(author) != str(expected_user_id)
    ):
        return False, "author_mismatch"
    try:
        serialized = json.dumps(content).encode("utf-8")
    except (TypeError, ValueError):
        return False, "unserializable"
    if len(serialized) > _MAX_PAYLOAD_BYTES:
        return False, "too_large"
    return True, ""


async def _ship_to_redis_stream(envelope: dict) -> None:
    """Push to Redis Streams via channels_redis's underlying client.

    Best-effort: a Redis hiccup must NOT close the WS. The client retries
    on its own (vector_clock + txn_id dedupe protects against double-apply).
    """
    try:
        import channels_redis.core  # noqa: F401 — confirm channels-redis present
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        # channels_redis pools to the same Redis we want. Use its raw conn.
        conn_pool = getattr(layer, "pools", None)
        stream_name = f"rmc.wal.{envelope['tenant_hash']}"
        payload = json.dumps(envelope).encode("utf-8")
        if conn_pool:
            for pool in conn_pool.values():
                async with pool.connection() as conn:
                    await conn.xadd(
                        stream_name,
                        {"envelope": payload},
                        maxlen=10_000,
                        approximate=True,
                    )
                    return
    except (ImportError, AttributeError, OSError) as exc:
        logger.debug("wal_stream.redis_ship_skipped: %s", exc)


async def _ship_to_kafka(envelope: dict) -> None:
    """Configured Kafka sink; remains inactive when no broker is declared."""
    try:
        from aiokafka import AIOKafkaProducer  # type: ignore[import-not-found]
    except ImportError:
        return
    bootstrap = getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "")
    if not bootstrap:
        return
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
    try:
        await producer.start()
        topic = f"rmc.wal.{envelope['tenant_hash']}"
        await producer.send_and_wait(topic, json.dumps(envelope).encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — Kafka is best-effort
        logger.warning("wal_stream.kafka_ship_failed: %s", exc)
    finally:
        try:
            await producer.stop()
        except Exception:  # noqa: BLE001
            pass
