"""Where the tenant's schedule meets the adaptive cadence — and who wins.

PRECEDENCE. This is the whole contract, written here rather than left implicit in code,
because a precedence rule that only exists in an ``if`` is one the next person will invert:

| Situation                                   | What wins            | Why                                                                                          |
|---------------------------------------------|----------------------|----------------------------------------------------------------------------------------------|
| An explicit wake (operator "Sync now", a queued directive, a local write) | the wake | A human asked. Making a person wait for a window is how a feature becomes a complaint.        |
| Consecutive failures                        | backoff              | A schedule is not permission to hammer a cloud that is down.                                  |
| Inside a configured window                  | the tenant's interval| It is their decision, on their deployment.                                                    |
| Outside every window                        | the idle ceiling     | Never zero: a box that stops checking in cannot be TOLD anything, including to start again.   |
| No schedule at all                          | adaptive cadence     | The zero-configuration default, unchanged from before this feature existed.                   |

THE IDLE CEILING, stated plainly because it is the one place the product does not do
exactly what the tenant typed. A tenant who asks for "06:00 and 18:00 only" still gets a
check-in at most ``RMC_EDGE_SYNC_IDLE_CEILING_SECONDS`` apart (default one hour). That is
deliberate: ``EdgeSyncDirective`` is the ONLY cloud→box channel, and it is collected by
the box asking. A box that goes twelve hours without asking cannot receive the operator's
"Queue full resync" for twelve hours, and from the cloud it is indistinguishable from a
box that has been switched off. The ceiling is configurable, and a tenant who genuinely
wants twice-daily-and-nothing-else can raise it.

MISSED WINDOWS: CATCH UP ONCE. If the box was off or offline through a scheduled moment,
it runs once when it comes back and then resumes the schedule. The alternative — skip and
wait for the next window — is wrong for the case that motivates schedules at all ("it
should have synced at 6, it was off, it synced when I turned it on"). One catch-up, not
one per missed window: the state is a single next-due marker, so a weekend outage produces
one run on Monday rather than forty-eight.
"""
from __future__ import annotations

import logging
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone as dj_timezone

from apps.sync_engine import cadence
from apps.sync_engine.schedule import is_within_window, next_run_at

logger = logging.getLogger(__name__)

_DEFAULT_IDLE_CEILING_SECONDS = 3600  # magic-number-allow: idle check-in ceiling (1h)


def idle_ceiling_seconds() -> int:
    """Longest a box may go without checking in, even with no scheduled run due."""
    raw = (os.getenv("RMC_EDGE_SYNC_IDLE_CEILING_SECONDS", "") or "").strip()
    try:
        value = int(raw) if raw else _DEFAULT_IDLE_CEILING_SECONDS
    except (TypeError, ValueError):
        value = _DEFAULT_IDLE_CEILING_SECONDS
    return max(cadence.MIN_INTERVAL_SECONDS, value)


def school_timezone(school):
    """The TENANT's zone, falling back to the platform default — never the server's guess.

    A bad or missing zone string must not stop a box syncing, so an unknown name degrades
    to the active Django timezone rather than raising.
    """
    name = (getattr(school, "timezone", "") or "").strip()
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            logger.warning("sync schedule: unknown timezone %r; using the platform default", name)
    return dj_timezone.get_current_timezone()


def active_rules(school) -> list:
    from apps.sync_engine.models_schedule import rules_for

    return rules_for(school)


def planned_next_run(school, *, after=None):
    """The tenant's next scheduled instant, or ``None`` when nothing is scheduled.

    THE function from the build directive's R3: the scheduler decides with it and the Sync
    Center displays it. A second implementation for display would drift, and a next-run
    label that is wrong is worse than none — it is the thing the user is planning around.
    """
    rules = active_rules(school)
    if not rules:
        return None
    moment = after or dj_timezone.now()
    try:
        return next_run_at(rules, after=moment, tz=school_timezone(school))
    except Exception:  # noqa: BLE001 — a bad rule must never stop a box syncing
        logger.exception("sync schedule evaluation failed; falling back to adaptive cadence")
        return None


def interval_for(school, *, now=None) -> tuple:
    """``(seconds, reason)`` for the next cycle, or ``(None, reason)`` to defer.

    ``None`` means "the adaptive cadence decides" — the zero-configuration path, and the
    fallback for every failure mode here. It never means "stop syncing".
    """
    now = now or dj_timezone.now()

    # Backoff outranks the schedule. Retrying on the tenant's cadence into a cloud that is
    # down turns their preference into a denial-of-service against their own operator.
    if cadence.current_state() == cadence.BACKOFF:
        return None, "backing off after consecutive failures"

    rules = active_rules(school)
    if not rules:
        return None, "no schedule configured — automatic cadence"

    tz = school_timezone(school)
    try:
        if is_within_window(rules, at=now, tz=tz):
            inside = _tightest_active_interval(rules, now=now, tz=tz)
            if inside:
                return inside, "inside a scheduled window"
        upcoming = next_run_at(rules, after=now, tz=tz)
    except Exception:  # noqa: BLE001
        logger.exception("sync schedule evaluation failed; falling back to adaptive cadence")
        return None, "schedule could not be evaluated — automatic cadence"

    if upcoming is None:
        return None, "nothing scheduled — automatic cadence"

    wait = int((upcoming - now).total_seconds())
    ceiling = idle_ceiling_seconds()
    if wait > ceiling:
        # Not zero, and not the full wait either. See THE IDLE CEILING above.
        return ceiling, f"next run {upcoming.isoformat()}; checking in meanwhile"
    return max(cadence.MIN_INTERVAL_SECONDS, wait), f"next scheduled run {upcoming.isoformat()}"


def _tightest_active_interval(rules, *, now, tz):
    """Seconds for the SHORTEST interval rule whose window covers ``now``.

    Shortest, not first: two overlapping windows mean the tenant asked for the busier
    behaviour during the overlap, and picking whichever rule was created first would make
    behaviour depend on row order.
    """
    from apps.sync_engine.schedule import MODE_INTERVAL, Rule  # noqa: F401

    best = None
    for rule in rules:
        if rule.mode != MODE_INTERVAL or not rule.interval_minutes:
            continue
        if not is_within_window([rule], at=now, tz=tz):
            continue
        seconds = int(rule.interval_minutes) * 60
        if best is None or seconds < best:
            best = seconds
    if best is None:
        return None
    return max(cadence.MIN_INTERVAL_SECONDS, best)


def missed_run(school, *, last_run_at, now=None):
    """The scheduled moment the box slept through, or ``None``.

    Catch-up is ONE run, not one per missed moment: this answers "was there at least one",
    and the caller runs a single cycle. A weekend outage must produce a Monday sync, not
    forty-eight of them.
    """
    if last_run_at is None:
        return None
    rules = active_rules(school)
    if not rules:
        return None
    now = now or dj_timezone.now()
    try:
        upcoming = next_run_at(rules, after=last_run_at, tz=school_timezone(school))
    except Exception:  # noqa: BLE001
        return None
    if upcoming is not None and upcoming <= now:
        return upcoming
    return None


def schedule_summary(school, *, now=None) -> dict:
    """What the Sync Center shows. Computed with :func:`planned_next_run`, deliberately.

    The build directive's R3 in one place: the label on the screen and the moment the
    scheduler will actually act are the SAME value, so they cannot drift. A next-run label
    that is wrong is worse than no label at all — it is the thing the person is planning
    around.

    ``last_run_at`` rides along because a next-run time on its own is only a promise. Shown
    beside the last ACTUAL run, a box that stopped a week ago is visible instead of being
    quietly implied to be fine.
    """
    from apps.sync_engine.schedule import describe

    now = now or dj_timezone.now()
    rules = active_rules(school)
    tz = school_timezone(school)
    upcoming = planned_next_run(school, after=now)

    last_run_at = None
    try:
        from apps.sync_engine.models import EdgeSyncRun

        latest = EdgeSyncRun.objects.filter(school=school).order_by("-created_at").first()
        last_run_at = getattr(latest, "created_at", None)
    except Exception:  # noqa: BLE001 — a status panel must never 500 on its own query
        logger.debug("schedule summary: last-run lookup failed", exc_info=True)

    stale = False
    if rules and last_run_at is not None:
        # "Stale" is not "old". It means a scheduled moment passed and the box did not act,
        # which is the state a next-run label would otherwise paper over.
        stale = missed_run(school, last_run_at=last_run_at, now=now) is not None

    return {
        "configured": bool(rules),
        "timezone": str(tz),
        "description": describe(rules),
        "next_run_at": upcoming.isoformat() if upcoming else None,
        "next_run_in_seconds": int((upcoming - now).total_seconds()) if upcoming else None,
        "last_run_at": last_run_at.isoformat() if last_run_at else None,
        "missed_window": stale,
        "idle_ceiling_seconds": idle_ceiling_seconds(),
        # Said in the payload rather than only in a template, so every surface that reads
        # this tells the same truth: the cloud cannot push, so a change lands on the next
        # cycle.
        "propagation_note": (
            "Schedule changes reach the box on its next sync — the cloud cannot contact "
            "a box directly."
        ),
    }


def arm_next_cycle(school, *, now=None) -> dict:
    """Re-arm the cadence marker from the tenant's schedule, if one applies.

    Called after a cycle. Returns a small dict for the run record so an operator can see
    WHY the next run is when it is — "not due for 2400s" with no reason is the kind of
    answer that makes people distrust a scheduler.
    """
    seconds, reason = interval_for(school, now=now)
    if seconds is None:
        return {"source": "cadence", "reason": reason}
    try:
        applied = cadence.schedule_next(seconds)
    except Exception:  # noqa: BLE001 — never break a completed cycle on the arming step
        logger.debug("schedule arm failed", exc_info=True)
        return {"source": "cadence", "reason": "could not arm from schedule"}
    return {"source": "schedule", "interval_seconds": applied, "reason": reason}
