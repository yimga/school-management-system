"""High-priority emergency social broadcast — bypasses standard queue."""

from __future__ import annotations

import heapq
import logging
import threading
import time
from dataclasses import dataclass


from apps.social_media.models import SocialPostOutbox, SocialPostPriority
from apps.social_media.services import publisher

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_heap: list[tuple[int, float, str]] = []
_row_index: dict[str, SocialPostOutbox] = {}


@dataclass
class EmergencyDispatchResult:
    posted: int
    failed: int
    elapsed_ms: float


def route_emergency_broadcast(request, *, body: str, media_urls: list[str] | None = None) -> EmergencyDispatchResult:
    """
    Enqueue and immediately process emergency posts for all tenant integrations.

    Priority 0 rows jump ahead of the in-memory standard backlog.
    """
    started = time.monotonic()
    rows = publisher.enqueue_cross_post(
        request,
        body=body,
        media_urls=media_urls,
        source="emergency",
    )
    for row in rows:
        row.priority = SocialPostPriority.EMERGENCY
        row.save(update_fields=["priority"])

    posted = 0
    failed = 0
    for row in rows:
        with _lock:
            heapq.heappush(_heap, (row.priority, time.monotonic(), str(row.id)))
            _row_index[str(row.id)] = row

    # Drain emergency rows immediately (before any standard backlog worker).
    #
    # Drain THROUGH the heap, which is what makes "priority 0 jumps the standard
    # backlog" an actual property of this code rather than a comment: heappop
    # returns the lowest priority first, so our EMERGENCY entries come out ahead of
    # any STANDARD entries already queued. The previous loop iterated
    # ``emergency_ids`` directly and popped only ``_row_index``, so nothing ever
    # left ``_heap`` -- no ``heappop`` existed in the module at all -- and every
    # broadcast leaked one entry per integration for the life of the worker.
    #
    # Entries belonging to someone else are set aside and pushed back afterwards
    # (rather than re-pushed inside the loop, which would spin on a concurrent
    # broadcast's priority-0 entry).
    remaining = {str(r.id) for r in rows}
    deferred: list[tuple[int, float, str]] = []
    while remaining:
        with _lock:
            if not _heap:
                break
            entry = heapq.heappop(_heap)
        row_id = entry[2]
        if row_id not in remaining:
            deferred.append(entry)
            continue
        remaining.discard(row_id)
        with _lock:
            row = _row_index.pop(row_id, None)
        if not row:
            continue
        outcome = publisher.process_outbox_row(row)
        if outcome.get("ok"):
            posted += 1
        else:
            failed += 1
    with _lock:
        for entry in deferred:
            heapq.heappush(_heap, entry)
        # Anything still unaccounted for (a peer already popped our entry) must not
        # be abandoned in _row_index -- drain it directly and keep the dict clean.
        stragglers = [_row_index.pop(row_id, None) for row_id in remaining]
    for row in stragglers:
        if row is None:
            continue
        outcome = publisher.process_outbox_row(row)
        if outcome.get("ok"):
            posted += 1
        else:
            failed += 1

    elapsed_ms = (time.monotonic() - started) * 1000.0
    logger.warning(
        "social_emergency_broadcast",
        extra={
            "posted": posted,
            "failed": failed,
            "elapsed_ms": round(elapsed_ms, 2),
            "school_id": str(getattr(getattr(request, "school", None), "id", "")),
        },
    )
    return EmergencyDispatchResult(posted=posted, failed=failed, elapsed_ms=elapsed_ms)


def backlog_depth() -> int:
    with _lock:
        return len(_heap)


def saturate_standard_backlog(count: int) -> None:
    """Test helper — simulate a deep standard-priority queue."""
    with _lock:
        for i in range(count):
            heapq.heappush(_heap, (SocialPostPriority.STANDARD, float(i), f"synthetic-{i}"))
