"""Move 2 — visual workflow versioning tests."""

from __future__ import annotations

from django.test import TestCase

from apps.automation import visual_workflow_versioning as vwv
from apps.automation.workflow_graph_models import (
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowRunLog,
    WorkflowVersion,
)
from apps.schools.models import School


class VisualWorkflowVersioningTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(slug="m2vs", name="VWS", subdomain="m2vs")
        self.workflow = Workflow.objects.create(
            school=self.school, name="On payment", trigger_event="payment_received"
        )
        self.n1 = WorkflowNode.objects.create(workflow=self.workflow, external_id="t1", kind="trigger")
        self.n2 = WorkflowNode.objects.create(workflow=self.workflow, external_id="a1", kind="action")
        WorkflowEdge.objects.create(workflow=self.workflow, source=self.n1, target=self.n2)

    def test_publish_snapshots_graph(self):
        v = vwv.publish_visual_workflow_version(self.workflow, notes="first cut")
        self.assertEqual(v.version_number, 1)
        self.assertTrue(v.is_current)
        snapshot = v.graph_snapshot
        self.assertEqual(len(snapshot["nodes"]), 2)
        self.assertEqual(len(snapshot["edges"]), 1)
        self.assertEqual(snapshot["trigger_event"], "payment_received")
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.status, Workflow.Status.PUBLISHED)
        self.assertEqual(self.workflow.current_version, 1)

    def test_publish_v2_supersedes_v1(self):
        v1 = vwv.publish_visual_workflow_version(self.workflow)
        WorkflowNode.objects.create(workflow=self.workflow, external_id="a2", kind="action")
        v2 = vwv.publish_visual_workflow_version(self.workflow)
        v1.refresh_from_db()
        self.assertFalse(v1.is_current)
        self.assertTrue(v2.is_current)
        self.assertEqual(v2.version_number, 2)
        self.assertEqual(len(v2.graph_snapshot["nodes"]), 3)

    def test_bind_run_pins_to_current_version(self):
        v1 = vwv.publish_visual_workflow_version(self.workflow)
        run = WorkflowRunLog.objects.create(workflow=self.workflow, trigger_event="payment_received")
        vwv.bind_run_to_current_version(run)
        run.refresh_from_db()
        self.assertEqual(run.workflow_version_id, v1.pk)
