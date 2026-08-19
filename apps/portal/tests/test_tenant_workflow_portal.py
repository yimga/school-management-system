from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.views import redirect_view
from apps.portal.tenant_workflow_portal import build_tenant_workflow_portal
from apps.siteconfig.portal_sidebar_items import build_portal_sidebar_items


ROOT = Path(__file__).resolve().parents[3]


class TenantWorkflowPortalTests(SimpleTestCase):
    @patch(
        "apps.portal.tenant_workflow_portal._safe_reverse",
        side_effect=lambda name: f"/resolved/{name.replace(':', '/')}/",
    )
    def test_workflow_payload_prioritizes_first_open_step(self, _mock_reverse):
        req = MagicMock()
        steps = [
            {
                "title": "1) Profile",
                "step_key": "profile",
                "subtitle": "Ready",
                "done": True,
                "links": [{"label": "Profile", "url": "/profile/"}],
            },
            {
                "title": "2) Marks",
                "step_key": "marks",
                "subtitle": "Pending",
                "done": False,
                "links": [{"label": "Enter marks", "url": "/marks/"}],
            },
        ]

        payload = build_tenant_workflow_portal(
            req,
            role=User.Role.TEACHER,
            steps=steps,
            workflow_progress={"assignments": 2, "completion_pct": 50, "pending_marks": 4},
        )

        self.assertEqual(payload["focus"]["step_key"], "marks")
        self.assertEqual(payload["primary_action"]["url"], "/marks/")
        self.assertEqual(payload["completion_pct"], 50)
        self.assertEqual(payload["role"], User.Role.TEACHER)

    def test_templates_use_shared_workflow_portal(self):
        for rel in (
            "templates/parent/workflow_center.html",
            "templates/teacher/workflow_center.html",
            "templates/student/workflow_center.html",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("partials/tenant/workflow_portal.html", text)

        partial = (ROOT / "templates/partials/tenant/workflow_portal.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("data-rmc-tenant-workflow-portal", partial)
        self.assertIn("data-rmc-workflow-focus", partial)
        self.assertIn("data-rmc-workflow-step", partial)

    def test_student_workflow_route_resolves(self):
        self.assertEqual(
            reverse("portal:student_workflow", urlconf="config.tenant_urls"),
            "/portal/student/workflow/",
        )

    def test_workflow_discovery_is_role_complete(self):
        sidebar = (ROOT / "templates/partials/portal_sidebar.html").read_text(
            encoding="utf-8"
        )
        builder = (ROOT / "apps/siteconfig/portal_sidebar_items.py").read_text(
            encoding="utf-8"
        )
        command_registry = (
            ROOT / "apps/siteconfig/command_bar_registry.py"
        ).read_text(encoding="utf-8")

        # Role hats live in the Python projector (nav_role / get_nav_portal_role).
        # The template no longer forks a second hardcoded role tree.
        self.assertIn("get_nav_portal_role", builder)
        self.assertIn("User.Role.STUDENT", builder)
        self.assertIn("nav_role != 'STUDENT'", sidebar)
        for hat_role in ("STUDENT", "TEACHER", "PARENT", "ADMIN"):
            for quote in ("'", '"'):
                self.assertNotIn(
                    f"request.user.role == {quote}{hat_role}{quote}",
                    sidebar,
                    f"sidebar branches on the raw role column for {hat_role}; "
                    "that ignores the portal role hat the user actually picked",
                )
        self.assertIn("portal:student_workflow", builder)
        self.assertNotIn("portal:student_learning_home", builder)
        for token in (
            "portal:teacher_workflow",
            "portal:parent_workflow",
            "portal:student_workflow",
        ):
            self.assertIn(token, command_registry)

    def test_config_driven_sidebar_includes_student_workflow(self):
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
        site = SimpleNamespace(get_feature_control_settings=lambda: {"portal_features": {}})

        with patch(
            "apps.siteconfig.portal_sidebar_items._backend_flags_for_sidebar",
            return_value={},
        ), patch(
            "apps.siteconfig.portal_sidebar_items._cached_sidebar_badge_counts",
            return_value=(None, None, None),
        ), patch(
            "apps.accounts.portal_roles.get_effective_portal_role",
            return_value=User.Role.STUDENT,
        ):
            items = build_portal_sidebar_items(request, site)
        by_id = {item["id"]: item for item in items}

        self.assertEqual(by_id["student_workflow"]["url"], "/portal/student/workflow/")
        self.assertEqual(by_id["student_home"]["url"], "/portal/student-portal/grades/")
        self.assertNotIn("student_progress", by_id)
        self.assertNotIn("admin_panel", by_id)


class StudentTenantRedirectTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _student_request(self, dashboard_view=None):
        request = self.factory.get("/authentication/redirect/", HTTP_HOST="gilead-school.runmycampus.com")
        request.school = object()
        request.session = {}
        request.user = SimpleNamespace(
            is_authenticated=True,
            role=User.Role.STUDENT,
            has_feature_permission=lambda _permission: False,
        )
        pref = SimpleNamespace(dashboard_view=dashboard_view)
        pref_qs = MagicMock()
        pref_qs.only.return_value.first.return_value = pref if dashboard_view else None
        return request, pref_qs

    def test_student_redirect_lands_on_student_home(self):
        request, pref_qs = self._student_request()

        with patch("apps.schools.tenant_url.get_tenant_prefix", return_value=""), patch(
            "apps.siteconfig.models.UserPreference.objects.filter",
            return_value=pref_qs,
        ), patch(
            "apps.accounts.portal_roles.get_effective_portal_role",
            return_value=User.Role.STUDENT,
        ):
            response = redirect_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/portal/student-portal/grades/")

    def test_student_workflow_preference_lands_on_student_workflow(self):
        request, pref_qs = self._student_request(dashboard_view="WORKFLOW")

        with patch("apps.schools.tenant_url.get_tenant_prefix", return_value=""), patch(
            "apps.siteconfig.models.UserPreference.objects.filter",
            return_value=pref_qs,
        ), patch(
            "apps.accounts.portal_roles.get_effective_portal_role",
            return_value=User.Role.STUDENT,
        ):
            response = redirect_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/portal/student/workflow/")
