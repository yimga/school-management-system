"""Adaptive edge<->cloud sync cadence: converge in seconds, idle cheaply, reconnect instantly.

WHY THIS EXISTS
---------------
The box attempted one full sync cycle on a FIXED timer (``RMC_EDGE_SYNC_INTERVAL_SECONDS``,
default 180s, floor 60s). One number had to serve three situations it cannot serve at once:

  * **data is actively flowing** — 180s is far too slow. An attendance mark taken on the
    box is invisible in the cloud for three minutes, and a fee recorded in the cloud is
    invisible on the box for three minutes.
  * **online but idle** — 180s of building empty bundles is pure waste; nothing changed.
  * **offline** — every tick pays a full DNS + TCP + read timeout for a connection that
    cannot succeed, and the operator STILL waits up to a full interval after the network
    comes back.

This module replaces the single number with a small state machine, and — the part that
actually matters — separates the cheap question *"is the network back?"* (see
:mod:`apps.sync_engine.connectivity`) from the expensive one *"run a full cycle"*.

STATES
------
======== ============================== =========================================
state    when                           interval
======== ============================== =========================================
HOT      the last cycle moved rows      short (default 10s) — stay behind the writer
STEADY   online, nothing moved          relaxed (default 45s)
BACKOFF  cycles are failing             exponential + jitter, capped (default 300s)
======== ============================== =========================================

**Backoff on its own would make reconnection worse than the fixed timer.** After a long
outage the box would be sitting on a five-minute sleep at exactly the moment the network
returns. That is why BACKOFF is only ever paired with the cheap reachability probe: the
probe keeps running on a short fixed interval while the expensive cycle backs off, and
the offline->online transition raises a WAKE that cancels the remaining backoff at once.

WAKE
----
A wake is a one-shot "run on the next tick regardless of cadence" flag. It is raised by
connectivity returning, a local write on the box, the operator pressing *Sync now*, and
the boot entrypoint. Wakes are what make this feel immediate without polling hard.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not decide *whether* syncing is allowed (``RMC_EDGE_SYNC_ENABLED`` does), it does
not touch conflict or money policy, and it never performs I/O of its own — it reads and
writes small cache keys and returns a decision. Every entry point is total: a dead cache
degrades to "run on the default cadence", never to a crash and never to "never run".
"""

from __future__ import annotations

import logging
import os
import random
import time

from django.core.cache import cache

logger = logging.getLogger(__name__)

HOT = "hot"
STEADY = "steady"
BACKOFF = "backoff"

# Defaults chosen so a school-management workload converges inside the time it takes an
# operator to walk to another terminal, without hammering a metered link when idle.
_DEFAULT_HOT_SECONDS = 10
_DEFAULT_STEADY_SECONDS = 45
_DEFAULT_BACKOFF_BASE_SECONDS = 20
_DEFAULT_BACKOFF_CAP_SECONDS = 300  # magic-number-allow: offline backoff ceiling (seconds)

# Floor for ANY computed interval, so a misconfigured 0/negative cannot spin the box.
MIN_INTERVAL_SECONDS = 5

# Longest wake reason we keep; reasons are human breadcrumbs, not payloads.
_WAKE_REASON_MAX_CHARS = 120  # magic-number-allow: wake-reason label cap (chars)

# Cache keys. Deliberately process-shared (Valkey in prod) so the beat path, the
# /health/ tick and the operator button all see one cadence.
_STATE_KEY = "rmc:edge_sync:cadence_state"
_FAILS_KEY = "rmc:edge_sync:cadence_fails"
_NEXT_DUE_KEY = "rmc:edge_sync:cadence_next_due"
_WAKE_KEY = "rmc:edge_sync:cadence_wake"
_LAST_REASON_KEY = "rmc:edge_sync:cadence_last_reason"
_SKIPS_KEY = "rmc:edge_sync:cadence_probe_skips"

#: How many consecutive ticks the cheap probe may veto before we run a full cycle anyway.
#:
#: The probe is a NETWORK check, not a service check, and it can be wrong — a middlebox
#: that drops TCP to port 443 while an HTTP proxy still works would report "offline"
#: forever. Letting it veto without bound would turn one wrong probe into a permanently
#: silent sync engine, which is the worst failure this system can have. Bounding it means
#: a wrong probe costs at most this many skipped ticks, after which a real cycle runs and
#: either succeeds (proving the probe wrong) or records an honest failure the operator can
#: see. The skips are cheap; the bound is the safety net.
MAX_CONSECUTIVE_PROBE_SKIPS = 5

# Long enough to survive several intervals, short enough that a box that stops syncing
# forgets stale state rather than honouring it after a redeploy.
_STATE_TTL_SECONDS = 6 * 3600  # magic-number-allow: cadence state retention (6h, seconds)


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _cache_get(key, default=None):
    try:
        value = cache.get(key)
    except Exception:  # noqa: BLE001 — cache down must not break the scheduler
        logger.debug("cadence cache read failed for %s", key, exc_info=True)
        return default
    return default if value is None else value


def _cache_set(key, value, ttl=_STATE_TTL_SECONDS) -> None:
    try:
        cache.set(key, value, ttl)
    except Exception:  # noqa: BLE001
        logger.debug("cadence cache write failed for %s", key, exc_info=True)


def _cache_delete(key) -> None:
    try:
        cache.delete(key)
    except Exception:  # noqa: BLE001
        logger.debug("cadence cache delete failed for %s", key, exc_info=True)


def pinned_interval_seconds() -> int:
    """The operator's explicit pin, or 0 when they have not set one.

    ``RMC_EDGE_SYNC_INTERVAL_SECONDS`` predates adaptive cadence and some boxes already
    set it. When it IS set we honour it exactly — an operator who pinned a cadence (a
    metered satellite link, a bandwidth window) meant it, and silently going faster than
    they asked would be a bandwidth bill, not a feature. Adaptive cadence applies only
    when the pin is absent.
    """
    raw = (os.getenv("RMC_EDGE_SYNC_INTERVAL_SECONDS", "") or "").strip()
    if not raw:
        return 0
    try:
        return max(MIN_INTERVAL_SECONDS, int(raw))
    except (TypeError, ValueError):
        return 0


def hot_seconds() -> int:
    return max(MIN_INTERVAL_SECONDS, _env_int("RMC_EDGE_SYNC_HOT_SECONDS", _DEFAULT_HOT_SECONDS))


def steady_seconds() -> int:
    return max(
        MIN_INTERVAL_SECONDS, _env_int("RMC_EDGE_SYNC_STEADY_SECONDS", _DEFAULT_STEADY_SECONDS)
    )


def backoff_cap_seconds() -> int:
    return max(
        MIN_INTERVAL_SECONDS,
        _env_int("RMC_EDGE_SYNC_BACKOFF_CAP_SECONDS", _DEFAULT_BACKOFF_CAP_SECONDS),
    )


def backoff_seconds(failures: int) -> int:
    """Exponential backoff with full jitter, capped.

    Full jitter (``random.uniform(0, window)``) rather than a fixed doubling: a site with
    several boxes coming back from the same power cut must not retry in lockstep and
    recreate the outage as a thundering herd against the operator.
    """
    base = max(MIN_INTERVAL_SECONDS, _env_int(
        "RMC_EDGE_SYNC_BACKOFF_BASE_SECONDS", _DEFAULT_BACKOFF_BASE_SECONDS
    ))
    cap = backoff_cap_seconds()
    exponent = max(0, min(int(failures) - 1, 16))  # 16 doublings is far past any cap
    window = min(cap, base * (2 ** exponent))
    jittered = random.uniform(base if window > base else 0, window)  # noqa: S311 — jitter, not crypto
    return int(max(MIN_INTERVAL_SECONDS, min(cap, jittered)))


def consecutive_failures() -> int:
    try:
        return max(0, int(_cache_get(_FAILS_KEY, 0) or 0))
    except (TypeError, ValueError):
        return 0


def current_state() -> str:
    state = str(_cache_get(_STATE_KEY, STEADY) or STEADY)
    return state if state in (HOT, STEADY, BACKOFF) else STEADY


def next_interval_seconds() -> int:
    """Seconds the box should wait before its next FULL cycle, given current state."""
    pin = pinned_interval_seconds()
    if pin:
        return pin
    state = current_state()
    if state == BACKOFF:
        return backoff_seconds(consecutive_failures())
    if state == HOT:
        return hot_seconds()
    return steady_seconds()


def request_wake(reason: str = "") -> None:
    """Raise the one-shot "run on the next tick" flag.

    Idempotent and cheap: many wakes between two ticks collapse into one cycle, which is
    exactly the debounce a burst of local writes needs.
    """
    _cache_set(
        _WAKE_KEY,
        (reason or "wake").strip()[:_WAKE_REASON_MAX_CHARS],
        _STATE_TTL_SECONDS,
    )


def pending_wake() -> str:
    """The pending wake reason without consuming it (for status surfaces)."""
    return str(_cache_get(_WAKE_KEY, "") or "")


def consume_wake() -> str:
    """Read and clear the wake flag. Returns the reason, or "" when none was pending."""
    reason = pending_wake()
    if reason:
        _cache_delete(_WAKE_KEY)
    return reason


def _now() -> float:
    return time.time()


def due_now() -> tuple[bool, str]:
    """Should a full cycle run right now? Returns ``(due, reason)``.

    PURE — this does not consume the wake flag. A caller that asks "am I due?" and then
    declines to run (wrong mode, no school resolved, a lock it lost) must not have
    silently eaten the wake; the wake has to survive to the tick that actually runs.
    Call :func:`consume_wake` at the moment you commit to running.

    Fail-open by design: if we have never recorded a next-due time (fresh process, cache
    just evicted, cache down) the answer is YES. A sync engine that silently stops
    because a cache key went missing is far worse than one that runs an extra cheap
    cycle, and the cycle itself is idempotent and cursor-based.
    """
    wake = pending_wake()
    if wake:
        return True, f"wake: {wake}"
    raw_due = _cache_get(_NEXT_DUE_KEY, None)
    if raw_due is None:
        return True, "no cadence recorded yet"
    try:
        due_at = float(raw_due)
    except (TypeError, ValueError):
        return True, "unreadable cadence marker"
    now = _now()
    if now >= due_at:
        return True, f"due ({current_state()})"
    return False, f"not due for {int(due_at - now)}s ({current_state()})"


def schedule_next(interval_seconds: int | None = None) -> int:
    """Arm the next-due marker. Returns the interval actually used."""
    interval = int(interval_seconds if interval_seconds is not None else next_interval_seconds())
    interval = max(MIN_INTERVAL_SECONDS, interval)
    _cache_set(_NEXT_DUE_KEY, _now() + interval, max(_STATE_TTL_SECONDS, interval * 4))
    return interval


def record_cycle(result: dict | None) -> dict:
    """Fold one cycle's outcome into the cadence state and arm the next tick.

    ``result`` is the dict :func:`apps.sync_engine.sync_runner.run_sync_cycle` returns.
    A cycle that MOVED rows goes HOT (a writer is active somewhere, so stay close behind);
    a clean but empty cycle relaxes to STEADY; a failure enters BACKOFF and increments the
    failure count that drives the exponential window.

    Returns a small dict describing the decision, for logging and the status surface.
    """
    result = result or {}
    ok = bool(result.get("ok"))
    moved = (
        int(result.get("pushed") or 0)
        + int(result.get("pulled") or 0)
        + int(result.get("created") or 0)
        + int(result.get("upserted") or 0)
    )

    if not ok:
        failures = consecutive_failures() + 1
        _cache_set(_FAILS_KEY, failures)
        _cache_set(_STATE_KEY, BACKOFF)
        state = BACKOFF
    else:
        _cache_set(_FAILS_KEY, 0)
        state = HOT if moved > 0 else STEADY
        _cache_set(_STATE_KEY, state)
        failures = 0

    clear_probe_skips()
    interval = schedule_next()
    decision = {
        "state": state,
        "moved": moved,
        "failures": failures,
        "interval_seconds": interval,
        "pinned": bool(pinned_interval_seconds()),
    }
    _cache_set(_LAST_REASON_KEY, decision)
    return decision


def probe_skips() -> int:
    """Consecutive ticks the reachability probe has vetoed."""
    try:
        return max(0, int(_cache_get(_SKIPS_KEY, 0) or 0))
    except (TypeError, ValueError):
        return 0


def note_probe_skip() -> int:
    """Record that the probe vetoed this tick; returns the new consecutive count."""
    count = probe_skips() + 1
    _cache_set(_SKIPS_KEY, count)
    return count


def clear_probe_skips() -> None:
    _cache_delete(_SKIPS_KEY)


def reset() -> None:
    """Forget all cadence state (used by tests and by an operator-forced resync)."""
    for key in (_STATE_KEY, _FAILS_KEY, _NEXT_DUE_KEY, _WAKE_KEY, _LAST_REASON_KEY, _SKIPS_KEY):
        _cache_delete(key)


def snapshot() -> dict:
    """Everything the Sync Center needs to explain the current cadence to a human."""
    raw_due = _cache_get(_NEXT_DUE_KEY, None)
    seconds_until_due = None
    if raw_due is not None:
        try:
            seconds_until_due = max(0, int(float(raw_due) - _now()))
        except (TypeError, ValueError):
            seconds_until_due = None
    return {
        "state": current_state(),
        "failures": consecutive_failures(),
        "interval_seconds": next_interval_seconds(),
        "seconds_until_due": seconds_until_due,
        "wake_pending": pending_wake(),
        "pinned_interval_seconds": pinned_interval_seconds(),
        "probe_skips": probe_skips(),
    }


__all__ = [
    "BACKOFF",
    "HOT",
    "MIN_INTERVAL_SECONDS",
    "STEADY",
    "backoff_seconds",
    "consecutive_failures",
    "MAX_CONSECUTIVE_PROBE_SKIPS",
    "clear_probe_skips",
    "consume_wake",
    "current_state",
    "due_now",
    "next_interval_seconds",
    "pending_wake",
    "pinned_interval_seconds",
    "note_probe_skip",
    "probe_skips",
    "record_cycle",
    "request_wake",
    "reset",
    "schedule_next",
    "snapshot",
]
