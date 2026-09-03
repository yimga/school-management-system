"""The dead-man's-switch must see a job that NEVER started, not only one that stopped.

MEASURED on the live cloud, 2026-09-01. 34 jobs registered, 8 heartbeat rows, and all 8
of those were `auto_eligible` (the tier that ticks off `/health/`). The other 26 --
outbound SMS/WhatsApp/push drain, the event outbox, webhook deliveries, payment
reminders, the billing lifecycle, DR snapshots, scheduled announcements -- had never run
a single time, because nothing on that deployment invokes the full-registry path: the
Render `type: cron` block is commented out and the nominated external scheduler (GitHub
Actions) has run no job since 2026-08-15.

`monitor_scheduled_job_health` ran on the hour, every hour, and reported `fails 0`.

WHY IT COULD NOT SEE THEM. A heartbeat row is written when a job RUNS, so a job that has
never run has no row, so `watched_for_seconds` was None -- and the never-succeeded arm of
`evaluate_staleness` reads None as "not watched long enough to judge yet":

    watched = j.get("watched_for_seconds")
    is_stale = watched is not None and watched > threshold

That guard exists for a real reason -- a fresh deploy with an empty table must not
false-alarm -- but it collapsed two states that could not be more different:

    row exists, no success yet, watching 5 minutes   -> correctly quiet
    NO row, never ran in the install's lifetime      -> quiet FOREVER

So the monitor built to turn "scheduled jobs stopped" into a loud alert was structurally
incapable of reporting "scheduled jobs never started". The failure it was written to
prevent is the one it could not see.

AND IT DISABLED THE CURE, NOT JUST THE ALARM. `select_recovery_candidates` already
handles this case explicitly -- `untriggered = started is None or ...` -- and exists to
auto-trigger overdue CRON-ONLY jobs when nothing is invoking them. It only ever considers
jobs already marked stale, so one condition in the staleness rule was holding back the
entire self-healing path that would have fixed the outage it was hiding.

These tests assert on WHICH jobs are flagged, because that is the whole defect: the data
was present and correct, the counting was correct, and the verdict was wrong.
"""
from __future__ import annotations

import time
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.platform_runtime.models_scheduling import ScheduledJobHeartbeat
from apps.platform_runtime.scheduled_job_health import (
    run_health_monitor,
    select_recovery_candidates,
)

_REGISTRY = "apps.platform_runtime.periodic.registry_status"
_RECOVER = "apps.platform_runtime.scheduled_job_health.auto_recovery_enabled"

_HOUR = 3600


def _registry(*names_intervals):
    return [
        {"job": name, "interval_seconds": interval, "auto_eligible": auto,
         "enabled": True, "description": "", "tags": []}
        for name, interval, auto in names_intervals
    ]


def _heartbeat(job_name, *, created_ago_s, last_success_ago_s=None):
    """A heartbeat row with a back-dated created_at (auto_now_add needs an UPDATE)."""
    hb = ScheduledJobHeartbeat.objects.create(job_name=job_name, expected_interval_seconds=_HOUR)
    now = timezone.now()
    ScheduledJobHeartbeat.objects.filter(pk=hb.pk).update(
        created_at=now - timezone.timedelta(seconds=created_ago_s),
        last_success_at=(
            None if last_success_ago_s is None
            else now - timezone.timedelta(seconds=last_success_ago_s)
        ),
    )
    return ScheduledJobHeartbeat.objects.get(pk=hb.pk)


class _NoInheritedHeartbeats:
    """Every test below states its own world, because the database remembers.

    The ``--keepdb`` test database ACCUMULATES COMMITTED heartbeat rows -- 15 of them
    were sitting in it after a single full ``apps/platform_runtime`` run, written by
    tests that commit rather than roll back. ``run_health_monitor`` reads the WHOLE
    table to find the oldest row, so an inherited row silently becomes this module's
    observation window and changes the verdict.

    That is not hypothetical: the fresh-install control below passed, then failed on a
    later run against the same code, because by then the suite had left a row 1874s old
    in the table and a 300s-interval job legitimately breached its 900s threshold. The
    test was not asserting about a fresh install at all -- it was asserting about
    whatever the previous run happened to leave behind.

    ``TestCase`` wraps each test in a transaction, so this delete is rolled back and the
    shared database is left exactly as found.
    """

    def setUp(self):
        super().setUp()
        ScheduledJobHeartbeat.objects.all().delete()


class NeverStartedJobsAreReportedTests(_NoInheritedHeartbeats, TestCase):
    """LOAD-BEARING. Each fails on its own assertion with the fix reverted."""

    def _run(self, registry):
        with patch(_REGISTRY, return_value=registry), patch(_RECOVER, return_value=False):
            return {f.job_name: f for f in run_health_monitor()}

    def test_a_registered_job_with_no_heartbeat_row_is_stale(self):
        # The live shape: one job has been running for days, another has never run at all.
        # Reverted: the never-run job is reported healthy, because "no row" read as
        # "not watched long enough to judge".
        _heartbeat("works.fine", created_ago_s=5 * 24 * _HOUR, last_success_ago_s=60)
        findings = self._run(_registry(
            ("works.fine", _HOUR, True),
            ("never.ran", _HOUR, False),
        ))
        self.assertTrue(findings["never.ran"].is_stale, findings["never.ran"])

    def test_the_whole_dark_tier_is_reported_not_just_one(self):
        # 26 jobs were dark on the live cloud. A rule that surfaced only the first would
        # still understate the outage by an order of magnitude.
        _heartbeat("works.fine", created_ago_s=5 * 24 * _HOUR, last_success_ago_s=60)
        findings = self._run(_registry(
            ("works.fine", _HOUR, True),
            ("dark.one", _HOUR, False),
            ("dark.two", 300, False),
            ("dark.three", 24 * _HOUR, False),
        ))
        stale = sorted(n for n, f in findings.items() if f.is_stale)
        self.assertEqual(stale, ["dark.one", "dark.three", "dark.two"])

    def test_a_never_started_cron_only_job_becomes_recoverable(self):
        # The point of seeing it. select_recovery_candidates already handled
        # `last_started_epoch is None`; it never got the chance because nothing upstream
        # marked these jobs stale.
        _heartbeat("works.fine", created_ago_s=5 * 24 * _HOUR, last_success_ago_s=60)
        findings = self._run(_registry(
            ("works.fine", _HOUR, True),
            ("never.ran", _HOUR, False),
        ))
        enriched = [
            {"job_name": "never.ran", "interval_seconds": _HOUR, "auto_eligible": False,
             "is_stale": findings["never.ran"].is_stale,
             "last_started_epoch": None, "consecutive_failures": 0}
        ]
        self.assertEqual(select_recovery_candidates(enriched, now=time.time()), ["never.ran"])


class QuietWhenItShouldBeQuietTests(_NoInheritedHeartbeats, TestCase):
    """CONTROLS. These hold on BOTH the fixed and the unfixed tree.

    They pin the guard the never-succeeded arm exists for. Without them the obvious
    "fix" -- treat a missing row as infinitely stale -- would pass every test above and
    make every deploy scream about every job before anything has had a chance to run.
    """

    def _run(self, registry):
        with patch(_REGISTRY, return_value=registry), patch(_RECOVER, return_value=False):
            return {f.job_name: f for f in run_health_monitor()}

    def test_the_job_that_is_running_normally_is_not_dragged_in(self):
        # Verified as a CONTROL, not an assertion of the fix: it passes on the
        # unfixed tree too. It guards over-reach -- if the fix turned "healthy" into
        # "stale" for the tier that works, the alert becomes noise and gets muted,
        # which is how the original blind spot survived unnoticed in the first place.
        _heartbeat("works.fine", created_ago_s=5 * 24 * _HOUR, last_success_ago_s=60)
        findings = self._run(_registry(
            ("works.fine", _HOUR, True),
            ("never.ran", _HOUR, False),
        ))
        self.assertFalse(findings["works.fine"].is_stale, findings["works.fine"])

    def test_a_completely_fresh_install_alarms_about_nothing(self):
        # No heartbeat rows at all: we have never observed a run, so we cannot yet claim
        # anything is overdue. This is the false-alarm the original guard prevented and
        # the fix must keep preventing.
        findings = self._run(_registry(
            ("never.ran", _HOUR, False),
            ("also.never", 300, False),
        ))
        self.assertEqual([n for n, f in findings.items() if f.is_stale], [])

    def test_a_young_heartbeat_without_a_success_is_not_stale(self):
        # Row exists, job has not succeeded yet, but we have only been watching a minute.
        _heartbeat("just.registered", created_ago_s=60, last_success_ago_s=None)
        findings = self._run(_registry(("just.registered", _HOUR, False)))
        self.assertFalse(findings["just.registered"].is_stale, findings["just.registered"])

    def test_an_auto_eligible_job_is_never_a_recovery_candidate(self):
        # Light jobs already tick off /health/. Recovering them would put heavy work back
        # on the request-serving thread the auto_eligible split exists to protect.
        enriched = [
            {"job_name": "light.job", "interval_seconds": _HOUR, "auto_eligible": True,
             "is_stale": True, "last_started_epoch": None, "consecutive_failures": 0}
        ]
        self.assertEqual(select_recovery_candidates(enriched, now=time.time()), [])

    def test_the_monitor_still_never_raises(self):
        # It runs on the /health/ tick thread; a crash here costs the health probe.
        with patch(_REGISTRY, side_effect=RuntimeError("registry exploded")), patch(
            _RECOVER, return_value=False
        ):
            self.assertEqual(run_health_monitor(), [])
