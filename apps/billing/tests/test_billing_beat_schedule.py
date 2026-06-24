"""B1: the platform billing lifecycle runs on a Celery beat, not just by hand.

Previously invoicing only advanced when an operator ran the management command.
A daily beat advances every subscription's billing state on its own cycle.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.billing.beat_schedule import (
    get_billing_beat_schedule,
    install_billing_beat_schedule,
)


class _FakeConf:
    def __init__(self):
        self.beat_schedule: dict = {}


class _FakeApp:
    def __init__(self):
        self.conf = _FakeConf()


class BillingBeatScheduleTests(SimpleTestCase):
    def test_schedule_has_daily_lifecycle_entry(self):
        sched = get_billing_beat_schedule()
        self.assertIn("platform-billing-lifecycle-daily", sched)
        self.assertEqual(
            sched["platform-billing-lifecycle-daily"]["task"],
            "apps.billing.run_platform_billing_lifecycle",
        )

    def test_schedule_has_holding_rollup_entry(self):
        sched = get_billing_beat_schedule()
        self.assertIn("holding-currency-rollup-daily", sched)
        self.assertEqual(
            sched["holding-currency-rollup-daily"]["task"],
            "apps.billing.materialize_holding_currency_rollups",
        )

    def test_install_adds_entry(self):
        app = _FakeApp()
        installed = install_billing_beat_schedule(app)
        self.assertIn("platform-billing-lifecycle-daily", installed)
        self.assertIn("platform-billing-lifecycle-daily", app.conf.beat_schedule)

    def test_install_preserves_operator_config(self):
        app = _FakeApp()
        app.conf.beat_schedule["platform-billing-lifecycle-daily"] = {"task": "operator.custom"}
        installed = install_billing_beat_schedule(app)
        self.assertNotIn("platform-billing-lifecycle-daily", installed)
        self.assertEqual(
            app.conf.beat_schedule["platform-billing-lifecycle-daily"]["task"],
            "operator.custom",
        )

    def test_disable_env_yields_empty_schedule(self):
        with mock.patch.dict("os.environ", {"RMC_PLATFORM_BILLING_BEAT_DISABLED": "1"}):
            self.assertEqual(get_billing_beat_schedule(), {})

    def test_task_is_importable(self):
        from apps.billing.tasks_billing_lifecycle import (
            run_platform_billing_lifecycle_task,
        )

        self.assertIsNotNone(run_platform_billing_lifecycle_task)

    def test_holding_rollup_task_is_importable(self):
        from apps.billing.tasks_holding_rollup import (
            materialize_holding_currency_rollups_task,
        )

        self.assertIsNotNone(materialize_holding_currency_rollups_task)
