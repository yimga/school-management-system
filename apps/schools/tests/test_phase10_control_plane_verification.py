"""
Phase 10 verification checklist (control plane shell and manager login).
Automated tests for items that can be asserted without a live manager host.
See docs/architecture/phase10_superadmin_vs_tenant_ui.md § Verification checklist.
"""

from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import resolve, reverse

from apps.accounts.models import User
from apps.accounts.views import auth_root_redirect, login_view
from config.urls import permission_denied, page_not_found, server_error


@override_settings(ALLOWED_HOSTS=["*"])
class Phase10ManagerLoginVerificationTests(TestCase):
    """Check 1 & 4: Manager login uses manager_login.html; tenant login uses login.html."""

    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(
        ROOT_URLCONF="config.manager_urls",
        RMC_PUBLIC_SITE_URL="https://runmycampus.com",
    )
    def test_unauthenticated_manager_login_redirects_to_public_host(self):
        client = Client(HTTP_HOST="manager.runmycampus.com")
        response = client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.startswith("https://runmycampus.com/authentication/login/")
        )

    def test_manager_host_gets_manager_login_template(self):
        request = self.factory.get(
            "/authentication/login/?next=/super/",
            HTTP_HOST="manager.runmycampus.com",
        )
        request.session = {}
        request.user = AnonymousUser()
        request.public_host_kind = "manager"
        response = login_view(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8", errors="replace")
        self.assertIn("Control plane sign-in", content)
        self.assertIn("RunMyCampus Manager", content)
        self.assertIn("manager-login-heading", content)
        self.assertIn("<head>", content)
        self.assertIn('type="password"', content)
        # shell_rmc_registry_html_attrs must not inject block tags inside <html>.
        self.assertNotRegex(
            content,
            r"<html[^>]*\n\s*<div",
            msg="invalid <div> inside <html> opening tag breaks manager DOM",
        )
        head_idx = content.find("<head>")
        body_idx = content.find("<body")
        login_idx = content.find("manager-login-heading")
        self.assertGreater(head_idx, 0)
        self.assertGreater(body_idx, head_idx)
        self.assertGreater(login_idx, body_idx)

    def test_non_manager_host_gets_standard_login_template(self):
        request = self.factory.get(
            "/authentication/login/", HTTP_HOST="school.runmycampus.com"
        )
        request.session = {}
        request.user = AnonymousUser()
        request.public_host_kind = None
        response = login_view(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8", errors="replace")
        self.assertIn("School portal login", content)

    def test_auth_root_redirects_to_login_on_manager_host(self):
        request = self.factory.get(
            "/authentication/", HTTP_HOST="manager.runmycampus.com"
        )
        request.session = {}
        request.user = AnonymousUser()
        request.public_host_kind = "manager"
        response = auth_root_redirect(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:login"))

    def test_auth_root_redirects_to_login_on_tenant_host(self):
        request = self.factory.get(
            "/authentication/", HTTP_HOST="school.runmycampus.com"
        )
        request.session = {}
        request.user = AnonymousUser()
        request.public_host_kind = None
        response = auth_root_redirect(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:login"))

    def test_auth_root_preserves_next_query_string(self):
        request = self.factory.get(
            "/authentication/?next=/portal/", HTTP_HOST="school.runmycampus.com"
        )
        request.session = {}
        request.user = AnonymousUser()
        request.public_host_kind = None
        response = auth_root_redirect(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"], reverse("accounts:login") + "?next=%2Fportal%2F"
        )


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
        # Control-plane 403 shows "Back to Manager" (generic), "Control Plane" (admin-forbidden button), or "Tenant Mission Control".
        self.assertTrue(
            "Back to Manager" in content
            or "Control Plane" in content
            or "Tenant Mission Control" in content,
            msg="Control plane 403 must show manager navigation (Back to Manager, Control Plane, or Tenant Mission Control)",
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
        self.assertTrue(
            "Access denied" in content or "Access needs approval" in content,
            msg="Tenant 403 must surface a clear denial headline (standard shell)",
        )


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
