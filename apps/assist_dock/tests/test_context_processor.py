"""v4.00.91 — assist_dock context processor surface + role + payload tests."""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.assist_dock import default_slots  # noqa: F401 — seed registry
from apps.assist_dock.context_processors import (
    DOCK_PAYLOAD_VERSION,
    _resolve_role,
    _resolve_surface,
    assist_dock_context,
)
from apps.assist_dock.registry import (
    SURFACE_ADMIN,
    SURFACE_ANY,
    SURFACE_MANAGER,
    SURFACE_PORTAL,
)


class ResolveSurfaceTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_manager_host_kind_wins(self):
        req = self.rf.get("/")
        req.public_host_kind = "manager"
        self.assertEqual(_resolve_surface(req), SURFACE_MANAGER)

    def test_tenant_host_with_admin_path(self):
        req = self.rf.get("/admin/auth/user/")
        req.public_host_kind = "tenant"
        self.assertEqual(_resolve_surface(req), SURFACE_ADMIN)

    def test_tenant_host_with_portal_path(self):
        req = self.rf.get("/portal/dashboard/")
        req.public_host_kind = "tenant"
        self.assertEqual(_resolve_surface(req), SURFACE_PORTAL)

    def test_super_path_implies_manager(self):
        req = self.rf.get("/super/migration/health/")
        self.assertEqual(_resolve_surface(req), SURFACE_MANAGER)

    def test_admin_path_implies_admin(self):
        req = self.rf.get("/admin/")
        self.assertEqual(_resolve_surface(req), SURFACE_ADMIN)

    def test_unknown_fallback_to_any(self):
        req = self.rf.get("/")
        self.assertEqual(_resolve_surface(req), SURFACE_ANY)


class ResolveRoleTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_anonymous_user(self):
        req = self.rf.get("/")
        req.user = mock.Mock(is_authenticated=False)
        self.assertEqual(_resolve_role(req), "anonymous")

    def test_superuser_wins(self):
        req = self.rf.get("/")
        user = mock.Mock(
            is_authenticated=True,
            is_superuser=True,
            is_staff=True,
            active_role="TEACHER",
        )
        req.user = user
        self.assertEqual(_resolve_role(req), "SUPERADMIN")

    def test_active_role_preferred(self):
        req = self.rf.get("/")
        user = mock.Mock(
            is_authenticated=True,
            is_superuser=False,
            is_staff=False,
            active_role="PRINCIPAL",
            primary_role="TEACHER",
            role="DEAN",
        )
        req.user = user
        self.assertEqual(_resolve_role(req), "PRINCIPAL")

    def test_falls_back_to_role(self):
        req = self.rf.get("/")
        user = mock.Mock(spec=["is_authenticated", "is_superuser", "is_staff", "role"])
        user.is_authenticated = True
        user.is_superuser = False
        user.is_staff = False
        user.role = "PARENT"
        req.user = user
        self.assertEqual(_resolve_role(req), "PARENT")

    def test_staff_fallback(self):
        req = self.rf.get("/")
        user = mock.Mock(spec=["is_authenticated", "is_superuser", "is_staff"])
        user.is_authenticated = True
        user.is_superuser = False
        user.is_staff = True
        req.user = user
        self.assertEqual(_resolve_role(req), "STAFF")


class ContextProcessorPayloadTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.flags_patcher = mock.patch(
            "apps.assist_dock.context_processors._effective_feature_flags",
            return_value={"enable_ai_help_assistant": True},
        )
        self.mock_flags = self.flags_patcher.start()

    def tearDown(self):
        self.flags_patcher.stop()

    def _build_request(self, path="/portal/dashboard/", role="TEACHER", host_kind="tenant"):
        req = self.rf.get(path)
        req.public_host_kind = host_kind
        req.user = mock.Mock(
            is_authenticated=True,
            is_superuser=False,
            is_staff=False,
            active_role=role,
        )
        return req

    def test_returns_assist_dock_key(self):
        ctx = assist_dock_context(self._build_request())
        self.assertIn("assist_dock", ctx)

    def test_payload_shape(self):
        ctx = assist_dock_context(self._build_request())
        payload = ctx["assist_dock"]
        for key in (
            "surface",
            "role",
            "slots",
            "expand_label",
            "collapse_label",
            "toolbar_label",
            "version",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["version"], DOCK_PAYLOAD_VERSION)

    def test_portal_surface_returns_default_slots(self):
        ctx = assist_dock_context(self._build_request())
        ids = {s["id"] for s in ctx["assist_dock"]["slots"]}
        for expected in ("ai-copilot", "messages", "back-to-top"):
            self.assertIn(expected, ids)

    def test_manager_host_payload(self):
        ctx = assist_dock_context(
            self._build_request(path="/super/", host_kind="manager")
        )
        self.assertEqual(ctx["assist_dock"]["surface"], SURFACE_MANAGER)
        # Default chips have ALL_SURFACES → should still appear.
        ids = {s["id"] for s in ctx["assist_dock"]["slots"]}
        self.assertIn("ai-copilot", ids)

    def test_anonymous_user_still_gets_payload(self):
        req = self.rf.get("/")
        req.user = mock.Mock(is_authenticated=False)
        ctx = assist_dock_context(req)
        self.assertEqual(ctx["assist_dock"]["role"], "anonymous")
        # Default chips use roles={"*"} so anonymous sees them too.
        self.assertGreaterEqual(len(ctx["assist_dock"]["slots"]), 6)

    def test_ai_copilot_hidden_when_feature_disabled(self):
        self.mock_flags.return_value = {"enable_ai_help_assistant": False}
        ctx = assist_dock_context(self._build_request())
        ids = {s["id"] for s in ctx["assist_dock"]["slots"]}
        self.assertNotIn("ai-copilot", ids)
        self.assertIn("messages", ids)

    def test_exception_safe(self):
        broken = mock.Mock()
        broken.user = mock.Mock(is_authenticated=True, is_superuser=False)
        # __getattr__ raising would propagate; we install ValueError on active_role.
        type(broken.user).active_role = mock.PropertyMock(side_effect=ValueError("boom"))
        type(broken).public_host_kind = mock.PropertyMock(side_effect=ValueError("boom"))
        type(broken).path = mock.PropertyMock(side_effect=ValueError("boom"))
        ctx = assist_dock_context(broken)
        self.assertIn("assist_dock", ctx)
        # Falls back to empty slots — never raises into the template.
        self.assertEqual(ctx["assist_dock"]["slots"], [])
