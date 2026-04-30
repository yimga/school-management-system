"""School-authored automation workflows: engine, logs, simulation parity."""

from unittest.mock import patch

from django.test import TestCase

from apps.schools.models import School
from apps.siteconfig import workflow_engine as workflow_engine_mod
from apps.siteconfig.models_workflow import (
    SchoolAutomationWorkflow,
    SchoolWorkflowExecutionLog,
)
from apps.siteconfig.workflow_engine import (
    get_school_workflow_dsl,
    retry_failed_actions_from_log,
    run_school_workflow,
    run_school_workflows_for_trigger,
    simulate_dsl,
    validate_school_workflow_dsl,
)


class SchoolAutomationEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="School Automation Test",
            slug="sat-wf",
            subdomain="sat-wf",
            is_active=True,
        )

    def test_validate_requires_trigger_and_action_types(self):
        errs = validate_school_workflow_dsl({"trigger": "", "conditions": [], "actions": []})
        self.assertTrue(any("trigger" in e for e in errs))
        errs2 = validate_school_workflow_dsl(
            {
                "trigger": "student_updated",
                "conditions": [{}],
                "actions": [{"type": ""}],
            }
        )
        self.assertTrue(len(errs2) >= 2)

    def test_simulate_includes_expected_output(self):
        sim = simulate_dsl(
            {
                "trigger": "manual",
                "conditions": [],
                "actions": [{"type": "notify", "params": {"channel": "log", "body": "x"}}],
            },
            {},
            school=self.school,
        )
        self.assertTrue(sim.get("expected_output"))
        self.assertEqual(sim["expected_output"][0].get("action"), "notify")

    def test_graph_validation_trigger_mismatch(self):
        errs = validate_school_workflow_dsl(
            {
                "trigger": "student_updated",
                "conditions": [{"field": "x", "op": "eq", "value": 1}],
                "actions": [{"type": "notify", "params": {"channel": "log"}}],
                "graph": {
                    "nodes": [
                        {"id": "t1", "kind": "trigger", "actionType": "payment_received"},
                        {"id": "c1", "kind": "condition", "actionType": ""},
                        {"id": "a1", "kind": "action", "actionType": "notify"},
                    ],
                    "edges": [
                        {"from": "t1", "to": "c1"},
                        {"from": "c1", "to": "a1"},
                    ],
                },
            }
        )
        self.assertTrue(any("visual graph trigger" in e for e in errs))

    def test_simulate_matches_execution_notify_path(self):
        wf = SchoolAutomationWorkflow.objects.create(
            school=self.school,
            name="Notify when score high",
            trigger="grade_submitted",
            conditions=[{"field": "score", "op": "gte", "value": 5}],
            actions=[{"type": "notify", "params": {"channel": "log", "body": "ok"}}],
            status=SchoolAutomationWorkflow.Status.PUBLISHED,
        )
        dsl = get_school_workflow_dsl(wf)
        ctx = {"score": 10}
        sim = simulate_dsl(dsl, ctx, school=self.school)
        self.assertTrue(sim["conditions_passed"])
        self.assertEqual(len(sim["planned_actions"]), 1)
        self.assertEqual(sim["planned_actions"][0].get("type"), "notify")

        r = run_school_workflow(wf, ctx)
        self.assertTrue(r.get("ok"))
        self.assertTrue(r["conditions_passed"])
        self.assertEqual(len(r["actions_run"]), 1)
        self.assertEqual(sim["planned_actions"][0]["type"], r["actions_run"][0]["type"])

    def test_execution_log_created(self):
        wf = SchoolAutomationWorkflow.objects.create(
            school=self.school,
            name="Log test",
            trigger="payment_received",
            conditions=[],
            actions=[{"type": "notify", "params": {"channel": "log", "body": "paid"}}],
            status=SchoolAutomationWorkflow.Status.PUBLISHED,
        )
        run_school_workflow(wf, {"amount": 1})
        self.assertEqual(
            SchoolWorkflowExecutionLog.objects.filter(workflow=wf).count(),
            1,
        )

    def test_run_school_workflows_for_trigger(self):
        SchoolAutomationWorkflow.objects.create(
            school=self.school,
            name="Att",
            trigger="attendance_marked",
            conditions=[{"field": "present", "op": "eq", "value": True}],
            actions=[{"type": "notify", "params": {"channel": "log", "body": "x"}}],
            status=SchoolAutomationWorkflow.Status.PUBLISHED,
        )
        results = run_school_workflows_for_trigger(
            self.school,
            "attendance_marked",
            {"present": True},
        )
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].get("ok"))

    def test_retry_failed_actions_from_log(self):
        wf = SchoolAutomationWorkflow.objects.create(
            school=self.school,
            name="Retry test",
            trigger="manual",
            conditions=[],
            actions=[{"type": "notify", "params": {"channel": "log"}}],
            status=SchoolAutomationWorkflow.Status.PUBLISHED,
        )
        log = SchoolWorkflowExecutionLog.objects.create(
            workflow=wf,
            conditions_passed=True,
            actions_run=[{"type": "notify", "error": "temporary"}],
            context_snapshot={"student_id": 1},
            context_keys=["student_id"],
            run_status=SchoolWorkflowExecutionLog.RunStatus.FAILED,
            error_message="temporary",
        )
        with patch.object(
            workflow_engine_mod,
            "run_actions",
            return_value=[{"type": "notify", "run_at": "2000-01-01T00:00:00+00:00"}],
        ):
            out = retry_failed_actions_from_log(log.pk)
        self.assertTrue(out.get("ok"))
        log.refresh_from_db()
        self.assertEqual(log.run_status, SchoolWorkflowExecutionLog.RunStatus.SUCCESS)
        self.assertEqual(log.retry_count, 1)
        self.assertFalse(any(isinstance(r, dict) and r.get("error") for r in log.actions_run))

    def test_date_condition_op(self):
        from django.utils import timezone

        dsl = {
            "trigger": "x",
            "conditions": [
                {
                    "field": "due_at",
                    "op": "date_on_or_after",
                    "value": "2026-01-01T00:00:00",
                }
            ],
            "actions": [],
        }
        self.assertTrue(
            simulate_dsl(dsl, {"due_at": timezone.now().isoformat()}, school=self.school)[
                "conditions_passed"
            ]
        )
