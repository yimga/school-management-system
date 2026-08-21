"""When should this box sync? One evaluator, used by the scheduler AND the screen.

WHY THIS MODULE IS PURE. The Sync Center tells a school administrator "Next sync: today
at 6:00 PM". That sentence is a promise, and a promise computed by different code than
the one that keeps it will drift — at which point the label is worse than no label,
because the person is planning around it. So :func:`next_run_at` is a pure, timezone-aware
function with no I/O, no cache and no request: the scheduler calls it to decide, the status
endpoint calls it to display, and a test can call it directly with a frozen clock.

WHY WINDOWS AND NOT CRON. The person configuring this runs a school. ``0 */2 7-18 * * 1-5``
is not a thing they should ever see, and a UI that accepts it will be filled in wrong. The
model is two shapes a human can read back to you:

  * ``INTERVAL`` — "every 30 minutes, 07:00 to 18:00, Monday to Friday"
  * ``AT_TIMES``  — "at 06:00 and 22:00, every day"

Both are the same object with a different mode, and a tenant may hold several (term time
and holidays are two rules, not two products).

WHY LOCAL WALL-CLOCK TIME. "06:00" means six in the morning where the school is. Rules
therefore store ``time`` values and a weekday set, and are resolved against the tenant's
timezone at evaluation time — never stored as UTC instants, which would silently shift by
an hour twice a year.

DST, decided and documented rather than left to chance:

  * **Spring forward.** A rule at a wall-clock time the day skips (02:30, where the clock
    jumps 02:00 → 03:00) still fires: at the instant that wall time WOULD have denoted,
    which lands just the other side of the gap (02:30 EST is 03:30 EDT — the same absolute
    moment, renamed by the clock). It is never dropped, and it never drifts by more than
    the gap: a nightly report that silently skipped one night a year would be blamed on
    anything but the clock.
  * **Fall back.** A rule inside the hour the clock repeats fires ONCE, on the first
    occurrence. Firing twice would double a nightly job with no way for the operator to
    tell why.

Both are asserted by tests, in both directions.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

# Monday=0 .. Sunday=6, matching ``datetime.date.weekday()`` so no translation layer can
# get the offset wrong. The names are for display only; the wire format is the integer.
WEEKDAYS: tuple[tuple[int, str], ...] = (
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
    (6, "Sunday"),
)
WEEKDAY_NAMES = dict(WEEKDAYS)

MODE_INTERVAL = "INTERVAL"
MODE_AT_TIMES = "AT_TIMES"

# The floor exists so a mis-typed "1" cannot turn a school's box into a request loop
# against the cloud. Five minutes is already far faster than any human notices.
MIN_INTERVAL_MINUTES = 5
MAX_INTERVAL_MINUTES = 24 * 60

# A weekly rule needs at most 8 days of look-ahead; the 9th covers a window that opened on
# the previous local day and runs past midnight. Bounded on purpose — an unbounded search
# over a rule that can never fire is an infinite loop in a request thread.
_SEARCH_DAYS = 9


@dataclass(frozen=True)
class Rule:
    """One schedule rule, detached from the ORM so the evaluator stays pure.

    ``days`` is a frozenset of ``date.weekday()`` values. ``times`` is used by
    ``AT_TIMES``; ``window_start`` / ``window_end`` / ``interval_minutes`` by ``INTERVAL``.
    """

    mode: str
    days: frozenset
    window_start: _dt.time | None = None
    window_end: _dt.time | None = None
    interval_minutes: int | None = None
    times: tuple = ()
    label: str = ""

    @property
    def crosses_midnight(self) -> bool:
        """A 22:00–02:00 window is ONE window, not zero.

        Without this an overnight rule silently never fires, which is the exact shape of
        bug that makes people stop trusting a scheduler.
        """
        if self.mode != MODE_INTERVAL or not self.window_start or not self.window_end:
            return False
        return self.window_end <= self.window_start


def _resolve_local(tz, naive: _dt.datetime) -> _dt.datetime:
    """Turn a local wall-clock datetime into a real instant, DST included.

    Round-tripping through UTC is what detects a spring-forward gap: a wall time the day
    never showed comes back as a DIFFERENT wall time, and that returned value is the
    instant the original wall time denoted under the pre-transition offset — 02:30 EST
    resolves to 07:30 UTC, which is 03:30 EDT. So the run keeps its absolute moment and
    lands just past the gap rather than being dropped. ``fold=0`` picks the first of an
    ambiguous fall-back pair.
    """
    aware = naive.replace(tzinfo=tz, fold=0)
    roundtrip = aware.astimezone(_dt.timezone.utc).astimezone(tz).replace(tzinfo=None)
    if roundtrip != naive:
        # Nonexistent local time (spring forward). Fire at the first instant that exists
        # rather than dropping the run.
        return roundtrip.replace(tzinfo=tz, fold=0)
    return aware


def _interval_occurrences(rule: Rule, day: _dt.date, tz) -> list:
    """Every firing instant of an INTERVAL rule for the window that OPENS on ``day``."""
    if not rule.window_start or not rule.window_end or not rule.interval_minutes:
        return []
    step = max(MIN_INTERVAL_MINUTES, int(rule.interval_minutes))
    start_naive = _dt.datetime.combine(day, rule.window_start)
    end_day = day + _dt.timedelta(days=1) if rule.crosses_midnight else day
    end_naive = _dt.datetime.combine(end_day, rule.window_end)
    if end_naive <= start_naive:
        return []

    out = []
    cursor = start_naive
    # Bounded by construction: cursor advances by >= MIN_INTERVAL_MINUTES each pass and
    # end_naive is at most 24h away, so this cannot spin.
    while cursor <= end_naive:
        out.append(_resolve_local(tz, cursor))
        cursor += _dt.timedelta(minutes=step)
    return out


def _at_times_occurrences(rule: Rule, day: _dt.date, tz) -> list:
    return [_resolve_local(tz, _dt.datetime.combine(day, t)) for t in rule.times]


def next_run_at(rules, *, after: _dt.datetime, tz, now: _dt.datetime | None = None):
    """The next instant any rule fires, strictly after ``after``. ``None`` if nothing can.

    ``None`` means "no rule is enabled" and callers MUST read it as "fall back to the
    adaptive cadence", never as "never sync". A box that stops checking in cannot be told
    anything — not even to start again.

    ``after`` must be timezone-aware. ``tz`` is the TENANT's zone, not the server's.
    """
    del now  # accepted for call-site symmetry; the decision only depends on `after`
    if after.tzinfo is None:
        raise ValueError("next_run_at requires an aware `after` datetime")

    usable = [r for r in rules if r.days and r.mode in (MODE_INTERVAL, MODE_AT_TIMES)]
    if not usable:
        return None

    local_after = after.astimezone(tz)
    # Start one day BEFORE, so a window that opened yesterday and runs past midnight is
    # still considered. Dropping it would make every overnight rule miss its tail.
    first_day = local_after.date() - _dt.timedelta(days=1)

    best = None
    for offset in range(_SEARCH_DAYS):
        day = first_day + _dt.timedelta(days=offset)
        for rule in usable:
            if day.weekday() not in rule.days:
                continue
            if rule.mode == MODE_INTERVAL:
                candidates = _interval_occurrences(rule, day, tz)
            else:
                candidates = _at_times_occurrences(rule, day, tz)
            for moment in candidates:
                if moment > after and (best is None or moment < best):
                    best = moment
        # Once a day has produced a hit, a LATER day can only be later — but the same day
        # may still hold an earlier one from another rule, so finish the day first.
        if best is not None and best.astimezone(tz).date() <= day:
            break
    return best


def is_within_window(rules, *, at: _dt.datetime, tz) -> bool:
    """True when ``at`` falls inside an INTERVAL rule's active window.

    Distinct from :func:`next_run_at` because the two answer different questions: this one
    decides how HARD to run right now, which is what the cadence layer needs in order to
    tell "the tenant wants frequent syncing at this hour" apart from "the next scheduled
    moment happens to be soon".
    """
    if at.tzinfo is None:
        raise ValueError("is_within_window requires an aware datetime")
    local = at.astimezone(tz)
    for rule in rules:
        if rule.mode != MODE_INTERVAL or not rule.days:
            continue
        if not rule.window_start or not rule.window_end:
            continue
        for day_offset in (-1, 0):
            day = local.date() + _dt.timedelta(days=day_offset)
            if day.weekday() not in rule.days:
                continue
            start = _resolve_local(tz, _dt.datetime.combine(day, rule.window_start))
            end_day = day + _dt.timedelta(days=1) if rule.crosses_midnight else day
            end = _resolve_local(tz, _dt.datetime.combine(end_day, rule.window_end))
            if start <= at <= end:
                return True
    return False


# ------------------------------------------------------------------ description --
def _format_time(value: _dt.time) -> str:
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    return f"{hour}:{value.minute:02d} {suffix}"


def _format_days(days) -> str:
    """"Monday–Friday", "Every day", "Monday, Wednesday and Friday" — never "0,2,4"."""
    ordered = sorted(days)
    if not ordered:
        return "no days"
    if len(ordered) == 7:
        return "every day"
    if ordered == [0, 1, 2, 3, 4]:
        return "Monday to Friday"
    if ordered == [5, 6]:
        return "weekends"
    names = [WEEKDAY_NAMES[d] for d in ordered]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _format_interval(minutes: int) -> str:
    minutes = int(minutes)
    if minutes % 60 == 0 and minutes >= 60:
        hours = minutes // 60
        return "every hour" if hours == 1 else f"every {hours} hours"
    return f"every {minutes} minutes"


def describe_rule(rule: Rule) -> str:
    """One sentence a school administrator can check against what they meant."""
    days = _format_days(rule.days)
    if rule.mode == MODE_AT_TIMES:
        times = [_format_time(t) for t in rule.times]
        if not times:
            return f"No times set, {days}."
        joined = times[0] if len(times) == 1 else ", ".join(times[:-1]) + " and " + times[-1]
        return f"At {joined}, {days}."
    if not (rule.window_start and rule.window_end and rule.interval_minutes):
        return f"Incomplete schedule, {days}."
    window = f"{_format_time(rule.window_start)} to {_format_time(rule.window_end)}"
    return f"{_format_interval(rule.interval_minutes).capitalize()}, {window}, {days}."


def describe(rules) -> str:
    parts = [describe_rule(r) for r in rules]
    return " ".join(parts) if parts else ""


# ------------------------------------------------------------------------- DST --
# The behaviour was already decided and asserted (see the module docstring). What was
# missing is that nobody could SEE it: a school administrator setting "02:30 every day"
# had no way to learn that one night a year that time does not exist. Offering a switch
# would be worse than useless -- there is one defensible answer in each direction -- so
# this makes the decision visible rather than configurable.
_DST_SEARCH_DAYS = 400  # magic-number-allow: just over a year, to always find the next one


def next_dst_transition(tz, *, after: _dt.datetime):
    """The next UTC-offset change for ``tz``, or ``None`` if the zone has no DST.

    Day-stepped to find the day, then hour-stepped inside it, so the cost is bounded and
    tiny (<= 400 + 24 offset lookups) and it is safe to call on a page render.
    """
    if after.tzinfo is None:
        raise ValueError("next_dst_transition requires an aware `after` datetime")

    def offset_at(moment: _dt.datetime):
        return moment.astimezone(tz).utcoffset()

    cursor = after
    previous = offset_at(cursor)
    for _ in range(_DST_SEARCH_DAYS):
        following = cursor + _dt.timedelta(days=1)
        current = offset_at(following)
        if current != previous:
            # Narrow to the hour inside the day we just crossed.
            lo = cursor
            for _hour in range(25):
                probe = lo + _dt.timedelta(hours=1)
                if offset_at(probe) != previous:
                    return {
                        "at": probe,
                        "shift_minutes": int(
                            (current - previous).total_seconds() // 60
                        ),
                        "direction": "forward" if current > previous else "back",
                    }
                lo = probe
            return {
                "at": following,
                "shift_minutes": int((current - previous).total_seconds() // 60),
                "direction": "forward" if current > previous else "back",
            }
        cursor = following
    return None


def describe_dst(tz, *, after: _dt.datetime) -> dict:
    """What the Sync Center says about the clock changing. Always safe to call."""
    try:
        transition = next_dst_transition(tz, after=after)
    except Exception:  # noqa: BLE001 — a status panel must never fail on a timezone
        return {"observes": False, "note": ""}
    if transition is None:
        return {"observes": False, "note": ""}

    local = transition["at"].astimezone(tz)
    # Built by hand rather than with "%-d": that directive is glibc-only and raises on
    # Windows, where this very code runs during development.
    when = f"{local.day} {local.strftime('%B')} {local.year}"
    if transition["direction"] == "forward":
        note = (
            f"The clocks go forward on {when}. A scheduled time the clock skips that "
            "morning still runs, just after the change — nothing is missed."
        )
    else:
        note = (
            f"The clocks go back on {when}. A scheduled time inside the hour that repeats "
            "runs once, not twice."
        )
    return {
        "observes": True,
        "at": transition["at"].isoformat(),
        "direction": transition["direction"],
        "note": note,
    }


# ----------------------------------------------------------------- week plan --
# What the Sync Center draws. The panel used to render one SENTENCE ("every 30 minutes,
# 06:00 to 18:00, Monday to Friday. At 22:00, every day.") and nothing else, so a school
# could not see that those two rules leave Sunday with a fourteen-hour hole, that they
# overlap at 18:00, or that the idle check-in is doing most of the real work.
#
# WHY IT LIVES HERE AND NOT IN JAVASCRIPT. This module's first paragraph is the reason:
# the promise on the screen and the moment the scheduler acts have to be the SAME
# computation. A strip drawn by a re-implementation in the browser would drift from the
# engine the first time either changed, and it would drift SILENTLY -- the picture would
# still look plausible. So the browser draws exactly what this returns and computes no
# occurrence of its own; the live preview while editing posts a candidate rule set back
# here and renders the answer.
#
# HOURLY BUCKETS, NOT RAW INSTANTS, is a bound rather than a simplification: a 5-minute
# rule over a full week is 2016 instants, and this is built on a page render. 7 x 24
# cells is 168 regardless of interval, and an hour is already finer than the strip can
# draw.
_WEEK_PLAN_DAYS = 7  # magic-number-allow: one week, the period of every rule shape here
_HOURS_PER_DAY = 24  # magic-number-allow: hours in a day
_STRIP_LEVELS = 4  # magic-number-allow: intensity steps the strip can render
_MINUTES_PER_HOUR = 60  # magic-number-allow: minutes in an hour


def _bucket_day_span(rules, day: _dt.date, tz) -> list:
    """Every occurrence produced by a window OPENING on ``day``, with its rule index."""
    out = []
    for index, rule in enumerate(rules):
        if not rule.days or day.weekday() not in rule.days:
            continue
        if rule.mode == MODE_INTERVAL:
            moments = _interval_occurrences(rule, day, tz)
        elif rule.mode == MODE_AT_TIMES:
            moments = _at_times_occurrences(rule, day, tz)
        else:
            continue
        for moment in moments:
            out.append((moment, index))
    return out


def week_plan(rules, *, start, tz, days: int = _WEEK_PLAN_DAYS) -> dict:
    """Hour-by-hour coverage for ``days`` local days beginning with ``start``'s day.

    Returns a structure the panel renders directly::

        {
          "days": [
            {"date": "2026-08-21", "weekday": 4, "label": "Friday",
             "hours": [{"count": 2, "rules": [0, 1], "first": "06:00"}, ... 24 ]},
            ...
          ],
          "total": 134,
          "rule_count": 2,
        }

    ``rules`` is positional-indexed: ``hours[h]["rules"]`` holds the INDEX of each rule
    that fires in that hour, so the caller can colour a cell without this module needing
    to know anything about names, colours or the ORM.

    Occurrences are bucketed by the local date they LAND on, not the date whose window
    produced them -- a 22:00-02:00 rule shows up in both Tuesday's late hours and
    Wednesday's early ones, which is what it actually does. That is also why the scan
    starts a day early.

    Pure and bounded: at most ``days + 1`` day-spans are expanded and each is bounded by
    :func:`_interval_occurrences`. Safe on a page render.
    """
    if start.tzinfo is None:
        raise ValueError("week_plan requires an aware `start` datetime")
    usable = [r for r in rules if r.mode in (MODE_INTERVAL, MODE_AT_TIMES)]

    first_day = start.astimezone(tz).date()
    wanted = [first_day + _dt.timedelta(days=offset) for offset in range(days)]
    index_of = {day: position for position, day in enumerate(wanted)}

    # `level` is `count` clamped to the strip's four intensity steps. It is computed
    # here because a Django template cannot call min(), and a strip that reads its own
    # shading from a raw count would go uniformly solid the moment a rule ran every five
    # minutes -- losing exactly the overlap the strip exists to show.
    grid = [
        [
            {"count": 0, "level": 0, "rules": [], "first": None, "in_gap": False}
            for _ in range(_HOURS_PER_DAY)
        ]
        for _ in wanted
    ]
    total = 0

    # One day EARLIER than the window, so a rule whose window opened yesterday and runs
    # past midnight still fills today's early hours instead of leaving a phantom gap.
    for offset in range(-1, days):
        span_day = first_day + _dt.timedelta(days=offset)
        for moment, rule_index in _bucket_day_span(usable, span_day, tz):
            local = moment.astimezone(tz)
            position = index_of.get(local.date())
            if position is None:
                continue
            cell = grid[position][local.hour]
            cell["count"] += 1
            if rule_index not in cell["rules"]:
                cell["rules"].append(rule_index)
            if cell["first"] is None or local.strftime("%H:%M") < cell["first"]:
                cell["first"] = local.strftime("%H:%M")
            cell["level"] = min(_STRIP_LEVELS, cell["count"])
            total += 1

    return {
        "days": [
            {
                "date": day.isoformat(),
                "weekday": day.weekday(),
                "label": WEEKDAY_NAMES[day.weekday()],
                "hours": grid[position],
            }
            for position, day in enumerate(wanted)
        ],
        "total": total,
        "rule_count": len(usable),
    }


def longest_gap(rules, *, start, tz, days: int = _WEEK_PLAN_DAYS) -> dict:
    """The longest stretch with no scheduled sync at all, over ``days`` from ``start``.

    This is the number the audit question reduces to. Every rule shape here repeats
    weekly, so a scan of one full week plus the WRAP (from the last occurrence of the
    week back round to the first) is the true periodic answer rather than an artefact of
    where the window happened to be cut.

    ``{"minutes": None, "unbounded": True}`` means no rule fires at all in the window --
    the honest answer, and distinct from "the gap is seven days", because with no rules
    the box falls back to the adaptive cadence rather than going silent.
    """
    if start.tzinfo is None:
        raise ValueError("longest_gap requires an aware `start` datetime")
    usable = [r for r in rules if r.days and r.mode in (MODE_INTERVAL, MODE_AT_TIMES)]

    first_day = start.astimezone(tz).date()
    window_start = _resolve_local(tz, _dt.datetime.combine(first_day, _dt.time.min))
    window_end = window_start + _dt.timedelta(days=days)

    moments = []
    for offset in range(-1, days + 1):
        span_day = first_day + _dt.timedelta(days=offset)
        for moment, _index in _bucket_day_span(usable, span_day, tz):
            if window_start <= moment < window_end:
                moments.append(moment)

    if not moments:
        return {"minutes": None, "unbounded": True, "start": None, "end": None}

    moments.sort()
    best_minutes = -1
    best_pair = (moments[0], moments[0])
    for earlier, later in zip(moments, moments[1:]):
        span = int((later - earlier).total_seconds() // 60)
        if span > best_minutes:
            best_minutes = span
            best_pair = (earlier, later)

    # The wrap. Without it a schedule whose only rule is "Monday 06:00" reports a gap of
    # zero, because it has a single occurrence and no consecutive pair.
    wrap_end = moments[0] + _dt.timedelta(days=days)
    wrap = int((wrap_end - moments[-1]).total_seconds() // 60)
    if wrap > best_minutes:
        best_minutes = wrap
        best_pair = (moments[-1], wrap_end)

    return {
        "minutes": max(0, best_minutes),
        "unbounded": False,
        "start": best_pair[0].isoformat(),
        "end": best_pair[1].isoformat(),
    }


# The panel shows FIVE upcoming syncs, not one. A single "next sync" answers "is it
# armed"; five answer "is it armed CORRECTLY" -- a rule that fires at 06:00 and then not
# again until Monday is indistinguishable from a healthy one until you can see the second
# entry. Five is also the point where a strip and a list start saying the same thing.
_DEFAULT_NEXT_RUNS = 5  # magic-number-allow: how many upcoming syncs the panel lists


def next_runs(rules, *, after, tz, count: int = _DEFAULT_NEXT_RUNS) -> list:
    """The next ``count`` firing instants, ascending, each with the rule that owns it.

    Built by walking :func:`next_run_at` forward rather than by re-deriving occurrences,
    so the list and the scheduler's own decision cannot disagree even by one entry.
    Bounded: it stops at ``count``, and at the first moment the walk stops advancing.
    """
    if after.tzinfo is None:
        raise ValueError("next_runs requires an aware `after` datetime")
    usable = [r for r in rules if r.days and r.mode in (MODE_INTERVAL, MODE_AT_TIMES)]
    out: list = []
    cursor = after
    for _ in range(max(0, int(count))):
        moment = next_run_at(usable, after=cursor, tz=tz)
        if moment is None or moment <= cursor:
            break
        # Which rule owns this instant. A moment can belong to more than one rule; the
        # first match is enough for a label, and the strip shows the overlap properly.
        owner = ""
        local_day = moment.astimezone(tz).date()
        for rule in usable:
            for day in (local_day - _dt.timedelta(days=1), local_day):
                if day.weekday() not in rule.days:
                    continue
                candidates = (
                    _interval_occurrences(rule, day, tz)
                    if rule.mode == MODE_INTERVAL
                    else _at_times_occurrences(rule, day, tz)
                )
                if moment in candidates:
                    owner = rule.label
                    break
            if owner:
                break
        # `at` is the wire format the browser re-formats; `display` is what the SERVER
        # renders, so the no-JavaScript path reads a time rather than an ISO string.
        # "%a" and "%H:%M" only -- "%-d" is glibc-only and raises on Windows.
        local = moment.astimezone(tz)
        out.append(
            {
                "at": moment.isoformat(),
                "display": f"{local.strftime('%a')} {local.strftime('%H:%M')}",
                "label": owner,
            }
        )
        cursor = moment
    return out


def dst_note_for_rule(rule: Rule, tz, *, after: _dt.datetime) -> str:
    """The clock-change note for THIS rule, or ``""`` if it is not affected.

    The page used to carry one DST paragraph for the whole tenant, rendered all year. It
    is only ever true of a rule whose configured wall-clock time falls in the hour the
    clock skips or repeats, and only in the week or so around the change -- so it belongs
    on that rule, where a school reading "At 02:30, every day" can see what happens to
    *that* line, and nowhere else for the other fifty-one weeks.

    Checked against the rule's CONFIGURED wall-clock values rather than its resolved
    instants, deliberately: a spring-forward time is resolved past the gap by
    :func:`_resolve_local`, so by the time it is an instant the evidence that it was ever
    inside the gap is gone.
    """
    try:
        transition = next_dst_transition(tz, after=after)
    except Exception:  # noqa: BLE001 -- a display aid must never break a panel
        return ""
    if transition is None:
        return ""

    local = transition["at"].astimezone(tz)
    if local.date().weekday() not in (rule.days or frozenset()):
        return ""

    # The affected wall-clock band: the hour the clock skips (forward) or repeats (back).
    # Derived from the offset delta rather than assumed to be exactly one hour, because
    # not every zone moves by 60 minutes.
    shift_minutes = abs(int(transition.get("shift_minutes") or 0)) or _MINUTES_PER_HOUR
    band_start = local.replace(minute=0, second=0, microsecond=0)
    if transition["direction"] == "forward":
        band_start = band_start - _dt.timedelta(minutes=shift_minutes)
    band_end = band_start + _dt.timedelta(minutes=shift_minutes)

    def _in_band(value: _dt.time) -> bool:
        stamp = _dt.datetime.combine(local.date(), value)
        return band_start.replace(tzinfo=None) <= stamp < band_end.replace(tzinfo=None)

    affected = False
    if rule.mode == MODE_AT_TIMES:
        affected = any(_in_band(t) for t in rule.times)
    elif rule.mode == MODE_INTERVAL and rule.window_start and rule.window_end:
        # A window that merely CONTAINS the band is affected: an interval rule stepping
        # through it will land inside.
        start = _dt.datetime.combine(local.date(), rule.window_start)
        end_day = local.date() + _dt.timedelta(days=1) if rule.crosses_midnight else local.date()
        end = _dt.datetime.combine(end_day, rule.window_end)
        affected = start < band_end.replace(tzinfo=None) and end > band_start.replace(tzinfo=None)

    if not affected:
        return ""

    when = f"{local.day} {local.strftime('%B')} {local.year}"
    if transition["direction"] == "forward":
        return (
            f"The clocks go forward on {when} and this rule's time does not exist that "
            "morning. It still runs, at the same absolute moment, just after the change — "
            "never dropped."
        )
    return (
        f"The clocks go back on {when} and this rule's time happens twice. It runs once, "
        "on the first."
    )
