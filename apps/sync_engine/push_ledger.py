"""Remember what the last cycle already sent, so the cursor overlap costs nothing.

The overlap (``models.get_sync_cursor_for_request``) exists because a wall-clock cursor
loses writes: a transaction that commits after a cycle read the high-water stamps an
``updated_at`` already behind it and is never offered again. Re-asking from slightly
behind the cursor closes that.

Paid for naively, it would undo a guarantee this engine already fought for: *a second
cycle with no local change pushes nothing*. Every row changed inside the overlap window
would be re-transmitted on every tick — six times per row at a 20-second cadence, on a
link a school may be paying for by the megabyte.

So the sender remembers, for one window, WHICH VERSION of each row it last put on the
wire, and drops a re-offer that has not changed since. A genuinely new edit has a
different ``updated_at`` and still ships. The race the overlap exists for still resolves
correctly, because a row lost to it was never sent and so is not in this memory at all.

Cache-backed on purpose, not a table: this is a hint, and losing it must cost nothing
worse than one extra re-send. Bounded by the overlap window rather than by history, so
it stays small no matter how large the school is.
"""
from __future__ import annotations

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

_KEY = "rmc:sync_engine:pushed:%s"
# Three overlap windows: long enough that the memory always outlives the window it
# guards, short enough that a stale entry cannot suppress a real change for long. The
# suppression is keyed on the row's exact updated_at, so even a stale entry can only ever
# drop a row that genuinely has not changed.
_TTL_MULTIPLIER = 3
_MIN_TTL_SECONDS = 300  # magic-number-allow: floor for the sent-memory TTL

# Schools this PROCESS has written a memory for. Only so reset() can clear them: the
# cache API has no key-prefix delete, and a test whose rolled-back school reuses a pk
# would otherwise inherit the previous test's "already sent" answer and see an empty
# delta for reasons that have nothing to do with what it is testing.
_WRITTEN: set = set()


def _ttl() -> int:
    from apps.sync_engine.models import cursor_overlap_seconds

    return max(_MIN_TTL_SECONDS, cursor_overlap_seconds() * _TTL_MULTIPLIER)


def _row_key(row) -> str:
    return f"{row.get('entity_type')}|{row.get('id')}|{row.get('op') or ''}"


def recent_sent(school) -> dict:
    """``{row_key: updated_at_iso}`` this side put on the wire recently."""
    if school is None:
        return {}
    try:
        value = cache.get(_KEY % school.pk)
    except Exception:  # noqa: BLE001 - a hint must never break a cycle
        return {}
    return value if isinstance(value, dict) else {}


def already_sent(memory: dict, row) -> bool:
    """True when this EXACT version of the row was already delivered."""
    if not memory:
        return False
    stamp = row.get("updated_at")
    if not stamp:
        # No position at all: never suppress it. A row with no timestamp cannot be shown
        # to be unchanged, and dropping it would be a silent loss.
        return False
    return memory.get(_row_key(row)) == stamp


def record_sent(school, rows) -> None:
    """Remember the rows a page just delivered. Never raises."""
    if school is None or not rows:
        return
    try:
        memory = recent_sent(school)
        for row in rows:
            stamp = row.get("updated_at")
            if stamp:
                memory[_row_key(row)] = stamp
        # Bounded: the window only ever holds rows changed inside the overlap, but a
        # pathological burst should not grow the cache entry without limit either.
        if len(memory) > 5000:  # magic-number-allow: sent-memory entry cap
            memory = dict(list(memory.items())[-5000:])
        cache.set(_KEY % school.pk, memory, _ttl())
        _WRITTEN.add(school.pk)
    except Exception:  # noqa: BLE001
        logger.debug("could not record the pushed-row memory", exc_info=True)


def reset(school=None) -> None:
    """Forget the memory - used by a full resync and by tests.

    A full resync means "send everything again", so a memory of what was already sent is
    exactly the thing that would defeat it.
    """
    try:
        if school is not None:
            cache.delete(_KEY % school.pk)
            _WRITTEN.discard(school.pk)
            return
        for pk in list(_WRITTEN):
            cache.delete(_KEY % pk)
        _WRITTEN.clear()
    except Exception:  # noqa: BLE001
        pass


__all__ = ["already_sent", "record_sent", "recent_sent", "reset"]
