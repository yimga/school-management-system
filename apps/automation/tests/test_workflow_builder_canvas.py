"""Visual workflow designer surface: save draft, validate, simulate, publish guardrails."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import Permission
from apps.automation.views_visual_workflow import (
    visual_workflow_publish,
    visual_workflow_save_graph,
    visual_workflow_simulate,
    visual_workflow_validate_graph,
)
from apps.schools.models import School

User = get_user_model()


def _staff_request(method: str, path: str, user: User, school: School, body: dict | None):
    factory = RequestFactory()
    data = json.dumps(body or {})
    req = getattr(factory, method.lower())(
        path,
        data=data,
        content_type="application/json",
    )
    req.user = user
    req.school = school
    return req


class WorkflowBuilderCanvasTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Canvas School",
            slug="canvas-school",
            subdomain="canvas-school",
            is_active=True,
        )
        self.other = School.objects.create(
            name="Other",
            slug="canvas-other",
            subdomain="canvas-other",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="wf_canvas_staff",
            password="pw",
            is_staff=True,
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.user.feature_permissions.add(manage_perm)

    def _valid_graph_payload(self):
        sid = str(self.school.pk)
        return {
            "name": "Canvas flow",
            "trigger_event": "attendance_saved",
            "nodes": [
                {
                    "id": "t1",
                    "kind": "trigger",
                    "config": {},
                    "position": {"x": 0, "y": 0},
                },
                {
                    "id": "c1",
                    "kind": "condition",
                    "config": {
                        "condition": {
                            "field": "school_id",
                            "op": "eq",
                            "value": sid,
                        }
                    },
                    "position": {"x": 40, "y": 0},
                },
                {
                    "id": "a1",
                    "kind": "action",
                    "config": {
                        "action": {
                            "type": "notify",
                            "params": {"channel": "log", "body": "ok"},
                        }
                    },
                    "position": {"x": 80, "y": 0},
                },
            ],
            "edges": [
                {"from": "t1", "to": "c1"},
                {"from": "c1", "to": "a1"},
            ],
        }

    def test_save_graph_creates_workflow_and_round_trip_simulate(self):
        path = reverse("automation:visual_workflow_save_graph")
        req = _staff_request("post", path, self.user, self.school, self._valid_graph_payload())
        resp = visual_workflow_save_graph(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertTrue(data.get("ok") is not False)
        wf_id = data["workflow_id"]

        val_req = _staff_request(
            "post",
            reverse("automation:visual_workflow_validate_graph"),
            self.user,
            self.school,
            {"workflow_id": wf_id},
        )
        val_resp = visual_workflow_validate_graph(val_req)
        val_data = json.loads(val_resp.content.decode())
        self.assertTrue(val_data.get("ok"))
        self.assertEqual(val_data.get("validation_errors"), [])

        sid = str(self.school.pk)
        sim_req = _staff_request(
            "post",
            reverse("automation:visual_workflow_simulate"),
            self.user,
            self.school,
            {
                "workflow_id": wf_id,
                "sample_payload": {"school_id": sid, "student_id": 1},
            },
        )
        sim_resp = visual_workflow_simulate(sim_req)
        sim_data = json.loads(sim_resp.content.decode())
        self.assertTrue(sim_data.get("ok"), msg=sim_data)

    def test_publish_blocked_then_succeeds(self):
        path = reverse("automation:visual_workflow_save_graph")
        bad = {
            "name": "Bad",
            "trigger_event": "payment_success",
            "nodes": [
                {"id": "t1", "kind": "trigger", "config": {}, "position": {}},
                {
                    "id": "a1",
                    "kind": "action",
                    "config": {
                        "action": {"type": "notify", "params": {"channel": "log", "body": "x"}}
                    },
                    "position": {},
                },
            ],
            "edges": [{"from": "t1", "to": "a1"}],
        }
        req = _staff_request("post", path, self.user, self.school, bad)
        resp = visual_workflow_save_graph(req)
        wf_id = json.loads(resp.content.decode())["workflow_id"]

        pub_req = _staff_request(
            "post",
            reverse("automation:visual_workflow_publish"),
            self.user,
            self.school,
            {"workflow_id": wf_id},
        )
        pub_resp = visual_workflow_publish(pub_req)
        self.assertEqual(pub_resp.status_code, 400)
        body = json.loads(pub_resp.content.decode())
        self.assertIn("missing_condition_node", body.get("validation_errors", []))

        good_req = _staff_request(
            "post", path, self.user, self.school, self._valid_graph_payload()
        )
        wf_id2 = json.loads(visual_workflow_save_graph(good_req).content.decode())[
            "workflow_id"
        ]
        pub2 = visual_workflow_publish(
            _staff_request(
                "post",
                reverse("automation:visual_workflow_publish"),
                self.user,
                self.school,
                {"workflow_id": wf_id2},
            )
        )
        self.assertEqual(pub2.status_code, 200)

    def test_tenant_isolation_save_graph_foreign_school(self):
        path = reverse("automation:visual_workflow_save_graph")
        req = _staff_request(
            "post",
            path,
            self.user,
            self.school,
            self._valid_graph_payload(),
        )
        wf_id = json.loads(visual_workflow_save_graph(req).content.decode())["workflow_id"]
        leak = _staff_request(
            "post",
            reverse("automation:visual_workflow_simulate"),
            self.user,
            self.other,
            {"workflow_id": wf_id, "sample_payload": {}},
        )
        resp = visual_workflow_simulate(leak)
        self.assertEqual(resp.status_code, 404)
