"""
Section 11.4 workflow_engine closure slice: Studio simulation guidance + canonical triggers +
visual workflow simulate/dispatch/publish guardrails + outcomes visibility.

Does not certify full Salesforce-style workflow catalog.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission

from apps.automation.graph_validate import validate_workflow_for_publish
from apps.automation.models import Workflow, WorkflowEdge, WorkflowNode
from apps.automation.views import outcomes_console
from apps.automation.visual_executor import run_workflow, simulate_workflow
from apps.automation.workflow_graph_models import WorkflowRunLog
from apps.automation.workflow_trigger_catalog import (
    CLOSURE_SLICE_TRIGGER_KEYS,
    get_operator_trigger_catalog_for_school,
    sample_payload_for_trigger,
)
from apps.automation.views_visual_workflow import visual_workflow_simulate
from apps.schools.models import School

User = get_user_model()


def _publishable_notify_workflow(school: School, trigger_event: str) -> Workflow:
    wf = Workflow.objects.create(
        school=school,
        name=f"Closure slice {trigger_event}",
        trigger_event=trigger_event,
        status=Workflow.Status.DRAFT,
    )
    t = WorkflowNode.objects.create(
        workflow=wf,
        external_id="t-root",
        kind=WorkflowNode.Kind.TRIGGER,
        config={},
        position={"x": 0, "y": 0},
    )
    c = WorkflowNode.objects.create(
        workflow=wf,
        external_id="c1",
        kind=WorkflowNode.Kind.CONDITION,
        config={
            "condition": {
                "field": "school_id",
                "op": "eq",
                "value": str(school.pk),
            }
        },
        position={"x": 40, "y": 0},
    )
    a = WorkflowNode.objects.create(
        workflow=wf,
        external_id="a1",
        kind=WorkflowNode.Kind.ACTION,
        config={
            "action": {
                "type": "notify",
                "params": {"channel": "log", "body": f"{trigger_event} closure"},
            }
        },
        position={"x": 80, "y": 0},
    )
    WorkflowEdge.objects.create(workflow=wf, source=t, target=c)
    WorkflowEdge.objects.create(workflow=wf, source=c, target=a)
    return wf


def _trigger_only_workflow(school: School, trigger_event: str) -> Workflow:
    wf = Workflow.objects.create(
        school=school,
        name="Invalid graph",
        trigger_event=trigger_event,
        status=Workflow.Status.DRAFT,
    )
    t = WorkflowNode.objects.create(
        workflow=wf,
        external_id="t-root",
        kind=WorkflowNode.Kind.TRIGGER,
        config={},
    )
    a = WorkflowNode.objects.create(
        workflow=wf,
        external_id="a1",
        kind=WorkflowNode.Kind.ACTION,
        config={
            "action": {"type": "notify", "params": {"channel": "log", "body": "x"}}
        },
    )
    WorkflowEdge.objects.create(workflow=wf, source=t, target=a)
    return wf


@override_settings(ALLOWED_HOSTS=["*"])
class WorkflowStudioClosureSliceTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(
            name="WF Slice A",
            slug="wf-slice-a",
            subdomain="wf-slice-a",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="WF Slice B",
            slug="wf-slice-b",
            subdomain="wf-slice-b",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="wf_studio_staff",
            password="pw",
            is_staff=True,
            role=User.Role.IT_ADMIN,
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.user.feature_permissions.add(manage_perm)

    def test_closure_trigger_catalog_keys(self):
        self.assertEqual(
            CLOSURE_SLICE_TRIGGER_KEYS,
            ("attendance_saved", "payment_success", "report_generated"),
        )
        sid = str(self.school_a.pk)
        rows = get_operator_trigger_catalog_for_school(sid)
        self.assertEqual(len(rows), 3)
        keys = {r["trigger_key"] for r in rows}
        self.assertEqual(keys, set(CLOSURE_SLICE_TRIGGER_KEYS))

    def test_canonical_trigger_simulations_dry_run(self):
        sid = str(self.school_a.pk)
        mapping = {
            "attendance_saved": Workflow.Trigger.ATTENDANCE_SAVED,
            "payment_success": Workflow.Trigger.PAYMENT_SUCCESS,
            "report_generated": Workflow.Trigger.REPORT_GENERATED,
        }
        for key in CLOSURE_SLICE_TRIGGER_KEYS:
            wf = _publishable_notify_workflow(self.school_a, mapping[key])
            payload = sample_payload_for_trigger(sid, key)
            out = simulate_workflow(wf.pk, payload, user=self.user)
            self.assertTrue(out.get("ok"), msg=out)
            self.assertTrue(out.get("dry_run"))
            self.assertTrue(out.get("conditions_passed"))
            self.assertTrue(out.get("expected_output"))

    def test_publish_validation_blocks_incomplete_graph(self):
        wf = _trigger_only_workflow(self.school_a, Workflow.Trigger.ATTENDANCE_SAVED)
        errs = validate_workflow_for_publish(wf.pk)
        self.assertIn("missing_condition_node", errs)

    def test_visual_simulate_api_rejects_foreign_school_workflow(self):
        wf_a = _publishable_notify_workflow(
            self.school_a, Workflow.Trigger.PAYMENT_SUCCESS
        )
        factory = RequestFactory()
        payload = sample_payload_for_trigger(str(self.school_a.pk), "payment_success")
        request = factory.post(
            reverse("automation:visual_workflow_simulate"),
            data=json.dumps(
                {"workflow_id": wf_a.pk, "sample_payload": payload},
            ),
            content_type="application/json",
        )
        request.user = self.user
        request.school = self.school_b
        response = visual_workflow_simulate(request)
        self.assertEqual(response.status_code, 404)

    def test_live_run_writes_workflow_run_log_visible_in_outcomes_console(self):
        wf = _publishable_notify_workflow(
            self.school_a, Workflow.Trigger.REPORT_GENERATED
        )
        self.assertEqual(validate_workflow_for_publish(wf.pk), [])
        wf.status = Workflow.Status.PUBLISHED
        wf.save(update_fields=["status", "updated_at"])
        payload = sample_payload_for_trigger(str(self.school_a.pk), "report_generated")
        before = WorkflowRunLog.objects.filter(workflow__school=self.school_a).count()
        out = run_workflow(wf.pk, payload, user=self.user, dry_run=False)
        self.assertTrue(out.get("ok"), msg=out)
        self.assertEqual(
            WorkflowRunLog.objects.filter(workflow__school=self.school_a).count(),
            before + 1,
        )

        factory = RequestFactory()
        req = factory.get(reverse("automation:outcomes_console"))
        req.user = self.user
        req.school = self.school_a
        resp = outcomes_console(req)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, wf.name)

    def test_studio_simulation_engine_lists_catalog_when_school_bound(self):
        self.client.force_login(self.user)
        url = reverse("studio_os:automation_simulation_engine")
        host = f"{self.school_a.subdomain}.runmycampus.com"
        response = self.client.get(url, HTTP_HOST=host)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("attendance_saved", content)
        self.assertIn("payment_success", content)
        self.assertIn("report_generated", content)
        self.assertIn("offline_action_conflict", content)
        self.assertIn("data-rmc-workflow-trigger-catalog", content)
        self.assertIn("data-rmc-workflow-playbook-catalog", content)
