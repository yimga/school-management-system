"""Wave 1 (H1 seal) — operator ("super") routes on the tenant host require
control-plane access, and re-gated operator views deny is_staff tenant admins.

The platform mints is_staff=True tenant admins, so @staff_member_required is not
an operator gate. These tests lock: (1) the super-segment middleware guard blocks
a tenant identity on a mid-path operator route (/portal/super/...), and (2) an
operator view re-gated to require_control_plane_access denies a non-operator.
"""
from unittest import mock

from django.http import HttpResponse, HttpResponseForbidden
from django.test import RequestFactory, TestCase

from apps.schools.middleware import (
    TenantSuperAdminRequiredMiddleware,
    _is_operator_super_route,
)


class OperatorSuperRouteHelperTest(TestCase):
    def test_truth_table(self):
        # operator: canonical prefix + any mid-path `super` segment
        self.assertTrue(_is_operator_super_route("/super/dashboard/"))
        self.assertTrue(_is_operator_super_route("/portal/super/merges/"))
        self.assertTrue(_is_operator_super_route("/api/v1/super/tenant-inspect/1/"))
        # not operator: normal tenant paths + `super` as a substring only
        self.assertFalse(_is_operator_super_route("/portal/parent/"))
        self.assertFalse(_is_operator_super_route("/supervisor/"))
        self.assertFalse(_is_operator_super_route("/finance/"))
        self.assertFalse(_is_operator_super_route("/"))


class TenantSuperSegmentGuardTest(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.mw = TenantSuperAdminRequiredMiddleware(lambda r: "OK")

    def _req(self, path, authed=True):
        req = self.rf.get(path)
        req.user = mock.Mock(is_authenticated=authed)
        return req

    @mock.patch("apps.schools.control_plane.user_has_control_plane_access", return_value=False)
    def test_tenant_staff_blocked_on_portal_super(self, _gate):
        # An is_staff tenant admin (no control-plane access) hitting the leaked
        # /portal/super/merges/ operator route must be forbidden.
        resp = self.mw.process_request(self._req("/portal/super/merges/"))
        self.assertIsInstance(resp, HttpResponseForbidden)

    @mock.patch("apps.schools.control_plane.user_has_control_plane_access", return_value=True)
    def test_operator_allowed_on_portal_super(self, _gate):
        resp = self.mw.process_request(self._req("/portal/super/merges/"))
        self.assertIsNone(resp)

    def test_normal_tenant_path_untouched(self):
        # No `super` segment -> guard is a pass-through (returns None before any gate).
        self.assertIsNone(self.mw.process_request(self._req("/portal/parent/")))
        self.assertIsNone(self.mw.process_request(self._req("/finance/dashboard/")))

    @mock.patch("apps.schools.control_plane.user_has_control_plane_access", return_value=False)
    def test_unauthenticated_redirected_on_portal_super(self, _gate):
        resp = self.mw.process_request(self._req("/portal/super/merges/", authed=False))
        self.assertIsNotNone(resp)
        self.assertEqual(getattr(resp, "status_code", None), 302)


class ReGatedOperatorViewTest(TestCase):
    """Views re-gated from @staff_member_required to @require_control_plane_access
    must deny a non-operator (is_staff tenant admin) even when reached directly."""

    def setUp(self):
        self.rf = RequestFactory()

    @mock.patch("apps.schools.control_plane.user_has_control_plane_access", return_value=False)
    def test_assist_dock_inspect_denies_non_operator(self, _gate):
        from apps.assist_dock.power_views import inspect_landing

        req = self.rf.get("/assist-dock/inspect/?page=/")
        req.user = mock.Mock(is_authenticated=True)
        resp = inspect_landing(req)
        self.assertEqual(resp.status_code, 403)

    @mock.patch("apps.assist_dock.power_views.render", return_value=HttpResponse("ok"))
    @mock.patch("apps.schools.control_plane.user_has_control_plane_access", return_value=True)
    def test_assist_dock_inspect_allows_operator(self, _gate, _render):
        # render() is mocked so the gate-allows path doesn't drag in the full
        # template + context processors (which need a real user, not a Mock);
        # we only assert the control-plane gate lets an operator reach the view.
        from apps.assist_dock.power_views import inspect_landing

        req = self.rf.get("/assist-dock/inspect/?page=/")
        req.user = mock.Mock(is_authenticated=True, is_staff=True, is_superuser=True)
        resp = inspect_landing(req)
        self.assertEqual(resp.status_code, 200)

    @mock.patch("apps.schools.control_plane.user_has_control_plane_access", return_value=False)
    def test_platform_health_center_denies_non_operator(self, _gate):
        from apps.platform_runtime.views_platform_health import platform_health_center

        req = self.rf.get("/platform-runtime/platform-health/")
        req.user = mock.Mock(is_authenticated=True)
        resp = platform_health_center(req)
        self.assertEqual(resp.status_code, 403)
