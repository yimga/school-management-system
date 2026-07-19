import os
from unittest.mock import patch

from django.test import TestCase

from apps.automation.models import AutomationExecutionLog


class HealthHeartbeatTaskTests(TestCase):
    def test_operator_heartbeat_skipped_when_explicitly_disabled(self):
        from apps.platform_runtime.tasks import operator_visibility_heartbeat

        with patch.dict(
            os.environ, {"ENABLE_OPERATOR_VISIBILITY_HEARTBEAT_BEAT": "0"}, clear=False
        ):
            out = operator_visibility_heartbeat()
        self.assertEqual(out, "skipped")

    @patch.dict(os.environ, {"ENABLE_OPERATOR_VISIBILITY_HEARTBEAT_BEAT": "1"})
    def test_operator_heartbeat_writes_execution_log(self):
        from apps.platform_runtime.tasks import operator_visibility_heartbeat

        operator_visibility_heartbeat()
        log = AutomationExecutionLog.objects.get(
            task_name="platform.operator_visibility_heartbeat"
        )
        self.assertEqual(log.status, AutomationExecutionLog.Status.SUCCESS)
        self.assertTrue(log.execution_summary.get("ok"))

    def test_operator_heartbeat_runs_by_default(self):
        from apps.platform_runtime.tasks import operator_visibility_heartbeat

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENABLE_OPERATOR_VISIBILITY_HEARTBEAT_BEAT", None)
            out = operator_visibility_heartbeat()
        self.assertEqual(out, "ok")

    def test_db_heartbeat_skipped_when_explicitly_disabled(self):
        from apps.platform_runtime.tasks import database_connectivity_heartbeat

        with patch.dict(
            os.environ, {"ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT": "0"}, clear=False
        ):
            out = database_connectivity_heartbeat()
        self.assertEqual(out, "skipped")

    @patch.dict(os.environ, {"ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT": "1"})
    def test_db_heartbeat_success_writes_log(self):
        from apps.platform_runtime.tasks import database_connectivity_heartbeat

        database_connectivity_heartbeat()
        log = AutomationExecutionLog.objects.get(
            task_name="platform.database_connectivity_heartbeat"
        )
        self.assertEqual(log.status, AutomationExecutionLog.Status.SUCCESS)

    @patch.dict(os.environ, {"ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT": "1"})
    @patch(
        "apps.platform_runtime.tasks._ensure_db_connection",
        side_effect=RuntimeError("db down"),
    )
    def test_db_heartbeat_failure_writes_failed_log(self, _mock_conn):
        from apps.platform_runtime.tasks import database_connectivity_heartbeat

        out = database_connectivity_heartbeat()
        self.assertIn("failed", out)
        log = AutomationExecutionLog.objects.get(
            task_name="platform.database_connectivity_heartbeat"
        )
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)

    def test_failure_trend_skipped_when_explicitly_disabled(self):
        from apps.platform_runtime.tasks import automation_failure_trend_signal

        with patch.dict(
            os.environ, {"ENABLE_AUTOMATION_FAILURE_TREND_BEAT": "0"}, clear=False
        ):
            out = automation_failure_trend_signal()
        self.assertEqual(out, "skipped")

    @patch.dict(
        os.environ,
        {
            "ENABLE_AUTOMATION_FAILURE_TREND_BEAT": "1",
            "AUTOMATION_FAILURE_TREND_MAX_FAILURES": "1",
            "AUTOMATION_FAILURE_TREND_LOOKBACK_HOURS": "24",
        },
    )
    def test_failure_trend_breach_marks_failed(self):
        from apps.platform_runtime.tasks import automation_failure_trend_signal

        AutomationExecutionLog.objects.create(
            task_name="any.task",
            status=AutomationExecutionLog.Status.FAILED,
            execution_type=AutomationExecutionLog.ExecutionType.SCHEDULED,
        )
        AutomationExecutionLog.objects.create(
            task_name="any.task2",
            status=AutomationExecutionLog.Status.FAILED,
            execution_type=AutomationExecutionLog.ExecutionType.SCHEDULED,
        )
        out = automation_failure_trend_signal()
        self.assertEqual(out, "failed")
        log = AutomationExecutionLog.objects.get(
            task_name="platform.automation_failure_trend_signal"
        )
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        self.assertTrue(log.execution_summary.get("breached"))

    @patch.dict(
        os.environ,
        {
            "ENABLE_AUTOMATION_FAILURE_TREND_BEAT": "1",
            "AUTOMATION_FAILURE_TREND_MAX_FAILURES": "10",
            "AUTOMATION_FAILURE_TREND_LOOKBACK_HOURS": "24",
        },
    )
    def test_failure_trend_under_threshold_succeeds(self):
        """When recent failures stay at or below max_failures, signal is SUCCESS (not breached)."""
        from apps.platform_runtime.tasks import automation_failure_trend_signal

        AutomationExecutionLog.objects.create(
            task_name="any.task",
            status=AutomationExecutionLog.Status.FAILED,
            execution_type=AutomationExecutionLog.ExecutionType.SCHEDULED,
        )
        out = automation_failure_trend_signal()
        self.assertEqual(out, "ok")
        log = AutomationExecutionLog.objects.get(
            task_name="platform.automation_failure_trend_signal"
        )
        self.assertEqual(log.status, AutomationExecutionLog.Status.SUCCESS)
        self.assertFalse(log.execution_summary.get("breached"))

    @patch.dict(
        os.environ,
        {
            "ENABLE_AUTOMATION_FAILURE_TREND_BEAT": "1",
            "AUTOMATION_FAILURE_TREND_MAX_FAILURES": "not-a-number",
            "AUTOMATION_FAILURE_TREND_LOOKBACK_HOURS": "also-bad",
        },
    )
    def test_failure_trend_invalid_env_integers_use_defaults(self):
        """Non-numeric operator env must not crash the beat (bucket C)."""
        from apps.platform_runtime.tasks import automation_failure_trend_signal

        out = automation_failure_trend_signal()
        self.assertEqual(out, "ok")
        log = AutomationExecutionLog.objects.get(
            task_name="platform.automation_failure_trend_signal"
        )
        self.assertEqual(log.execution_summary.get("lookback_hours"), 24)
        self.assertEqual(log.execution_summary.get("max_failures"), 10)

    def test_health_beats_are_on_celery_schedule_by_default(self):
        """Metric 22 — three secret-free health beats must not be dead-by-deferral."""
        from django.conf import settings

        keys = set(getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {})
        self.assertIn("operator-visibility-heartbeat-daily", keys)
        self.assertIn("database-connectivity-heartbeat-daily", keys)
        self.assertIn("automation-failure-trend-daily", keys)
