"""Where the tenant's schedule meets the adaptive cadence — and who wins.

PRECEDENCE. This is the whole contract, written here rather than left implicit in code,
because a precedence rule that only exists in an ``if`` is one the next person will invert:

| Situation                                   | What wins            | Why                                                                                          |
|---------------------------------------------|----------------------|----------------------------------------------------------------------------------------------|
| An explicit wake (operator "Sync now", a queued directive, a local write) | the wake | A human asked. Making a person wait for a window is how a feature becomes a complaint.        |
| Consecutive failures                        | backoff              | A schedule is not permission to hammer a cloud that is down.                                  |
| Inside a configured window                  | the tenant's interval| It is their decision, on their deployment.                                                    |
| Outside every window                        | the idle ceiling     | Never zero: a box that stops checking in cannot be TOLD anything, including to start again.   |
| A scheduled time was slept through          | one catch-up run     | The motivating case: "it should have synced at 6, it was off, it synced when I turned it on". |
| No schedule at all                          | adaptive cadence     | The zero-configuration default, unchanged from before this feature existed.                   |

THE IDLE CEILING. A tenant who asks for "06:00 and 18:00 only" still gets a check-in in
between. ``EdgeSyncDirective`` is the ONLY cloud→box channel and it is collected by the
box ASKING, so this ceiling is also the worst case on "Queue full resync" reaching this
box: go twelve hours without asking and an operator instruction waits twelve hours, which
from the cloud is indistinguishable from a box that has been switched off.

That used to be a deviation the product made silently, with the only knob an environment
variable on a host the school cannot see — so "the tenant configures their sync" was half
true. It is now the TENANT's number, on the Sync Center, replicated to the box like every
other decision here (:class:`~apps.sync_engine.models_policy.SyncPolicy`), bounded at one
day because beyond that a box cannot be reached at all. Resolution order is: the
operator's ``RMC_EDGE_SYNC_IDLE_CEILING_SECONDS`` pin, then the tenant's row, then one
hour. The screen states the consequence in words rather than leaving it to be discovered.

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
from apps.sync_engine.schedule import (
    is_within_window,
    longest_gap,
    next_run_at,
    next_runs,
    week_plan,
)

logger = logging.getLogger(__name__)

_DEFAULT_IDLE_CEILING_SECONDS = 3600  # magic-number-allow: idle check-in ceiling (1h)

# WHEN IS A HOLE WORTH FLAGGING. The strip always REPORTS the longest gap, because that
# is a fact; it only paints it as a problem past this multiple of the check-in ceiling.
# Expressed as a multiple rather than a fixed number of hours on purpose: a school on a
# 15-minute ceiling and a school on a 12-hour one do not mean the same thing by "a long
# silence", and a fixed threshold would nag the first and never fire for the second.
_DEFAULT_GAP_FLAG_MULTIPLE = 4  # magic-number-allow: gap alarm, in check-in ceilings


def _gap_flag_multiple() -> int:
    """Operator override for the gap alarm, or the documented default.

    Same shape as the idle-ceiling pin above and for the same reason: somebody running a
    deployment with a deliberately sparse schedule has to be able to stop the panel
    crying wolf, without a code change and without touching the tenant's data.
    """
    raw = (os.getenv("RMC_EDGE_SYNC_GAP_FLAG_MULTIPLE", "") or "").strip()
    if not raw:
        return _DEFAULT_GAP_FLAG_MULTIPLE
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_GAP_FLAG_MULTIPLE
    return value if value > 0 else _DEFAULT_GAP_FLAG_MULTIPLE


def _env_idle_ceiling_seconds() -> int | None:
    """The operator's pin for ONE box, or ``None``.

    Kept, and kept WINNING, for the same reason ``RMC_EDGE_SYNC_INTERVAL_SECONDS`` wins:
    somebody debugging a box in front of them has to be able to hold it still, and they
    cannot do that if a row that arrives down the rail can move it back.
    """
    raw = (os.getenv("RMC_EDGE_SYNC_IDLE_CEILING_SECONDS", "") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def idle_ceiling_seconds(school=None) -> int:
    """Longest a box may go without checking in, even with no scheduled run due.

    Resolution order, highest first:

      1. ``RMC_EDGE_SYNC_IDLE_CEILING_SECONDS`` -- the operator's pin for one box.
      2. The tenant's :class:`~apps.sync_engine.models_policy.SyncPolicy` row, which is
         what the Sync Center writes and what the rail carries down to the box.
      3. The documented default (one hour).

    ``school`` is optional so the older call sites keep working, but passing it is what
    makes this the TENANT's number rather than the host's.
    """
    pinned = _env_idle_ceiling_seconds()
    if pinned is not None:
        return max(cadence.MIN_INTERVAL_SECONDS, pinned)
    if school is not None:
        try:
            from apps.sync_engine.models_policy import policy_for

            return max(cadence.MIN_INTERVAL_SECONDS, policy_for(school).idle_ceiling_seconds)
        except Exception:  # noqa: BLE001 — never let a settings read stop a sync
            logger.debug("idle ceiling: policy read failed", exc_info=True)
    return max(cadence.MIN_INTERVAL_SECONDS, _DEFAULT_IDLE_CEILING_SECONDS)


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
    ceiling = idle_ceiling_seconds(school)
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


def last_run_at_for(school):
    """When this box last recorded a cycle, or ``None``. Never raises."""
    try:
        from apps.sync_engine.models import EdgeSyncRun

        latest = EdgeSyncRun.objects.filter(school=school).order_by("-created_at").first()
        return getattr(latest, "created_at", None)
    except Exception:  # noqa: BLE001 — a status panel must never 500 on its own query
        logger.debug("last-run lookup failed", exc_info=True)
        return None


# One catch-up per missed moment, remembered OUTSIDE the run record on purpose. Clearing
# on "a run happened" alone would be wrong twice: a cycle that fails writes a run row and
# would count as having made the moment up, and a cycle that dies before writing one would
# make the box catch up again on every single tick. Keyed by the moment itself, so the
# next missed moment is a different key and still gets its run.
_CATCHUP_KEY_PREFIX = "rmc:edge_sync:catchup_claimed"
_CATCHUP_TTL_SECONDS = 36 * 3600  # magic-number-allow: outlives a weekend outage


def _catchup_key(school, moment) -> str:
    return f"{_CATCHUP_KEY_PREFIX}:{getattr(school, 'pk', 'na')}:{moment.isoformat()}"


def should_catch_up(school, *, now=None):
    """The scheduled moment this box slept through and has not made up yet, or ``None``.

    THE GAP THIS CLOSES. ``missed_run`` existed and was correct, and nothing called it
    except the status panel — so the Sync Center would say "missed window" while the box
    quietly waited for the NEXT scheduled time. The motivating sentence for the whole
    feature ("it should have synced at 6, it was off, it synced when I turned it on") was
    documented in three places and implemented in none.

    Backoff still outranks this: a box catching up into a cloud that is down is just the
    schedule finding a new way to hammer it.
    """
    try:
        if cadence.current_state() == cadence.BACKOFF:
            return None
        policy = _policy(school)
        if not policy.catch_up_missed:
            return None
        now = now or dj_timezone.now()
        moment = missed_run(school, last_run_at=last_run_at_for(school), now=now)
        if moment is None:
            return None
        from django.core.cache import cache

        key = _catchup_key(school, moment)
        # add() is atomic: two workers ticking at once cannot both claim the same moment.
        if not cache.add(key, "1", _CATCHUP_TTL_SECONDS):
            return None
        return moment
    except Exception:  # noqa: BLE001 — a catch-up check must never break a cycle
        logger.debug("catch-up check failed", exc_info=True)
        return None


def _policy(school):
    from apps.sync_engine.models_policy import ResolvedPolicy, policy_for

    try:
        return policy_for(school)
    except Exception:  # noqa: BLE001
        return ResolvedPolicy()


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


def _stamp_gap_hours(plan, gap, tz) -> None:
    """Mark the hour cells that fall inside the flagged gap.

    Done here rather than in the template, which cannot compare instants, and rather than
    in ``week_plan``, which is pure and does not know what a school considers too long a
    silence. Only ever called for a gap already past the threshold, so an ordinary
    overnight quiet period is never painted as a fault.
    """
    import datetime as _dt

    start_raw = gap.get("start")
    end_raw = gap.get("end")
    if not start_raw or not end_raw:
        return
    try:
        start = _dt.datetime.fromisoformat(start_raw).astimezone(tz)
        end = _dt.datetime.fromisoformat(end_raw).astimezone(tz)
    except (TypeError, ValueError):
        return
    for day in plan.get("days", []):
        try:
            day_date = _dt.date.fromisoformat(day["date"])
        except (KeyError, TypeError, ValueError):
            continue
        for hour_index, cell in enumerate(day.get("hours", [])):
            cell_start = _dt.datetime.combine(
                day_date, _dt.time(hour=hour_index), tzinfo=tz
            )
            cell_end = cell_start + _dt.timedelta(hours=1)
            # Half-open overlap: an hour containing the boundary occurrence is NOT in the
            # gap, because a sync happened in it.
            if cell_end > start and cell_start < end and not cell.get("count"):
                cell["in_gap"] = True


def _local_display(moment, tz) -> str:
    """A wall-clock string in the tenant's zone, or ``""``.

    Built by hand rather than with ``%-d``: that directive is glibc-only and raises on
    Windows, where this code runs during development.
    """
    if moment is None:
        return ""
    try:
        local = moment.astimezone(tz)
    except (AttributeError, ValueError):  # pragma: no cover - defensive
        return ""
    return f"{local.day} {local.strftime('%b')} {local.strftime('%H:%M')}"


def coverage_for(school, *, now=None, rules=None) -> dict:
    """The week strip and the gap alarm, for the Sync Center's schedule panel.

    ``rules`` lets a CANDIDATE set be costed without saving it -- that is the live
    preview, and the reason it posts back here instead of being re-implemented in the
    browser: the strip a school looks at before pressing Save is drawn by the same code
    that will decide when the box actually runs. Passing ``None`` uses what is saved.

    Never raises. A panel that cannot draw its strip still has to render the sentence,
    the rules and the Save button.
    """
    now = now or dj_timezone.now()
    if rules is None:
        rules = active_rules(school)
    tz = school_timezone(school)
    multiple = _gap_flag_multiple()
    ceiling_minutes = max(1, idle_ceiling_seconds(school) // 60)
    try:
        plan = week_plan(rules, start=now, tz=tz)
        gap = longest_gap(rules, start=now, tz=tz)
        upcoming = next_runs(rules, after=now, tz=tz)
    except Exception:  # noqa: BLE001 -- the strip is a display aid, never a blocker
        logger.debug("week coverage failed", exc_info=True)
        return {
            "available": False,
            "week": None,
            "gap": None,
            "next_runs": [],
            "gap_flagged": False,
            "gap_threshold_minutes": ceiling_minutes * multiple,
            "floor_minutes": ceiling_minutes,
        }
    threshold = ceiling_minutes * multiple
    minutes = gap.get("minutes")
    flagged = bool(minutes is not None and minutes > threshold)
    if flagged:
        _stamp_gap_hours(plan, gap, tz)
    return {
        "available": True,
        "week": plan,
        "gap": gap,
        # The next five, not the next one. One answers "is it armed"; five answer "is it
        # armed CORRECTLY" -- a rule that fires at 06:00 and then not again until Monday
        # is indistinguishable from a healthy one until the second entry is visible.
        "next_runs": upcoming,
        # Reported always, painted as a problem only past the threshold. An unbounded
        # gap (no rules at all) is NOT flagged: that tenant is on the adaptive cadence
        # by choice, which is the zero-configuration default and not a hole.
        "gap_flagged": flagged,
        "gap_threshold_minutes": threshold,
        "gap_flag_multiple": multiple,
        # The check-in ceiling drawn as the floor UNDER the strip: the guarantee that
        # holds even where no rule fires. Without it a school reads an empty Sunday as
        # "the box is off all day", which is not what happens.
        "floor_minutes": ceiling_minutes,
    }


def schedule_summary(school, *, now=None, include_coverage=False) -> dict:
    """What the Sync Center shows. Computed with :func:`planned_next_run`, deliberately.

    The build directive's R3 in one place: the label on the screen and the moment the
    scheduler will actually act are the SAME value, so they cannot drift. A next-run label
    that is wrong is worse than no label at all — it is the thing the person is planning
    around.

    ``last_run_at`` rides along because a next-run time on its own is only a promise. Shown
    beside the last ACTUAL run, a box that stopped a week ago is visible instead of being
    quietly implied to be fine.
    """
    from apps.sync_engine.schedule import describe, describe_dst

    now = now or dj_timezone.now()
    rules = active_rules(school)
    tz = school_timezone(school)
    upcoming = planned_next_run(school, after=now)

    last_run_at = last_run_at_for(school)

    stale = False
    if rules and last_run_at is not None:
        # "Stale" is not "old". It means a scheduled moment passed and the box did not act,
        # which is the state a next-run label would otherwise paper over.
        stale = missed_run(school, last_run_at=last_run_at, now=now) is not None

    policy = _policy(school)
    return {
        "configured": bool(rules),
        "timezone": str(tz),
        "description": describe(rules),
        # DST is a DECISION, not a setting -- there is one defensible answer in each
        # direction. What was missing is that nobody could see it, so it is stated here
        # and rendered on the panel. Only shown when the tenant's zone actually observes
        # it; telling a school in Douala about clock changes would be noise.
        "dst": describe_dst(tz, after=now),
        "idle_ceiling_minutes": policy.idle_ceiling_minutes,
        "idle_ceiling_source": (
            "operator pin" if _env_idle_ceiling_seconds() is not None else policy.source
        ),
        "catch_up_missed": policy.catch_up_missed,
        "next_run_at": upcoming.isoformat() if upcoming else None,
        "next_run_in_seconds": int((upcoming - now).total_seconds()) if upcoming else None,
        "last_run_at": last_run_at.isoformat() if last_run_at else None,
        # The ISO strings above are the wire format the poller reads. These are what the
        # SERVER renders, in the tenant's own zone -- without them the no-JavaScript path
        # shows a reader "2026-08-21T14:22:00+00:00", which is a machine's answer to a
        # person's question.
        "next_run_display": _local_display(upcoming, tz),
        "last_run_display": _local_display(last_run_at, tz),
        "missed_window": stale,
        "idle_ceiling_seconds": idle_ceiling_seconds(school),
        # Said in the payload rather than only in a template, so every surface that reads
        # this tells the same truth: the cloud cannot push, so a change lands on the next
        # cycle.
        "propagation_note": (
            "Schedule changes reach the box on its next sync — the cloud cannot contact "
            "a box directly."
        ),
        # OPT-IN, because it is the one expensive field here. The status endpoint is
        # polled every few seconds by every open Sync Center; the strip changes only when
        # a rule does, so the page render asks for it and the poll does not.
        "coverage": (
            coverage_for(school, now=now, rules=rules) if include_coverage else None
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
