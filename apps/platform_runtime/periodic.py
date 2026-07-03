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
DAILY_SECONDS = 24 * 60 * 60
# Reliability drainers (outbound message queue, event outbox) must drain far more
# often than daily so a queued SMS/WhatsApp/push or an outbox-routed event delivers
# within minutes, not a day. They are auto_eligible=False (secured cron path only),
# so this cadence is the floor at which the cron tick will run them when invoked.
FREQUENT_DRAIN_SECONDS = 5 * 60  # magic-number-allow: drainer min interval (seconds)
# A heavy, tenant-fan-out job (e.g. the billing lifecycle) can run longer than the
# default lock TTL, especially via the management-command / Render-cron path which
# has no HTTP cap. Keep the claim lock well past its worst-case runtime so a second
# trigger can't start it mid-run. (last_run gating is the backstop regardless.)
HEAVY_JOB_LOCK_TTL_SECONDS = 1800  # magic-number-allow: heavy cron-only job lock TTL (seconds)
# last_run is kept well past one interval so it survives between ticks; extra hour
# beyond 2x interval absorbs clock skew / scheduler lag.
_LASTRUN_TTL_BUFFER_SECONDS = 3600  # magic-number-allow: last_run cache buffer (seconds)
_CACHE_PREFIX = "rmc:periodic"
_MS_PER_SECOND = 1000  # magic-number-allow: milliseconds per second
# Scheduler health monitor (dead-man's-switch) cadence. Light + auto_eligible so
# it runs off the /health/ tick; see scheduled_job_health.run_health_monitor.
MONITOR_INTERVAL_SECONDS = 60 * 60


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
    # When False the job is SKIPPED by the AUTO (/health/-tick) path and runs ONLY
    # via the explicit triggers (secured cron endpoint, run_periodic_jobs command,
    # Render cron). This is how heavy / tenant-fan-out / financial work stays off
    # the constantly-pinged web health thread while still being scheduled.
    auto_eligible: bool = True
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
    auto_eligible: bool = True,
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
            auto_eligible=bool(auto_eligible),
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
        # Heavy + financial + tenant-fan-out: matures the platform billing
        # lifecycle daily (trial->active conversion, period renewal + charge,
        # dunning past-due/suspend, and collection restore). Marked
        # auto_eligible=False so it NEVER runs on the hot /health/ thread — it is
        # driven only by the secured cron endpoint, the run_periodic_jobs command,
        # or Render cron, each running off the request-serving hot path. The
        # command is idempotent + resumable, so a duplicate/late tick is a no-op.
        _REGISTRY["billing.run_platform_billing_lifecycle"] = PeriodicJob(
            name="billing.run_platform_billing_lifecycle",
            interval_seconds=DAILY_SECONDS,
            func=_run_platform_billing_lifecycle,
            description="Daily platform billing lifecycle (trial conversion, renewal/charge, dunning).",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("billing", "heavy"),
        )
        # Heavy + tenant-fan-out: publishes renewal + trial-ending reminders for
        # subscriptions inside the warning window (the email matrix turns each
        # published event into the tenant-admin reminder email). Registered here
        # for the SAME reason as the lifecycle above: the no-worker topology has no
        # beat, so the beat-only reminder entry never fired in the default
        # deployment. cron-only (never on the hot /health/ thread); each sweep is
        # idempotent per period via PlatformEventLog, so a duplicate/late tick
        # re-publishes nothing already sent. Now also watched by the dead-man's-
        # switch monitor + auto-recovery, at parity with the lifecycle.
        _REGISTRY["billing.run_subscription_reminders"] = PeriodicJob(
            name="billing.run_subscription_reminders",
            interval_seconds=DAILY_SECONDS,
            func=_run_subscription_reminders,
            description="Daily: publish renewal + trial-ending subscription reminders.",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("billing", "reminders"),
        )
        # Heavy + tenant-fan-out: mints DonationPledges for due recurring giving
        # schedules. The platform has no card-on-file auto-charge, so recurring giving
        # produces expected-gift pledges (donors fulfil them as usual). cron-only like
        # the billing job — never on the hot /health/ thread; the command is idempotent
        # per due-date, so a duplicate/late tick re-mints only genuinely-due schedules.
        _REGISTRY["advancement.mint_recurring_donation_pledges"] = PeriodicJob(
            name="advancement.mint_recurring_donation_pledges",
            interval_seconds=DAILY_SECONDS,
            func=_run_mint_recurring_donation_pledges,
            description="Daily: mint pledges for due recurring donation schedules.",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("advancement", "heavy"),
        )
        # --- GAP-2: notification / reliability jobs that were beat-only (DEAD) ----
        # The production topology has NO Celery worker, so every job below was wired
        # only into CELERY_BEAT_SCHEDULE and therefore never fired. Each delegates to
        # the SAME task/command the beat entry references, so a future worker runs
        # identical code. All are auto_eligible=False — they iterate every tenant /
        # touch send providers, so they belong on the secured cron path, never the
        # constantly-pinged /health/ thread. Each task/command is already idempotent +
        # atomic-claim safe; run_job() isolates a failure so one job cannot abort the
        # others.
        #
        # 1. Outbound message queue drainer (SMS / WhatsApp / push retry). Frequent.
        _REGISTRY["communication.process_outbound_message_queue"] = PeriodicJob(
            name="communication.process_outbound_message_queue",
            interval_seconds=FREQUENT_DRAIN_SECONDS,
            func=_run_process_outbound_message_queue,
            description="Drain pending outbound SMS/WhatsApp/push queue (atomic-claim, per-tenant).",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("communication", "drainer"),
        )
        # 2. Email dead-letter redrive (parked transactional sends). Frequent.
        _REGISTRY["schoolops.redrive_email_dead_letters"] = PeriodicJob(
            name="schoolops.redrive_email_dead_letters",
            interval_seconds=FREQUENT_DRAIN_SECONDS,
            func=_run_redrive_email_dead_letters,
            description="Redrive parked email dead-letters (no-op unless SCHOOLOPS_EMAIL_DLQ_ENABLED).",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("schoolops", "drainer"),
        )
        # 3. Event outbox drainer — CRITICAL: outbox-routed domain events never
        #    deliver without this. Frequent.
        _REGISTRY["events.process_event_outbox"] = PeriodicJob(
            name="events.process_event_outbox",
            interval_seconds=FREQUENT_DRAIN_SECONDS,
            func=_run_process_event_outbox,
            description="Drain the domain-event outbox (queue webhook deliveries + internal subscribers).",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("events", "drainer"),
        )
        # 4. Payment reminders + retry of failed reminders. Daily.
        _REGISTRY["finance.send_payment_reminders"] = PeriodicJob(
            name="finance.send_payment_reminders",
            interval_seconds=DAILY_SECONDS,
            func=_run_send_payment_reminders,
            description="Daily: send payment reminders for upcoming invoice due dates (per-tenant).",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("finance", "reminders"),
        )
        _REGISTRY["finance.retry_failed_payment_reminders"] = PeriodicJob(
            name="finance.retry_failed_payment_reminders",
            interval_seconds=DAILY_SECONDS,
            func=_run_retry_failed_payment_reminders,
            description="Daily: retry payment reminders that previously failed to send (per-tenant).",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("finance", "reminders"),
        )
        # 5. Grading deadline reminders to teachers. Daily.
        _REGISTRY["analytics.send_deadline_reminders"] = PeriodicJob(
            name="analytics.send_deadline_reminders",
            interval_seconds=DAILY_SECONDS,
            func=_run_send_deadline_reminders,
            description="Daily: send grading-deadline reminders to teachers (per-tenant).",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("analytics", "reminders"),
        )
        # 6. Low-meal-balance sweep (catch low rows the signal missed). Daily.
        _REGISTRY["schoolops.sweep_low_meal_plan_balances"] = PeriodicJob(
            name="schoolops.sweep_low_meal_plan_balances",
            interval_seconds=DAILY_SECONDS,
            func=_run_sweep_low_meal_plan_balances,
            description="Daily: sweep low meal-plan balances and enqueue low-balance notifications.",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("schoolops", "reminders"),
        )
        # 7. Access-request assignee reminders + certification/badge-expiry alerts. Daily.
        _REGISTRY["requests.remind_pending_assignees"] = PeriodicJob(
            name="requests.remind_pending_assignees",
            interval_seconds=DAILY_SECONDS,
            func=_run_remind_pending_assignees,
            description="Daily: remind staff assigned to pending access requests (per-tenant).",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("requests", "reminders"),
        )
        _REGISTRY["people.check_badge_expiry_alerts"] = PeriodicJob(
            name="people.check_badge_expiry_alerts",
            interval_seconds=DAILY_SECONDS,
            func=_run_check_badge_expiry_alerts,
            description="Daily: alert on certifications/badges expiring within the configured window (per-tenant).",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("people", "reminders"),
        )
        # 8. Phase-4 comms reach: deliver due scheduled announcements + parent digests.
        # The announcement sender runs frequently so a scheduled post fans out within
        # minutes of its scheduled_at (idempotent via delivered_at). Digests are split
        # by cadence so each fires on its own period; the command itself only sends to
        # guardians whose NotificationPreference.digest_cadence matches the run.
        _REGISTRY["communication.send_due_scheduled_announcements"] = PeriodicJob(
            name="communication.send_due_scheduled_announcements",
            interval_seconds=FREQUENT_DRAIN_SECONDS,
            func=_run_send_due_scheduled_announcements,
            description="Frequent: fan out announcements whose scheduled_at has passed (idempotent via delivered_at).",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("communication", "announcements"),
        )
        _REGISTRY["communication.send_parent_digests_daily"] = PeriodicJob(
            name="communication.send_parent_digests_daily",
            interval_seconds=DAILY_SECONDS,
            func=_run_send_parent_digests_daily,
            description="Daily: parent digest for guardians on the daily cadence.",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("communication", "digests"),
        )
        _REGISTRY["communication.send_parent_digests_weekly"] = PeriodicJob(
            name="communication.send_parent_digests_weekly",
            interval_seconds=WEEKLY_SECONDS,
            func=_run_send_parent_digests_weekly,
            description="Weekly: parent digest for guardians on the weekly cadence.",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("communication", "digests"),
        )
        # Scheduler observability (dead-man's-switch). LIGHT + auto_eligible so it
        # runs off the /health/ tick and keeps watching the heavy, cron-driven jobs
        # even when the external cron is down — turning a silent outage into an
        # alert (and, when RMC_JOB_AUTO_RECOVER is on, a recovery run).
        _REGISTRY["platform_runtime.monitor_scheduled_job_health"] = PeriodicJob(
            name="platform_runtime.monitor_scheduled_job_health",
            interval_seconds=MONITOR_INTERVAL_SECONDS,
            func=_run_monitor_scheduled_job_health,
            description="Hourly dead-man's-switch: alert/recover when any periodic job is overdue.",
            tags=("platform", "monitor", "light"),
        )
        # Cross-rail sync backlog watch (2026-07-02). LIGHT: a handful of COUNT
        # queries + a Redis SCAN. Before this job, SODP conflicts and the WAL
        # dead-letter streams could pile up forever with zero operator signal;
        # a threshold breach now auto-opens (and recovery auto-resolves) a
        # PlatformIncident via the idempotent incident services.
        _REGISTRY["observability.sync_backlog_monitor"] = PeriodicJob(
            name="observability.sync_backlog_monitor",
            interval_seconds=MONITOR_INTERVAL_SECONDS,
            func=_run_sync_backlog_monitor,
            description="Hourly cross-rail sync backlog watch: gauges + auto-incident on breach.",
            tags=("observability", "sync", "light"),
        )
        # Migration Cloud content-store retention sweep (gap #2, 2026-07-02).
        # LIGHT: one indexed DELETE on the shared-schema blob table. Deletes the
        # captured source PII (rosters/grades/guardian contacts) once past
        # ``expires_at`` — the backstop for bundles that never reach RECONCILED
        # (whose blobs are dropped immediately). Auto_eligible: no tenant fan-out.
        _REGISTRY["migration_cloud.purge_expired_artifact_blobs"] = PeriodicJob(
            name="migration_cloud.purge_expired_artifact_blobs",
            interval_seconds=DAILY_SECONDS,
            func=_run_purge_expired_artifact_blobs,
            description="Daily PII-minimisation sweep: delete Migration Cloud artifact source blobs past expires_at.",
            tags=("migration_cloud", "retention", "light"),
        )
        # School merge/split batch advancer (merge/split Wave D, 2026-07-03).
        # HEAVY: each tick drives up to a few TransferCases end-to-end
        # (envelope export + migration-cloud apply at the target), so it is
        # cron-only like the billing lifecycle — never on the hot /health/
        # thread. Each advance is single-flighted per batch and every case
        # run is idempotent (bundle idempotency key = case id), so a
        # duplicate or late tick re-runs nothing already applied.
        _REGISTRY["people.advance_school_transfer_batches"] = PeriodicJob(
            name="people.advance_school_transfer_batches",
            interval_seconds=FREQUENT_DRAIN_SECONDS,
            func=_run_advance_school_transfer_batches,
            description="Frequent: advance RUNNING school merge/split batches a chunk of transfer cases at a time.",
            lock_ttl_seconds=HEAVY_JOB_LOCK_TTL_SECONDS,
            auto_eligible=False,
            tags=("people", "transfers", "heavy"),
        )
        _DEFAULTS_INSTALLED = True


def _run_advance_school_transfer_batches() -> object:
    # Lazy import: people owns the batch engine (merge/split Wave D).
    from apps.people.school_batch_service import advance_running_batches

    return advance_running_batches()


def _run_purge_expired_artifact_blobs() -> object:
    # Lazy import: migration_cloud owns the store; keep it out of startup.
    from apps.migration_cloud.artifact_blob_store import purge_expired_artifact_blobs

    return purge_expired_artifact_blobs()


def _run_sync_backlog_monitor() -> object:
    # Lazy import: observability app owns the cross-rail collector; keeping the
    # import inside the job func avoids app-loading-order coupling at startup.
    from apps.observability.sync_health import evaluate_backlog_incidents

    outcome = evaluate_backlog_incidents()
    return {"opened": outcome["opened"], "resolved": outcome["resolved"]}


def _run_recompute_benchmark_cohorts() -> object:
    # Delegates to the SAME management command the Celery task wraps, so the
    # future-worker path runs identical code (no duplicate logic).
    from django.core.management import call_command

    return call_command("recompute_benchmark_cohorts")


def _run_platform_billing_lifecycle() -> object:
    # Delegates to the SAME management command an operator runs by hand / a future
    # Celery beat task would wrap, so every trigger path runs identical code.
    from django.core.management import call_command

    return call_command("run_platform_billing_lifecycle")


def _run_subscription_reminders() -> object:
    # Delegates to the SAME management command an operator runs by hand / the beat
    # task wraps, so every trigger path runs identical code: renewal (period-end)
    # AND trial-ending reminders, each idempotent per period via PlatformEventLog.
    from django.core.management import call_command

    return call_command("send_renewal_reminders")


def _run_mint_recurring_donation_pledges() -> object:
    # Delegates to the management command so the cron, manual, and future-worker
    # trigger paths all run identical code.
    from django.core.management import call_command

    return call_command("mint_recurring_donation_pledges")


# --- GAP-2 notification / reliability delegates ------------------------------
# Each delegates to the SAME Celery task / management command its beat entry
# referenced. For a ``@shared_task`` object, ``.run(...)`` executes the wrapped
# function body synchronously (binding ``self``) WITHOUT needing a worker or
# broker — identical code to the future-worker path. Plain functions are called
# directly. With no ``school_id`` argument, every per-tenant task iterates all
# active tenants itself, which is exactly the cron-sweep behaviour we want.


def _run_process_outbound_message_queue() -> object:
    # Drains the outbound SMS/WhatsApp/push queue across every tenant (the task
    # iterates active schools when school_id is omitted). Atomic-claim safe.
    from apps.communication.tasks import process_outbound_message_queue

    return process_outbound_message_queue.run()


def _run_redrive_email_dead_letters() -> object:
    # Same management command an operator runs by hand / a future beat task wraps.
    # No-op (logs "DLQ disabled") unless SCHOOLOPS_EMAIL_DLQ_ENABLED.
    from django.core.management import call_command

    return call_command("redrive_email_dead_letters")


def _run_process_event_outbox() -> object:
    # CRITICAL: outbox-routed domain events never deliver without this. Delegates
    # to the SAME batch helper the apps.events.process_event_outbox task wraps.
    from apps.events.tasks import process_outbox_batch

    return process_outbox_batch()


def _run_send_payment_reminders() -> object:
    from apps.finance.tasks import send_payment_reminders_task

    return send_payment_reminders_task.run()


def _run_retry_failed_payment_reminders() -> object:
    from apps.finance.tasks import retry_failed_payment_reminders_task

    return retry_failed_payment_reminders_task.run()


def _run_send_deadline_reminders() -> object:
    from apps.analytics.tasks import send_deadline_reminders_task

    return send_deadline_reminders_task.run()


def _run_sweep_low_meal_plan_balances() -> object:
    from apps.schoolops.tasks import sweep_low_meal_plan_balances

    return sweep_low_meal_plan_balances.run()


def _run_remind_pending_assignees() -> object:
    from apps.requests.tasks import remind_pending_assignees_task

    return remind_pending_assignees_task.run()


def _run_check_badge_expiry_alerts() -> object:
    from apps.people.tasks import check_badge_expiry_alerts_task

    return check_badge_expiry_alerts_task.run()


def _run_send_due_scheduled_announcements() -> object:
    # Delivers announcements whose scheduled_at has passed via the dispatch engine
    # (per-recipient pref/consent honoured inside). Idempotent via delivered_at.
    from apps.communication.announcement_delivery import (
        send_due_scheduled_announcements,
    )

    return send_due_scheduled_announcements()


def _run_send_parent_digests_daily() -> object:
    from django.core.management import call_command

    return call_command("send_parent_digests", cadence="daily", apply=True)


def _run_send_parent_digests_weekly() -> object:
    from django.core.management import call_command

    return call_command("send_parent_digests", cadence="weekly", apply=True)


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


def _record_heartbeat_safe(job: PeriodicJob, *, status: str, duration_ms=None, error: str = "") -> None:
    """Durably record a job's run outcome. Best-effort: never raises into run_job.

    The durable heartbeat (``apps.platform_runtime.models_scheduling``) is what the
    dead-man's-switch monitor reads — the cache ``last_run`` is wiped on every
    deploy and cannot answer "did this job go silently dark?".
    """
    try:
        from apps.platform_runtime.scheduled_job_health import record_heartbeat

        record_heartbeat(
            job.name,
            status=status,
            interval_seconds=job.interval_seconds,
            duration_ms=duration_ms,
            error=error,
        )
    except Exception:  # noqa: BLE001 — observability must never break the job
        logger.debug("heartbeat record failed for %s", job.name, exc_info=True)


def _run_monitor_scheduled_job_health() -> object:
    # Dead-man's-switch monitor: alert (and, when RMC_JOB_AUTO_RECOVER is on,
    # auto-recover) overdue jobs. Light + auto_eligible so it runs off /health/ and
    # keeps watching the heavy, cron-driven jobs even when the external cron is down.
    from apps.platform_runtime.scheduled_job_health import run_health_monitor

    return run_health_monitor()


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
        duration_ms = int((time.monotonic() - started) * _MS_PER_SECOND)
        _record_heartbeat_safe(job, status="ran", duration_ms=duration_ms)
        return {
            "job": name,
            "status": "ran",
            "duration_s": round(duration_ms / _MS_PER_SECOND, 3),
        }
    except Exception as exc:  # noqa: BLE001 — a failing job must never crash the caller
        logger.exception("periodic job %s failed", name)
        _record_heartbeat_safe(job, status="error", error=str(exc))
        return {"job": name, "status": "error", "error": str(exc)}
    finally:
        _release(job)


def run_due_jobs(*, force: bool = False, auto_only: bool = False) -> list[dict]:
    """Run every due (or, with ``force``, every enabled) registered job.

    ``auto_only=True`` restricts the run to AUTO-eligible jobs — used by the
    health-tick path so heavy / cron-only jobs (``auto_eligible=False``) never run
    on the request-serving hot thread. The explicit triggers (cron endpoint,
    management command) leave it False so they run the full registry.
    """
    ensure_default_jobs()
    results: list[dict] = []
    for name in list(_REGISTRY.keys()):
        if auto_only:
            job = _REGISTRY.get(name)
            if job is not None and not job.auto_eligible:
                continue
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
        # AUTO path: only auto-eligible jobs. Heavy / financial / fan-out jobs
        # (auto_eligible=False) are deliberately excluded from the hot health
        # thread and run via the secured cron endpoint / command instead.
        results = run_due_jobs(force=False, auto_only=True)
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
                "auto_eligible": job.auto_eligible,
                "tags": list(job.tags),
                "last_run_epoch": last,
                "seconds_until_due": seconds_until_due,
                "due_now": _is_due(job, now, force=False),
            }
        )
    return out
