"""Stuck-run remediation + safe-by-default unattended autopilot.

Covers Gap #1 (every STUCK run gets a one-click Retry card) and Gap #2 (the
5-min stuck sweep can auto-requeue a stalled run, but ONLY when a policy opts
in — shadow otherwise — and bounded by a per-school circuit breaker).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.platform_runtime.models import (
    WorkflowAutopilotApplyLog,
    WorkflowAutopilotPolicy,
    WorkflowRun,
)
from apps.platform_runtime.workflow_autopilot import try_auto_apply_on_stuck
from apps.platform_runtime.workflow_fix_handlers import resolve_stuck_remediation
from apps.schools.models import School


class StuckAutopilotMixin:
    def setUp(self):
        self.school = School.objects.create(
            name="Stuck Autopilot School",
            slug=f"stuck-{uuid.uuid4().hex[:8]}",
            subdomain=f"stuck{uuid.uuid4().hex[:6]}",
            is_active=False,
        )
        self.school_id = str(self.school.pk)

    def _disable_provision_autopilot(self):
        WorkflowAutopilotPolicy.objects.filter(
            workflow_key="tenant_school_provision",
            tenant_schema="",
        ).update(enabled=False)

    def _enable_provision_autopilot(self):
        WorkflowAutopilotPolicy.objects.filter(
            workflow_key="tenant_school_provision",
            tenant_schema="",
        ).update(enabled=True, allowed_auto_fix_kinds=["requeue_provision"])


def _stuck_run(
    *,
    workflow_key="tenant_school_provision",
    school_id="",
    status="stuck",
):
    return WorkflowRun.objects.create(
        workflow_key=workflow_key,
        workflow_label="Provision school",
        tenant_schema="",
        school_id=school_id,
        status=status,
        total_steps=5,
        current_step_ordinal=3,
        current_step_name="tenant_schema",
        expected_duration_seconds=180,
    )


class ResolveStuckRemediationTests(TestCase):
    def test_provisioning_gets_requeue_autofix(self):
        run = _stuck_run()
        rem = resolve_stuck_remediation(run=run)
        self.assertTrue(rem["auto_fix_available"])
        self.assertEqual(rem["auto_fix_kind"], "requeue_provision")
        self.assertTrue(rem["human_action"])
        self.assertEqual(rem["reason"], "stuck")

    def test_unknown_workflow_gets_explain_only(self):
        run = _stuck_run(workflow_key="some_other_workflow")
        rem = resolve_stuck_remediation(run=run)
        self.assertFalse(rem["auto_fix_available"])
        self.assertTrue(rem["human_action"])


class TryAutoApplyOnStuckTests(StuckAutopilotMixin, TestCase):
    def test_shadow_when_no_policy(self):
        """Safe-by-default: no enabling policy => propose only, mutate nothing."""
        self._disable_provision_autopilot()
        run = _stuck_run(school_id=self.school_id)
        run.suggested_remediation = resolve_stuck_remediation(run=run)
        run.save(update_fields=["suggested_remediation"])

        with mock.patch(
            "apps.schools.tasks.dispatch_provision_school"
        ) as dispatch:
            out = try_auto_apply_on_stuck(run_pk=run.pk)

        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "policy_disabled")
        self.assertEqual(out["mode"], "shadow")
        dispatch.assert_not_called()
        log = WorkflowAutopilotApplyLog.objects.get(run_id=run.pk)
        self.assertEqual(log.outcome, "shadow")
        self.assertTrue(log.autopilot)

    def test_applies_when_policy_enabled(self):
        self._enable_provision_autopilot()
        run = _stuck_run(school_id=self.school_id)
        run.suggested_remediation = resolve_stuck_remediation(run=run)
        run.save(update_fields=["suggested_remediation"])

        with mock.patch(
            "apps.schools.tasks.dispatch_provision_school"
        ) as dispatch:
            out = try_auto_apply_on_stuck(run_pk=run.pk)

        self.assertTrue(out["applied"])
        self.assertEqual(out["kind"], "requeue_provision")
        dispatch.assert_called_once()
        log = WorkflowAutopilotApplyLog.objects.get(run_id=run.pk, outcome="applied")
        self.assertTrue(log.autopilot)

    def test_circuit_breaker_opens_after_max_attempts(self):
        self._enable_provision_autopilot()
        for _ in range(3):
            # Prior attempts are FINALIZED (failed), not concurrently active — the
            # uniq_active_provision_run_per_school constraint allows only one
            # running/stuck run per school+key. The circuit counts apply-logs
            # across all runs for the school+key regardless of run status.
            r = _stuck_run(school_id=self.school_id, status="failed")
            WorkflowAutopilotApplyLog.objects.create(
                run_id=r.pk,
                workflow_key="tenant_school_provision",
                auto_fix_kind="requeue_provision",
                outcome="applied",
                autopilot=True,
            )
        run = _stuck_run(school_id=self.school_id)
        run.suggested_remediation = resolve_stuck_remediation(run=run)
        run.save(update_fields=["suggested_remediation"])

        with mock.patch(
            "apps.schools.tasks.dispatch_provision_school"
        ) as dispatch:
            out = try_auto_apply_on_stuck(run_pk=run.pk)

        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "circuit_open")
        dispatch.assert_not_called()

    def test_not_stuck_run_is_ignored(self):
        run = _stuck_run(school_id=self.school_id, status="running")
        out = try_auto_apply_on_stuck(run_pk=run.pk)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "not_stuck")


class StuckSweepIntegrationTests(StuckAutopilotMixin, TestCase):
    def test_sweep_marks_stuck_and_stamps_retry_card(self):
        from apps.platform_runtime.tasks import workflow_stuck_alert_sweep_task

        run = _stuck_run(school_id=self.school_id, status="running")
        WorkflowRun.objects.filter(pk=run.pk).update(
            last_heartbeat_at=timezone.now() - timedelta(seconds=600)
        )

        with mock.patch(
            "apps.platform_runtime.event_bus.publish_event"
        ), mock.patch("apps.schools.tasks.dispatch_provision_school"):
            result = workflow_stuck_alert_sweep_task()

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["published"], 1)
        run.refresh_from_db()
        self.assertEqual(run.status, "stuck")
        self.assertTrue(run.suggested_remediation.get("auto_fix_available"))
        self.assertEqual(
            run.suggested_remediation.get("auto_fix_kind"), "requeue_provision"
        )
