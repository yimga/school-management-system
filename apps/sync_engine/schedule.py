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
