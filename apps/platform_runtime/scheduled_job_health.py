"""Dead-man's-switch monitor for the in-process periodic scheduler.

PHASE 1 of scheduler observability. The cache-based ``last_run`` in
``apps.platform_runtime.periodic`` is wiped on every deploy and expires ~2x
interval after a run, so it cannot answer "did a scheduled job go silently
dark?". ``ScheduledJobHeartbeat`` is the durable source of truth; this module
reads it, flags overdue jobs, and logs them at ERROR so they surface in logs and
in Sentry (via the logging integration) — turning the previously-silent failure
(e.g. the GitHub Actions cron budget being exhausted → heavy jobs stop) into a
loud alert.

``evaluate_staleness`` is a PURE function (no DB / cache) so the staleness rule
is unit-testable without a database. ``run_health_monitor`` is the thin
DB-backed wrapper registered as a light ``auto_eligible`` job in ``periodic.py``
— it runs off the constantly-pinged ``/health/`` path, so it keeps watching the
heavy, cron-driven jobs even when the EXTERNAL cron is down. That self-contained
watch is exactly the outage this exists to catch.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# A job is "stale" once it has not SUCCEEDED within (interval x grace_factor)
# plus a small floor that absorbs clock skew / scheduler lag. grace_factor 2.0 =
# "missed roughly two full cycles". Env-tunable without a deploy.
DEFAULT_STALE_GRACE_FACTOR = float(os.getenv("RMC_JOB_STALE_GRACE_FACTOR", "2.0") or "2.0")
STALE_GRACE_FLOOR_SECONDS = 300  # magic-number-allow: clock-skew/lag floor before stale
MAX_ERROR_TEXT_LEN = 2000  # magic-number-allow: stored last_error truncation length
_STATUS_FIELD_LEN = 32

STATUS_RAN = "ran"
STATUS_ERROR = "error"

# PHASE 2 (self-healing). When an overdue job is CRON-ONLY (auto_eligible=False)
# AND is not even being triggered (the external cron is down), the monitor kicks
# a one-shot background recovery run. Capped: a job that IS being run but keeps
# erroring is alerted, never hammered (that is a bug, not a trigger outage).
MAX_AUTO_RECOVERY_FAILURES = 3


@dataclass
class JobHealth:
    job_name: str
    interval_seconds: int
    last_success_epoch: float | None
    age_seconds: float | None
    threshold_seconds: float
    is_stale: bool
    reason: str


def staleness_threshold_seconds(interval_seconds: int, grace_factor: float) -> float:
    """Seconds-since-last-success beyond which a job is considered stale."""
    return float(interval_seconds) * float(grace_factor) + STALE_GRACE_FLOOR_SECONDS


def evaluate_staleness(jobs, *, now=None, grace_factor=None) -> list[JobHealth]:
    """Pure staleness rule — no DB / cache, so it is unit-testable in isolation.

    ``jobs`` is an iterable of dicts with keys:
        job_name           (str)
        interval_seconds   (int)
        last_success_epoch (float | None)   last successful run, epoch seconds
        watched_for_seconds(float | None)   how long a heartbeat row has existed
    Returns one ``JobHealth`` per job.
    """
    if now is None:
        now = time.time()
    if grace_factor is None:
        grace_factor = DEFAULT_STALE_GRACE_FACTOR

    findings: list[JobHealth] = []
    for j in jobs:
        interval = int(j["interval_seconds"])
        threshold = staleness_threshold_seconds(interval, grace_factor)
        last = j.get("last_success_epoch")

        if last is not None:
            age = float(now) - float(last)
            is_stale = age > threshold
            findings.append(
                JobHealth(
                    job_name=j["job_name"],
                    interval_seconds=interval,
                    last_success_epoch=float(last),
                    age_seconds=age,
                    threshold_seconds=threshold,
                    is_stale=is_stale,
                    reason="overdue" if is_stale else "healthy",
                )
            )
            continue

        # Never succeeded (no last_success). Only stale once we have been WATCHING
        # (the heartbeat row has existed) longer than the threshold — so a fresh
        # deploy with an empty table does NOT immediately false-alarm.
        watched = j.get("watched_for_seconds")
        is_stale = watched is not None and watched > threshold
        findings.append(
            JobHealth(
                job_name=j["job_name"],
                interval_seconds=interval,
                last_success_epoch=None,
                age_seconds=watched,
                threshold_seconds=threshold,
                is_stale=is_stale,
                reason="never_succeeded" if is_stale else "no_data_yet",
            )
        )
    return findings


def auto_recovery_enabled() -> bool:
    """Whether the monitor should auto-recover overdue cron-only jobs.

    ``RMC_JOB_AUTO_RECOVER``: ``on`` | ``off`` | ``auto`` (default). In auto mode
    it is enabled ONLY while no Celery broker is configured — mirroring
    ``periodic.inprocess_scheduler_enabled`` so it yields automatically the moment
    a real worker + beat are provisioned.
    """
    mode = (os.getenv("RMC_JOB_AUTO_RECOVER", "auto") or "auto").strip().lower()
    if mode in ("off", "0", "false", "no", "disabled"):
        return False
    if mode in ("on", "1", "true", "yes", "enabled"):
        return True
    return not bool((os.getenv("CELERY_BROKER_URL") or "").strip())


def select_recovery_candidates(enriched_jobs, *, now=None, max_failures=MAX_AUTO_RECOVERY_FAILURES):
    """Pure: choose which overdue jobs to auto-recover. No DB / cache.

    ``enriched_jobs`` = dicts with keys: job_name, interval_seconds, is_stale,
    auto_eligible, last_started_epoch (float|None), consecutive_failures (int).

    A job is recoverable iff ALL hold:
      * it is stale (overdue), AND
      * it is CRON-ONLY (``auto_eligible`` False) — light jobs already tick off
        ``/health/`` so they never need recovery, AND
      * it appears UN-TRIGGERED — ``last_started_epoch`` is None or older than one
        interval, i.e. nothing is invoking it (vs running-and-erroring), AND
      * ``consecutive_failures`` < ``max_failures`` — so a job that runs but keeps
        failing is alerted, not hammered.
    Returns the list of job names to recover.
    """
    if now is None:
        now = time.time()
    out: list[str] = []
    for j in enriched_jobs:
        if not j.get("is_stale"):
            continue
        if j.get("auto_eligible"):
            continue
        if int(j.get("consecutive_failures") or 0) >= int(max_failures):
            continue
        started = j.get("last_started_epoch")
        interval = int(j["interval_seconds"])
        untriggered = started is None or (float(now) - float(started)) > interval
        if untriggered:
            out.append(j["job_name"])
    return out


def _spawn_recovery(job_names) -> None:
    """Run overdue cron-only jobs in ONE daemon thread, off the caller's thread,
    with DB-connection cleanup. The per-job claim lock in ``periodic.run_job``
    prevents a double-run if another trigger fires concurrently.
    """
    import threading

    def _runner() -> None:
        try:
            from apps.platform_runtime import periodic

            for name in job_names:
                try:
                    result = periodic.run_job(name, force=False)
                    logger.warning("auto-recovery ran %s -> %s", name, result.get("status"))
                except Exception:  # noqa: BLE001 — one job must not abort the rest
                    logger.exception("auto-recovery failed for %s", name)
        finally:
            try:
                from apps.platform_runtime import periodic

                periodic.close_thread_connections()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                logger.debug("auto-recovery connection close failed", exc_info=True)

    threading.Thread(target=_runner, name="rmc-job-recovery", daemon=True).start()


def record_heartbeat(job_name, *, status, interval_seconds, duration_ms=None, error="") -> None:
    """Durably upsert a job's heartbeat after a run. Best-effort: never raises.

    Called from ``periodic.run_job`` on every completion (success or error), so
    the durable record always reflects the last real outcome regardless of which
    trigger path (health tick, secured cron, management command) ran the job.
    """
    try:
        from django.utils import timezone

        from apps.platform_runtime.models_scheduling import ScheduledJobHeartbeat

        now = timezone.now()
        # tenant-isolation-allow: platform-level scheduler heartbeat, not tenant-scoped
        hb, _created = ScheduledJobHeartbeat.objects.get_or_create(job_name=job_name)
        hb.expected_interval_seconds = int(interval_seconds)
        hb.last_status = (status or "")[:_STATUS_FIELD_LEN]
        hb.last_started_at = now
        if duration_ms is not None:
            hb.last_duration_ms = int(duration_ms)
        if status == STATUS_RAN:
            hb.last_success_at = now
            hb.consecutive_failures = 0
            hb.last_error = ""
        else:
            hb.consecutive_failures = (hb.consecutive_failures or 0) + 1
            hb.last_error = (error or "")[:MAX_ERROR_TEXT_LEN]
        hb.save()
    except Exception:  # noqa: BLE001 — heartbeat is observability; never break the job
        logger.debug("record_heartbeat failed for %s", job_name, exc_info=True)


def run_health_monitor(*, grace_factor=None) -> list[JobHealth]:
    """DB-backed monitor: join registry intervals with durable heartbeats, flag
    overdue jobs, and log stale ones at ERROR (→ logs + Sentry). Returns findings.

    Never raises — it runs on the ``/health/`` tick thread and via the secured
    cron path, and must not crash either.
    """
    findings: list[JobHealth] = []
    try:
        from apps.platform_runtime import periodic
        from apps.platform_runtime.models_scheduling import ScheduledJobHeartbeat

        now = time.time()
        registry = {r["job"]: r for r in periodic.registry_status()}
        # tenant-isolation-allow: platform-level scheduler heartbeat, not tenant-scoped
        heartbeats = {h.job_name: h for h in ScheduledJobHeartbeat.objects.all()}

        jobs = []
        for name, row in registry.items():
            hb = heartbeats.get(name)
            last_success_epoch = None
            watched_for = None
            if hb is not None:
                if hb.last_success_at is not None:
                    last_success_epoch = hb.last_success_at.timestamp()
                if hb.created_at is not None:
                    watched_for = now - hb.created_at.timestamp()
            jobs.append(
                {
                    "job_name": name,
                    "interval_seconds": row["interval_seconds"],
                    "last_success_epoch": last_success_epoch,
                    "watched_for_seconds": watched_for,
                }
            )
        findings = evaluate_staleness(jobs, now=now, grace_factor=grace_factor)
    except Exception:  # noqa: BLE001 — monitor must never crash the caller / tick
        logger.exception("run_health_monitor failed")
        return findings

    stale = [f for f in findings if f.is_stale]
    for f in stale:
        logger.error(
            "SCHEDULED JOB STALE: %s has not succeeded (age=%ss, threshold=%ss, "
            "interval=%ss, reason=%s) — scheduler/cron may be down",
            f.job_name,
            int(f.age_seconds) if f.age_seconds is not None else "n/a",
            int(f.threshold_seconds),
            f.interval_seconds,
            f.reason,
        )
    if not stale:
        logger.info("scheduled-job health OK: %d job(s) within threshold", len(findings))

    # PHASE 2 — self-healing: auto-recover overdue CRON-ONLY jobs that aren't even
    # being triggered (external cron down), in a background thread. Best-effort.
    if stale and auto_recovery_enabled():
        try:
            enriched = []
            for f in stale:
                row = registry.get(f.job_name)
                if row is None:
                    continue
                hb = heartbeats.get(f.job_name)
                enriched.append(
                    {
                        "job_name": f.job_name,
                        "interval_seconds": row["interval_seconds"],
                        "auto_eligible": row.get("auto_eligible", True),
                        "is_stale": True,
                        "last_started_epoch": (
                            hb.last_started_at.timestamp()
                            if (hb and hb.last_started_at)
                            else None
                        ),
                        "consecutive_failures": (hb.consecutive_failures if hb else 0),
                    }
                )
            candidates = select_recovery_candidates(enriched, now=now)
            if candidates:
                logger.warning(
                    "scheduled-job auto-recovery: triggering %d overdue cron-only job(s): %s",
                    len(candidates),
                    candidates,
                )
                _spawn_recovery(candidates)
        except Exception:  # noqa: BLE001 — recovery is best-effort; never crash the monitor
            logger.exception("auto-recovery selection failed")
    return findings
