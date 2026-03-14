"""
Tests for backend-only navigation: is_backend_context and sidebar items when in backend.
"""
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.siteconfig.context_processors import site_settings
from apps.siteconfig.portal_sidebar_items import build_portal_sidebar_items

User = get_user_model()


class BackendContextProcessorTests(TestCase):
    """Test that is_backend_context is set correctly by site_settings context processor."""

    def setUp(self):
        self.factory = RequestFactory()
        self.site = get_platform_site_settings_record(create=True)
        self.user = User.objects.create_user(
            username="staff1",
            password="test",
            email="staff1@example.com",
            role=User.Role.ADMIN,
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

    def _request(self, path, user=None):
        request = self.factory.get(path)
        request.user = user or self.user
        request.session = {}
        return request

    def test_is_backend_context_true_for_backend_root(self):
        request = self._request("/backend/")
        ctx = site_settings(request)
        self.assertTrue(ctx["is_backend_context"], "path /backend/ should set is_backend_context True")

    def test_is_backend_context_true_for_authentication_backend(self):
        request = self._request("/authentication/backend/")
        ctx = site_settings(request)
        self.assertTrue(
            ctx["is_backend_context"],
            "path /authentication/backend/ should set is_backend_context True",
        )

    def test_is_backend_context_true_for_authentication_backend_students(self):
        request = self._request("/authentication/backend/students/")
        ctx = site_settings(request)
        self.assertTrue(
            ctx["is_backend_context"],
            "path with /authentication/backend/ should set is_backend_context True",
        )

    def test_is_backend_context_false_for_portal(self):
        request = self._request("/portal/")
        ctx = site_settings(request)
        self.assertFalse(ctx["is_backend_context"], "path /portal/ should set is_backend_context False")

    def test_is_backend_context_false_for_admin(self):
        request = self._request("/admin/")
        ctx = site_settings(request)
        self.assertFalse(ctx["is_backend_context"], "path /admin/ should set is_backend_context False")


class BackendSidebarItemsTests(TestCase):
    """Test that build_portal_sidebar_items omits admin-only links when in backend."""

    def setUp(self):
        self.factory = RequestFactory()
        self.site = get_platform_site_settings_record(create=True)
        self.superuser = User.objects.create_superuser(
            username="super1",
            email="super1@example.com",
            password="test",
        )

    def _items_for_path(self, path, user=None):
        request = self.factory.get(path)
        request.user = user or self.superuser
        request.session = {}
        return build_portal_sidebar_items(request, self.site)

    def test_in_backend_superuser_has_no_guardians_groups_site_region(self):
        items = self._items_for_path("/authentication/backend/", self.superuser)
        ids = [it["id"] for it in items]
        self.assertNotIn("guardians", ids, "In backend, guardians should not appear")
        self.assertNotIn("groups", ids, "In backend, groups should not appear")
        self.assertNotIn("site_settings", ids, "In backend, site_settings should not appear")
        self.assertNotIn("region_config", ids, "In backend, region_config should not appear")

    def test_in_backend_superuser_has_configuration_engine(self):
        items = self._items_for_path("/authentication/backend/", self.superuser)
        ids = [it["id"] for it in items]
        self.assertIn("admin_panel", ids, "In backend, Configuration Engine (admin_panel) should appear for superuser")
        admin_item = next(it for it in items if it["id"] == "admin_panel")
        self.assertIn("/admin/", admin_item["url"], "Configuration Engine should link to /admin/")

    def test_in_backend_students_point_to_backend_when_present(self):
        items = self._items_for_path("/authentication/backend/", self.superuser)
        students_item = next((it for it in items if it["id"] == "students"), None)
        if students_item is not None:
            self.assertIn("backend", students_item["url"], "Students should link to backend (not admin)")

    def test_not_in_backend_superuser_has_guardians_and_site_settings(self):
        items = self._items_for_path("/portal/", self.superuser)
        ids = [it["id"] for it in items]
        self.assertTrue(
            "guardians_backend" in ids or "guardians" in ids,
            "Outside backend, superuser should see a guardians management destination",
        )
        self.assertIn("site_settings", ids, "Outside backend, superuser should see site_settings")


class DashboardExtrasTests(TestCase):
    """Test that build_dashboard_extras returns sidebar_quick_access and empty_panel_quick_actions."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="dash1",
            password="test",
            email="dash1@example.com",
            role=User.Role.ADMIN,
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

    def test_build_dashboard_extras_returns_quick_access_and_empty_actions(self):
        from apps.dashboard.context import build_dashboard_extras

        request = self.factory.get("/authentication/backend/")
        request.user = self.user
        request.session = {}
        base = {"stats": {}, "gce_enabled": False}
        extras = build_dashboard_extras(request, base=base)
        self.assertIn("sidebar_quick_access", extras)
        self.assertIn("empty_panel_quick_actions", extras)
        self.assertIsInstance(extras["sidebar_quick_access"], list)
        self.assertIsInstance(extras["empty_panel_quick_actions"], list)
        self.assertIn("operations_watch", extras)
        self.assertIsInstance(extras["operations_watch"], list)
        self.assertIn("role_home", extras)
        self.assertIn("dashboard_priority_queue", extras)
        self.assertIn("dashboard_next_best_actions", extras)
        self.assertIn("dashboard_recent_activity", extras)
        self.assertIn("role_home_destinations", extras)
        self.assertIn("role_home_focus_areas", extras)
        self.assertIn("role_home_primary_action", extras)
        self.assertIn("role_home_supporting_actions", extras)
        self.assertIn("contextual_actions", extras)
        self.assertEqual(extras["role_home"]["default_intent"], "setup")
        self.assertEqual(extras["role_home_primary_action"]["label"], "Setup Studio")
        self.assertTrue(extras["contextual_actions"])
        self.assertEqual(extras["contextual_actions"][0]["id"], "setup_studio")
        self.assertEqual(extras["dashboard_next_best_actions"][0]["label"], "Setup Studio")

    def test_finance_role_home_promotes_finance_console(self):
        from apps.dashboard.context import build_dashboard_extras

        finance_user = User.objects.create_user(
            username="dash-finance",
            password="test",
            email="dash-finance@example.com",
            role=User.Role.BURSAR,
        )
        finance_user.is_staff = True
        finance_user.save(update_fields=["is_staff"])

        request = self.factory.get("/authentication/backend/")
        request.user = finance_user
        request.session = {}
        base = {
            "stats": {"overdue_invoices": 8},
            "pending_approvals_count": 2,
            "dashboard_intent": "finance",
            "workflow_progress": {"students": 120, "teachers": 9, "classrooms": 6},
            "recommended_next_steps": [
                {
                    "label": "Review collections",
                    "url": reverse("finance:dashboard"),
                    "icon": "bi-cash-stack",
                    "reason": "Collections are the dominant finance action right now.",
                    "category": "Finance",
                    "id": "finance_console",
                }
            ],
        }
        extras = build_dashboard_extras(request, base=base)

        self.assertEqual(extras["role_home"]["key"], "finance")
        self.assertEqual(extras["role_home_primary_action"]["label"], "Review collections")


class RecommendationServiceTests(TestCase):
    def test_setup_intent_prioritizes_setup_studio(self):
        from apps.dashboard.recommendation_service import get_recommended_next_steps

        steps = get_recommended_next_steps({}, intent="setup", max_steps=4)

        self.assertTrue(steps)
        self.assertEqual(steps[0]["action_id"], "setup_studio")
        self.assertEqual(steps[0]["priority"], "now")

    def test_finance_risk_prioritizes_finance_console(self):
        from apps.dashboard.recommendation_service import get_recommended_next_steps

        steps = get_recommended_next_steps(
            {
                "classrooms": 6,
                "students": 120,
                "teachers": 12,
            },
            year=object(),
            intent="finance",
            priority_signals={"overdue_invoices": 7, "draft_invoices": 3},
            max_steps=4,
        )

        self.assertTrue(steps)
        self.assertEqual(steps[0]["action_id"], "finance_console")
        self.assertEqual(steps[0]["priority"], "now")
