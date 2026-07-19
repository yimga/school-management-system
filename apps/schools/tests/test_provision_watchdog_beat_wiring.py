"""The provisioning watchdog must run in BOTH topologies — not just the one it was written for.

Found post-deploy (2026-07-16). The watchdog was registered only as an in-process
periodic job ticking off ``/health/``. That path is gated on
``periodic.inprocess_scheduler_enabled()``, whose default ``auto`` mode returns
``not bool(CELERY_BROKER_URL)`` — so the moment a real worker + beat are
provisioned (the deployed ``render.yaml`` sets ``CELERY_BROKER_URL`` on web from
the Valkey service), the in-process scheduler stands down and the watchdog
**stopped running entirely**.

Two further paths that look like they'd cover the hand-off do not:
  * ``scheduled_job_health_monitor``'s ``auto_recovery_enabled()`` mirrors the
    same broker check, so it is off in exactly the same topology; and
  * ``select_recovery_candidates`` deliberately skips ``auto_eligible`` jobs
    ("light jobs already tick off /health/"), which the watchdog is.

Net effect: the self-heal ran only in the broker-less topology that needs it
least, and never in production — the very failure class it was built to fix.
The fix is a ``schools.resume_stuck_provisions`` beat entry alongside the
in-process registration (mirroring ``reconcile_half_provisioned_tenants``, which
has always had both). These tests pin BOTH halves so a future edit cannot
silently drop one and re-open the gap.
"""

from __future__ import annotations

from django.test import SimpleTestCase


class WatchdogBeatWiringTests(SimpleTestCase):
    def test_watchdog_has_a_beat_entry(self):
        from django.conf import settings

        schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
        tasks = {entry.get("task") for entry in schedule.values() if isinstance(entry, dict)}
        self.assertIn(
            "schools.resume_stuck_provisions",
            tasks,
            "the watchdog MUST have a beat entry — its in-process /health/ twin "
            "stands down whenever CELERY_BROKER_URL is set, so without this it "
            "never runs in the deployed worker+beat topology",
        )

    def test_watchdog_beat_entry_is_frequent_enough_to_heal(self):
        from django.conf import settings

        schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
        entry = next(
            e
            for e in schedule.values()
            if isinstance(e, dict) and e.get("task") == "schools.resume_stuck_provisions"
        )
        # A heal slower than the staleness threshold would let a dead run sit
        # visibly frozen for longer than it takes to *detect* it.
        from apps.schools.provision_watchdog import provision_resume_stale_seconds

        self.assertLessEqual(
            float(entry["schedule"]),
            float(provision_resume_stale_seconds()) * 2,
            "beat cadence must be within ~2x the staleness threshold",
        )

    def test_watchdog_celery_task_is_registered_under_its_beat_name(self):
        # A beat entry naming a task Celery has never registered is a silent
        # no-op: beat publishes it and nothing consumes it.
        from celery import current_app

        import apps.schools.tasks  # noqa: F401  (registers the @shared_task)

        self.assertIn("schools.resume_stuck_provisions", current_app.tasks)

    def test_inprocess_registration_still_present(self):
        # The broker-less topology must keep working too.
        from apps.platform_runtime import periodic

        periodic.ensure_default_jobs()
        self.assertIn("schools.resume_stuck_provisions", periodic._REGISTRY)


class InprocessSchedulerHandoffTests(SimpleTestCase):
    """Pin the exact gate that made the watchdog inert, so the reasoning above
    can't silently rot if someone changes the default mode."""

    def test_inprocess_scheduler_stands_down_when_a_broker_is_configured(self):
        import os
        from unittest.mock import patch

        from apps.platform_runtime.periodic import inprocess_scheduler_enabled

        with patch.dict(
            os.environ,
            {"RMC_INPROCESS_SCHEDULER": "auto", "CELERY_BROKER_URL": "redis://x:6379/0"},
        ):
            self.assertFalse(
                inprocess_scheduler_enabled(),
                "with a broker set, the /health tick must NOT run jobs — which is "
                "exactly why the beat entry is required",
            )
        with patch.dict(
            os.environ, {"RMC_INPROCESS_SCHEDULER": "auto", "CELERY_BROKER_URL": ""}
        ):
            self.assertTrue(inprocess_scheduler_enabled())

    def test_auto_recovery_does_not_cover_the_handoff(self):
        # select_recovery_candidates skips auto_eligible jobs, so the hourly
        # job-health monitor is NOT a fallback for the watchdog.
        from apps.platform_runtime.scheduled_job_health import select_recovery_candidates

        chosen = select_recovery_candidates(
            [
                {
                    "job_name": "schools.resume_stuck_provisions",
                    "interval_seconds": 120,
                    "is_stale": True,
                    "auto_eligible": True,
                    "last_started_epoch": None,
                    "consecutive_failures": 0,
                }
            ]
        )
        self.assertEqual(
            chosen,
            [],
            "auto-recovery skips auto_eligible jobs — it cannot be relied on to "
            "run the watchdog once beat takes over",
        )
