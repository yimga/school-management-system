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

    #: Every tenant role and the workflow destination it must be able to find.
    ROLE_WORKFLOW_ITEMS = {
        User.Role.STUDENT: ("student_workflow", "/portal/student/workflow/"),
        User.Role.TEACHER: ("teacher_workflow", "/portal/teacher/workflow/"),
        User.Role.PARENT: ("parent_workflow", "/portal/parent/workflow/"),
    }

    def test_workflow_discovery_is_role_complete(self):
        """Discovery is asserted against the sidebar BUILDER, not template text.

        This test used to read partials/portal_sidebar.html looking for
        ``portal:student_workflow`` and a hardcoded role branch. Both have moved
        twice already - first from ``request.user.role`` to ``nav_role`` when
        role hats landed, then again as the markup was reorganised. Each move
        broke the assertion with nothing wrong in the product, which is the
        signature of testing at the wrong level. What actually has to hold is
        that ``build_portal_sidebar_items`` offers every role its own workflow
        page; that survives any amount of template reshuffling.
        """
        for role, (item_id, url) in self.ROLE_WORKFLOW_ITEMS.items():
            with self.subTest(role=role):
                by_id = {item["id"]: item for item in self._sidebar_items_for(role)}
                self.assertIn(
                    item_id,
                    by_id,
                    f"{role} can no longer discover its workflow page from the sidebar",
                )
                self.assertEqual(by_id[item_id]["url"], url)

    def test_sidebar_never_branches_on_the_raw_role_column(self):
        """Role hats are only honoured if the nav reads the EFFECTIVE role.

        A staff member wearing a parent or teacher hat still has
        ``request.user.role == ADMIN``, so a template that branches on the
        column shows them the wrong sidebar for the role they are acting as.
        The one legitimate raw-column read is the SUPERADMIN check on the
        manager host, where no tenant hat applies.
        """
        sidebar = (ROOT / "templates/partials/portal_sidebar.html").read_text(
            encoding="utf-8"
        )
        builder = (ROOT / "apps/siteconfig/portal_sidebar_items.py").read_text(
            encoding="utf-8"
        )
        # Hats are resolved in the Python projector, not a second hardcoded
        # role tree in the template.
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
        self.assertNotIn(
            "portal:student_learning_home",
            (ROOT / "apps/siteconfig/portal_sidebar_items.py").read_text(
                encoding="utf-8"
            ),
            "the retired student_learning_home route is back in the sidebar builder",
        )


    def test_command_palette_carries_every_role_workflow(self):
        command_registry = (
            ROOT / "apps/siteconfig/command_bar_registry.py"
        ).read_text(encoding="utf-8")
        for token in (
            "portal:teacher_workflow",
            "portal:parent_workflow",
            "portal:student_workflow",
        ):
            self.assertIn(token, command_registry)

    @staticmethod
    def _sidebar_items_for(role):
        """Build the real sidebar for ``role`` with only the DB seams stubbed."""
        request = MagicMock()
        request.session = {}
        request.messages_unread_count = 0
        request.user = SimpleNamespace(
            is_authenticated=True,
            role=role,
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
            return_value=role,
        ):
            return build_portal_sidebar_items(request, site)

    def test_config_driven_sidebar_includes_student_workflow(self):
        by_id = {
            item["id"]: item for item in self._sidebar_items_for(User.Role.STUDENT)
        }

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
