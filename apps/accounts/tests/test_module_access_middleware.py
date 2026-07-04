"""Tests for ModuleAccessMiddleware: fail-closed when path looks module-like but module cannot be resolved."""

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, TestCase

from apps.accounts.middleware import ModuleAccessMiddleware
from apps.accounts.models import User


def get_response(request: HttpRequest) -> HttpResponse:
    return HttpResponse(status=200)


class ModuleAccessMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = ModuleAccessMiddleware(get_response)

    def test_unauthenticated_module_like_path_bypass(self):
        """Unauthenticated request to module-like path that resolves to None still gets through (no 403)."""
        request = self.factory.get("/portal")
        request.user = AnonymousUser()
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_authenticated_module_like_path_unresolved_denied(self):
        """Authenticated request to path that looks module-like but _resolve_module returns None gets 403."""
        user = User.objects.create_user(username="teacher1", password="pass1234")
        user.role = User.Role.TEACHER
        user.save(update_fields=["role"])
        request = self.factory.get(
            "/portal"
        )  # no trailing slash: prefix match fails, resolve may fail
        request.user = user
        response = self.middleware(request)
        self.assertEqual(response.status_code, 403)

    def test_authenticated_module_like_path_api_returns_json_403(self):
        """When module access is denied for an /api/ path, response is JSON 403."""
        user = User.objects.create_user(username="apiuser", password="pass1234")
        user.role = User.Role.TEACHER
        user.save(update_fields=["role"])
        request = self.factory.get("/api/some-endpoint", HTTP_ACCEPT="application/json")
        request.user = user
        with patch("apps.accounts.middleware.can_access_module", return_value=False):
            response = self.middleware(request)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_path_looks_module_like(self):
        """_path_looks_module_like returns True for first segment in MODULE_LIKE_FIRST_SEGMENTS."""
        self.assertTrue(self.middleware._path_looks_module_like("/portal"))
        self.assertTrue(self.middleware._path_looks_module_like("/portal/"))
        self.assertTrue(self.middleware._path_looks_module_like("/evals"))
        self.assertTrue(self.middleware._path_looks_module_like("/admin"))
        self.assertTrue(self.middleware._path_looks_module_like("/api"))
        self.assertFalse(self.middleware._path_looks_module_like("/"))
        self.assertFalse(self.middleware._path_looks_module_like("/other"))
        self.assertFalse(self.middleware._path_looks_module_like("/static/foo"))

    def test_bypass_path_not_checked(self):
        """Bypass paths (e.g. static, login) do not go through module resolution."""
        user = User.objects.create_user(username="bypassuser", password="pass1234")
        user.role = User.Role.TEACHER
        user.save(update_fields=["role"])
        request = self.factory.get("/static/css/admin.css")
        request.user = user
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_admin_path_bypasses_module_access_middleware(self):
        user = User.objects.create_user(username="tenantadminbypass", password="pass1234")
        user.role = User.Role.ADMIN
        user.save(update_fields=["role"])
        request = self.factory.get("/admin/")
        request.user = user

        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
