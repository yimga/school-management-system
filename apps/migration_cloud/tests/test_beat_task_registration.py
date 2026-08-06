"""Must-fire guards for the four Migration Cloud beat tasks woken 2026-08-05.

Each was a phantom beat entry — the @shared_task lived outside an autodiscovered
tasks.py, so beat looked the name up, found nothing, and the job silently never
ran. MigrationCloudConfig.ready() now imports the modules so the names resolve.

These tests fail if any task is un-registered again (dropping it back to a
silent no-op) AND pin the two safety gates that let the outbound / write-capable
tasks be scheduled safely:
  * the webhook dispatcher beat wrapper no-ops unless explicitly enabled;
  * the nightly smoke kill-switch no-ops unless explicitly enabled.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase, override_settings

from config.celery import app

REGISTERED = (
    "apps.migration_cloud.tasks_retention.purge_completed_migration_bundles_audit_task",
    "apps.migration_cloud.tasks_smoke.run_smoke_against_synthetic_tenant",
    "apps.migration_cloud.tasks_alerts.token_rotation_watchdog",
    "apps.migration_cloud.api.webhook_dispatch.deliver_due_task",
)


class MigrationCloudBeatRegistrationTests(TestCase):
    def test_all_four_beat_tasks_are_registered(self):
        # Importing the modules is what registers the shared_task; ready() does
        # this at boot. Import here too so the assertion is independent of order.
        import apps.migration_cloud.tasks_retention  # noqa: F401
        import apps.migration_cloud.tasks_smoke  # noqa: F401
        import apps.migration_cloud.tasks_alerts  # noqa: F401
        import apps.migration_cloud.api.webhook_dispatch  # noqa: F401

        for name in REGISTERED:
            self.assertIn(
                name, app.tasks,
                f"{name} is not registered — its beat entry is a silent no-op",
            )

    # ---- webhook dispatcher: outbound, gated OFF by default ----------------

    @override_settings(MIGRATION_CLOUD_WEBHOOK_DISPATCH_ENABLED=False)
    def test_webhook_deliver_due_task_noops_when_gate_off(self):
        from apps.migration_cloud.api import webhook_dispatch

        with mock.patch.object(webhook_dispatch, "deliver_due") as inner:
            result = webhook_dispatch.deliver_due_task()
        self.assertTrue(result.get("disabled"))
        self.assertEqual(result.get("delivered"), 0)
        inner.assert_not_called()  # the real outbound path never ran

    @override_settings(MIGRATION_CLOUD_WEBHOOK_DISPATCH_ENABLED=True)
    def test_webhook_deliver_due_task_runs_when_gate_on(self):
        from apps.migration_cloud.api import webhook_dispatch

        sentinel = {"processed": 0, "delivered": 0, "deferred": 0}
        with mock.patch.object(
            webhook_dispatch, "deliver_due", return_value=sentinel
        ) as inner:
            result = webhook_dispatch.deliver_due_task(batch_size=7)
        inner.assert_called_once_with(batch_size=7)
        self.assertIs(result, sentinel)

    # ---- nightly smoke: write-capable, kill-switched OFF by default --------

    @override_settings(MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED=False)
    def test_smoke_task_noops_when_kill_switch_off(self):
        from apps.migration_cloud.tasks_smoke import (
            run_smoke_against_synthetic_tenant,
        )

        result = run_smoke_against_synthetic_tenant()
        self.assertEqual(result.get("status"), "disabled")

    # ---- read-only tasks: run without raising ------------------------------

    def test_retention_audit_runs_read_only(self):
        from apps.migration_cloud.tasks_retention import (
            purge_completed_migration_bundles_audit_task,
        )

        result = purge_completed_migration_bundles_audit_task()
        self.assertIn("tenants_audited", result)

    def test_token_rotation_watchdog_runs(self):
        from apps.migration_cloud.tasks_alerts import token_rotation_watchdog

        result = token_rotation_watchdog()
        self.assertIn(result.get("status"), {"ran", "import_failed", "queryset_failed"})
