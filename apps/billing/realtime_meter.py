"""v4.00.36 Phase 3 — AWS-style hot-path Redis meter buffer.

Closes the high-throughput gap. The existing ``apps.billing.models_metering.record``
helper writes one ``UsageMeter`` row per increment via Django ORM. That's
fine for the dozens-of-events-per-minute regime, but at thousands per
second (LiteLLM proxy bursts, exam-day SMS fan-out, bulk file uploads),
ORM round-trips dominate.

This module ships a two-stage pipeline:

1. ``hot_increment(school, dimension, delta=1)`` — atomic ``HINCRBY``
   against a per-day Redis hash keyed by ``billing:hot:{day}:{school_pk}``.
   No ORM round-trip, no transaction. Returns immediately.
2. ``flush_hot_buffers()`` — Celery beat task running every 60 seconds.
   Atomically drains each hash via ``HGETALL`` + ``DEL`` (a Lua script so
   no race between the two), then writes the accumulated deltas into
   ``UsageMeter`` via the canonical ``record`` helper.

Graceful degradation: when the cache backend isn't Redis, ``hot_increment``
falls back to the synchronous ``record`` path so dev / test environments
still see correct totals. The flush task is then a no-op.
"""

from __future__ import annotations

import logging
from datetime import date as _date_cls
from typing import Any

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

_HOT_KEY_PREFIX = "billing:hot:"
# Drain script: atomic HGETALL + DEL so a concurrent hot_increment between
# the two commands cannot lose ticks. KEYS[1] is the hash key.
_DRAIN_LUA = """
local data = redis.call('HGETALL', KEYS[1])
if #data > 0 then
    redis.call('DEL', KEYS[1])
end
return data
"""


def _redis_client(write: bool = True):
    try:
        return cache.client.get_client(write=write)  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError):
        return None


def _strip_django_redis_version_prefix(key: str) -> str:
    for prefix_guess in (":1:", ":2:", ":3:"):
        if key.startswith(prefix_guess):
            return key[len(prefix_guess):]
    return key


def _hot_key(day: _date_cls, school_pk: int) -> str:
    return f"{_HOT_KEY_PREFIX}{day.isoformat()}:{school_pk}"


def hot_increment(school: Any, dimension: str, delta: int = 1) -> None:
    """Atomically increment ``dimension`` for ``school`` in the hot buffer.

    Falls back to the synchronous ORM path when Redis is unavailable. Never
    raises — metering must never block the request path.
    """
    from apps.billing.models_metering import USAGE_DIMENSION_CODES

    if school is None or dimension not in USAGE_DIMENSION_CODES:
        return
    try:
        delta_int = int(delta)
    except (TypeError, ValueError):
        return
    if delta_int <= 0:
        return
    school_pk = getattr(school, "pk", None) or getattr(school, "id", None)
    if not school_pk:
        return

    client = _redis_client(write=True)
    if client is None:
        # Backend without Redis client — go straight to the ORM path.
        _fallback_orm_record(school, dimension, delta_int)
        return

    key = _hot_key(timezone.now().date(), int(school_pk))
    try:
        client.hincrby(key, dimension, delta_int)
        # Keep the hash for at most 24h even if flush is down — protects
        # against unbounded growth during an outage.
        client.expire(key, 86400)  # magic-number-allow: cache-ttl-seconds
    except (AttributeError, RuntimeError, ConnectionError, TimeoutError) as exc:
        logger.debug("hot_increment fallback to ORM for %s: %s", dimension, exc)
        _fallback_orm_record(school, dimension, delta_int)


def _fallback_orm_record(school: Any, dimension: str, delta: int) -> None:
    try:
        from apps.billing.models_metering import record

        record(school, dimension, delta=delta)
    except (ImportError, RuntimeError, AttributeError, ValueError) as exc:
        logger.debug("hot_increment ORM fallback failed: %s", exc)


def _enumerate_hot_keys() -> list[str]:
    client = _redis_client(write=False)
    if client is None:
        return []
    out: list[str] = []
    try:
        for raw in client.scan_iter(match=f"{_HOT_KEY_PREFIX}*", count=500):
            key = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
            out.append(_strip_django_redis_version_prefix(key))
            if len(out) >= 100_000:  # magic-number-allow: result-set-row-cap
                break
    except (AttributeError, RuntimeError, ConnectionError, TimeoutError) as exc:
        logger.warning("realtime meter scan_iter failed: %s", exc)
    return out


def _parse_hot_key(key: str) -> tuple[_date_cls, int] | None:
    if not key.startswith(_HOT_KEY_PREFIX):
        return None
    tail = key[len(_HOT_KEY_PREFIX):]
    parts = tail.split(":")
    if len(parts) != 2:
        return None
    day_str, pk_str = parts
    try:
        y, m, d = day_str.split("-")
        return _date_cls(int(y), int(m), int(d)), int(pk_str)
    except (TypeError, ValueError):
        return None


def _drain_hash(client: Any, key: str) -> dict[str, int]:
    try:
        result = client.eval(_DRAIN_LUA, 1, key)
    except (AttributeError, RuntimeError, ConnectionError, TimeoutError) as exc:
        logger.debug("realtime meter drain Lua failed for %s: %s", key, exc)
        return {}
    if not result:
        return {}
    # Lua HGETALL returns a flat list [field1, value1, field2, value2, ...].
    out: dict[str, int] = {}
    for i in range(0, len(result), 2):
        try:
            field = result[i]
            value = result[i + 1]
        except IndexError:
            break
        field_s = field.decode("utf-8") if isinstance(field, (bytes, bytearray)) else str(field)
        try:
            value_i = int(value)
        except (TypeError, ValueError):
            continue
        if value_i > 0:
            out[field_s] = value_i
    return out


@shared_task(name="apps.billing.realtime_meter.flush_hot_buffers")
def flush_hot_buffers() -> dict[str, int]:
    """Drain every hot-buffer hash and roll its deltas into ``UsageMeter``.

    Returns ``{keys_seen, flushed, ticks_written}`` for monitoring.
    """
    try:
        from apps.billing.models_metering import record
        from apps.schools.models import School
    except (ImportError, RuntimeError):
        logger.warning("realtime meter flush: dependencies missing")
        return {"keys_seen": 0, "flushed": 0, "ticks_written": 0}

    client = _redis_client(write=True)
    if client is None:
        logger.info("realtime meter flush: no Redis client; nothing to drain")
        return {"keys_seen": 0, "flushed": 0, "ticks_written": 0}

    keys_seen = 0
    flushed = 0
    ticks_written = 0
    for key in _enumerate_hot_keys():
        keys_seen += 1
        parsed = _parse_hot_key(key)
        if not parsed:
            continue
        day, school_pk = parsed
        try:
            # tenant-isolation-allow: realtime-meter-flush-pk-lookup-tenant-derived-from-buffer-key
            school = School.objects.filter(pk=school_pk).first()
        except (AttributeError, RuntimeError, ValueError):
            school = None
        if school is None:
            # Tenant deleted between increment and flush — drop the hash.
            try:
                client.delete(key)
            except (AttributeError, RuntimeError, ConnectionError, TimeoutError):
                pass
            continue
        deltas = _drain_hash(client, key)
        if not deltas:
            continue
        for dimension, delta_int in deltas.items():
            try:
                record(school, dimension, delta=delta_int, day=day, metadata={
                    "source": "realtime_meter.flush_hot_buffers",
                })
                ticks_written += delta_int
            except (AttributeError, RuntimeError, ValueError) as exc:
                logger.debug("realtime meter flush: record() failed: %s", exc)
        flushed += 1
    logger.info(
        "realtime meter flush summary: keys_seen=%d flushed=%d ticks_written=%d",
        keys_seen, flushed, ticks_written,
    )
    return {"keys_seen": keys_seen, "flushed": flushed, "ticks_written": ticks_written}


__all__ = ["hot_increment", "flush_hot_buffers"]
