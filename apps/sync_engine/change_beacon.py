"""A per-school "something changed" beacon, so a long-poll costs no database work.

WHY. Cloud->box latency is poll-bound: the appliance sits behind NAT, the cloud cannot
call it, so the box asks on a cadence and a cloud write waits out the interval (up to
~15s when busy, longer when idle). The fix is the CouchDB ``_changes`` pattern - the box
holds one request open and the cloud answers the instant a change exists - and the whole
value of that pattern is destroyed if "does a change exist?" is itself expensive.

Answering it from the database means an existence query PER SYNCED ENTITY, and there are
fifteen. Once a second, per connected appliance, that is a self-inflicted load problem
several times larger than the polling it replaces.

So every save/delete on a synced model stamps one cache key for its school, and the
long-poll reads that key. The database is consulted only as a periodic safety net (see
``apps.api.sync_changes_api``), because the beacon has one honest weakness: with a
per-process cache (LocMemCache) a write served by worker A is invisible to a long-poll
held by worker B. The safety net is what makes the feature correct anyway; the beacon is
what makes it cheap. On a deployment with a shared cache (Redis/Memcached) the safety net
almost never fires.

The beacon is advisory in the strict sense: missing it delays a change to the next
cadence tick, which is exactly the behaviour that existed before this module. It can
never cause a wrong answer, only a late one.
"""
from __future__ import annotations

import logging
import time

from django.db.models.signals import post_delete, post_save

logger = logging.getLogger(__name__)

_KEY = "rmc:sync_engine:change_beacon:%s"

# Coalescing window. Without it, a beacon write rides EVERY save of fifteen models — so a
# 10,000-row student import becomes 10,000 cache round trips, and on a Redis-backed cloud
# that is a real, self-inflicted slowdown on the platform's heaviest write path. Nothing
# is lost by coalescing: the beacon only ever answers "something changed recently", and
# the long-poll's step interval is a full second, so sub-second precision buys nothing.
_COALESCE_SECONDS = 0.5  # magic-number-allow: beacon write coalescing window
# In-process, per school. A worker that has not bumped recently always writes, so the
# worst case of a cold or per-process view is one extra write, never a missed change.
_LAST_LOCAL_BUMP: dict = {}
# Long enough that an idle school's beacon does not expire mid-long-poll and force a
# needless database sweep; short enough that the key set stays bounded.
_TTL_SECONDS = 3600  # magic-number-allow: change-beacon TTL (1 hour)


def _cache():
    from django.core.cache import cache

    return cache


def bump(school_id, when: float | None = None, *, force: bool = False) -> None:
    """Record that ``school_id`` changed at ``when`` (default: now). Never raises.

    Coalesced to one write per ``_COALESCE_SECONDS`` per school in this process, because
    this rides every save of fifteen models and a bulk import must not turn into a cache
    write per row. ``force=True`` bypasses it (tests, and any caller that needs the write
    to be observable immediately).
    """
    if not school_id:
        return
    now = float(when if when is not None else time.time())
    if not force:
        last = _LAST_LOCAL_BUMP.get(school_id)
        if last is not None and (now - last) < _COALESCE_SECONDS:
            return
    _LAST_LOCAL_BUMP[school_id] = now
    try:
        _cache().set(_KEY % school_id, now, _TTL_SECONDS)
    except Exception:  # noqa: BLE001 - a beacon must never break a write
        logger.debug("could not bump the change beacon for %s", school_id, exc_info=True)


def last_change(school_id) -> float | None:
    """Unix time of the last recorded change for ``school_id``, or ``None`` if unknown.

    ``None`` means "no information" - never "no changes". The caller must fall back to
    the database rather than treat it as an answer.
    """
    if not school_id:
        return None
    try:
        value = _cache().get(_KEY % school_id)
    except Exception:  # noqa: BLE001
        return None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _on_change(sender, instance, **_kwargs):
    try:
        bump(getattr(instance, "school_id", None))
    except Exception:  # noqa: BLE001 - never break a save or a delete
        logger.debug("change beacon receiver failed for %s", sender, exc_info=True)


_REGISTERED = {"done": False}


def register_change_signals() -> int:
    """Connect the beacon to every registered synced model. Idempotent; never raises."""
    if _REGISTERED["done"]:
        return 0
    count = 0
    try:
        from apps.sync_engine.tombstones import _entity_type_by_model

        for model in _entity_type_by_model():
            uid = f"sync_engine.beacon.{model._meta.label_lower}"
            post_save.connect(_on_change, sender=model, dispatch_uid=uid)
            post_delete.connect(_on_change, sender=model, dispatch_uid=uid + ".del")
            count += 1
        _REGISTERED["done"] = True
    except Exception:  # noqa: BLE001 - never break app startup
        logger.warning("could not register sync change-beacon signals", exc_info=True)
    return count


def reset() -> None:
    """Drop the registration flag and the coalescing memory - tests only."""
    _REGISTERED["done"] = False
    _LAST_LOCAL_BUMP.clear()


__all__ = ["bump", "last_change", "register_change_signals", "reset"]
