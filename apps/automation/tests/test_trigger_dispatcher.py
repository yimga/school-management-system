"""Tests for the trigger dispatcher."""

from __future__ import annotations

from django.test import TestCase

from apps.automation.models import AutomationExecutionLog
from apps.automation.trigger_dispatcher import (
    UnknownTriggerError,
    clear_registry_for_tests,
    fire,
    register_handler,
    registered_handlers,
)


class TriggerDispatcherTests(TestCase):
    def setUp(self):
        clear_registry_for_tests()

    def tearDown(self):
        clear_registry_for_tests()

    def test_register_unknown_trigger_raises(self):
        with self.assertRaises(UnknownTriggerError):
            @register_handler("not_a_real_trigger_key")
            def _h(payload, school, actor):
                return None

    def test_register_and_fire_invokes_handler(self):
        captured: list[dict] = []

        @register_handler("payment_success")
        def my_handler(payload, school, actor):
            captured.append(payload)
            return {"records_processed": 1}

        results = fire("payment_success", {"amount_cents": 1000}, school=None, actor=None)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "success")
        self.assertEqual(captured, [{"amount_cents": 1000}])

    def test_handler_failure_recorded_and_others_still_run(self):
        @register_handler("payment_success")
        def fails(payload, school, actor):
            raise RuntimeError("boom")

        @register_handler("payment_success")
        def succeeds(payload, school, actor):
            return {"ok": True}

        results = fire("payment_success", {}, school=None, actor=None)
        self.assertEqual(len(results), 2)
        statuses = sorted([r["status"] for r in results])
        self.assertEqual(statuses, ["failed", "success"])

    def test_fire_writes_execution_log_rows(self):
        @register_handler("attendance_saved")
        def my_handler(payload, school, actor):
            return {"records_processed": 3}

        before = AutomationExecutionLog.objects.count()
        fire("attendance_saved", {}, school=None, actor=None)
        after = AutomationExecutionLog.objects.count()
        self.assertEqual(after - before, 1)
        last = AutomationExecutionLog.objects.order_by("-id").first()
        self.assertIn("attendance_saved", last.task_name)
        self.assertEqual(last.records_processed, 3)
        self.assertEqual(last.status, AutomationExecutionLog.Status.SUCCESS)

    def test_fire_unknown_trigger_raises(self):
        with self.assertRaises(UnknownTriggerError):
            fire("not_a_trigger", {}, school=None, actor=None)

    def test_raise_on_first_error_propagates(self):
        @register_handler("report_generated")
        def fails(payload, school, actor):
            raise ValueError("nope")

        with self.assertRaises(ValueError):
            fire("report_generated", {}, school=None, actor=None, raise_on_first_error=True)

    def test_registered_handlers_returns_immutable_view(self):
        @register_handler("marks_submitted")
        def h(payload, school, actor):
            return None

        snapshot = registered_handlers("marks_submitted")
        snapshot.append(lambda p, s, a: None)
        # Snapshot mutation must not affect the registry
        self.assertEqual(len(registered_handlers("marks_submitted")), 1)
