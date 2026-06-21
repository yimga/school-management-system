"""Pure-logic tests for the scheduled-job dead-man's-switch staleness rule.

These cover the pure ``evaluate_staleness`` rule and need NO database. DB-backed
tests for ``record_heartbeat`` / ``run_health_monitor`` are added when the
``ScheduledJobHeartbeat`` migration lands (see the apply checklist) — they are
kept out of this file for now so it stays CI-safe before the table exists.
"""
from __future__ import annotations

import datetime
import os
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.platform_runtime import periodic
from apps.platform_runtime.models_scheduling import ScheduledJobHeartbeat
from apps.platform_runtime.scheduled_job_health import (
    MAX_AUTO_RECOVERY_FAILURES,
    STALE_GRACE_FLOOR_SECONDS,
    auto_recovery_enabled,
    evaluate_staleness,
    record_heartbeat,
    run_health_monitor,
    select_recovery_candidates,
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


def _job(**over):
    base = {
        "job_name": "j",
        "interval_seconds": _DAY,
        "is_stale": True,
        "auto_eligible": False,
        "last_started_epoch": None,
        "consecutive_failures": 0,
    }
    base.update(over)
    return base


class SelectRecoveryCandidatesTests(SimpleTestCase):
    def test_stale_crononly_untriggered_is_recovered(self):
        self.assertEqual(select_recovery_candidates([_job()], now=_NOW), ["j"])

    def test_not_stale_is_skipped(self):
        self.assertEqual(select_recovery_candidates([_job(is_stale=False)], now=_NOW), [])

    def test_light_auto_eligible_job_is_skipped(self):
        # Light jobs already tick off /health/ — never need recovery.
        self.assertEqual(select_recovery_candidates([_job(auto_eligible=True)], now=_NOW), [])

    def test_recently_triggered_but_erroring_is_skipped(self):
        # last_started within one interval => something IS invoking it; it's a bug,
        # not a trigger outage — alert only, don't hammer.
        job = _job(last_started_epoch=_NOW - 60, consecutive_failures=2)
        self.assertEqual(select_recovery_candidates([job], now=_NOW), [])

    def test_untriggered_means_started_older_than_one_interval(self):
        job = _job(last_started_epoch=_NOW - (_DAY + 10))
        self.assertEqual(select_recovery_candidates([job], now=_NOW), ["j"])

    def test_failure_cap_stops_recovery(self):
        job = _job(consecutive_failures=MAX_AUTO_RECOVERY_FAILURES)
        self.assertEqual(select_recovery_candidates([job], now=_NOW), [])


class AutoRecoveryEnabledTests(SimpleTestCase):
    def test_explicit_off(self):
        with mock.patch.dict(os.environ, {"RMC_JOB_AUTO_RECOVER": "off"}):
            self.assertFalse(auto_recovery_enabled())

    def test_explicit_on(self):
        with mock.patch.dict(os.environ, {"RMC_JOB_AUTO_RECOVER": "on"}):
            self.assertTrue(auto_recovery_enabled())

    def test_auto_mode_enabled_without_broker(self):
        with mock.patch.dict(
            os.environ, {"RMC_JOB_AUTO_RECOVER": "auto", "CELERY_BROKER_URL": ""}
        ):
            self.assertTrue(auto_recovery_enabled())

    def test_auto_mode_yields_to_broker(self):
        with mock.patch.dict(
            os.environ,
            {"RMC_JOB_AUTO_RECOVER": "auto", "CELERY_BROKER_URL": "redis://x:6379/0"},
        ):
            self.assertFalse(auto_recovery_enabled())


class RecordHeartbeatTests(TestCase):
    def test_ran_creates_row_and_marks_success(self):
        record_heartbeat("test.job", status="ran", interval_seconds=_DAY, duration_ms=5)
        hb = ScheduledJobHeartbeat.objects.get(job_name="test.job")
        self.assertIsNotNone(hb.last_success_at)
        self.assertEqual(hb.last_status, "ran")
        self.assertEqual(hb.consecutive_failures, 0)
        self.assertEqual(hb.last_duration_ms, 5)

    def test_error_increments_failures_and_keeps_last_success(self):
        record_heartbeat("test.job", status="ran", interval_seconds=_DAY, duration_ms=1)
        ran_at = ScheduledJobHeartbeat.objects.get(job_name="test.job").last_success_at
        record_heartbeat("test.job", status="error", interval_seconds=_DAY, error="boom")
        record_heartbeat("test.job", status="error", interval_seconds=_DAY, error="boom2")
        hb = ScheduledJobHeartbeat.objects.get(job_name="test.job")
        self.assertEqual(hb.consecutive_failures, 2)
        self.assertEqual(hb.last_status, "error")
        self.assertIn("boom2", hb.last_error)
        self.assertEqual(hb.last_success_at, ran_at)  # errors never clear last success

    def test_error_text_is_truncated(self):
        record_heartbeat("test.job", status="error", interval_seconds=_DAY, error="x" * 5000)
        hb = ScheduledJobHeartbeat.objects.get(job_name="test.job")
        self.assertLessEqual(len(hb.last_error), 2000)


class RunHealthMonitorTests(TestCase):
    """Integration: a real registered job with a long-ago durable heartbeat is
    flagged stale; a recent one is not. Auto-recovery is forced OFF so the test
    never spawns a thread that runs the real billing command."""

    JOB = "billing.run_platform_billing_lifecycle"

    def _seed(self, *, age_days):
        periodic.ensure_default_jobs()
        when = timezone.now() - datetime.timedelta(days=age_days)
        ScheduledJobHeartbeat.objects.create(
            job_name=self.JOB,
            expected_interval_seconds=_DAY,
            last_success_at=when,
            last_started_at=when,
            last_status="ran",
        )

    def test_old_heartbeat_is_flagged_stale(self):
        self._seed(age_days=30)
        with mock.patch.dict(os.environ, {"RMC_JOB_AUTO_RECOVER": "off"}):
            findings = run_health_monitor()
        by_name = {f.job_name: f for f in findings}
        self.assertIn(self.JOB, by_name)
        self.assertTrue(by_name[self.JOB].is_stale)

    def test_recent_heartbeat_is_not_stale(self):
        self._seed(age_days=0)
        with mock.patch.dict(os.environ, {"RMC_JOB_AUTO_RECOVER": "off"}):
            findings = run_health_monitor()
        by_name = {f.job_name: f for f in findings}
        self.assertIn(self.JOB, by_name)
        self.assertFalse(by_name[self.JOB].is_stale)
