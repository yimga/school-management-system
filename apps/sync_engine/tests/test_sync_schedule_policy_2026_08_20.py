"""Acceptance criteria 9-11 + catch-up: who wins when the schedule and the cadence disagree.

The precedence table lives in ``schedule_policy``'s module docstring. These tests are what
stop it from being quietly inverted — every row of that table is one test here, and the
two that matter most are the ones that let something OTHER than the tenant's schedule win:
an explicit human action, and a cloud that is down.
"""
from __future__ import annotations

import datetime as _dt
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from apps.sync_engine import cadence, schedule_policy
from apps.sync_engine.schedule import MODE_AT_TIMES, MODE_INTERVAL, Rule

DOUALA = ZoneInfo("Africa/Douala")
WEEKDAYS = frozenset({0, 1, 2, 3, 4})
ALL_DAYS = frozenset(range(7))


class _School:
    """The only two attributes the policy layer reads."""

    def __init__(self, tz="Africa/Douala"):
        self.timezone = tz
        self.pk = 1


def _office_hours(interval=30):
    return Rule(
        mode=MODE_INTERVAL,
        days=WEEKDAYS,
        window_start=_dt.time(7, 0),
        window_end=_dt.time(18, 0),
        interval_minutes=interval,
    )


def _nightly():
    return Rule(mode=MODE_AT_TIMES, days=ALL_DAYS, times=(_dt.time(22, 0),))


def _with_rules(rules, state=cadence.STEADY):
    return (
        mock.patch.object(schedule_policy, "active_rules", return_value=rules),
        mock.patch.object(cadence, "current_state", return_value=state),
    )


class IntervalPrecedenceTests(SimpleTestCase):
    def _interval(self, rules, when, state=cadence.STEADY):
        rules_patch, state_patch = _with_rules(rules, state)
        with rules_patch, state_patch:
            return schedule_policy.interval_for(_School(), now=when)

    def test_inside_a_window_the_tenants_interval_wins(self):
        seconds, reason = self._interval([_office_hours(30)], _dt.datetime(2026, 8, 20, 9, 0, tzinfo=DOUALA))
        self.assertEqual(seconds, 30 * 60)
        self.assertIn("inside a scheduled window", reason)

    def test_10_backoff_wins_even_inside_a_window(self):
        """A schedule is not permission to hammer a cloud that is down."""
        seconds, reason = self._interval(
            [_office_hours(30)],
            _dt.datetime(2026, 8, 20, 9, 0, tzinfo=DOUALA),
            state=cadence.BACKOFF,
        )
        self.assertIsNone(seconds, "backoff must defer to the adaptive cadence")
        self.assertIn("backing off", reason)

    def test_11_outside_every_window_the_interval_is_the_idle_ceiling_never_zero(self):
        """A box that stops checking in cannot be told anything — including to start again."""
        seconds, reason = self._interval(
            [_office_hours(30)], _dt.datetime(2026, 8, 20, 21, 0, tzinfo=DOUALA)
        )
        self.assertIsNotNone(seconds)
        self.assertGreater(seconds, 0)
        self.assertEqual(seconds, schedule_policy.idle_ceiling_seconds())
        self.assertIn("checking in", reason)

    def test_a_soon_scheduled_run_is_waited_for_exactly_not_capped(self):
        """Ten minutes before the window opens, wait ten minutes — not the ceiling."""
        seconds, _ = self._interval(
            [_office_hours(30)], _dt.datetime(2026, 8, 20, 6, 50, tzinfo=DOUALA)
        )
        self.assertEqual(seconds, 10 * 60)

    def test_no_schedule_defers_to_the_adaptive_cadence(self):
        """The zero-configuration path: a tenant who never opens the screen sees no change."""
        seconds, reason = self._interval([], _dt.datetime(2026, 8, 20, 9, 0, tzinfo=DOUALA))
        self.assertIsNone(seconds)
        self.assertIn("automatic cadence", reason)

    def test_overlapping_windows_use_the_SHORTEST_interval_not_the_first(self):
        """Row order must never decide behaviour."""
        slow = _office_hours(120)
        fast = Rule(
            mode=MODE_INTERVAL,
            days=WEEKDAYS,
            window_start=_dt.time(8, 0),
            window_end=_dt.time(10, 0),
            interval_minutes=15,
        )
        at_nine = _dt.datetime(2026, 8, 20, 9, 0, tzinfo=DOUALA)
        self.assertEqual(self._interval([slow, fast], at_nine)[0], 15 * 60)
        self.assertEqual(self._interval([fast, slow], at_nine)[0], 15 * 60)

    def test_an_at_times_rule_alone_produces_a_wait_not_a_window_interval(self):
        seconds, reason = self._interval([_nightly()], _dt.datetime(2026, 8, 20, 21, 55, tzinfo=DOUALA))
        self.assertEqual(seconds, 5 * 60)
        self.assertIn("next scheduled run", reason)

    def test_a_broken_evaluator_degrades_to_the_cadence_instead_of_stopping_sync(self):
        with mock.patch.object(schedule_policy, "active_rules", return_value=[_office_hours()]):
            with mock.patch.object(cadence, "current_state", return_value=cadence.STEADY):
                with mock.patch(
                    "apps.sync_engine.schedule_policy.is_within_window",
                    side_effect=RuntimeError("boom"),
                ):
                    seconds, reason = schedule_policy.interval_for(
                        _School(), now=_dt.datetime(2026, 8, 20, 9, 0, tzinfo=DOUALA)
                    )
        self.assertIsNone(seconds)
        self.assertIn("automatic cadence", reason)


class WakePrecedenceTests(SimpleTestCase):
    def test_9_an_explicit_wake_runs_outside_every_window(self):
        """The operator clicked "Sync now" at 9pm. Making them wait until 7am is the bug.

        Asserted at the layer that actually decides — ``cadence.due_now`` checks the wake
        FIRST, before any next-due marker the schedule armed.
        """
        with mock.patch.object(cadence, "pending_wake", return_value="operator clicked sync now"):
            due, reason = cadence.due_now()
        self.assertTrue(due)
        self.assertIn("wake", reason)

    def test_a_schedule_armed_marker_cannot_suppress_a_wake(self):
        """Belt and braces: even with a far-future marker, the wake short-circuits."""
        far_future = cadence._now() + 86400
        with mock.patch.object(cadence, "_cache_get", return_value=far_future):
            with mock.patch.object(cadence, "pending_wake", return_value="directive queued"):
                due, _ = cadence.due_now()
        self.assertTrue(due)


class IdleCeilingTests(SimpleTestCase):
    def test_the_ceiling_is_configurable(self):
        with mock.patch.dict("os.environ", {"RMC_EDGE_SYNC_IDLE_CEILING_SECONDS": "7200"}):
            self.assertEqual(schedule_policy.idle_ceiling_seconds(), 7200)

    def test_junk_falls_back_to_the_default_rather_than_crashing(self):
        with mock.patch.dict("os.environ", {"RMC_EDGE_SYNC_IDLE_CEILING_SECONDS": "soon"}):
            self.assertEqual(schedule_policy.idle_ceiling_seconds(), 3600)

    def test_the_ceiling_can_never_go_below_the_cadence_floor(self):
        with mock.patch.dict("os.environ", {"RMC_EDGE_SYNC_IDLE_CEILING_SECONDS": "1"}):
            self.assertEqual(schedule_policy.idle_ceiling_seconds(), cadence.MIN_INTERVAL_SECONDS)


class CatchUpTests(SimpleTestCase):
    """Catch up ONCE — a weekend outage produces a Monday sync, not forty-eight."""

    def _missed(self, rules, last_run, now):
        with mock.patch.object(schedule_policy, "active_rules", return_value=rules):
            return schedule_policy.missed_run(_School(), last_run_at=last_run, now=now)

    def test_a_window_slept_through_is_reported(self):
        got = self._missed(
            [_nightly()],
            last_run=_dt.datetime(2026, 8, 19, 20, 0, tzinfo=DOUALA),
            now=_dt.datetime(2026, 8, 20, 8, 0, tzinfo=DOUALA),
        )
        self.assertEqual(got, _dt.datetime(2026, 8, 19, 22, 0, tzinfo=DOUALA))

    def test_a_long_outage_reports_ONE_moment_not_every_missed_moment(self):
        """The signature is a single datetime, so a caller cannot fan out."""
        got = self._missed(
            [_nightly()],
            last_run=_dt.datetime(2026, 8, 1, 12, 0, tzinfo=DOUALA),
            now=_dt.datetime(2026, 8, 20, 8, 0, tzinfo=DOUALA),
        )
        self.assertIsInstance(got, _dt.datetime)

    def test_nothing_missed_returns_None(self):
        got = self._missed(
            [_nightly()],
            last_run=_dt.datetime(2026, 8, 20, 22, 1, tzinfo=DOUALA),
            now=_dt.datetime(2026, 8, 20, 23, 0, tzinfo=DOUALA),
        )
        self.assertIsNone(got)

    def test_a_box_that_has_never_run_is_not_a_missed_window(self):
        """It is a NEW box. Reporting a catch-up would be inventing history."""
        self.assertIsNone(
            self._missed([_nightly()], last_run=None, now=_dt.datetime(2026, 8, 20, 8, 0, tzinfo=DOUALA))
        )

    def test_no_schedule_means_no_catch_up(self):
        self.assertIsNone(
            self._missed(
                [],
                last_run=_dt.datetime(2026, 8, 1, 12, 0, tzinfo=DOUALA),
                now=_dt.datetime(2026, 8, 20, 8, 0, tzinfo=DOUALA),
            )
        )


class TimezoneResolutionTests(SimpleTestCase):
    def test_the_tenants_zone_is_used(self):
        self.assertEqual(str(schedule_policy.school_timezone(_School("America/New_York"))),
                         "America/New_York")

    def test_an_unknown_zone_degrades_instead_of_stopping_the_box(self):
        """A typo in a config field must never be able to stop a school syncing."""
        tz = schedule_policy.school_timezone(_School("Mars/Olympus_Mons"))
        self.assertIsNotNone(tz)

    def test_a_missing_zone_degrades_too(self):
        self.assertIsNotNone(schedule_policy.school_timezone(_School("")))


class ArmingTests(SimpleTestCase):
    def test_arming_reports_the_source_so_an_operator_can_see_why(self):
        """"not due for 2400s" with no reason is what makes people distrust a scheduler."""
        with mock.patch.object(schedule_policy, "active_rules", return_value=[_office_hours()]):
            with mock.patch.object(cadence, "current_state", return_value=cadence.STEADY):
                with mock.patch.object(cadence, "schedule_next", return_value=1800) as armed:
                    out = schedule_policy.arm_next_cycle(
                        _School(), now=_dt.datetime(2026, 8, 20, 9, 0, tzinfo=DOUALA)
                    )
        self.assertEqual(out["source"], "schedule")
        self.assertEqual(out["interval_seconds"], 1800)
        armed.assert_called_once()

    def test_with_no_schedule_arming_leaves_the_cadence_alone(self):
        with mock.patch.object(schedule_policy, "active_rules", return_value=[]):
            with mock.patch.object(cadence, "current_state", return_value=cadence.STEADY):
                with mock.patch.object(cadence, "schedule_next") as armed:
                    out = schedule_policy.arm_next_cycle(_School())
        self.assertEqual(out["source"], "cadence")
        armed.assert_not_called()

    def test_a_failure_while_arming_never_breaks_a_completed_cycle(self):
        with mock.patch.object(schedule_policy, "active_rules", return_value=[_office_hours()]):
            with mock.patch.object(cadence, "current_state", return_value=cadence.STEADY):
                with mock.patch.object(cadence, "schedule_next", side_effect=RuntimeError("cache down")):
                    out = schedule_policy.arm_next_cycle(
                        _School(), now=_dt.datetime(2026, 8, 20, 9, 0, tzinfo=DOUALA)
                    )
        self.assertEqual(out["source"], "cadence")
