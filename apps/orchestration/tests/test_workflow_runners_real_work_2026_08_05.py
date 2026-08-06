"""Must-fire tests: orchestration runners do REAL work, not just count (2026-08-05).

Each test FAILS against the pre-fix code:
  * FeeFollowUpRunner only counted reminders due and never sent → these assert it
    drives the real sender and honours dry_run (simulation must not send).
  * ApprovalChainRunner echoed chain_id and did nothing → asserts a real pending
    count.
  * orchestration.trigger_runs_for_definition was orphaned (no scheduler) → asserts
    the new opt-in periodic auto-trigger fires enabled definitions and respects
    cadence.
"""

from __future__ import annotations

import uuid
from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.automation.models import AutomationApprovalQueue
from apps.orchestration.models import OrchestrationRun, ProcessDefinition
from apps.orchestration.runners import (
    ApprovalChainRunner,
    FeeFollowUpRunner,
)


class FeeFollowUpRunnerSendsTests(SimpleTestCase):
    """fee_follow_up must actually SEND, not just count."""

    def test_run_step_drives_the_real_sender_in_tenant_context(self):
        run = OrchestrationRun(school_id=uuid.uuid4())  # unsaved, no DB
        with mock.patch(
            "apps.finance.tasks.send_payment_reminders_task"
        ) as mock_task:
            mock_task.apply.return_value.get.return_value = {
                "sent": 3,
                "count": 5,
                "channels": {"email": 3},
            }
            out = FeeFollowUpRunner(run=run).run_step()
        mock_task.apply.assert_called_once_with(
            kwargs={"school_id": str(run.school_id), "dry_run": False}
        )
        # The pre-fix runner returned only "reminders_due" and never called a sender.
        self.assertEqual(out["reminders_sent"], 3)
        self.assertEqual(out["reminders_due"], 5)
        self.assertEqual(out["channels"], {"email": 3})

    def test_dry_run_counts_and_never_sends(self):
        """Simulation path must have NO side effects (no real sends)."""
        run = OrchestrationRun(school_id=uuid.uuid4())
        runner = FeeFollowUpRunner(run=run)
        runner.dry_run = True
        with mock.patch(
            "apps.finance.tasks.send_payment_reminders_task"
        ) as mock_task, mock.patch.object(
            FeeFollowUpRunner, "_count_due", return_value=7
        ):
            out = runner.run_step()
        mock_task.apply.assert_not_called()
        self.assertEqual(out["reminders_sent"], 0)
        self.assertEqual(out["reminders_due"], 7)
        self.assertTrue(out["dry_run"])

    def test_no_school_bound_sends_nothing(self):
        run = OrchestrationRun(school_id=None)
        with mock.patch(
            "apps.finance.tasks.send_payment_reminders_task"
        ) as mock_task:
            out = FeeFollowUpRunner(run=run).run_step()
        mock_task.apply.assert_not_called()
        self.assertEqual(out["reminders_sent"], 0)


class ApprovalChainReadinessTests(TestCase):
    """approval_chain must report a real pending-approval backlog (was a no-op)."""

    def test_run_step_counts_pending_approvals(self):
        defn = ProcessDefinition.objects.create(code="approval_chain", name="Approval chain")
        run = OrchestrationRun.objects.create(definition=defn, school=None)
        # school is nullable; a school-less run counts all pending rows.
        AutomationApprovalQueue.objects.create(
            automation_type="x", status=AutomationApprovalQueue.Status.PENDING
        )
        AutomationApprovalQueue.objects.create(
            automation_type="y", status=AutomationApprovalQueue.Status.PENDING
        )
        AutomationApprovalQueue.objects.create(
            automation_type="z", status=AutomationApprovalQueue.Status.APPROVED
        )
        out = ApprovalChainRunner(run=run).run_step()
        self.assertEqual(out["pending_approvals"], 2)
        self.assertTrue(out["requires_action"])


class AutoTriggerSchedulerTests(TestCase):
    """The opt-in recurring auto-trigger wires the orphaned task into the scheduler."""

    def test_registered_in_default_jobs(self):
        from apps.platform_runtime import periodic

        # Force a fresh install (ensure_default_jobs is guarded by
        # _DEFAULTS_INSTALLED; clearing the registry alone would early-return).
        periodic._REGISTRY.clear()
        periodic._DEFAULTS_INSTALLED = False
        periodic.ensure_default_jobs()
        self.assertIn("orchestration.auto_trigger", periodic._REGISTRY)

    def test_fires_only_enabled_definitions_and_respects_cadence(self):
        from apps.platform_runtime.periodic import _run_orchestration_auto_trigger

        ProcessDefinition.objects.create(
            code="fee_follow_up",
            name="Fee follow-up",
            config_schema={"auto_trigger": {"enabled": True, "cadence_hours": 24}},
        )
        ProcessDefinition.objects.create(
            code="admissions", name="Admissions", config_schema={}
        )  # not opted in

        with mock.patch("django.core.management.call_command") as mock_cmd:
            result = _run_orchestration_auto_trigger()
        self.assertEqual(result["auto_triggered"], ["fee_follow_up"])
        mock_cmd.assert_called_once_with(
            "trigger_orchestration_runs", code="fee_follow_up"
        )

        # cadence gate: an immediate second tick must NOT re-fire.
        defn = ProcessDefinition.objects.get(code="fee_follow_up")
        self.assertIn("last_triggered_at", defn.config_schema["auto_trigger"])
        with mock.patch("django.core.management.call_command") as mock_cmd2:
            result2 = _run_orchestration_auto_trigger()
        self.assertEqual(result2["auto_triggered"], [])
        mock_cmd2.assert_not_called()
