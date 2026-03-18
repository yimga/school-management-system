from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.automation.models import AutomationExecutionLog


class RunPayrollCycleCommandTests(TestCase):
    @patch("apps.payroll.management.commands.run_payroll_cycle.generate_payslips")
    @patch(
        "apps.payroll.management.commands.run_payroll_cycle.PayrollRun.objects.get_or_create"
    )
    @patch(
        "apps.payroll.management.commands.run_payroll_cycle.get_active_payroll_profile"
    )
    def test_command_logs_success(
        self, mock_profile, mock_get_or_create, mock_generate
    ):
        mock_profile.return_value = SimpleNamespace(id=1)
        mock_run = SimpleNamespace(id=77)
        mock_get_or_create.return_value = (mock_run, True)
        mock_generate.return_value = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

        call_command("run_payroll_cycle", year=2026, month=2)

        log = AutomationExecutionLog.objects.filter(
            task_name="payroll.run_payroll_cycle"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.SUCCESS)
        self.assertEqual(log.records_processed, 2)
        self.assertEqual(log.execution_summary.get("payroll_run_id"), 77)

    @patch(
        "apps.payroll.management.commands.run_payroll_cycle.get_active_payroll_profile"
    )
    def test_command_logs_failed_when_profile_missing(self, mock_profile):
        mock_profile.return_value = None

        with self.assertRaises(CommandError):
            call_command("run_payroll_cycle")

        log = AutomationExecutionLog.objects.filter(
            task_name="payroll.run_payroll_cycle"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        self.assertIn("No active compliance profile", log.error_message)
