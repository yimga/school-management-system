"""Provisioning watchdog — detect a dead/stuck provision and re-drive it.

ROOT CAUSE THIS SEALS
---------------------
The ``tenant_schema`` provisioning step ("Preparing your campus workspace") runs
a multi-minute, blocking, full-app-set schema ``migrate``. When the process
running it dies BEFORE ``finalize_run`` — the gunicorn 120s request timeout on
the in-request sync paths, a worker recycle on the post-response daemon thread,
or a deploy/OOM kill on a Celery worker — the kill is a signal, not a Python
exception, so ``_do_provision`` never reaches ``finalize_run`` and
``provision_school_task.retry`` never fires. The ``WorkflowRun`` is stranded
``status="running"`` pinned at ``tenant_schema`` with its heartbeat frozen, and
the owner watches "Preparing your campus workspace" forever.

Why the pre-existing self-healing never rescued it:
  * The whole stuck→requeue autopilot is gated on ``status="stuck"``, and the ONLY
    code that writes that status is a Celery-BEAT sweep. The default topology runs
    web-only (no beat), so nothing ever flips the status and the autopilot bails
    ``"not_stuck"``.
  * ``reconcile_half_provisioned_tenants`` (the durable catch-all) is gated on
    ``is_active`` + ``phase_a_complete`` — both set only AFTER ``tenant_schema`` —
    so it is structurally blind to a run that died DURING ``tenant_schema``.
  * The lazy abandonment reaper needs ~3.3h of a frozen heartbeat and only marks
    the run FAILED; it never resumes provisioning.
  * ``_provisioning_job_in_flight`` treats any ``status="running"`` row as "in
    flight" — even one whose heartbeat died minutes ago — so it actively BLOCKS a
    re-kick of the exact runs that need one.

THE FIX
-------
One canonical, single-flight resume with three properties:

1. Liveness is judged by HEARTBEAT STALENESS, not status. ``heartbeat_during``
   pings every ``HEARTBEAT_INTERVAL`` (30s) while the migrate is genuinely alive,
   so a heartbeat older than ``provision_resume_stale_seconds()`` (default 120s =
   four missed pings) reliably means the runner died — safe to resume without
   racing a healthy slow migrate.
2. The re-drive resumes the IDEMPOTENT migrate (already-applied migrations are
   skipped), so each cycle makes forward progress and provisioning converges even
   under a per-run time ceiling that is shorter than a cold full migrate.
3. Every resume is single-flighted through an atomic ``cache.add`` lock keyed on
   the school, so concurrent polls / dynos / sweeps cannot stampede into a
   double-migrate on one fresh schema (the pre-existing ``force=True`` re-kick had
   no such guard and could spawn a migrate thread on every poll).

Triggers (both wired so healing does not depend on Celery beat):
  * the owner / pending-subdomain progress polls — the owner is literally watching
    the spinner and polling every few seconds, the most reliable trigger there is;
  * the in-process ``/health/``-tick scheduler (``apps.platform_runtime.periodic``)
    for when nobody is watching.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

PROVISION_WORKFLOW_KEY = "tenant_school_provision"

# ``heartbeat_during`` pings every 30s while a migrate is genuinely running
# (workflow_tracker.heartbeat_during interval_seconds default). Kept here as a
# named constant so the staleness floor below stays meaningfully above it.
HEARTBEAT_INTERVAL_SECONDS = 30

_CACHE_PREFIX = "rmc:provision-watchdog"


def provision_resume_stale_seconds() -> int:
    """Heartbeat age past which a ``running`` provision is treated as dead.

    Must be comfortably above ``HEARTBEAT_INTERVAL_SECONDS`` so a healthy, slow
    migrate (which pings every 30s) is never mistaken for a dead one. Default
    120s = four missed pings. Env/settings overridable (no hardcoding).
    """
    from django.conf import settings

    raw = getattr(settings, "PROVISION_RESUME_STALE_SECONDS", None)
    try:
        value = int(raw) if raw is not None else 4 * HEARTBEAT_INTERVAL_SECONDS
    except (TypeError, ValueError):
        value = 4 * HEARTBEAT_INTERVAL_SECONDS
    # Never allow a value that could false-fire on a healthy heartbeat.
    return max(value, 3 * HEARTBEAT_INTERVAL_SECONDS)


def provision_resume_max_per_hour() -> int:
    """Cap on automatic resumes per school per hour (runaway-loop backstop).

    Generous by design: a killed migrate makes forward progress on every resume,
    so many cycles are legitimate. Past the cap the watchdog simply STOPS
    auto-resuming for the hour (it does NOT force-fail a possibly-progressing
    migrate); the operator flight-deck Retry and the genuine-error FAILED path
    remain available.
    """
    from django.conf import settings

    raw = getattr(settings, "PROVISION_RESUME_MAX_PER_HOUR", None)
    try:
        value = int(raw) if raw is not None else 12
    except (TypeError, ValueError):
        value = 12
    return max(value, 1)


def _now():
    return timezone.now()


def _run_heartbeat_age_seconds(run: Any) -> float | None:
    last = getattr(run, "last_heartbeat_at", None)
    if last is None:
        return None
    try:
        return max(0.0, (_now() - last).total_seconds())
    except (TypeError, ValueError, AttributeError):
        return None


def _run_is_live(run: Any) -> bool:
    """A ``running`` run whose heartbeat is fresh — a genuine in-flight provision.

    Do NOT touch these: interrupting a healthy migrate is the one thing worse
    than a stuck one.
    """
    if run is None or (getattr(run, "status", "") or "").lower() != "running":
        return False
    age = _run_heartbeat_age_seconds(run)
    if age is None:
        # No heartbeat timestamp at all — cannot prove it is alive; treat as
        # not-live so the resume path (which is itself single-flighted) can act.
        return False
    return age <= provision_resume_stale_seconds()


def provisioning_drive_is_live(school) -> bool:
    """True when this school already has a genuinely in-flight provision.

    Single source of truth for "a drive is already running, don't start another"
    — used by ``_do_provision`` to skip a concurrent re-entry (killing the
    double-migrate race where a queued task and an in-request booster both migrate
    one fresh schema). Unlike the pre-existing ``_provisioning_job_in_flight``,
    this treats a heartbeat-DEAD ``running`` row as NOT live, so it never blocks
    the resume of a run whose process died.
    """
    return _run_is_live(_latest_run(school))


def _school_is_settled(school) -> bool:
    """True when there is nothing to do: portal is ready AND Phase B is complete."""
    try:
        from apps.schools.provisioning_progress import (
            provisioning_needs_resume,
            resolve_portal_ready,
        )
    except ImportError:
        return bool(getattr(school, "is_active", False))
    if not resolve_portal_ready(school):
        return False
    # portal_ready but Phase B unfinished still needs a resume.
    return not provisioning_needs_resume(school)


def _latest_run(school):
    try:
        from apps.schools.provisioning_progress import _latest_workflow_run

        return _latest_workflow_run(school)
    except (ImportError, AttributeError, TypeError, ValueError):
        return None


def _owner_email(school) -> str:
    try:
        from apps.schools.pending_tenant_discovery import _primary_owner_user

        owner = _primary_owner_user(school)
        return (getattr(owner, "email", "") or "").strip()
    except (ImportError, AttributeError, TypeError, ValueError):
        return ""


def _hourly_resume_count(school_id: str) -> int:
    key = f"{_CACHE_PREFIX}:count:{school_id}"
    try:
        return int(cache.get(key) or 0)
    except (ValueError, TypeError):
        return 0


def _bump_hourly_resume_count(school_id: str) -> int:
    key = f"{_CACHE_PREFIX}:count:{school_id}"
    # add() seeds the TTL window only when the key is absent, so the hour window
    # starts at the first resume and does not slide on every bump.
    cache.add(key, 0, timeout=3600)  # magic-number-allow: one-hour resume-count window
    try:
        return int(cache.incr(key))
    except ValueError:
        # Key expired between add() and incr(); reseed at 1.
        cache.set(key, 1, timeout=3600)  # magic-number-allow: one-hour resume-count window
        return 1


def _cancel_dead_run(run) -> None:
    """Terminally cancel a heartbeat-dead ``running`` zombie so it stops showing
    as in-flight and the fresh run the kick creates becomes the latest."""
    if run is None or getattr(run, "pk", None) is None:
        return
    try:
        from apps.platform_runtime.models import WorkflowRun

        # tenant-isolation-allow: provision-watchdog-cancel-dead-zombie-run-by-pk
        WorkflowRun.objects.filter(pk=run.pk, status="running").update(
            status="cancelled",
            ended_at=_now(),
        )
    except Exception:  # noqa: BLE001 — cancel must never break the resume path
        logger.debug("provision_watchdog: cancel dead run failed", exc_info=True)


def resume_provision_if_stuck(school, *, reason: str = "poll") -> dict:
    """Re-drive a single school's provisioning iff its latest run is dead/failed.

    Single-flighted per school. Safe to call on every poll tick — a live provision
    or a settled school is a cheap no-op, and concurrent callers collapse to one
    resume via the atomic cache lock.
    """
    if school is None:
        return {"action": "none", "reason": "no_school"}
    school_id = str(getattr(school, "pk", "") or getattr(school, "id", "") or "")
    if not school_id:
        return {"action": "none", "reason": "no_school_id"}

    if _school_is_settled(school):
        return {"action": "none", "reason": "settled", "school_id": school_id}

    run = _latest_run(school)
    if _run_is_live(run):
        return {"action": "none", "reason": "in_flight", "school_id": school_id}

    # Atomic single-flight lock: whoever wins re-drives; everyone else backs off
    # for one staleness window (by which point the new run's heartbeat is fresh,
    # so the next poll sees it as live and skips).
    lock_key = f"{_CACHE_PREFIX}:lock:{school_id}"
    stale = provision_resume_stale_seconds()
    if not cache.add(lock_key, reason, timeout=stale):
        return {"action": "none", "reason": "debounced", "school_id": school_id}

    if _hourly_resume_count(school_id) >= provision_resume_max_per_hour():
        logger.warning(
            "provision_watchdog: hourly resume cap reached school_id=%s reason=%s",
            school_id,
            reason,
        )
        return {"action": "capped", "reason": "hourly_cap", "school_id": school_id}

    # Clear the heartbeat-dead zombie so it stops masquerading as in-flight.
    if run is not None and (getattr(run, "status", "") or "").lower() == "running":
        _cancel_dead_run(run)

    contact_email = _owner_email(school)
    try:
        from apps.schools.tasks import kick_complete_provisioning_background

        kick_complete_provisioning_background(school_id, contact_email=contact_email)
    except (ImportError, AttributeError, TypeError, ValueError):
        logger.warning(
            "provision_watchdog: kick failed school_id=%s", school_id, exc_info=True
        )
        return {"action": "error", "reason": "kick_failed", "school_id": school_id}

    count = _bump_hourly_resume_count(school_id)
    logger.info(
        "provision_watchdog: resumed provisioning school_id=%s reason=%s attempt=%s",
        school_id,
        reason,
        count,
    )
    _record_resume_event(school, reason=reason, attempt=count)
    return {
        "action": "resumed",
        "reason": reason,
        "school_id": school_id,
        "attempt": count,
    }


def _record_resume_event(school, *, reason: str, attempt: int) -> None:
    """Leave an audit breadcrumb on the provisioning timeline (best-effort)."""
    try:
        from apps.schools.models import SchoolProvisioningEvent

        SchoolProvisioningEvent.log_event(
            school=school,
            event_type="PROVISION_AUTO_RESUMED",
            status="INFO",
            message="Provisioning auto-resumed after a stalled/dead run.",
            payload={"reason": reason, "attempt": attempt},
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        logger.debug("provision_watchdog: resume event log failed", exc_info=True)


def _dead_running_school_ids(limit: int) -> list[str]:
    """School ids whose latest provisioning run is ``running`` but heartbeat-dead."""
    try:
        from apps.platform_runtime.models import WorkflowRun
    except ImportError:
        return []
    cutoff = _now() - timedelta(seconds=provision_resume_stale_seconds())
    try:
        rows = (
            # tenant-isolation-allow: provision-watchdog-system-sweep-cross-tenant-stuck-runs
            WorkflowRun.objects.filter(
                workflow_key=PROVISION_WORKFLOW_KEY,
                status__in=("running", "stuck", "failed"),
                last_heartbeat_at__lt=cutoff,
            )
            .exclude(school_id="")
            .order_by("-started_at")
            .values_list("school_id", flat=True)[: max(limit * 4, limit)]
        )
    except Exception:  # noqa: BLE001 — a sweep must never raise into the /health/ tick
        logger.debug("provision_watchdog: sweep query failed", exc_info=True)
        return []
    seen: list[str] = []
    for sid in rows:
        sid = str(sid or "")
        if sid and sid not in seen:
            seen.append(sid)
        if len(seen) >= limit:
            break
    return seen


def resume_stuck_provisions(*, limit: int = 10, reason: str = "sweep") -> dict:
    """System sweep: re-drive up to ``limit`` schools whose provisioning died.

    Registered as a LIGHT ``/health/``-tick job (the scan is one indexed query;
    each re-drive is a background kick, never an inline migrate) so self-healing
    fires in the default no-beat topology. Idempotent + single-flighted per
    school, so a duplicate/late tick re-drives nothing already in flight.
    """
    school_ids = _dead_running_school_ids(limit)
    if not school_ids:
        return {"ok": True, "scanned": 0, "resumed": 0}
    try:
        from apps.schools.models import School
    except ImportError:
        return {"ok": False, "reason": "school_import_failed"}

    resumed = 0
    settled = 0
    for sid in school_ids:
        school = School.objects.filter(pk=sid).first()
        if school is None:
            continue
        result = resume_provision_if_stuck(school, reason=reason)
        if result.get("action") == "resumed":
            resumed += 1
        elif result.get("reason") == "settled":
            settled += 1
    summary = {
        "ok": True,
        "scanned": len(school_ids),
        "resumed": resumed,
        "settled": settled,
    }
    if resumed:
        logger.info("provision_watchdog: sweep summary=%s", summary)
    return summary
