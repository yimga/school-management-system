"""The social cross-post outbox must be DRAINED on a schedule.

``social_media.process_outbox_batch`` (the standard-priority cross-post drainer)
had ZERO schedulers anywhere — no ``CELERY_BEAT_SCHEDULE`` entry, no in-process
periodic registry row, no management command, and no other caller. Rows ARE
produced by the live ``POST /api/v1/social/publish/`` endpoint, so every queued
non-emergency post orphaned in ``pending`` forever, on cloud AND edge. (Emergency
broadcasts drain inline in-request and were unaffected.) This seals that gap: the
task is registered in ``apps.platform_runtime.periodic`` so the ``run_periodic_jobs``
cron / secured cron endpoint drives it without a worker.

RULE ZERO: 'is registered' proves nothing. ``test_running_...`` produces a real
pending row and asserts the registered job (driven through the SAME path
``run_periodic_jobs`` uses) actually drains it (must-FIRE, effect-probing).
"""
from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime import periodic
from apps.social_media.models import (
    SocialMediaIntegration,
    SocialPostOutbox,
    SocialPostPriority,
)

_JOB = "social_media.process_outbox_batch"


class _DefaultsInstalledMixin:
    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        self._saved_registry = dict(periodic._REGISTRY)
        self._saved_installed = periodic._DEFAULTS_INSTALLED
        periodic._REGISTRY.clear()
        periodic._DEFAULTS_INSTALLED = False
        cache.clear()
        periodic.ensure_default_jobs()

    def tearDown(self):
        from django.core.cache import cache

        periodic._REGISTRY.clear()
        periodic._REGISTRY.update(self._saved_registry)
        periodic._DEFAULTS_INSTALLED = self._saved_installed
        cache.clear()
        super().tearDown()


class SocialOutboxRegisteredCronOnlyTests(_DefaultsInstalledMixin, TestCase):
    def test_registered_cron_only_frequent(self):
        job = periodic._REGISTRY.get(_JOB)
        self.assertIsNotNone(
            job,
            f"{_JOB} is absent from the periodic registry — queued social posts "
            "never drain.",
        )
        # Touches outbound providers → off the hot /health/ thread.
        self.assertFalse(job.auto_eligible)
        self.assertEqual(job.interval_seconds, periodic.FREQUENT_DRAIN_SECONDS)
        self.assertIn("drainer", job.tags)

    def test_auto_health_tick_never_runs_social_drain(self):
        auto = periodic.run_due_jobs(force=True, auto_only=True)
        self.assertNotIn(_JOB, {r["job"] for r in auto})


class SocialOutboxPeriodicRunDrainsTests(_DefaultsInstalledMixin, TestCase):
    """Must-FIRE: driving the registered job through the cron path drains a
    real pending cross-post (not merely 'is registered')."""

    def _pending_row(self):
        integration = SocialMediaIntegration.objects.create(
            provider="x",
            is_active=True,
            # A non-empty token → the dry-run provider posts it (empty would raise
            # ProviderNotConfiguredError → 'failed'); we assert the happy drain.
            encrypted_oauth_token="test-token",
        )
        return SocialPostOutbox.objects.create(
            integration=integration,
            body="Welcome to the new term!",
            priority=SocialPostPriority.STANDARD,
            status="pending",
        )

    def test_running_registered_job_drains_pending_post(self):
        row = self._pending_row()
        self.assertEqual(
            SocialPostOutbox.objects.filter(status="pending").count(), 1
        )

        result = periodic.run_job(_JOB, force=True)
        self.assertEqual(result["status"], "ran", result)

        row.refresh_from_db()
        # EFFECT: the pending post was drained through the publisher to the
        # (dry-run) provider and marked posted — not left orphaned in 'pending'.
        self.assertNotEqual(row.status, "pending")
        self.assertEqual(row.status, "posted", row.status)
        self.assertTrue(row.external_post_id.startswith("dry-run-"), row.external_post_id)
