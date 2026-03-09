"""
Phase 10 verification checklist (control plane shell and manager login).
Automated tests for items that can be asserted without a live manager host.
See docs/architecture/phase10_superadmin_vs_tenant_ui.md § Verification checklist.
"""
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest
from django.test import RequestFactory, TestCase, override_settings
from django.urls import resolve, reverse

from apps.accounts.models import User
from apps.accounts.views import auth_root_redirect, login_view
from config.urls import permission_denied, page_not_found, server_error


@override_settings(ALLOWED_HOSTS=["*"])
class Phase10ManagerLoginVerificationTests(TestCase):
    """Check 1 & 4: Manager login uses manager_login.html; tenant login uses login.html."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_manager_host_gets_manager_login_template(self):
        request = self.factory.get("/authentication/login/", HTTP_HOST="manager.runmycampus.com")
        request.session = {}
        request.user = AnonymousUser()
        request.public_host_kind = "manager"
        response = login_view(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8", errors="replace")
        self.assertIn("Control plane sign-in", content)
        self.assertIn("RunMyCampus Manager", content)

    def test_non_manager_host_gets_standard_login_template(self):
        request = self.factory.get("/authentication/login/", HTTP_HOST="school.runmycampus.com")
        request.session = {}
        request.user = AnonymousUser()
        request.public_host_kind = None
        response = login_view(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8", errors="replace")
        self.assertIn("School portal login", content)

    def test_auth_root_redirects_to_login_on_manager_host(self):
        request = self.factory.get("/authentication/", HTTP_HOST="manager.runmycampus.com")
        request.session = {}
        request.user = AnonymousUser()
        request.public_host_kind = "manager"
        response = auth_root_redirect(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:login"))

    def test_auth_root_redirects_to_login_on_tenant_host(self):
        request = self.factory.get("/authentication/", HTTP_HOST="school.runmycampus.com")
        request.session = {}
        request.user = AnonymousUser()
        request.public_host_kind = None
        response = auth_root_redirect(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:login"))

    def test_auth_root_preserves_next_query_string(self):
        request = self.factory.get("/authentication/?next=/portal/", HTTP_HOST="school.runmycampus.com")
        request.session = {}
        request.user = AnonymousUser()
        request.public_host_kind = None
        response = auth_root_redirect(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:login") + "?next=%2Fportal%2F")


class Phase10ErrorPagesVerificationTests(TestCase):
    """Check 5: Manager host gets control-plane 403/404/500 templates."""

    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_manager_403_uses_control_plane_template(self):
        request = self.factory.get("/admin/")
        request.user = User(is_staff=True, is_superuser=False)
        request.public_host_kind = "manager"
        response = permission_denied(request, None)
        self.assertEqual(response.status_code, 403)
        content = response.content.decode("utf-8", errors="replace")
        # Control-plane 403 shows either "Back to Manager" (generic) or "Tenant Mission Control" (admin-forbidden).
        self.assertTrue(
            "Back to Manager" in content or "Tenant Mission Control" in content,
            msg="Control plane 403 must show manager navigation (Back to Manager or Tenant Mission Control)",
        )

    def test_manager_404_uses_control_plane_template(self):
        request = self.factory.get("/super/nonexistent/")
        request.public_host_kind = "manager"
        response = page_not_found(request, None)
        self.assertEqual(response.status_code, 404)
        content = response.content.decode("utf-8", errors="replace")
        self.assertIn("Back to Manager", content)

    def test_manager_500_uses_control_plane_template(self):
        request = self.factory.get("/super/")
        request.public_host_kind = "manager"
        response = server_error(request)
        self.assertEqual(response.status_code, 500)
        content = response.content.decode("utf-8", errors="replace")
        self.assertIn("Back to Manager", content)

    def test_tenant_403_uses_standard_template(self):
        request = self.factory.get("/admin/")
        request.user = User(is_staff=True, is_superuser=False)
        request.public_host_kind = None
        response = permission_denied(request, None)
        self.assertEqual(response.status_code, 403)
        content = response.content.decode("utf-8", errors="replace")
        self.assertIn("Access denied", content)


class Phase10UrlConfVerificationTests(TestCase):
    """Check 2 & 3: Manager urlconf has /super/ and admin; tenant urlconf does not have /super/."""

    def test_manager_urlconf_resolves_super_dashboard(self):
        match = resolve("/super/", urlconf="config.manager_urls")
        self.assertEqual(match.namespace, "super")
        self.assertIsNotNone(match.url_name)

    def test_manager_urlconf_resolves_admin(self):
        match = resolve("/admin/", urlconf="config.manager_urls")
        self.assertIsNotNone(match)

    def test_manager_urlconf_resolves_auth_root(self):
        match = resolve("/authentication/", urlconf="config.manager_urls")
        self.assertEqual(match.namespace, "accounts")
        self.assertEqual(match.url_name, "root")

    def test_tenant_urlconf_resolves_auth_root(self):
        match = resolve("/authentication/", urlconf="config.tenant_urls")
        self.assertEqual(match.namespace, "accounts")
        self.assertEqual(match.url_name, "root")

    def test_tenant_urlconf_does_not_resolve_super(self):
        from django.urls import Resolver404
        with self.assertRaises(Resolver404):
            resolve("/super/", urlconf="config.tenant_urls")
