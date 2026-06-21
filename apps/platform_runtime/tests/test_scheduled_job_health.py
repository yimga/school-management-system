"""Pure-logic tests for the scheduled-job dead-man's-switch staleness rule.

These cover the pure ``evaluate_staleness`` rule and need NO database. DB-backed
tests for ``record_heartbeat`` / ``run_health_monitor`` are added when the
``ScheduledJobHeartbeat`` migration lands (see the apply checklist) — they are
kept out of this file for now so it stays CI-safe before the table exists.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.scheduled_job_health import (
    STALE_GRACE_FLOOR_SECONDS,
    evaluate_staleness,
    staleness_threshold_seconds,
)

_DAY = 24 * 60 * 60
_NOW = 1_000_000.0


class EvaluateStalenessTests(SimpleTestCase):
    def test_recent_success_is_healthy(self):
        jobs = [{"job_name": "j", "interval_seconds": _DAY, "last_success_epoch": _NOW - 10}]
        [f] = evaluate_staleness(jobs, now=_NOW, grace_factor=2.0)
        self.assertFalse(f.is_stale)
        self.assertEqual(f.reason, "healthy")

    def test_overdue_success_is_stale(self):
        # threshold = 1*day*2 + floor; 5 days old clearly exceeds it.
        jobs = [{"job_name": "j", "interval_seconds": _DAY, "last_success_epoch": _NOW - 5 * _DAY}]
        [f] = evaluate_staleness(jobs, now=_NOW, grace_factor=2.0)
        self.assertTrue(f.is_stale)
        self.assertEqual(f.reason, "overdue")

    def test_just_one_interval_old_is_not_yet_stale(self):
        # Due, but within the 2x grace window → must not alarm on normal jitter.
        jobs = [{"job_name": "j", "interval_seconds": _DAY, "last_success_epoch": _NOW - _DAY}]
        [f] = evaluate_staleness(jobs, now=_NOW, grace_factor=2.0)
        self.assertFalse(f.is_stale)

    def test_never_succeeded_is_no_data_yet_when_freshly_watched(self):
        jobs = [
            {
                "job_name": "j",
                "interval_seconds": _DAY,
                "last_success_epoch": None,
                "watched_for_seconds": 60,
            }
        ]
        [f] = evaluate_staleness(jobs, now=_NOW, grace_factor=2.0)
        self.assertFalse(f.is_stale)
        self.assertEqual(f.reason, "no_data_yet")

    def test_never_succeeded_becomes_stale_after_threshold(self):
        jobs = [
            {
                "job_name": "j",
                "interval_seconds": _DAY,
                "last_success_epoch": None,
                "watched_for_seconds": 5 * _DAY,
            }
        ]
        [f] = evaluate_staleness(jobs, now=_NOW, grace_factor=2.0)
        self.assertTrue(f.is_stale)
        self.assertEqual(f.reason, "never_succeeded")

    def test_threshold_floor_applies_at_zero_interval(self):
        self.assertEqual(staleness_threshold_seconds(0, 2.0), float(STALE_GRACE_FLOOR_SECONDS))

    def test_grace_factor_widens_threshold(self):
        self.assertGreater(
            staleness_threshold_seconds(_DAY, 3.0),
            staleness_threshold_seconds(_DAY, 2.0),
        )
