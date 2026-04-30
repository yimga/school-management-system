"""Relational visual workflow: compiler, executor, dispatch integration."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.graph_compiler import compile_workflow_to_dsl
from apps.automation.models import Workflow, WorkflowEdge, WorkflowNode
from apps.automation.visual_executor import (
    run_matching_visual_workflows,
    run_workflow,
    simulate_workflow,
)
from apps.schools.models import School
from apps.siteconfig.workflow_engine import dispatch_domain_triggers

User = get_user_model()


class VisualWorkflowEngineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Visual WF school",
            slug="visual-wf-school",
            subdomain="visual-wf-school",
            is_active=True,
        )

    def _minimal_notify_graph(self, wf: Workflow) -> None:
        t = WorkflowNode.objects.create(
            workflow=wf,
            external_id="t-root",
            kind=WorkflowNode.Kind.TRIGGER,
            config={},
            position={"x": 0, "y": 0},
        )
        a = WorkflowNode.objects.create(
            workflow=wf,
            external_id="a1",
            kind=WorkflowNode.Kind.ACTION,
            config={
                "action": {
                    "type": "notify",
                    "params": {"channel": "log", "body": "ping"},
                }
            },
            position={"x": 100, "y": 0},
        )
        WorkflowEdge.objects.create(workflow=wf, source=t, target=a)

    def test_compile_workflow_to_dsl_collects_notify_action(self):
        wf = Workflow.objects.create(
            school=self.school,
            name="Notify flow",
            trigger_event=Workflow.Trigger.STUDENT_CREATED,
            status=Workflow.Status.DRAFT,
        )
        self._minimal_notify_graph(wf)
        dsl = compile_workflow_to_dsl(wf)
        self.assertEqual(dsl.get("trigger"), Workflow.Trigger.STUDENT_CREATED)
        self.assertEqual(dsl.get("conditions"), [])
        actions = dsl.get("actions") or []
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].get("type"), "notify")

    def test_simulate_draft_workflow_dry_run_ok(self):
        wf = Workflow.objects.create(
            school=self.school,
            name="Draft sim",
            trigger_event=Workflow.Trigger.PAYMENT_RECEIVED,
            status=Workflow.Status.DRAFT,
        )
        self._minimal_notify_graph(wf)
        out = simulate_workflow(wf.pk, {"school_id": self.school.pk})
        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("dry_run"))

    def test_live_run_rejects_unpublished_workflow(self):
        wf = Workflow.objects.create(
            school=self.school,
            name="Draft live",
            trigger_event=Workflow.Trigger.ATTENDANCE_MARKED,
            status=Workflow.Status.DRAFT,
        )
        self._minimal_notify_graph(wf)
        out = run_workflow(
            wf.pk, {"school_id": self.school.pk}, dry_run=False
        )
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "workflow_not_published")

    def test_dispatch_domain_triggers_returns_visual_workflows(self):
        wf = Workflow.objects.create(
            school=self.school,
            name="Published push",
            trigger_event=Workflow.Trigger.REPORT_GENERATED,
            status=Workflow.Status.PUBLISHED,
            is_active=True,
        )
        self._minimal_notify_graph(wf)
        ctx = {"school_id": self.school.pk}
        bundle = dispatch_domain_triggers(
            self.school, Workflow.Trigger.REPORT_GENERATED, ctx
        )
        self.assertIn("visual_workflows", bundle)
        vis = bundle["visual_workflows"]
        self.assertEqual(len(vis), 1)
        self.assertTrue(vis[0].get("ok"))

    def test_run_matching_visual_workflows_respects_trigger_filter(self):
        wf = Workflow.objects.create(
            school=self.school,
            name="Other trigger",
            trigger_event=Workflow.Trigger.STUDENT_CREATED,
            status=Workflow.Status.PUBLISHED,
            is_active=True,
        )
        self._minimal_notify_graph(wf)
        rows = run_matching_visual_workflows(
            self.school,
            Workflow.Trigger.PAYMENT_RECEIVED,
            {"school_id": self.school.pk},
            dry_run=True,
        )
        self.assertEqual(rows, [])
