"""Operator-route denials raise PermissionDenied (branded handler403), not bare text.

User scenario: visiting an operator-only route (e.g. /siteconfig/regions/validation/,
a manager control-plane surface) on a TENANT host returned a raw, unstyled
``HttpResponseForbidden("Control-plane surface required (manager host or /super/).")``
— a dead-end that looked nothing like the rest of the platform.

The gate itself is CORRECT (cross-region validation is operator-only). The fix is
presentational: the ``control_plane`` decorators now ``raise PermissionDenied`` so
Django routes the rejection through the platform's branded ``handler403``
(``config/error_handlers.py::permission_denied`` -> ``errors/403.html`` on tenant
hosts, ``errors/403_control_plane.html`` on the manager host) instead of dumping
developer-facing text.

These are no-DB unit tests of the decorator layer: the surface gate is evaluated
before any user/DB lookup, so ``RequestFactory`` + ``SimpleTestCase`` is enough and
avoids tenant/host/urlconf flakiness.
"""

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from apps.schools.control_plane import (
    require_control_plane_access,
    require_super_access,
    require_super_access_with_host,
)


def _ok_view(request):
    return HttpResponse("ok")


class RequireSuperAccessWithHostBrandedDenialTest(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_operator_route_on_tenant_surface_raises_permission_denied(self):
        """The exact reported scenario: an operator-only route reached on a
        non-control-plane (tenant) surface must raise PermissionDenied so the
        branded 403 renders — NOT return a bare-text HttpResponseForbidden."""
        view = require_super_access_with_host(_ok_view)
        req = self.rf.get("/siteconfig/regions/validation/")
        # No public_host_kind attr => not the manager surface; path is not /super/.
        req.user = AnonymousUser()
        with self.assertRaises(PermissionDenied):
            view(req)

    def test_super_path_still_passes_surface_gate(self):
        """Guard against an over-broad change: the /super/ path must still pass the
        surface gate. An anonymous user there gets the login redirect (302), proving
        the surface check was NOT turned into a blanket PermissionDenied."""
        view = require_super_access_with_host(_ok_view)
        req = self.rf.get("/super/regions/validation/")
        req.user = AnonymousUser()
        resp = view(req)
        self.assertEqual(resp.status_code, 302)  # redirect_to_login, not a raise

    def test_manager_surface_passes_surface_gate(self):
        """A request flagged as the manager host passes the surface gate too."""
        view = require_super_access_with_host(_ok_view)
        req = self.rf.get("/anything/")
        req.public_host_kind = "manager"
        req.user = AnonymousUser()
        resp = view(req)
        self.assertEqual(resp.status_code, 302)  # anon -> login redirect, not raise


class OtherControlPlaneDecoratorsAnonRedirectTest(SimpleTestCase):
    """The sibling decorators keep sending anonymous users to login (302); only the
    authenticated-but-forbidden branches changed to PermissionDenied."""

    def setUp(self):
        self.rf = RequestFactory()

    def test_require_control_plane_access_anon_redirects(self):
        view = require_control_plane_access(_ok_view)
        req = self.rf.get("/manager/ops/")
        req.user = AnonymousUser()
        self.assertEqual(view(req).status_code, 302)

    def test_require_super_access_anon_redirects(self):
        view = require_super_access(_ok_view)
        req = self.rf.get("/super/thing/")
        req.user = AnonymousUser()
        self.assertEqual(view(req).status_code, 302)
