"""Student portal toggle gates views and sidebar discovery."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.http import HttpResponseForbidden
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.portal.views_student import student_workflow_center
from apps.siteconfig.portal_sidebar_items import build_portal_sidebar_items

UserModel = get_user_model()

ROOT = Path(__file__).resolve().parents[3]


class StudentPortalViewGateTests(TestCase):
    def test_workflow_center_forbidden_when_portal_disabled(self):
        user = UserModel.objects.create_user(
            username="student-gate-user",
            password="Test1234!",
            role=User.Role.STUDENT,
        )
        request = RequestFactory().get("/portal/student/workflow/")
        request.user = user
        request.school = SimpleNamespace(pk=1)

        with patch(
            "apps.portal.views_student.get_effective_config",
            return_value=False,
        ):
            response = student_workflow_center(request)

        self.assertIsInstance(response, HttpResponseForbidden)


class StudentPortalSidebarGateTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_sidebar_hides_workflow_when_portal_disabled(self):
        request = MagicMock()
        request.session = {}
        request.messages_unread_count = 0
        request.user = SimpleNamespace(
            is_authenticated=True,
            role=User.Role.STUDENT,
            is_staff=False,
            is_superuser=False,
            pk=None,
            has_feature_permission=lambda _permission: False,
        )
        site = SimpleNamespace(
            enable_student_portal=False,
            get_feature_control_settings=lambda: {"portal_features": {}},
        )

        with patch(
            "apps.siteconfig.portal_sidebar_items._backend_flags_for_sidebar",
            return_value={},
        ), patch(
            "apps.siteconfig.portal_sidebar_items._cached_sidebar_badge_counts",
            return_value=(None, None, None),
        ), patch(
            "apps.accounts.portal_roles.get_nav_portal_role",
            return_value=User.Role.STUDENT,
        ):
            items = build_portal_sidebar_items(request, site)

        ids = [item["id"] for item in items]
        self.assertNotIn("student_workflow", ids)
        self.assertNotIn("student_home", ids)
        self.assertNotIn("student_syllabus", ids)
        self.assertIn("help_center", ids)

    def test_template_gates_student_portal_nav(self):
        builder = (ROOT / "apps/siteconfig/portal_sidebar_items.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("enable_student_portal", builder)
        self.assertIn("portal:student_workflow", builder)


class StudentWorkflowRouteTests(TestCase):
    def test_student_workflow_route_resolves(self):
        self.assertEqual(
            reverse("portal:student_workflow", urlconf="config.tenant_urls"),
            "/portal/student/workflow/",
        )
