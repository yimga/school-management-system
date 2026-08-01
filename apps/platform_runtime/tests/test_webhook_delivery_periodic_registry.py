"""Outbound webhook DELIVERY must drain on a broker-less box via the registry.

The three outbound webhook senders were all dead in the no-worker topology:
  * migration_cloud.deliver_due (beat-only migration-cloud-webhook-deliver-due) —
    LIVE producer, so HMAC-signed deliveries genuinely never sent on a bare box.
  * events.process_webhook_deliveries (the SEND half of the event outbox — the
    registered process_event_outbox only QUEUES deliveries) — beat-only/command.
  * marketplace.deliver_due (beat-only) — dormant producer, symmetric hardening.

Each is now registered in apps.platform_runtime.periodic so run_periodic_jobs /
the secured cron endpoint drives it without a worker.

RULE ZERO: 'is registered' proves nothing about whether the delegate actually
invokes the real drainer. Each test below runs the job through the SAME run_job
path the cron uses and asserts the underlying drainer function is invoked
(must-FIRE). The drainers' own delivery correctness (HMAC, backoff, quota) is
covered by the migration_cloud / marketplace / events webhook test suites.
"""
from __future__ import annotations

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.platform_runtime import periodic


class _DefaultsInstalledMixin:
    def setUp(self):
        super().setUp()
        self._saved_registry = dict(periodic._REGISTRY)
        self._saved_installed = periodic._DEFAULTS_INSTALLED
        periodic._REGISTRY.clear()
        periodic._DEFAULTS_INSTALLED = False
        cache.clear()
        periodic.ensure_default_jobs()

    def tearDown(self):
        periodic._REGISTRY.clear()
        periodic._REGISTRY.update(self._saved_registry)
        periodic._DEFAULTS_INSTALLED = self._saved_installed
        cache.clear()
        super().tearDown()


# (registry job name, patch target of the drainer the delegate must invoke)
_JOBS = {
    "migration_cloud.deliver_due_webhooks": "apps.migration_cloud.api.webhook_dispatch.deliver_due",
    "events.process_webhook_deliveries": "apps.events.tasks.process_webhook_deliveries_batch",
    "marketplace.deliver_due_webhooks": "apps.marketplace.webhooks.deliver_due",
}


class WebhookDeliveryDrainersRegisteredTests(_DefaultsInstalledMixin, TestCase):
    def test_all_three_registered_cron_only_frequent_drainers(self):
        for name in _JOBS:
            job = periodic._REGISTRY.get(name)
            self.assertIsNotNone(job, f"{name} absent from the periodic registry")
            # Outbound HTTP → cron-only, off the hot /health/ thread.
            self.assertFalse(job.auto_eligible, name)
            self.assertEqual(job.interval_seconds, periodic.FREQUENT_DRAIN_SECONDS, name)
            self.assertIn("webhook", job.tags, name)
            self.assertIn("drainer", job.tags, name)

    def test_auto_health_tick_never_runs_any_webhook_drainer(self):
        auto = {r["job"] for r in periodic.run_due_jobs(force=True, auto_only=True)}
        for name in _JOBS:
            self.assertNotIn(name, auto, name)


class WebhookDeliveryDrainersMustFireTests(_DefaultsInstalledMixin, TestCase):
    """Running each job through the cron path actually invokes the real drainer."""

    def _assert_job_invokes_drainer(self, name, patch_target):
        with mock.patch(patch_target) as drainer:
            drainer.return_value = {"processed": 0}
            result = periodic.run_job(name, force=True)
        self.assertEqual(result["status"], "ran", result)
        self.assertEqual(
            drainer.call_count,
            1,
            f"{name} ran but did NOT invoke {patch_target} — the delegate wiring is "
            "a no-op.",
        )

    def test_migration_cloud_delivery_job_invokes_drainer(self):
        self._assert_job_invokes_drainer(
            "migration_cloud.deliver_due_webhooks",
            _JOBS["migration_cloud.deliver_due_webhooks"],
        )

    def test_events_delivery_job_invokes_drainer(self):
        self._assert_job_invokes_drainer(
            "events.process_webhook_deliveries",
            _JOBS["events.process_webhook_deliveries"],
        )

    def test_marketplace_delivery_job_invokes_drainer(self):
        self._assert_job_invokes_drainer(
            "marketplace.deliver_due_webhooks",
            _JOBS["marketplace.deliver_due_webhooks"],
        )
