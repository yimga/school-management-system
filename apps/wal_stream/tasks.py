"""Celery drainer for the WAL Redis Stream (v4.00.0).

One worker per tenant_hash consumes ``rmc.wal.<tenant_hash>`` in batches
of up to 64 envelopes, applies them under ``apps.schools.rls_context.rls_school``
so RLS bites, and trims the stream.

Idempotency: each envelope carries a client-issued ``txn_id``. The drainer
maintains a 24h dedupe set in Redis (``rmc.wal.dedupe.<tenant_hash>``).

The actual per-domain writer lives in ``apps.wal_stream.writers.<domain>``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)

_DEDUPE_TTL_SECONDS = 24 * 60 * 60
_BATCH_SIZE = 64
# After this many failed apply attempts an envelope is dead-lettered instead of
# being retried forever. Without this, a permanently-failing envelope (e.g. a
# writer IntegrityError, or an envelope for a deleted tenant whose hash no
# longer resolves) is never xdel'd and is re-delivered on every drain — a
# head-of-line poison pill that blocks every later envelope for that tenant.
_MAX_APPLY_ATTEMPTS = 5


@shared_task(name="wal_stream.drain_tenant_stream", bind=True)
def drain_tenant_stream(self, tenant_hash: str) -> dict[str, int]:
    """Drain up to ``_BATCH_SIZE`` envelopes for one tenant. Idempotent."""
    try:
        import redis  # type: ignore[import-not-found]
    except ImportError:
        return {"applied": 0, "skipped": 0, "missing_redis": 1}

    from django.conf import settings

    redis_url = getattr(settings, "REDIS_URL", "") or getattr(settings, "CELERY_BROKER_URL", "")
    if not redis_url:
        return {"applied": 0, "skipped": 0, "missing_redis_url": 1}

    from django.db import DatabaseError

    client = redis.Redis.from_url(redis_url)
    stream = f"rmc.wal.{tenant_hash}"
    dedupe_key = f"rmc.wal.dedupe.{tenant_hash}"
    attempts_key = f"rmc.wal.attempts.{tenant_hash}"
    deadletter_stream = f"rmc.wal.deadletter.{tenant_hash}"

    entries = client.xrange(stream, count=_BATCH_SIZE)
    applied = 0
    skipped = 0
    dead_lettered = 0
    for entry_id, fields in entries:
        raw = fields.get(b"envelope") or fields.get("envelope")
        if raw is None:
            continue
        try:
            envelope = json.loads(raw)
        except (TypeError, ValueError):
            client.xdel(stream, entry_id)
            continue
        txn_id = envelope.get("txn_id")
        if not txn_id:
            client.xdel(stream, entry_id)
            continue
        if client.sismember(dedupe_key, txn_id):
            client.xdel(stream, entry_id)
            skipped += 1
            continue
        try:
            _apply_envelope(envelope)
            client.sadd(dedupe_key, txn_id)
            client.expire(dedupe_key, _DEDUPE_TTL_SECONDS)
            applied += 1
        except (ValueError, TypeError, RuntimeError, DatabaseError) as exc:
            # Bounded retry, then dead-letter — so a permanently-failing
            # envelope (writer IntegrityError, deleted-tenant unknown hash,
            # malformed action) cannot wedge the tenant's whole drain forever.
            # DatabaseError (incl. IntegrityError) MUST be caught here; before,
            # it propagated out of the loop, the entry was never xdel'd, and it
            # re-delivered on every drain blocking all later envelopes.
            attempts = client.hincrby(attempts_key, txn_id, 1)
            client.expire(attempts_key, _DEDUPE_TTL_SECONDS)
            if attempts >= _MAX_APPLY_ATTEMPTS:
                logger.error(
                    "wal_stream.dead_letter txn=%s attempts=%s err=%s",
                    txn_id, attempts, exc,
                )
                try:
                    client.xadd(deadletter_stream, {"envelope": raw, "error": str(exc)[:500]})
                except redis.RedisError as dl_exc:
                    logger.error("wal_stream.dead_letter_xadd_failed txn=%s err=%s", txn_id, dl_exc)
                client.hdel(attempts_key, txn_id)
                client.xdel(stream, entry_id)
                dead_lettered += 1
            else:
                logger.warning(
                    "wal_stream.apply_failed txn=%s attempt=%s err=%s",
                    txn_id, attempts, exc,
                )
                # leave entry in stream for retry on next drain
            continue
        client.xdel(stream, entry_id)
        client.hdel(attempts_key, txn_id)
    return {
        "applied": applied,
        "skipped": skipped,
        "dead_lettered": dead_lettered,
        "tenant_hash": tenant_hash,
    }


def _apply_envelope(envelope: dict[str, Any]) -> None:
    """Dispatch to per-domain writer under RLS context."""
    from apps.schools.rls_context import rls_school
    from apps.wal_stream.writers import dispatch

    school_lookup_hash = envelope["tenant_hash"]
    school_id = _resolve_school_id_from_hash(school_lookup_hash)
    if not school_id:
        raise RuntimeError(f"unknown_tenant_hash:{school_lookup_hash}")
    # Stamp the authoritative, server-resolved school onto the envelope so each
    # writer scopes its rows to the right tenant. Writers (communication_send,
    # billing_charge, announcement_create) use bulk_create, which bypasses each
    # model's save() — without this, the school FK would land NULL because the
    # client never sends (and must not be trusted for) school_id.
    envelope["school_id"] = school_id
    with rls_school(school_id):
        dispatch(envelope)


def _resolve_school_id_from_hash(tenant_hash: str) -> str | None:
    """Reverse ``sha256[:12]`` lookup via the RLS-bypassed school directory.

    The drainer is the only context that legitimately walks every school.
    """
    import hashlib

    from apps.schools.models import School
    from apps.schools.rls_context import rls_bypass

    with rls_bypass():
        for school in School.objects.all().only("id"):  # tenant-isolation-allow: celery-wal-fanout-iterates-all-schools
            if hashlib.sha256(str(school.id).encode("utf-8")).hexdigest()[:12] == tenant_hash:
                return str(school.id)
    return None


@shared_task(name="wal_stream.drain_fanout", bind=True)
def drain_fanout(self) -> dict[str, int]:
    """Periodic fan-out: discover every tenant_hash with a non-empty WAL stream
    and queue a per-tenant drainer.

    Walks Redis directly (XLEN per stream key matching ``rmc.wal.*``) so we
    only spawn work for tenants who actually have queued envelopes.
    """
    try:
        import redis  # type: ignore[import-not-found]
    except ImportError:
        return {"queued": 0, "missing_redis": 1}

    from django.conf import settings

    redis_url = getattr(settings, "REDIS_URL", "") or getattr(settings, "CELERY_BROKER_URL", "")
    if not redis_url:
        return {"queued": 0, "missing_redis_url": 1}

    client = redis.Redis.from_url(redis_url)
    queued = 0
    try:
        for raw_key in client.scan_iter(match="rmc.wal.*", count=200):
            key = raw_key.decode("utf-8") if isinstance(raw_key, (bytes, bytearray)) else raw_key
            if key.startswith("rmc.wal.dedupe."):
                continue
            tenant_hash = key.rsplit(".", 1)[-1]
            if not tenant_hash:
                continue
            try:
                if client.xlen(key) == 0:
                    continue
            except (TypeError, ValueError):
                continue
            drain_tenant_stream.delay(tenant_hash)
            queued += 1
    except Exception as exc:  # noqa: BLE001 — periodic task must never crash beat
        logger.warning("wal_stream.drain_fanout_failed: %s", exc)
    return {"queued": queued}
