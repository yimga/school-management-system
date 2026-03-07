"""
Phase 7 regression sanity checks for automation commands.
"""

from io import StringIO

from django.core.management import call_command, get_commands
from django.test import TestCase


class AutomationCommandAvailabilityTest(TestCase):
    def test_core_automation_commands_registered(self):
        commands = get_commands()
        self.assertIn("run_payroll_cycle", commands)
        self.assertIn("send_payment_reminders", commands)
        self.assertIn("apply_split_late_fees", commands)
        self.assertIn("run_phase7_checks", commands)


class PaymentReminderCommandSmokeTest(TestCase):
    def test_send_payment_reminders_dry_run_executes(self):
        output = StringIO()
        call_command("send_payment_reminders", "--dry-run", stdout=output)
        text = output.getvalue()
        self.assertTrue(
            "No reminders" in text or "[DRY RUN]" in text or "Would send" in text,
            msg=f"Unexpected command output: {text}",
        )
