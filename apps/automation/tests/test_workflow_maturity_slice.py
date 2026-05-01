"""
Workflow engine maturity slice: trigger catalog, validation, conditions, simulation parity, templates JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.test import TestCase

from apps.automation.graph_compiler import compile_workflow_to_dsl
from apps.automation.graph_validate import validate_workflow_for_publish
from apps.automation.models import Workflow, WorkflowEdge, WorkflowNode
from apps.automation.visual_executor import run_workflow
from apps.siteconfig.workflow_engine import evaluate_conditions, simulate_dsl
from apps.schools.models import School


class WorkflowMaturityCatalogTests(TestCase):
    def test_trigger_enum_covers_core_catalog(self):
        codes = {c[0] for c in Workflow.Trigger.choices}
        for key in (
            "attendance_saved",
            "marks_submitted",
            "payment_success",
            "payment_failed",
            "report_generated",
            "student_risk_detected",
            "app_installed",
            "payment_received",
        ):
            self.assertIn(key, codes)

    def test_status_enum_includes_paused(self):
        self.assertIn(
            Workflow.Status.PAUSED,
            {c[0] for c in Workflow.Status.choices},
        )


class WorkflowConditionOpsTests(TestCase):
    def test_role_in_and_feature_enabled(self):
        ctx = {
            "actor_role": "TEACHER",
            "school_features": {"risk_alerts": True},
        }
        self.assertTrue(
            evaluate_conditions(
                [{"field": "", "op": "role_in", "value": ["TEACHER", "ADMIN"]}],
                ctx,
            )
        )
        self.assertFalse(
            evaluate_conditions(
                [{"field": "", "op": "role_in", "value": ["ADMIN"]}],
                ctx,
            )
        )
        self.assertTrue(
            evaluate_conditions(
                [{"field": "", "op": "feature_enabled", "value": "risk_alerts"}],
                ctx,
            )
        )


class WorkflowPublishValidationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="WF maturity school",
            slug="wf-maturity",
            subdomain="wf-maturity",
            is_active=True,
        )

    def test_invalid_graph_blocks_publish(self):
        wf = Workflow.objects.create(
            school=self.school,
            name="Broken",
            trigger_event=Workflow.Trigger.REPORT_GENERATED,
            status=Workflow.Status.DRAFT,
        )
        t = WorkflowNode.objects.create(
            workflow=wf,
            external_id="t1",
            kind=WorkflowNode.Kind.TRIGGER,
            config={},
        )
        a = WorkflowNode.objects.create(
            workflow=wf,
            external_id="a1",
            kind=WorkflowNode.Kind.ACTION,
            config={"action": {"type": "delay", "params": {"seconds": 0}}},
        )
        WorkflowEdge.objects.create(workflow=wf, source=t, target=a)
        errs = validate_workflow_for_publish(wf.pk)
        self.assertIn("missing_condition_node", errs)

    def test_valid_chain_publish_validation_ok(self):
        wf = Workflow.objects.create(
            school=self.school,
            name="Good",
            trigger_event=Workflow.Trigger.REPORT_GENERATED,
            status=Workflow.Status.DRAFT,
        )
        t = WorkflowNode.objects.create(
            workflow=wf,
            external_id="t1",
            kind=WorkflowNode.Kind.TRIGGER,
            config={},
        )
        c = WorkflowNode.objects.create(
            workflow=wf,
            external_id="c1",
            kind=WorkflowNode.Kind.CONDITION,
            config={"conditions": [{"field": "x", "op": "eq", "value": 1}]},
        )
        a = WorkflowNode.objects.create(
            workflow=wf,
            external_id="a1",
            kind=WorkflowNode.Kind.ACTION,
            config={"action": {"type": "delay", "params": {"seconds": 0}}},
        )
        WorkflowEdge.objects.create(workflow=wf, source=t, target=c)
        WorkflowEdge.objects.create(workflow=wf, source=c, target=a)
        self.assertEqual(validate_workflow_for_publish(wf.pk), [])


class WorkflowSimulationParityTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="WF sim school",
            slug="wf-sim",
            subdomain="wf-sim",
            is_active=True,
        )

    def test_simulate_workflow_matches_compile_simulate_dsl(self):
        wf = Workflow.objects.create(
            school=self.school,
            name="Parity",
            trigger_event=Workflow.Trigger.STUDENT_CREATED,
            status=Workflow.Status.DRAFT,
        )
        t = WorkflowNode.objects.create(
            workflow=wf,
            external_id="t1",
            kind=WorkflowNode.Kind.TRIGGER,
            config={},
        )
        c = WorkflowNode.objects.create(
            workflow=wf,
            external_id="c1",
            kind=WorkflowNode.Kind.CONDITION,
            config={"conditions": [{"field": "student_id", "op": "neq", "value": None}]},
        )
        a = WorkflowNode.objects.create(
            workflow=wf,
            external_id="a1",
            kind=WorkflowNode.Kind.ACTION,
            config={"action": {"type": "notify", "params": {"channel": "log", "body": "x"}}},
        )
        WorkflowEdge.objects.create(workflow=wf, source=t, target=c)
        WorkflowEdge.objects.create(workflow=wf, source=c, target=a)
        dsl = compile_workflow_to_dsl(wf)
        ctx = {"student_id": "123"}
        direct = simulate_dsl(dsl, ctx, school=self.school)
        via_executor = run_workflow(wf.pk, ctx, dry_run=True)
        self.assertEqual(
            direct.get("conditions_passed"),
            via_executor.get("conditions_passed"),
        )


class ProductionTemplatesJsonTests(TestCase):
    def test_templates_file_loads_five_pack(self):
        path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "production_workflow_templates.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 5)
        slugs = {d["slug"] for d in data}
        self.assertIn("missing_attendance_reminder", slugs)
        self.assertIn("payment_overdue_escalation", slugs)
