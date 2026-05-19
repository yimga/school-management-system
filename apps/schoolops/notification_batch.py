"""
Notification batching helpers (Salesforce pillar).

Keeps Celery sweep/enqueue paths from stampeding the broker when many rows
qualify in one beat window.
"""

from __future__ import annotations

from typing import Iterable, Iterator, TypeVar

T = TypeVar("T")

DEFAULT_ENQUEUE_CHUNK = 50
MAX_ENQUEUE_PER_SWEEP = 500


def chunked(iterable: Iterable[T], size: int) -> Iterator[list[T]]:
    """Yield fixed-size lists from ``iterable``."""
    if size < 1:
        size = 1
    batch: list[T] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def enqueue_in_chunks(
    task,
    ids: Iterable[int],
    *,
    chunk_size: int = DEFAULT_ENQUEUE_CHUNK,
    max_total: int = MAX_ENQUEUE_PER_SWEEP,
    task_kwarg: str = "meal_plan_balance_id",
) -> dict[str, int]:
    """
    Enqueue ``task.delay`` for each id with bounded fan-out.

    Returns summary counts: ``enqueued``, ``skipped_cap``.
    """
    summary = {"enqueued": 0, "skipped_cap": 0}
    seen = 0
    for batch in chunked(ids, chunk_size):
        for pk in batch:
            if seen >= max_total:
                summary["skipped_cap"] += 1
                continue
            task.delay(**{task_kwarg: int(pk)})
            summary["enqueued"] += 1
            seen += 1
    return summary


__all__ = [
    "DEFAULT_ENQUEUE_CHUNK",
    "MAX_ENQUEUE_PER_SWEEP",
    "chunked",
    "enqueue_in_chunks",
]
