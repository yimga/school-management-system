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
   racing a healthy slow migrate. But heartbeat freshness alone is NOT sufficient
   proof of health: the heartbeat pings from a BACKGROUND THREAD, so a migrate
   wedged on a DB lock / hung call keeps it fresh forever while making zero
   progress — an eternal "Preparing…" that neither resume nor re-entry ever
   escapes. So liveness also carries an ABSOLUTE WALL-CLOCK CEILING
   (``provision_resume_wall_clock_ceiling_seconds()``, default 30 min, far above
   the 600s expected duration and below the ~3.3h reaper): past it a ``running``
   run is not-live regardless of heartbeat, and the sweep's wall-clock arm reaches
   it even when nobody is polling.
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
import re
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


def provision_resume_wall_clock_ceiling_seconds() -> int:
    """Absolute wall-clock age past which a ``running`` provision is treated as
    NOT live *even if its heartbeat is fresh*.

    ``heartbeat_during`` pings from a BACKGROUND THREAD, so a migrate that is
    genuinely WEDGED — blocked on a DB lock, a hung network call, an infinite
    loop — keeps the heartbeat fresh forever while making zero progress. The
    heartbeat proves the PROCESS is alive, not that the migrate ADVANCES. Judged
    on heartbeat staleness alone, such a run reads "live" indefinitely: the owner
    watches "Preparing your campus workspace" forever, the poll-driven resume
    keeps returning ``in_flight``, and ``_do_provision``'s re-entry guard keeps
    skipping — nothing ever offers a way out.

    Set FAR above ``expected_duration_seconds`` (600s) so a legitimately slow cold
    migrate (which keeps pinging every 30s) is never mistaken for wedged, and well
    below the ~3.3h abandonment reaper. Default 30 min, floored at 20 min.
    Env/settings overridable (no hardcoding).
    """
    from django.conf import settings

    raw = getattr(settings, "PROVISION_RESUME_WALL_CLOCK_CEILING_SECONDS", None)
    try:
        value = int(raw) if raw is not None else 1800  # magic-number-allow: default-wall-clock-ceiling-30min
    except (TypeError, ValueError):
        value = 1800  # magic-number-allow: default-wall-clock-ceiling-30min
    # Never allow a ceiling low enough to cancel a genuinely-slow migrate: floor
    # comfortably above expected_duration (600s) plus the heartbeat margin.
    return max(value, 1200)  # magic-number-allow: wall-clock-ceiling-floor-20min


def provision_max_no_progress_resumes() -> int:
    """Consecutive auto-resumes with ZERO forward progress after which a school's
    provisioning is declared terminally ``needs_attention`` and auto-resume STOPS.

    Ends the "requeue ~12x/hour forever" loop for a DETERMINISTIC failure (a
    genuinely broken migration, a permanently-missing column) WITHOUT ever falsely
    terminating a slow-but-converging migrate: the streak only advances when
    ``_provision_progress_signature`` did NOT increase since the previous resume
    (a killed migrate that applied more tables, or a run that reached a further
    milestone, resets the streak to 0). Generous default so only a truly wedged
    provision terminates; a human ``manual`` retry always overrides. Env/settings
    overridable (no hardcoding). Kept strictly below ``provision_resume_max_per_hour``
    (12) so terminal fires within the first hour, before the hourly cap matters.
    """
    from django.conf import settings

    raw = getattr(settings, "PROVISION_MAX_NO_PROGRESS_RESUMES", None)
    try:
        value = int(raw) if raw is not None else 8
    except (TypeError, ValueError):
        value = 8
    return max(value, 3)


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


def _run_wall_clock_age_seconds(run: Any) -> float | None:
    """Seconds since the run STARTED — independent of heartbeat freshness.

    Used for the wedged-but-heartbeating ceiling: a blocked migrate keeps its
    heartbeat fresh, so only the wall-clock since ``started_at`` reveals it.
    """
    started = getattr(run, "started_at", None)
    if started is None:
        return None
    try:
        return max(0.0, (_now() - started).total_seconds())
    except (TypeError, ValueError, AttributeError):
        return None


def _run_is_live(run: Any) -> bool:
    """A ``running`` run whose heartbeat is fresh AND which is under the absolute
    wall-clock ceiling — a genuine in-flight provision.

    Do NOT touch a healthy migrate: interrupting one is the one thing worse than a
    stuck one. But a fresh heartbeat is NOT sufficient proof of health — the
    heartbeat pings from a background thread, so a wedged migrate keeps it fresh
    forever (see ``provision_resume_wall_clock_ceiling_seconds``). Past the
    ceiling, a ``running`` run is treated as not-live so the single-flighted,
    idempotent resume path can act.
    """
    if run is None or (getattr(run, "status", "") or "").lower() != "running":
        return False
    run_age = _run_wall_clock_age_seconds(run)
    if run_age is not None and run_age >= provision_resume_wall_clock_ceiling_seconds():
        # Wedged-but-alive: heartbeat may be fresh, but the run has been "running"
        # longer than any legitimate migrate. Stop treating it as live.
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


def provision_workflow_run_is_live(run: Any) -> bool:
    """Public liveness check for a WorkflowRun (Flight Deck + auto-fix UI).

    Heartbeat-dead or wall-clock-expired ``running`` rows are NOT live — operators
    and autopilot must see an executable auto-fix, never "Diagnostic only".
    """
    return _run_is_live(run)


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
    """Owner address for the re-drive — resolved from every durable record.

    Deliberately NOT a bare ``_primary_owner_user`` lookup: a school whose
    admin_user step skipped (no email on the first drive) has no owner membership
    to read, so that lookup returns "" and the resume re-runs the pipeline with
    the same empty email that broke it — a fixed point. The resolver also reads
    SignupVerification / the onboarding blob, which predate provisioning.
    """
    try:
        from apps.schools.tasks import resolve_provisioning_contact_email

        return resolve_provisioning_contact_email(school)
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


# --- Forward-progress detection + terminal 'needs attention' state -----------
#
# Ordered provisioning milestones (durable ``SchoolProvisioningEvent`` types). The
# INDEX of the furthest-present milestone is a monotonic "how far did we get"
# signal that survives restarts and is tenancy-mode-agnostic.
_PROGRESS_MILESTONE_EVENTS: tuple[str, ...] = (
    "STARTED",
    "PROFILE_APPLIED",
    "TENANT_SCHEMA_READY",
    "ACADEMIC_YEAR_READY",
    "PORTAL_READY",
    "COMPLETED",
)

_SCHEMA_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _furthest_milestone_index(school) -> int:
    try:
        from apps.schools.models import SchoolProvisioningEvent

        present = set(
            # tenant-isolation-allow: provision-progress-milestone-events-by-school-fk
            SchoolProvisioningEvent.objects.filter(
                school=school, event_type__in=_PROGRESS_MILESTONE_EVENTS
            ).values_list("event_type", flat=True)
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        return 0
    furthest = 0
    for idx, event_type in enumerate(_PROGRESS_MILESTONE_EVENTS):
        if event_type in present:
            furthest = idx
    return furthest


def _tenant_schema_migration_count(school) -> int:
    """Applied-migration count in this school's tenant schema (schema mode only).

    This is the signal that a KILLED-but-converging migrate is making progress:
    each cycle applies more migrations, so the count climbs even while the
    ``tenant_schema`` step never reaches ``TENANT_SCHEMA_READY``. Returns 0 in RLS
    mode (where the step is a no-op) and on ANY error — a 0 never fabricates
    progress, it only fails to detect it (biasing toward NOT terminating).
    """
    try:
        from apps.schools.domain_sync import use_django_tenants

        if not use_django_tenants():
            return 0
        from apps.customers.models import Client

        sid = str(getattr(school, "pk", "") or getattr(school, "id", "") or "")
        client = (
            # tenant-isolation-allow: provision-progress-tenant-client-by-school-id
            Client.objects.filter(school_id=sid).only("schema_name").first()
        )
        schema = str(getattr(client, "schema_name", "") or "").strip()
        if not schema or not _SCHEMA_NAME_RE.match(schema):
            return 0
        from django.db import connection

        with connection.cursor() as cur:
            # schema is our OWN Client-row value validated against _SCHEMA_NAME_RE
            # (no user input); the table may not exist yet on a bare schema → except.
            cur.execute(f'SELECT count(*) FROM "{schema}".django_migrations')
            row = cur.fetchone()
        return int(row[0]) if row else 0
    except Exception:  # noqa: BLE001 — a progress probe must never break healing
        return 0


def _provision_progress_signature(school) -> tuple[int, int]:
    """(furthest milestone index, tenant-schema applied-migration count).

    A resume made FORWARD PROGRESS iff this signature INCREASED since the previous
    resume (lexicographic: a further milestone, or the same milestone with more
    migrations applied). Only when it does NOT increase does the no-progress streak
    advance toward the terminal ``needs_attention`` state.
    """
    return (_furthest_milestone_index(school), _tenant_schema_migration_count(school))


def _read_provisioning_settings(school) -> dict:
    raw = getattr(school, "settings", None) or {}
    if not isinstance(raw, dict):
        return {}
    block = raw.get("provisioning")
    return dict(block) if isinstance(block, dict) else {}


def _write_provisioning_settings(school, **updates) -> None:
    """Durably merge keys into ``school.settings['provisioning']`` (best-effort).

    Re-reads the row FRESH and merges so a concurrent phase-A/B write from the live
    drive is not clobbered; only the disjoint healing keys here are touched. Uses
    ``.update()`` (no save signals). Also syncs the in-memory object so a caller
    re-reading ``school.settings`` in the same request sees the change.
    """
    sid = str(getattr(school, "pk", "") or getattr(school, "id", "") or "")
    if not sid:
        return
    try:
        from apps.schools.models import School

        # tenant-isolation-allow: provision-watchdog-heal-metadata-by-pk
        obj = School.objects.filter(pk=sid).only("settings").first()
        if obj is None:
            return
        blob = dict(obj.settings if isinstance(obj.settings, dict) else {})
        prov = dict(blob.get("provisioning") or {})
        prov.update(updates)
        blob["provisioning"] = prov
        # tenant-isolation-allow: provision-watchdog-heal-metadata-by-pk
        School.objects.filter(pk=sid).update(settings=blob)
        mem = getattr(school, "settings", None)
        if isinstance(mem, dict):
            mem_prov = mem.get("provisioning")
            if not isinstance(mem_prov, dict):
                mem_prov = {}
            mem_prov.update(updates)
            mem["provisioning"] = mem_prov
    except Exception:  # noqa: BLE001 — healing metadata write is best-effort
        logger.debug(
            "provision_watchdog: settings write failed sid=%s", sid, exc_info=True
        )


def provision_needs_attention(school) -> bool:
    """True when auto-resume has GIVEN UP (terminal) — surfaced to owner/operator."""
    return bool(_read_provisioning_settings(school).get("needs_attention"))


def clear_provision_needs_attention(school) -> None:
    """Clear the terminal marker — a human is (re)driving; give it a fresh chance.

    Called when a drive actually BEGINS (see ``_do_provision``): auto-resume and
    the requeue sweep both SKIP a needs_attention school, so reaching a fresh drive
    means an explicit human retry.
    """
    prov = _read_provisioning_settings(school)
    if prov.get("needs_attention") or prov.get("no_progress_streak"):
        _write_provisioning_settings(school, needs_attention=False, no_progress_streak=0)


def _alert_needs_attention(school, *, streak: int, signature: tuple[int, int]) -> None:
    """One-time operator/owner signal that provisioning is terminally stuck.

    Only reached on the TRANSITION into needs_attention (the guard in
    ``resume_provision_if_stuck`` returns before here once the flag is set), so it
    fires once, not every tick.
    """
    try:
        from apps.schools.models import SchoolProvisioningEvent

        SchoolProvisioningEvent.log_event(
            school=school,
            event_type="PROVISION_NEEDS_ATTENTION",
            status="ERROR",
            message=(
                "Provisioning auto-resume stopped after repeated attempts with no "
                "forward progress — needs a human (retry or contact support)."
            ),
            payload={"no_progress_streak": streak, "signature": list(signature)},
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        logger.debug(
            "provision_watchdog: needs-attention event log failed", exc_info=True
        )
    try:
        from apps.schools.tasks import (
            _emit_provisioning_failed_notification,
            resolve_provisioning_contact_email,
        )

        _emit_provisioning_failed_notification(
            school,
            resolve_provisioning_contact_email(school),
            error="Provisioning is stuck and needs attention (auto-resume exhausted).",
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        logger.debug("provision_watchdog: needs-attention alert failed", exc_info=True)


def _cancel_dead_run(run) -> None:
    """Cancel a heartbeat-dead zombie (``running`` OR ``stuck``).

    Stuck-sweep flips dead ``running`` → ``stuck``; resume must clear BOTH so a
    fresh kick never leaves dual Flight Deck cards (STUCK + RUNNING).
    """
    if run is None or getattr(run, "pk", None) is None:
        return
    try:
        from apps.platform_runtime.models import WorkflowRun

        # tenant-isolation-allow: provision-watchdog-cancel-dead-zombie-run-by-pk
        WorkflowRun.objects.filter(
            pk=run.pk, status__in=("running", "stuck")
        ).update(
            status="cancelled",
            ended_at=_now(),
        )
    except Exception:  # noqa: BLE001 — cancel must never break the resume path
        logger.debug("provision_watchdog: cancel dead run failed", exc_info=True)


def cancel_unfinished_provision_runs_for_school(school_id: str, *, keep_pk=None) -> int:
    """Cancel all active provision runs for a school (one-active invariant).

    Returns count cancelled. ``keep_pk`` is preserved when set (e.g. current row).
    """
    sid = str(school_id or "").strip()
    if not sid:
        return 0
    try:
        from apps.platform_runtime.models import WorkflowRun

        qs = WorkflowRun.objects.filter(  # tenant-isolation-allow: provision-single-active-cancel-by-school-id
            workflow_key=PROVISION_WORKFLOW_KEY,
            school_id=sid,
            status__in=("running", "stuck"),
        )
        if keep_pk is not None:
            qs = qs.exclude(pk=keep_pk)
        return int(
            qs.update(
                status="cancelled",
                ended_at=_now(),
            )
        )
    except Exception:  # noqa: BLE001
        logger.debug(
            "provision_watchdog: cancel_unfinished failed school_id=%s",
            sid,
            exc_info=True,
        )
        return 0


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

    prov = _read_provisioning_settings(school)
    manual = reason == "manual"

    # Terminal 'needs attention': auto-resume has GIVEN UP. Auto callers back off
    # so the loop stops instead of requeuing ~12x/hour forever; a human retry
    # (reason="manual", or a fresh drive via _do_provision) overrides and clears it.
    if prov.get("needs_attention") and not manual:
        return {
            "action": "needs_attention",
            "reason": "needs_attention",
            "school_id": school_id,
        }

    if _school_is_settled(school):
        # Success clears any accrued terminal/streak state.
        if prov.get("needs_attention") or prov.get("no_progress_streak"):
            _write_provisioning_settings(
                school, needs_attention=False, no_progress_streak=0
            )
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

    # Forward-progress / terminal detection — only at a genuine resume point. The
    # streak advances ONLY when this drive made no forward progress since the last
    # resume (milestone did not advance AND no new migrations applied), so a
    # slow-but-converging migrate is never falsely terminated.
    signature = _provision_progress_signature(school)
    prev_signature = tuple(prov.get("resume_progress_signature") or ())
    streak = int(prov.get("no_progress_streak") or 0)
    made_progress = (not prev_signature) or (signature > prev_signature)
    if manual:
        streak = 0  # human override: a fresh chance
    elif made_progress:
        streak = 0
    else:
        streak += 1

    if not manual and streak >= provision_max_no_progress_resumes():
        # Clean up the dead zombie run that triggered terminal, so the owner/Flight
        # Deck sees the honest 'needs attention' state, not a lingering 'running' card.
        cancel_unfinished_provision_runs_for_school(school_id)
        _write_provisioning_settings(
            school,
            needs_attention=True,
            needs_attention_at=_now().isoformat(),
            no_progress_streak=streak,
            resume_progress_signature=list(signature),
        )
        _alert_needs_attention(school, streak=streak, signature=signature)
        logger.warning(
            "provision_watchdog: school_id=%s declared needs_attention after %s "
            "no-progress resumes (signature=%s)",
            school_id,
            streak,
            signature,
        )
        return {
            "action": "needs_attention",
            "reason": "no_forward_progress",
            "school_id": school_id,
            "streak": streak,
        }

    _write_provisioning_settings(
        school,
        needs_attention=False,
        no_progress_streak=streak,
        resume_progress_signature=list(signature),
        resume_attempts_total=int(prov.get("resume_attempts_total") or 0) + 1,
    )

    # Clear ALL unfinished zombies (running + stuck) so resume never dual-cards.
    cancel_unfinished_provision_runs_for_school(school_id)

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


# Statuses a school's provisioning run may sit in while the tenant is NOT done.
#
# ``cancelled`` is load-bearing and was missing: ``_cancel_dead_run`` (below)
# writes exactly that status onto a heartbeat-dead zombie before kicking a fresh
# drive. If that fresh drive ALSO dies before it can write its own run row — a
# deploy landing mid-resume, an OOM kill — the school's only run is left
# ``cancelled``, and a sweep that ignores that status can never see the school
# again. The watchdog's own cleanup step would have made the tenant permanently
# unscannable: the exact failure it exists to prevent.
#
# Re-scanning a cancelled run is cheap and cannot storm: ``resume_provision_if_stuck``
# no-ops on a settled school, and every resume is single-flighted + hourly-capped.
_UNFINISHED_RUN_STATUSES: tuple[str, ...] = ("running", "stuck", "failed", "cancelled")


def _dead_running_school_ids(limit: int) -> list[str]:
    """School ids whose latest provisioning run is unfinished AND either
    heartbeat-dead OR past the wall-clock ceiling (wedged-but-heartbeating).

    The heartbeat-staleness filter alone is blind to the wedged case: a migrate
    blocked on a lock keeps pinging from its background thread, so its
    ``last_heartbeat_at`` never goes stale and the sweep never selects it. The
    wall-clock arm (``started_at`` older than the ceiling) catches exactly those,
    so the no-one-is-watching backstop reaches a wedged run just like the
    owner-poll path does.
    """
    try:
        from apps.platform_runtime.models import WorkflowRun
    except ImportError:
        return []
    from django.db.models import Q

    now = _now()
    heartbeat_cutoff = now - timedelta(seconds=provision_resume_stale_seconds())
    wallclock_cutoff = now - timedelta(
        seconds=provision_resume_wall_clock_ceiling_seconds()
    )
    try:
        rows = (
            # tenant-isolation-allow: provision-watchdog-system-sweep-cross-tenant-stuck-runs
            WorkflowRun.objects.filter(
                workflow_key=PROVISION_WORKFLOW_KEY,
                status__in=_UNFINISHED_RUN_STATUSES,
            )
            .filter(
                Q(last_heartbeat_at__lt=heartbeat_cutoff)
                | Q(started_at__lt=wallclock_cutoff)
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
    # Surface a non-draining outbox queue (schools stuck PENDING with NO
    # WorkflowRun — invisible to the run-keyed sweep below). Runs every tick,
    # independent of whether any run is dead.
    stale_pending = 0
    try:
        from apps.platform_runtime.heavy_work_outbox import (
            reconcile_stale_pending_provisions,
        )

        stale_pending = int(
            reconcile_stale_pending_provisions().get("stale_pending") or 0
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        logger.debug("provision_watchdog: stale-pending reconcile skipped", exc_info=True)

    school_ids = _dead_running_school_ids(limit)
    if not school_ids:
        return {"ok": True, "scanned": 0, "resumed": 0, "stale_pending": stale_pending}
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
        "stale_pending": stale_pending,
    }
    if resumed:
        logger.info("provision_watchdog: sweep summary=%s", summary)
    return summary
