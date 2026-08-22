"""``SYNC_STATE_HELD_FOR_UPGRADE`` — the flag that stops data moving under stale code.

WHY IT LIVES IN THE CACHE AND NOT IN A TABLE. The state this flag describes is
"the database may be mid-migration". Reading it from a row means the sync worker asks the
very database that is being altered whether it is safe to talk to that database — and if
the migration takes a lock, the worker blocks on its own status check and the box hangs
with no diagnosis. So the flag lives in the volatile cache
(``django_redis`` -> Valkey on a self-hosted box, ``LocMemCache`` where none is
configured) and nowhere else.

THE COROLLARY OF THAT CHOICE, STATED HONESTLY. A cache is allowed to forget. With
``LocMemCache`` the flag is per-process, so on a multi-worker box one worker can hold
while another does not. That is not a defect to paper over: the flag is a
LATENCY-and-safety optimisation on top of the guarantees that already exist — the schema
handshake still withholds entities a box cannot apply, the per-row savepoints still
contain a row that does not fit, and the cursors still refuse to advance over ground that
did not land. Losing the flag costs an extra cycle, never a row.

EVERY HOLD EXPIRES. A hold with no TTL is a box that stops syncing forever because an
upgrade failed at 2am on a Sunday. ``RMC_OTA_HOLD_TTL_SECONDS`` (default one hour) is the
ceiling: past it the hold lapses, data sync resumes on the OLD code — which is exactly
the state the box was in before the upgrade was offered, and a state it is known to
survive — and the next handshake re-offers the upgrade.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

SYNC_STATE_ACTIVE = "SYNC_STATE_ACTIVE"
SYNC_STATE_HELD_FOR_UPGRADE = "SYNC_STATE_HELD_FOR_UPGRADE"

# Cloud side: one key per school, so a tenant whose box is upgrading does not hold any
# other tenant's rail. Box side: a single key, because a box serves exactly one school.
_CLOUD_KEY = "rmc:edge_sync:upgrade_hold:%s"
_LOCAL_KEY = "rmc:edge_sync:upgrade_hold:local"

_DEFAULT_HOLD_TTL_SECONDS = 3600  # magic-number-allow: hold ceiling (1h, seconds)

# How long a box remembers that it already reported an upgrade failure upstream, so a
# crash-looping appliance does not attach the same traceback to every handshake.
_FAILURE_TTL_SECONDS = 6 * 3600  # magic-number-allow: failure-report retention (6h)
_FAILURE_KEY = "rmc:edge_sync:upgrade_failure:local"


def hold_ttl_seconds() -> int:
    from django.conf import settings

    try:
        return max(60, int(getattr(settings, "RMC_OTA_HOLD_TTL_SECONDS", _DEFAULT_HOLD_TTL_SECONDS)))
    except (TypeError, ValueError):
        return _DEFAULT_HOLD_TTL_SECONDS


def _cache():
    from django.core.cache import cache

    return cache


def _get(key, default=None):
    try:
        value = _cache().get(key)
    except Exception:  # noqa: BLE001 - a broken cache must not break sync
        logger.debug("upgrade hold: cache read failed for %s", key, exc_info=True)
        return default
    return default if value is None else value


def _set(key, value, ttl) -> None:
    try:
        _cache().set(key, value, ttl)
    except Exception:  # noqa: BLE001
        logger.debug("upgrade hold: cache write failed for %s", key, exc_info=True)


def _delete(key) -> None:
    try:
        _cache().delete(key)
    except Exception:  # noqa: BLE001
        logger.debug("upgrade hold: cache delete failed for %s", key, exc_info=True)


# ── cloud side ───────────────────────────────────────────────────────────────
def hold(school, *, target_hash: str, current_hash: str = "", reason: str = "") -> dict:
    """Place this school's rail into ``SYNC_STATE_HELD_FOR_UPGRADE``.

    Idempotent for the same target: re-holding does not reset the original ``since``, so
    an operator can see how long a box has actually been stuck rather than how long ago
    it last called home.
    """
    key = _CLOUD_KEY % getattr(school, "pk", school)
    existing = _get(key) or {}
    since = existing.get("since") if existing.get("target_hash") == target_hash else None
    payload = {
        "state": SYNC_STATE_HELD_FOR_UPGRADE,
        "target_hash": str(target_hash or ""),
        "current_hash": str(current_hash or ""),
        "reason": str(reason or "")[:200],
        "since": since or time.time(),
    }
    _set(key, payload, hold_ttl_seconds())
    return payload


def release(school) -> None:
    """Return this school's rail to ``SYNC_STATE_ACTIVE``."""
    _delete(_CLOUD_KEY % getattr(school, "pk", school))


def state(school) -> dict:
    """``{state, target_hash, current_hash, reason, since, held_seconds}``."""
    payload = _get(_CLOUD_KEY % getattr(school, "pk", school))
    if not isinstance(payload, dict) or payload.get("state") != SYNC_STATE_HELD_FOR_UPGRADE:
        return {"state": SYNC_STATE_ACTIVE, "target_hash": "", "held_seconds": 0}
    out = dict(payload)
    out["held_seconds"] = max(0, int(time.time() - float(payload.get("since") or time.time())))
    return out


def is_held(school) -> bool:
    return state(school).get("state") == SYNC_STATE_HELD_FOR_UPGRADE


# ── box side ─────────────────────────────────────────────────────────────────
def arm_local(*, target_hash: str, current_hash: str = "", reason: str = "") -> dict:
    """Record that the cloud has offered this box an upgrade it has not applied yet.

    Armed from a response HEADER on an ordinary cycle, so learning about an upgrade costs
    the box no extra request. The hold takes effect from the NEXT tick — the cycle that
    learned about it has already completed under the protection of the schema handshake,
    which withholds exactly the entities this box could not have applied.
    """
    existing = _get(_LOCAL_KEY) or {}
    since = existing.get("since") if existing.get("target_hash") == target_hash else None
    payload = {
        "state": SYNC_STATE_HELD_FOR_UPGRADE,
        "target_hash": str(target_hash or ""),
        "current_hash": str(current_hash or ""),
        "reason": str(reason or "")[:200],
        "since": since or time.time(),
    }
    _set(_LOCAL_KEY, payload, hold_ttl_seconds())
    return payload


def disarm_local() -> None:
    _delete(_LOCAL_KEY)


def local_state() -> dict:
    payload = _get(_LOCAL_KEY)
    if not isinstance(payload, dict) or payload.get("state") != SYNC_STATE_HELD_FOR_UPGRADE:
        return {"state": SYNC_STATE_ACTIVE, "target_hash": "", "held_seconds": 0}
    out = dict(payload)
    out["held_seconds"] = max(0, int(time.time() - float(payload.get("since") or time.time())))
    return out


def local_is_held() -> bool:
    return local_state().get("state") == SYNC_STATE_HELD_FOR_UPGRADE


# A target this box has already carried as far as its mode allows. Remembered so a box
# that legitimately cannot finish an upgrade — an asset-only lane, or a code lane needing
# an image rebuild — does not re-hold its data rail on every single cycle forever. The
# upgrade stays VISIBLE (the runner still reports it); it simply stops being a blocker
# once the box has done everything it is permitted to do about it.
_ACK_KEY = "rmc:edge_sync:upgrade_ack:local"
_ACK_TTL_SECONDS = 7 * 24 * 3600  # magic-number-allow: acknowledged-target retention (7d)


def acknowledge_local(target_hash: str) -> None:
    _set(_ACK_KEY, {"target_hash": str(target_hash or ""), "at": time.time()}, _ACK_TTL_SECONDS)


def acknowledged_target() -> str:
    payload = _get(_ACK_KEY)
    return str((payload or {}).get("target_hash") or "") if isinstance(payload, dict) else ""


def clear_acknowledged() -> None:
    _delete(_ACK_KEY)


def record_local_failure(*, target_hash: str, error: str) -> None:
    """Remember a failed apply so the next handshake can report it once, not forever."""
    _set(
        _FAILURE_KEY,
        {"target_hash": str(target_hash or ""), "error": str(error or "")[:500], "at": time.time()},
        _FAILURE_TTL_SECONDS,
    )


def local_failure() -> dict:
    payload = _get(_FAILURE_KEY)
    return payload if isinstance(payload, dict) else {}


def clear_local_failure() -> None:
    _delete(_FAILURE_KEY)


def reset() -> None:
    """Test hook: forget every hold this process can see."""
    _delete(_LOCAL_KEY)
    _delete(_FAILURE_KEY)
    _delete(_ACK_KEY)


__all__ = [
    "SYNC_STATE_ACTIVE",
    "SYNC_STATE_HELD_FOR_UPGRADE",
    "hold_ttl_seconds",
    "hold",
    "release",
    "state",
    "is_held",
    "arm_local",
    "disarm_local",
    "local_state",
    "local_is_held",
    "record_local_failure",
    "local_failure",
    "clear_local_failure",
    "acknowledge_local",
    "acknowledged_target",
    "clear_acknowledged",
    "reset",
]
