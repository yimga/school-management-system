"""Ready playbook templates: simulation samples + tenant isolation."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import Permission
from apps.automation.models import Workflow, WorkflowEdge, WorkflowNode
from apps.automation.visual_executor import simulate_workflow
from apps.automation.views_visual_workflow import visual_workflow_simulate
from apps.automation.workflow_playbook_templates import (
    READY_PLAYBOOKS,
    enrich_playbooks_for_template,
    playbook_simulation_sample,
)
from apps.schools.models import School

User = get_user_model()


def _publishable_graph(school: School, trigger: str) -> Workflow:
    wf = Workflow.objects.create(
        school=school,
        name=f"pb {trigger}",
        trigger_event=trigger,
        status=Workflow.Status.DRAFT,
    )
    sid = str(school.pk)
    t = WorkflowNode.objects.create(
        workflow=wf,
        external_id="t-root",
        kind=WorkflowNode.Kind.TRIGGER,
        config={},
    )
    c = WorkflowNode.objects.create(
        workflow=wf,
        external_id="c1",
        kind=WorkflowNode.Kind.CONDITION,
        config={
            "condition": {"field": "school_id", "op": "eq", "value": sid},
        },
    )
    a = WorkflowNode.objects.create(
        workflow=wf,
        external_id="a1",
        kind=WorkflowNode.Kind.ACTION,
        config={
            "action": {"type": "notify", "params": {"channel": "log", "body": "playbook"}},
        },
    )
    WorkflowEdge.objects.create(workflow=wf, source=t, target=c)
    WorkflowEdge.objects.create(workflow=wf, source=c, target=a)
    return wf


class WorkflowPlaybookTemplatesTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="PB School",
            slug="pb-school",
            subdomain="pb-school",
            is_active=True,
        )
        self.other = School.objects.create(
            name="PB Other",
            slug="pb-other",
            subdomain="pb-other",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="wf_pb_staff",
            password="pw",
            is_staff=True,
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.user.feature_permissions.add(manage_perm)

    def test_six_ready_playbooks(self):
        self.assertEqual(len(READY_PLAYBOOKS), 6)
        slugs = {p["slug"] for p in READY_PLAYBOOKS}
        self.assertIn("missing_attendance_reminder", slugs)
        self.assertIn("offline_conflict_follow_up", slugs)

    def test_enrich_attaches_simulation_json(self):
        rows = enrich_playbooks_for_template(str(self.school.pk))
        self.assertEqual(len(rows), 6)
        for r in rows:
            self.assertIn("simulation_sample_json", r)
            self.assertIn("trigger_key", r)

    def test_each_playbook_simulates_when_graph_built(self):
        sid = str(self.school.pk)
        for pb in READY_PLAYBOOKS:
            trig = str(pb["trigger_key"])
            wf = _publishable_graph(self.school, trig)
            payload = playbook_simulation_sample(sid, pb)
            out = simulate_workflow(wf.pk, payload, user=self.user)
            self.assertTrue(out.get("ok"), msg=(pb["slug"], out))

    def test_playbook_foreign_school_simulate_blocked(self):
        pb = READY_PLAYBOOKS[0]
        wf = _publishable_graph(self.school, pb["trigger_key"])
        factory = RequestFactory()
        payload = playbook_simulation_sample(str(self.school.pk), pb)
        req = factory.post(
            reverse("automation:visual_workflow_simulate"),
            data=json.dumps(
                {"workflow_id": wf.pk, "sample_payload": payload},
            ),
            content_type="application/json",
        )
        req.user = self.user
        req.school = self.other
        resp = visual_workflow_simulate(req)
        self.assertEqual(resp.status_code, 404)
