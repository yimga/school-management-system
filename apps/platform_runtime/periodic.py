"""In-process periodic-job dispatcher — "Celery beat without a worker".

WHY THIS EXISTS
---------------
The production topology is web + Valkey + Postgres with NO Celery worker (the
cost-minimal default; see render.yaml). With ``CELERY_BROKER_URL`` unset, Celery
runs EAGER (tasks execute inline in the request) and, crucially, NOTHING fires
the ~90 ``CELERY_BEAT_SCHEDULE`` entries — there is no beat process. So scheduled
work (e.g. the weekly benchmark-cohort recompute) silently never runs.

This module is a tiny, dependency-free scheduler that runs LIGHT, idempotent,
periodic jobs without a worker. It has three entry points, all converging on the
same registry + the same per-job code:

  1. ``maybe_run_due_jobs()``  — the AUTO trigger. Hung off the constantly-pinged
     ``/health/`` view. Non-blocking and fail-open: the request thread only does a
     pure in-memory monotonic-throttle check, then (at most once per
     ``SCAN_THROTTLE_SECONDS`` per process) spawns ONE daemon thread that does the
     cache I/O + job execution. The health response is NEVER delayed by cache or
     job runtime — that is the whole point (a blocking health probe is exactly the
     502 crash-loop we already fixed).
  2. ``run_due_jobs()`` / ``run_job()`` — the EXPLICIT triggers. Used by the
     secured internal cron endpoint (Option 2), the ``run_periodic_jobs``
     management command / Render cron (Option 3), and the tests. They run
     synchronously and always work (not gated on scheduler mode / RUNNING_TESTS).

CONCURRENCY / "exactly-once-per-interval"
-----------------------------------------
Up to 2 workers x 4 threads can hit ``/health/`` at once. Two guards keep a job
from double-firing across that fleet:

  * a shared ``cache.add()`` lock (atomic, Redis-backed in prod — the same
    cross-worker lock idiom used across the codebase) so only one thread enters a
    job at a time, and
  * a shared ``last_run`` timestamp in the cache, set at claim time, so the job
    will not re-run until ``interval_seconds`` has elapsed regardless of how many
    threads check.

In prod the cache is Valkey (shared) → the lock + last_run are genuinely
cluster-wide. With no Redis (local dev) the cache is per-process LocMem, so the
guarantee degrades to per-process — acceptable for dev.

FUTURE: ADDING A REAL CELERY WORKER (no disruption)
---------------------------------------------------
Every registered job delegates to the SAME callable the Celery task uses (the
management command / service function), so turning on a worker introduces no
duplicate logic. And ``inprocess_scheduler_enabled()`` defaults to "auto" =
ENABLED only while ``CELERY_BROKER_URL`` is unset. The moment you provision a
broker + worker + beat, this in-process scheduler stands down automatically — no
code change, no double execution. (Override explicitly with
``RMC_INPROCESS_SCHEDULER=on|off`` if you ever want both, or neither.)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from django.core.cache import cache

logger = logging.getLogger(__name__)

# --- tunables (module-level named constants; env-overridable) ----------------
SCAN_THROTTLE_SECONDS = int(os.getenv("RMC_PERIODIC_SCAN_THROTTLE", "60"))
DEFAULT_LOCK_TTL_SECONDS = 600  # magic-number-allow: default per-job lock TTL (seconds)
WEEKLY_SECONDS = 7 * 24 * 60 * 60
# last_run is kept well past one interval so it survives between ticks; extra hour
# beyond 2x interval absorbs clock skew / scheduler lag.
_LASTRUN_TTL_BUFFER_SECONDS = 3600  # magic-number-allow: last_run cache buffer (seconds)
_CACHE_PREFIX = "rmc:periodic"


@dataclass
class PeriodicJob:
    """A single light, idempotent, periodic job."""

    name: str
    interval_seconds: int
    func: Callable[[], object]
    description: str = ""
    # Lock TTL must comfortably exceed the job's worst-case runtime so a second
    # thread cannot start it mid-run; a crashed run lets the lock expire (and
    # ``last_run`` is already set, so there is no immediate re-run anyway).
    lock_ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS
    enabled: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)


_REGISTRY: dict[str, PeriodicJob] = {}
_REGISTRY_LOCK = threading.Lock()
_DEFAULTS_INSTALLED = False

# Process-local throttle so the hot ``/health/`` path does no work (not even a
# cache read) between scans. monotonic() is immune to wall-clock jumps.
_last_scan_monotonic = 0.0
_scan_gate = threading.Lock()


# --- registration ------------------------------------------------------------
def register_job(
    name: str,
    *,
    interval_seconds: int,
    func: Callable[[], object],
    description: str = "",
    lock_ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
    enabled: bool = True,
    tags: tuple[str, ...] = (),
) -> None:
    """Register (idempotently) a periodic job. Last writer for a name wins."""
    with _REGISTRY_LOCK:
        _REGISTRY[name] = PeriodicJob(
            name=name,
            interval_seconds=int(interval_seconds),
            func=func,
            description=description,
            lock_ttl_seconds=int(lock_ttl_seconds),
            enabled=bool(enabled),
            tags=tuple(tags),
        )


def ensure_default_jobs() -> None:
    """Install the built-in jobs exactly once. Cheap + idempotent.

    Kept tiny on purpose: ONLY light, idempotent, already-guarded jobs belong in
    the in-process scheduler (they share the web dyno's threads). Heavy or
    tenant-fan-out work should be triggered via the secured cron endpoint or
    Render cron (which run their own process), or by a real Celery worker.
    """
    global _DEFAULTS_INSTALLED
    if _DEFAULTS_INSTALLED:
        return
    with _REGISTRY_LOCK:
        if _DEFAULTS_INSTALLED:
            return
        # Register directly under the lock (NOT via register_job, which would
        # re-acquire this non-reentrant lock) and flip the flag in the SAME
        # critical section, so a racing caller never sees "installed" before the
        # job is actually present.
        _REGISTRY["customersuccess.recompute_benchmark_cohorts"] = PeriodicJob(
            name="customersuccess.recompute_benchmark_cohorts",
            interval_seconds=WEEKLY_SECONDS,
            func=_run_recompute_benchmark_cohorts,
            description="Weekly k-anonymous peer-benchmark cohort recompute.",
            tags=("analytics", "light"),
        )
        _DEFAULTS_INSTALLED = True


def _run_recompute_benchmark_cohorts() -> object:
    # Delegates to the SAME management command the Celery task wraps, so the
    # future-worker path runs identical code (no duplicate logic).
    from django.core.management import call_command

    return call_command("recompute_benchmark_cohorts")


# --- mode / gating -----------------------------------------------------------
def inprocess_scheduler_enabled() -> bool:
    """Whether the AUTO (health-triggered) scheduler should run.

    ``RMC_INPROCESS_SCHEDULER``: ``on`` | ``off`` | ``auto`` (default). In auto
    mode it is enabled ONLY while no Celery broker is configured — so it yields
    automatically the moment a real worker + beat are provisioned.
    """
    mode = (os.getenv("RMC_INPROCESS_SCHEDULER", "auto") or "auto").strip().lower()
    if mode in ("off", "0", "false", "no", "disabled"):
        return False
    if mode in ("on", "1", "true", "yes", "enabled"):
        return True
    return not bool((os.getenv("CELERY_BROKER_URL") or "").strip())


# --- claim / run -------------------------------------------------------------
def _lastrun_key(name: str) -> str:
    return f"{_CACHE_PREFIX}:lastrun:{name}"


def _lock_key(name: str) -> str:
    return f"{_CACHE_PREFIX}:lock:{name}"


def _get_last_run(name: str) -> float | None:
    try:
        val = cache.get(_lastrun_key(name))
    except Exception:  # noqa: BLE001 — cache down → treat as never-run, never raise
        logger.debug("periodic last_run read failed for %s", name, exc_info=True)
        return None
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _is_due(job: PeriodicJob, now: float, *, force: bool) -> bool:
    if force:
        return True
    last = _get_last_run(job.name)
    return last is None or (now - last) >= job.interval_seconds


def _claim(job: PeriodicJob, now: float, *, force: bool = False) -> bool:
    """Atomically claim a run slot across the whole fleet. False = skip."""
    try:
        acquired = cache.add(_lock_key(job.name), "1", job.lock_ttl_seconds)
    except Exception:  # noqa: BLE001 — cache down → cannot coordinate, skip safely
        logger.debug("periodic lock add failed for %s", job.name, exc_info=True)
        return False
    if not acquired:
        return False
    # Re-check under the lock: another worker may have just run it. ``force``
    # deliberately bypasses due-gating (operator override), so skip the re-check.
    if not force:
        last = _get_last_run(job.name)
        if last is not None and (now - last) < job.interval_seconds:
            _release(job)
            return False
    # Mark claimed BEFORE running so concurrent ticks see it as not-due even while
    # the job is still in flight. last_run persists well past one interval.
    #
    # NB: this runs for forced runs too, so a forced run REBASES the schedule
    # (next auto run is ~one interval later). That is intentional and the safe
    # choice: if we left last_run stale, the very next /health/ tick after a
    # forced run of an already-overdue job would immediately run it AGAIN (a
    # double run). Jobs here are idempotent, so a rebased cadence is harmless.
    try:
        cache.set(
            _lastrun_key(job.name),
            now,
            timeout=int(job.interval_seconds) * 2 + _LASTRUN_TTL_BUFFER_SECONDS,
        )
    except Exception:  # noqa: BLE001 — non-fatal; lock alone still prevents overlap
        logger.debug("periodic last_run write failed for %s", job.name, exc_info=True)
    return True


def _release(job: PeriodicJob) -> None:
    try:
        cache.delete(_lock_key(job.name))
    except Exception:  # noqa: BLE001
        logger.debug("periodic lock release failed for %s", job.name, exc_info=True)


def run_job(name: str, *, force: bool = False) -> dict:
    """Run a single registered job if due (or unconditionally with ``force``).

    Synchronous. Safe to call off-request (closes stale DB connections around the
    work). Never raises — returns a structured result dict.
    """
    ensure_default_jobs()
    job = _REGISTRY.get(name)
    if job is None:
        return {"job": name, "status": "unknown"}
    if not job.enabled:
        return {"job": name, "status": "disabled"}

    now = time.time()
    if not _is_due(job, now, force=force):
        return {"job": name, "status": "not_due"}
    if not _claim(job, now, force=force):
        return {"job": name, "status": "skipped_locked"}

    # NB: connection hygiene is the THREAD wrapper's job (see _close_thread_connections),
    # not this function's — run_job also runs synchronously in the request thread, in
    # the management command, and in tests, where Django owns the connection lifecycle.
    started = time.monotonic()
    try:
        job.func()
        return {
            "job": name,
            "status": "ran",
            "duration_s": round(time.monotonic() - started, 3),
        }
    except Exception as exc:  # noqa: BLE001 — a failing job must never crash the caller
        logger.exception("periodic job %s failed", name)
        return {"job": name, "status": "error", "error": str(exc)}
    finally:
        _release(job)


def run_due_jobs(*, force: bool = False) -> list[dict]:
    """Run every due (or, with ``force``, every enabled) registered job."""
    ensure_default_jobs()
    results: list[dict] = []
    for name in list(_REGISTRY.keys()):
        results.append(run_job(name, force=force))
    return results


# --- auto trigger (health path) ---------------------------------------------
def close_thread_connections() -> None:
    """Release this thread's DB connections — call in a one-shot worker thread's
    ``finally`` so it never leaks a connection from the pool/budget."""
    try:
        from django.db import connections

        connections.close_all()
    except Exception:  # noqa: BLE001 — best-effort cleanup, never raise
        logger.debug("periodic thread connection close failed", exc_info=True)


def _scan_and_run() -> None:
    try:
        results = run_due_jobs(force=False)
        ran = [r for r in results if r.get("status") == "ran"]
        if ran:
            logger.info("periodic tick ran %d job(s): %s", len(ran), [r["job"] for r in ran])
    except Exception:  # noqa: BLE001 — background thread must never escalate
        logger.exception("periodic scan_and_run failed")
    finally:
        close_thread_connections()


def maybe_run_due_jobs() -> None:
    """AUTO entry point for the ``/health/`` view. Pure-memory and instant.

    Does at most a monotonic comparison on the request thread, then (no more than
    once per ``SCAN_THROTTLE_SECONDS`` per process) hands ALL cache I/O + job
    execution to a daemon thread. Never blocks the caller, never raises.
    """
    global _last_scan_monotonic
    try:
        from django.conf import settings

        if getattr(settings, "RUNNING_TESTS", False):
            return
        if not inprocess_scheduler_enabled():
            return

        now_m = time.monotonic()
        if (now_m - _last_scan_monotonic) < SCAN_THROTTLE_SECONDS:
            return
        # Only one thread per process advances the gate per window.
        if not _scan_gate.acquire(blocking=False):
            return
        try:
            if (now_m - _last_scan_monotonic) < SCAN_THROTTLE_SECONDS:
                return
            _last_scan_monotonic = now_m
        finally:
            _scan_gate.release()

        threading.Thread(
            target=_scan_and_run, name="rmc-periodic-tick", daemon=True
        ).start()
    except Exception:  # noqa: BLE001 — the health probe must be untouchable
        logger.debug("maybe_run_due_jobs guard tripped", exc_info=True)


# --- introspection (status endpoint / debugging) ----------------------------
def registry_status() -> list[dict]:
    """Snapshot of registered jobs + their schedule state (for the cron status)."""
    ensure_default_jobs()
    now = time.time()
    out: list[dict] = []
    for name, job in sorted(_REGISTRY.items()):
        last = _get_last_run(name)
        seconds_until_due = None
        if last is not None:
            seconds_until_due = max(0, int(job.interval_seconds - (now - last)))
        out.append(
            {
                "job": name,
                "description": job.description,
                "interval_seconds": job.interval_seconds,
                "enabled": job.enabled,
                "tags": list(job.tags),
                "last_run_epoch": last,
                "seconds_until_due": seconds_until_due,
                "due_now": _is_due(job, now, force=False),
            }
        )
    return out
