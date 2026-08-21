"""Acceptance criteria 1-8: the evaluator. Pure, so these need no database and no clock.

The sharpest test in this file is ``test_the_same_rules_fire_at_different_instants_in_
different_timezones``. It is the tenant-wide proof: a schedule that only works because the
server happens to sit in the same zone as one school is not a feature, it is a coincidence
that will be discovered by the second customer.
"""
from __future__ import annotations

import datetime as _dt
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from apps.sync_engine.schedule import (
    MODE_AT_TIMES,
    MODE_INTERVAL,
    Rule,
    describe_rule,
    is_within_window,
    next_run_at,
)

WEEKDAYS = frozenset({0, 1, 2, 3, 4})
ALL_DAYS = frozenset(range(7))
DOUALA = ZoneInfo("Africa/Douala")  # UTC+1, no DST — the actual tenant
LONDON = ZoneInfo("Europe/London")  # has DST, for the transition tests
NEW_YORK = ZoneInfo("America/New_York")


def _at(tz, y, m, d, hh, mm=0):
    return _dt.datetime(y, m, d, hh, mm, tzinfo=tz)


def _office_hours(**over):
    base = dict(
        mode=MODE_INTERVAL,
        days=WEEKDAYS,
        window_start=_dt.time(7, 0),
        window_end=_dt.time(18, 0),
        interval_minutes=30,
    )
    base.update(over)
    return Rule(**base)


class IntervalRuleTests(SimpleTestCase):
    def test_1_inside_a_window_returns_the_next_boundary_not_now(self):
        """A scheduler that returns `now` runs forever; a display that shows it is a lie."""
        rule = _office_hours()
        # Thursday 2026-08-20, 09:05 local.
        got = next_run_at([rule], after=_at(DOUALA, 2026, 8, 20, 9, 5), tz=DOUALA)
        self.assertEqual(got, _at(DOUALA, 2026, 8, 20, 9, 30))

    def test_before_the_window_opens_returns_the_opening(self):
        got = next_run_at([_office_hours()], after=_at(DOUALA, 2026, 8, 20, 5, 0), tz=DOUALA)
        self.assertEqual(got, _at(DOUALA, 2026, 8, 20, 7, 0))

    def test_after_the_window_closes_rolls_to_the_next_selected_day(self):
        # Friday 19:00 -> Monday 07:00, because Sat/Sun are not selected.
        got = next_run_at([_office_hours()], after=_at(DOUALA, 2026, 8, 21, 19, 0), tz=DOUALA)
        self.assertEqual(got, _at(DOUALA, 2026, 8, 24, 7, 0))
        self.assertEqual(got.astimezone(DOUALA).weekday(), 0)

    def test_2_a_day_that_is_not_selected_never_fires_even_at_the_exact_time(self):
        """The "days_of_week stored but not evaluated" defect, asserted directly."""
        monday_only = _office_hours(days=frozenset({0}))
        # Tuesday 08:59:59 -> must NOT be Tuesday 09:00.
        got = next_run_at([monday_only], after=_at(DOUALA, 2026, 8, 18, 8, 59), tz=DOUALA)
        self.assertEqual(got.astimezone(DOUALA).weekday(), 0)
        self.assertEqual(got, _at(DOUALA, 2026, 8, 24, 7, 0))

    def test_the_boundary_is_strict_so_a_run_does_not_reschedule_itself(self):
        """`after` is exclusive. If it were inclusive the scheduler would loop."""
        exact = _at(DOUALA, 2026, 8, 20, 9, 30)
        self.assertEqual(next_run_at([_office_hours()], after=exact, tz=DOUALA),
                         _at(DOUALA, 2026, 8, 20, 10, 0))

    def test_the_window_end_itself_is_a_valid_firing_moment(self):
        got = next_run_at([_office_hours()], after=_at(DOUALA, 2026, 8, 20, 17, 35), tz=DOUALA)
        self.assertEqual(got, _at(DOUALA, 2026, 8, 20, 18, 0))


class MidnightCrossingTests(SimpleTestCase):
    def test_4_a_window_crossing_midnight_is_one_window_not_zero(self):
        """22:00-02:00 is the overnight backup window. It must not silently never fire."""
        overnight = Rule(
            mode=MODE_INTERVAL,
            days=ALL_DAYS,
            window_start=_dt.time(22, 0),
            window_end=_dt.time(2, 0),
            interval_minutes=60,
        )
        # 23:30 -> 00:00 the next day, INSIDE the same window.
        got = next_run_at([overnight], after=_at(DOUALA, 2026, 8, 20, 23, 30), tz=DOUALA)
        self.assertEqual(got, _at(DOUALA, 2026, 8, 21, 0, 0))

    def test_the_tail_of_an_overnight_window_still_fires_after_midnight(self):
        overnight = Rule(
            mode=MODE_INTERVAL,
            days=ALL_DAYS,
            window_start=_dt.time(22, 0),
            window_end=_dt.time(2, 0),
            interval_minutes=60,
        )
        got = next_run_at([overnight], after=_at(DOUALA, 2026, 8, 21, 0, 30), tz=DOUALA)
        self.assertEqual(got, _at(DOUALA, 2026, 8, 21, 1, 0))

    def test_an_overnight_window_belongs_to_the_day_it_OPENS_on(self):
        """A Friday-only overnight window runs into Saturday morning — that is the point."""
        friday_night = Rule(
            mode=MODE_INTERVAL,
            days=frozenset({4}),
            window_start=_dt.time(23, 0),
            window_end=_dt.time(1, 0),
            interval_minutes=60,
        )
        got = next_run_at([friday_night], after=_at(DOUALA, 2026, 8, 21, 23, 30), tz=DOUALA)
        self.assertEqual(got, _at(DOUALA, 2026, 8, 22, 0, 0))
        self.assertEqual(got.astimezone(DOUALA).weekday(), 5)


class MultipleRuleTests(SimpleTestCase):
    def test_3_overlapping_rules_return_the_EARLIER_run_not_the_first_declared(self):
        """Declaration order must never decide behaviour."""
        late = Rule(mode=MODE_AT_TIMES, days=ALL_DAYS, times=(_dt.time(22, 0),))
        early = Rule(mode=MODE_AT_TIMES, days=ALL_DAYS, times=(_dt.time(6, 0),))
        after = _at(DOUALA, 2026, 8, 20, 3, 0)
        self.assertEqual(next_run_at([late, early], after=after, tz=DOUALA),
                         _at(DOUALA, 2026, 8, 20, 6, 0))
        # Same answer with the list reversed.
        self.assertEqual(next_run_at([early, late], after=after, tz=DOUALA),
                         _at(DOUALA, 2026, 8, 20, 6, 0))

    def test_a_term_time_rule_and_a_nightly_rule_coexist(self):
        rules = [_office_hours(), Rule(mode=MODE_AT_TIMES, days=ALL_DAYS, times=(_dt.time(22, 0),))]
        # Saturday: office hours do not apply, the nightly one does.
        got = next_run_at(rules, after=_at(DOUALA, 2026, 8, 22, 12, 0), tz=DOUALA)
        self.assertEqual(got, _at(DOUALA, 2026, 8, 22, 22, 0))


class DstTests(SimpleTestCase):
    """Decided and documented in the module docstring; asserted here in both directions."""

    def test_5_spring_forward_a_skipped_wall_time_still_fires(self):
        """2026-03-29, Europe/London: 01:00 GMT jumps to 02:00 BST. 01:30 never happens."""
        rule = Rule(mode=MODE_AT_TIMES, days=ALL_DAYS, times=(_dt.time(1, 30),))
        got = next_run_at([rule], after=_at(LONDON, 2026, 3, 29, 0, 30), tz=LONDON)
        self.assertIsNotNone(got, "a skipped wall time must not drop the run entirely")
        local = got.astimezone(LONDON)
        self.assertEqual(local.date(), _dt.date(2026, 3, 29))
        # It fires at the first instant that exists, i.e. after the jump — never before it.
        self.assertGreaterEqual(local.hour, 2)

    def test_6_fall_back_a_repeated_wall_time_fires_once_not_twice(self):
        """2026-10-25, Europe/London: 02:00 BST returns to 01:00 GMT, so 01:30 happens twice."""
        rule = Rule(mode=MODE_AT_TIMES, days=ALL_DAYS, times=(_dt.time(1, 30),))
        first = next_run_at([rule], after=_at(LONDON, 2026, 10, 25, 0, 0), tz=LONDON)
        self.assertIsNotNone(first)
        # The NEXT run after that one must be the following day, not the repeat of 01:30.
        second = next_run_at([rule], after=first, tz=LONDON)
        self.assertEqual(second.astimezone(LONDON).date(), _dt.date(2026, 10, 26))

    def test_an_interval_window_spanning_the_spring_gap_produces_ordered_instants(self):
        rule = Rule(
            mode=MODE_INTERVAL,
            days=ALL_DAYS,
            window_start=_dt.time(0, 0),
            window_end=_dt.time(4, 0),
            interval_minutes=30,
        )
        moments = []
        cursor = _at(LONDON, 2026, 3, 29, 0, 0) - _dt.timedelta(minutes=1)
        for _ in range(8):
            cursor = next_run_at([rule], after=cursor, tz=LONDON)
            self.assertIsNotNone(cursor)
            moments.append(cursor)
        self.assertEqual(moments, sorted(moments), "instants must be strictly ordered")
        self.assertEqual(len(set(moments)), len(moments), "no instant may repeat")


class TenantTimezoneTests(SimpleTestCase):
    def test_8_the_same_rules_fire_at_different_instants_in_different_timezones(self):
        """THE TENANT-WIDE PROOF. 06:00 means six in the morning WHERE THE SCHOOL IS."""
        rule = Rule(mode=MODE_AT_TIMES, days=ALL_DAYS, times=(_dt.time(6, 0),))
        after = _dt.datetime(2026, 8, 20, 0, 0, tzinfo=_dt.timezone.utc)

        douala = next_run_at([rule], after=after, tz=DOUALA)
        new_york = next_run_at([rule], after=after, tz=NEW_YORK)

        self.assertNotEqual(douala, new_york)
        self.assertEqual(douala.astimezone(DOUALA).hour, 6)
        self.assertEqual(new_york.astimezone(NEW_YORK).hour, 6)
        # Douala is UTC+1, New York is UTC-4 in August: 9 hours apart, and Douala first.
        self.assertLess(douala, new_york)

    def test_a_naive_after_is_refused_rather_than_guessed(self):
        """Guessing a zone here is how a schedule silently shifts by hours."""
        with self.assertRaises(ValueError):
            next_run_at([_office_hours()], after=_dt.datetime(2026, 8, 20, 9, 0), tz=DOUALA)


class FallbackTests(SimpleTestCase):
    def test_7_no_usable_rules_returns_None_and_the_caller_falls_back(self):
        """None means "use the adaptive cadence", never "never sync"."""
        self.assertIsNone(next_run_at([], after=_at(DOUALA, 2026, 8, 20, 9, 0), tz=DOUALA))

    def test_a_rule_with_no_days_selected_is_not_usable(self):
        """It can never fire, so it must not mask a working rule or look scheduled."""
        empty = _office_hours(days=frozenset())
        self.assertIsNone(next_run_at([empty], after=_at(DOUALA, 2026, 8, 20, 9, 0), tz=DOUALA))

    def test_an_incomplete_interval_rule_does_not_crash_the_evaluator(self):
        broken = Rule(mode=MODE_INTERVAL, days=ALL_DAYS, window_start=None,
                      window_end=None, interval_minutes=None)
        self.assertIsNone(next_run_at([broken], after=_at(DOUALA, 2026, 8, 20, 9, 0), tz=DOUALA))

    def test_a_window_whose_end_equals_its_start_is_treated_as_overnight_not_empty(self):
        """Ambiguous input must resolve to the reading a human meant, or to nothing —
        never to a rule that fires once per millisecond."""
        rule = Rule(mode=MODE_INTERVAL, days=ALL_DAYS, window_start=_dt.time(9, 0),
                    window_end=_dt.time(9, 0), interval_minutes=60)
        got = next_run_at([rule], after=_at(DOUALA, 2026, 8, 20, 10, 0), tz=DOUALA)
        self.assertIsNotNone(got)
        self.assertGreater(got, _at(DOUALA, 2026, 8, 20, 10, 0))


class WithinWindowTests(SimpleTestCase):
    def test_inside_office_hours_is_within_the_window(self):
        self.assertTrue(is_within_window([_office_hours()], at=_at(DOUALA, 2026, 8, 20, 9, 5), tz=DOUALA))

    def test_outside_office_hours_is_not(self):
        self.assertFalse(is_within_window([_office_hours()], at=_at(DOUALA, 2026, 8, 20, 21, 0), tz=DOUALA))

    def test_a_weekend_is_not_inside_a_weekday_window(self):
        self.assertFalse(is_within_window([_office_hours()], at=_at(DOUALA, 2026, 8, 22, 9, 0), tz=DOUALA))

    def test_the_tail_of_an_overnight_window_counts_as_inside(self):
        overnight = Rule(mode=MODE_INTERVAL, days=ALL_DAYS, window_start=_dt.time(22, 0),
                         window_end=_dt.time(2, 0), interval_minutes=60)
        self.assertTrue(is_within_window([overnight], at=_at(DOUALA, 2026, 8, 21, 1, 0), tz=DOUALA))

    def test_at_times_rules_have_no_window(self):
        nightly = Rule(mode=MODE_AT_TIMES, days=ALL_DAYS, times=(_dt.time(22, 0),))
        self.assertFalse(is_within_window([nightly], at=_at(DOUALA, 2026, 8, 20, 22, 0), tz=DOUALA))


class DescriptionTests(SimpleTestCase):
    """A school administrator must be able to read the rule back. Never a cron string."""

    def test_office_hours_reads_like_english(self):
        self.assertEqual(
            describe_rule(_office_hours()),
            "Every 30 minutes, 7:00 AM to 6:00 PM, Monday to Friday.",
        )

    def test_an_hourly_interval_is_not_called_every_60_minutes(self):
        self.assertIn("every hour", describe_rule(_office_hours(interval_minutes=60)).lower())

    def test_at_times_reads_like_english(self):
        rule = Rule(mode=MODE_AT_TIMES, days=ALL_DAYS, times=(_dt.time(6, 0), _dt.time(22, 0)))
        self.assertEqual(describe_rule(rule), "At 6:00 AM and 10:00 PM, every day.")

    def test_weekends_are_named_not_enumerated(self):
        rule = Rule(mode=MODE_AT_TIMES, days=frozenset({5, 6}), times=(_dt.time(8, 0),))
        self.assertIn("weekends", describe_rule(rule))

    def test_the_description_never_contains_a_cron_expression_or_raw_weekday_numbers(self):
        text = describe_rule(_office_hours(days=frozenset({0, 2, 4})))
        self.assertNotIn("*", text)
        self.assertIn("Monday, Wednesday and Friday", text)

    def test_midnight_and_noon_are_not_rendered_as_zero_oclock(self):
        rule = Rule(mode=MODE_AT_TIMES, days=ALL_DAYS, times=(_dt.time(0, 0), _dt.time(12, 0)))
        text = describe_rule(rule)
        self.assertIn("12:00 AM", text)
        self.assertIn("12:00 PM", text)
