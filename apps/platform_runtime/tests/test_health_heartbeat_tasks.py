import os
from unittest.mock import patch

from django.test import TestCase

from apps.automation.models import AutomationExecutionLog


class HealthHeartbeatTaskTests(TestCase):
    def test_operator_heartbeat_skipped_without_env(self):
        from apps.platform_runtime.tasks import operator_visibility_heartbeat

        with patch.dict(
            os.environ, {"ENABLE_OPERATOR_VISIBILITY_HEARTBEAT_BEAT": ""}, clear=False
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

    def test_db_heartbeat_skipped_without_env(self):
        from apps.platform_runtime.tasks import database_connectivity_heartbeat

        with patch.dict(
            os.environ, {"ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT": ""}, clear=False
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

    def test_failure_trend_skipped_without_env(self):
        from apps.platform_runtime.tasks import automation_failure_trend_signal

        with patch.dict(
            os.environ, {"ENABLE_AUTOMATION_FAILURE_TREND_BEAT": ""}, clear=False
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
