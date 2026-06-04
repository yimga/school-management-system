"""v4.00.36 — AI gateway Redis-bucket → UsageMeter flush task.

Closes the audit gap: ``services.ai_gateway._record_metric`` writes
per-(date, tenant, task, tier, cost_class) buckets to the Django cache
under the key prefix ``ai:metrics:`` with a 3-day TTL. Nothing flushed
them to ``UsageMeter`` before TTL expiry — so AI invocation counts
weren't reaching the billing ledger.

This task runs every 5 minutes (Celery beat — register in settings):

    "billing-flush-ai-metrics": {
        "task": "apps.billing.tasks_ai_token_flush.flush_ai_metrics_buckets",
        "schedule": crontab(minute="*/5"),
    }

For each ``ai:metrics:*`` key:

* parse ``(date, tenant_id, task_type, tier, cost_class)`` from the key;
* fetch the bucket dict, increment ``UsageMeter[ai_invocations]`` for
  the resolved school on ``period_start == period_end == date``;
* atomically delete the key so the next run does not double-count.

Backend portability: the Redis backend supports key enumeration via
``client.scan_iter()``. Other Django cache backends (locmem, dummy) do
not — the task logs a single WARNING and returns. This is intentional:
production runs on Redis; dev/test mock the task directly.

Task is best-effort. Any exception during a single key flush is logged
and the loop continues — one corrupt bucket cannot block billing.
"""

from __future__ import annotations

import logging
from datetime import date as _date
from typing import Any

from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)

_KEY_PREFIX = "ai:metrics:"
# Soft cap so a runaway key-scan can't OOM the worker on a misconfigured cluster.
_MAX_KEYS_PER_RUN = 50_000  # magic-number-allow: in-memory-ring-buffer-cap


def _parse_key(raw_key: str) -> tuple[str, str, str, str, str] | None:
    """Parse ``ai:metrics:{date}:{tenant}:{task}:{tier}:{cost_class}``.

    Returns ``None`` for malformed keys so they get skipped rather than
    crashing the flush loop.
    """
    if not raw_key or not raw_key.startswith(_KEY_PREFIX):
        return None
    tail = raw_key[len(_KEY_PREFIX):]
    parts = tail.split(":")
    if len(parts) != 5:
        return None
    return parts[0], parts[1], parts[2], parts[3], parts[4]


def _iter_keys() -> list[str]:
    """Enumerate ``ai:metrics:*`` keys via the Redis backend client.

    Returns ``[]`` for non-Redis backends. ``scan_iter`` is preferred
    over ``keys()`` so we never block the Redis event loop on a large
    keyspace.
    """
    try:
        client = cache.client.get_client(write=False)  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError):
        logger.warning(
            "AI metric flush: cache backend lacks .client.get_client; backend=%s",
            type(cache).__name__,
        )
        return []
    try:
        out: list[str] = []
        for raw in client.scan_iter(match=f"{_KEY_PREFIX}*", count=500):
            key = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
            # django-redis prefixes keys with ":1:" (version) by default — strip if present.
            if ":" in key and key.startswith(":") and _KEY_PREFIX not in key.split(":", 3)[2]:
                pass  # not our key shape
            stripped = key
            for prefix_guess in (":1:", ":2:", ":3:"):
                if stripped.startswith(prefix_guess):
                    stripped = stripped[len(prefix_guess):]
                    break
            if stripped.startswith(_KEY_PREFIX):
                out.append(stripped)
            if len(out) >= _MAX_KEYS_PER_RUN:
                logger.warning(
                    "AI metric flush hit _MAX_KEYS_PER_RUN=%d; remaining keys drain next run",
                    _MAX_KEYS_PER_RUN,
                )
                break
        return out
    except (AttributeError, RuntimeError, ConnectionError, TimeoutError) as exc:
        logger.warning("AI metric flush scan_iter failed: %s", exc)
        return []


def _resolve_school(tenant_id_str: str) -> Any | None:
    if not tenant_id_str or tenant_id_str == "global":
        return None
    try:
        tenant_pk = int(tenant_id_str)
    except (TypeError, ValueError):
        return None
    try:
        from apps.schools.models import School

        # tenant-isolation-allow: ai-metric-flush-pk-lookup-tenant-derived-from-bucket-key
        return School.objects.filter(pk=tenant_pk).first()
    except (ImportError, RuntimeError, AttributeError, ValueError):
        return None


def _date_from_str(date_str: str) -> _date | None:
    try:
        parts = date_str.split("-")
        if len(parts) != 3:
            return None
        return _date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (TypeError, ValueError):
        return None


@shared_task(name="apps.billing.tasks_ai_token_flush.flush_ai_metrics_buckets")
def flush_ai_metrics_buckets() -> dict[str, int]:
    """Drain ``ai:metrics:*`` cache buckets into ``UsageMeter``.

    Returns a small accounting dict: ``{keys_seen, flushed, skipped}``.
    Safe to invoke directly from tests with ``flush_ai_metrics_buckets()``.
    """
    try:
        from apps.billing.models_metering import record
    except (ImportError, RuntimeError):
        logger.warning("AI metric flush: billing.models_metering unavailable")
        return {"keys_seen": 0, "flushed": 0, "skipped": 0}

    seen = 0
    flushed = 0
    skipped = 0
    for key in _iter_keys():
        seen += 1
        parsed = _parse_key(key)
        if not parsed:
            skipped += 1
            continue
        date_str, tenant_id_str, _task, _tier, _cost_class = parsed
        try:
            bucket = cache.get(key)
        except (AttributeError, RuntimeError, ConnectionError, TimeoutError) as exc:
            logger.debug("AI metric flush: cache.get failed key=%s: %s", key, exc)
            skipped += 1
            continue
        if not isinstance(bucket, dict):
            cache.delete(key)
            skipped += 1
            continue
        count = int(bucket.get("count", 0) or 0)
        if count <= 0:
            cache.delete(key)
            skipped += 1
            continue
        day = _date_from_str(date_str)
        school = _resolve_school(tenant_id_str)
        if day is None or school is None:
            # Cannot route to a tenant: drop the key so it doesn't accumulate forever,
            # but log so misrouted entries are visible.
            logger.debug(
                "AI metric flush: dropping unrouteable key=%s day=%s school=%s",
                key,
                day,
                school,
            )
            cache.delete(key)
            skipped += 1
            continue
        try:
            record(school, "ai_invocations", delta=count, day=day, metadata={
                "source": "tasks_ai_token_flush",
                "task_type": _task,
                "tier": _tier,
                "cost_class": _cost_class,
            })
            cache.delete(key)
            flushed += 1
        except (AttributeError, RuntimeError, ValueError) as exc:
            logger.debug("AI metric flush: record() failed key=%s: %s", key, exc)
            skipped += 1
    logger.info(
        "AI metric flush summary: keys_seen=%d flushed=%d skipped=%d", seen, flushed, skipped
    )
    return {"keys_seen": seen, "flushed": flushed, "skipped": skipped}


__all__ = ["flush_ai_metrics_buckets"]
