"""Must-fire tests: Automation Studio panes are honest + real (2026-08-05).

Pre-fix, four automation panes were static explainer prose presented as
first-class features, and the SHIPPED visual builder was described as available
"when productized". These assert:
  * the visual builder is surfaced as available with a real designer deep-link
    and the "when productized" copy is gone;
  * NL-workflow and staged activation are honestly flagged roadmap;
  * conflict detection and replay/rollback run over REAL tenant data.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from apps.automation.models import Workflow, WorkflowEdge, WorkflowNode, WorkflowRunLog
from apps.schools.models import School
from apps.studio_os.automation_panes import (
    build_workflow_conflict_report,
    recent_workflow_runs,
)
from apps.studio_os.views import _automation_explainer_context


class AutomationExplainerHonestyTests(SimpleTestCase):
    def test_visual_builder_is_available_and_links_the_real_designer(self):
        ctx = _automation_explainer_context("visual_builder")
        self.assertEqual(ctx["maturity"], "available")
        self.assertTrue(ctx["primary_url"])  # real designer deep-link
        self.assertNotIn("productized", ctx["body"].lower())

    def test_nl_workflow_is_honestly_roadmap(self):
        ctx = _automation_explainer_context("nl_workflow")
        self.assertEqual(ctx["maturity"], "roadmap")

    def test_staged_is_honestly_roadmap(self):
        ctx = _automation_explainer_context("staged")
        self.assertEqual(ctx["maturity"], "roadmap")

    def test_conflict_is_available_with_deep_link(self):
        ctx = _automation_explainer_context("conflict")
        self.assertEqual(ctx["maturity"], "available")
        self.assertTrue(ctx["primary_url"])


class ConflictReportTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Conflict school", slug="conflict-school", subdomain="conflict-school"
        )

    def _publish(self, name, trigger):
        wf = Workflow.objects.create(
            school=self.school,
            name=name,
            trigger_event=trigger,
            status=Workflow.Status.PUBLISHED,
            is_active=True,
        )
        return wf

    def test_detects_trigger_overlap(self):
        # Two live workflows firing on the same event = a real conflict.
        self._publish("A", Workflow.Trigger.STUDENT_CREATED)
        self._publish("B", Workflow.Trigger.STUDENT_CREATED)
        report = build_workflow_conflict_report(SimpleNamespace(school=self.school))
        self.assertTrue(report["available"])
        self.assertFalse(report["clean"])
        self.assertEqual(len(report["trigger_overlaps"]), 1)
        self.assertEqual(report["trigger_overlaps"][0]["count"], 2)

    def test_no_school_degrades_gracefully(self):
        report = build_workflow_conflict_report(SimpleNamespace(school=None))
        self.assertFalse(report["available"])


class RecentRunsTests(TestCase):
    def test_lists_real_runs_for_the_tenant(self):
        school = School.objects.create(
            name="Runs school", slug="runs-school", subdomain="runs-school"
        )
        wf = Workflow.objects.create(
            school=school,
            name="Flow",
            trigger_event=Workflow.Trigger.PAYMENT_RECEIVED,
            status=Workflow.Status.PUBLISHED,
        )
        WorkflowRunLog.objects.create(
            workflow=wf, trigger_event="payment_received", status="success"
        )
        data = recent_workflow_runs(SimpleNamespace(school=school))
        self.assertTrue(data["available"])
        self.assertEqual(data["count"], 1)

    def test_no_school_degrades_gracefully(self):
        data = recent_workflow_runs(SimpleNamespace(school=None))
        self.assertFalse(data["available"])
        self.assertEqual(data["runs"], [])
