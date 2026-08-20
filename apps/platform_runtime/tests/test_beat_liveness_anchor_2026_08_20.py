"""The grace window that re-armed itself, and stopped every periodic job on a box.

MEASURED on the sovereign box at 10.10.20.137, 2026-08-20:

    /health/   "celery_broker_configured": true,  "inprocess_scheduler": false
    /healthz/  "celery_beat": {"status":"degraded","detail":"beat canary stale"}
               "celery_queue_depth": no queue 'celery' in vhost '1'

``inprocess_scheduler_enabled()`` stands the in-process scheduler down while a broker
is configured AND ``celery_beat_appears_alive()`` says beat is running. The broker was
configured (the selfhost compose always sets one) and beat was NOT running — the vhost
held no ``celery`` queue at all — yet the verdict said alive, so nothing on that box
ran a periodic job. Edge sync, provisioning heals and digests were all stopped.

The cause was the grace anchor: a cache key with a 24-hour TTL that, on expiry, was
re-seeded with ``now`` and returned True. A beat that had never ticked was declared
alive again every 24 hours, forever — and any Valkey restart did the same immediately.
Observed flipping degraded → ok inside 20 minutes with no beat activity.

The anchor is now ``ScheduledJobHeartbeat.created_at``, which survives deploys, cache
flushes and restarts. The sharpest test here is ``test_an_expired_cache_anchor_does_not
_buy_another_grace_window`` — that is the exact bug.
"""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.platform_runtime import periodic


class BeatWatchAnchorTests(SimpleTestCase):
    def test_the_durable_anchor_is_preferred_over_the_cache(self):
        """The DB survives the cache flush that used to reset the verdict."""

        class _HB:
            created_at = mock.Mock(timestamp=lambda: 1000.0)

        with mock.patch(
            "apps.platform_runtime.models_scheduling.ScheduledJobHeartbeat"
        ) as model:
            model.objects.get_or_create.return_value = (_HB(), False)
            with mock.patch.object(periodic, "cache") as cache:
                anchor = periodic._beat_watch_anchor_epoch(9999.0)
                self.assertEqual(anchor, 1000.0)
                cache.get.assert_not_called()

    def test_an_expired_cache_anchor_does_not_buy_another_grace_window(self):
        """THE BUG. The old code re-seeded with `now` and returned "beat is alive".

        With the DB unavailable and the cache empty we may seed once — but the value
        seeded must be a real anchor the caller can age out, never a verdict.
        """
        with mock.patch(
            "apps.platform_runtime.models_scheduling.ScheduledJobHeartbeat"
        ) as model:
            model.objects.get_or_create.side_effect = RuntimeError("no db")
            with mock.patch.object(periodic, "cache") as cache:
                cache.get.return_value = None
                anchor = periodic._beat_watch_anchor_epoch(5000.0)

        self.assertEqual(anchor, 5000.0)
        # And it is written with a TTL far longer than the staleness threshold, so an
        # expiry cannot hand a dead beat a fresh window on any realistic cadence.
        self.assertGreater(
            periodic._BEAT_WATCH_TTL_SECONDS,
            periodic.celery_beat_liveness_threshold_seconds() * 100,
        )

    def test_an_existing_cache_anchor_is_returned_not_refreshed(self):
        with mock.patch(
            "apps.platform_runtime.models_scheduling.ScheduledJobHeartbeat"
        ) as model:
            model.objects.get_or_create.side_effect = RuntimeError("no db")
            with mock.patch.object(periodic, "cache") as cache:
                cache.get.return_value = 100.0
                anchor = periodic._beat_watch_anchor_epoch(9999.0)
                self.assertEqual(anchor, 100.0)
                cache.add.assert_not_called()

    def test_no_db_and_no_cache_is_unknown_not_alive(self):
        with mock.patch(
            "apps.platform_runtime.models_scheduling.ScheduledJobHeartbeat"
        ) as model:
            model.objects.get_or_create.side_effect = RuntimeError("no db")
            with mock.patch.object(periodic, "cache") as cache:
                cache.get.side_effect = RuntimeError("no cache")
                self.assertIsNone(periodic._beat_watch_anchor_epoch(1.0))


class BeatAppearsAliveTests(SimpleTestCase):
    def _no_recent_run(self):
        return mock.patch.object(periodic, "_get_last_run", return_value=None)

    def test_no_broker_means_beat_is_not_expected(self):
        with mock.patch.dict("os.environ", {"CELERY_BROKER_URL": ""}, clear=False):
            self.assertTrue(periodic.celery_beat_appears_alive())

    def test_a_stale_anchor_reports_beat_as_dead(self):
        """And therefore hands the schedule back to the in-process heal."""
        threshold = periodic.celery_beat_liveness_threshold_seconds()
        with mock.patch.dict(
            "os.environ", {"CELERY_BROKER_URL": "redis://valkey:6379/1"}, clear=False
        ):
            with self._no_recent_run():
                with mock.patch.object(
                    periodic, "_beat_watch_anchor_epoch", return_value=0.0
                ):
                    self.assertFalse(
                        periodic.celery_beat_appears_alive(now=threshold + 10)
                    )

    def test_a_fresh_deploy_still_gets_its_grace(self):
        """A brand-new box must not flip red before beat's first tick."""
        with mock.patch.dict(
            "os.environ", {"CELERY_BROKER_URL": "redis://valkey:6379/1"}, clear=False
        ):
            with self._no_recent_run():
                with mock.patch.object(
                    periodic, "_beat_watch_anchor_epoch", return_value=1000.0
                ):
                    self.assertTrue(periodic.celery_beat_appears_alive(now=1001.0))

    def test_an_unknown_anchor_is_treated_as_dead_not_alive(self):
        """Fail toward RUNNING the scheduler.

        Both running is harmless — ``run_job``'s per-job claim lock makes the second
        one a no-op. Neither running is what stopped the box.
        """
        with mock.patch.dict(
            "os.environ", {"CELERY_BROKER_URL": "redis://valkey:6379/1"}, clear=False
        ):
            with self._no_recent_run():
                with mock.patch.object(
                    periodic, "_beat_watch_anchor_epoch", return_value=None
                ):
                    self.assertFalse(periodic.celery_beat_appears_alive(now=1.0))

    def test_a_dead_beat_re_enables_the_inprocess_scheduler(self):
        """The end-to-end property. This is what was false on the box."""
        with mock.patch.dict(
            "os.environ",
            {"CELERY_BROKER_URL": "redis://valkey:6379/1", "RMC_INPROCESS_SCHEDULER": "auto"},
            clear=False,
        ):
            with mock.patch.object(
                periodic, "celery_beat_appears_alive", return_value=False
            ):
                self.assertTrue(periodic.inprocess_scheduler_enabled())


class HealthVerdictAgreementTests(SimpleTestCase):
    """/healthz and /health must not contradict each other about the same fact."""

    def test_healthz_says_nothing_is_scheduled_when_that_is_true(self):
        from apps.observability.views import _check_celery_beat

        with mock.patch("django.conf.settings.CELERY_BROKER_URL", "redis://x/1", create=True):
            with mock.patch.object(periodic, "celery_beat_appears_alive", return_value=False):
                with mock.patch.object(
                    periodic, "inprocess_scheduler_enabled", return_value=False
                ):
                    result = _check_celery_beat()

        self.assertEqual(result["status"], "degraded")
        # The old text promised a heal that was not happening.
        self.assertNotIn("should re-enable", result["detail"])
        self.assertIn("NOTHING is running periodic jobs", result["detail"])

    def test_healthz_says_the_heal_took_over_when_it_did(self):
        from apps.observability.views import _check_celery_beat

        with mock.patch("django.conf.settings.CELERY_BROKER_URL", "redis://x/1", create=True):
            with mock.patch.object(periodic, "celery_beat_appears_alive", return_value=False):
                with mock.patch.object(
                    periodic, "inprocess_scheduler_enabled", return_value=True
                ):
                    result = _check_celery_beat()

        self.assertEqual(result["status"], "degraded")
        self.assertIn("has taken over", result["detail"])
