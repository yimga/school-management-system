"""M6 seal — workflow ``notify`` actions now deliver to resolved recipients.

Before this, a ``notify_parent`` node compiled to a bare ``notify`` with no
recipient and the engine only ``logger.info``-d it; the email leg required a
hardcoded ``to`` address. These tests pin that (1) the compiler preserves the
notify audience, (2) the engine resolves real recipients from the run context,
(3) it dispatches through the shared rail, and (4) the template gallery is no
longer locked to ``is_staff`` (tenant admins are ``role=ADMIN``).
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.automation.graph_compiler import normalize_action_dict
from apps.automation.views_workflow_gallery import _can_view_gallery
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School
from apps.siteconfig.workflow_engine import (
    _resolve_workflow_notify_recipients,
    _run_action_notify,
)

User = get_user_model()

_DISPATCH = "apps.communication.dispatch.dispatch_event"


class WorkflowNotifyCompileTests(SimpleTestCase):
    def test_notify_parent_preserves_audience(self):
        out = normalize_action_dict({"type": "notify_parent", "params": {"body": "hi"}})
        self.assertEqual(out["type"], "notify")
        self.assertEqual(out["params"]["audience"], "parent")

    def test_notify_admin_preserves_audience(self):
        out = normalize_action_dict({"type": "notify_admin"})
        self.assertEqual(out["params"]["audience"], "admin")


class WorkflowGalleryGateTests(SimpleTestCase):
    def test_tenant_admin_can_view_gallery(self):
        # role=ADMIN, is_staff=False — the exact tenant-admin shape the old gate blocked.
        self.assertTrue(_can_view_gallery(User(is_staff=False, role=User.Role.ADMIN)))

    def test_parent_cannot_view_gallery(self):
        self.assertFalse(_can_view_gallery(User(is_staff=False, role=User.Role.PARENT)))


class WorkflowNotifyDeliveryTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="WF School", slug="wf-school", subdomain="wf-school",
        )
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Zoe", last_name="W", student_code="WF-1",
        )
        self.parent = User.objects.create_user(
            username="wf_parent", password="p", role=User.Role.PARENT,
            email="wfp@example.test",
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent, student=self.student, phone="+237600000009",
        )

    def test_resolve_parent_recipients_from_student_id(self):
        users = _resolve_workflow_notify_recipients(
            "parent", {"student_id": self.student.pk}, self.school,
        )
        self.assertEqual([u.pk for u in users], [self.parent.pk])

    def test_notify_parent_dispatches_to_guardian(self):
        with mock.patch(_DISPATCH) as dispatch:
            result = _run_action_notify(
                {"audience": "parent", "subject": "Well done", "body": "Zoe improved!"},
                {"student_id": self.student.pk},
                school=self.school,
            )
        self.assertEqual(result["delivered"], 1)
        kwargs = dispatch.call_args_list[0].kwargs
        self.assertEqual(kwargs["recipient"].pk, self.parent.pk)
        self.assertEqual(kwargs["context"]["message"], "Zoe improved!")
        self.assertEqual(dispatch.call_args_list[0].args[0], "workflow.notification")

    def test_notify_with_no_recipient_is_honest_noop(self):
        with mock.patch(_DISPATCH) as dispatch:
            result = _run_action_notify({"audience": "parent"}, {}, school=self.school)
        self.assertFalse(dispatch.called)
        self.assertEqual(result, {"delivered": 0, "reason": "no_recipient"})
