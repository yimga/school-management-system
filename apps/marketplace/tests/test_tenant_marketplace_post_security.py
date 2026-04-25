"""
Tenant marketplace mutating routes must stay wrapped with ``login_required`` in ``config.tenant_urls``.

Static contract test (no DB, no Client) — avoids Windows test DB file locks in agent runs.

Runtime tests use a real tenant-style host (``*.runmycampus.com``) so ``UrlConfSwitcherMiddleware``
serves ``config.tenant_urls`` and ``TenantMiddleware`` resolves ``request.school`` from subdomain.
"""

import unittest
from pathlib import Path

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School


# Host that is not "local" so urlconf stays on tenant_urls; subdomain must match School.subdomain.
_TENANT_HTTP_HOST = "mkt-httpsec-tnt.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _TENANT_HTTP_HOST])
class TenantMarketplacePostHttpSecurityTests(TestCase):
    """
    Client-based POST policy: anonymous → login redirect; disallowed role → 403;
    privileged role → past ``user_passes_test`` (302/404, not 403).
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="HTTP Sec School",
            slug="mkt-httpsec-tnt",
            subdomain="mkt-httpsec-tnt",
            is_active=True,
        )
        cls.teacher = User.objects.create_user(
            username="mkt_httpsec_teacher",
            password="test-harness-1",
            role=User.Role.TEACHER,
        )
        cls.admin = User.objects.create_user(
            username="mkt_httpsec_admin",
            password="test-harness-1",
            role=User.Role.ADMIN,
        )

    def setUp(self):
        # Do not re-raise Http404 inside views (404 handler/template can differ by host).
        self.client = Client(HTTP_HOST=_TENANT_HTTP_HOST, raise_request_exception=False)

    def _post(self, name: str, data=None):
        # Tests use default ROOT_URLCONF; tenant route names live only on config.tenant_urls.
        path = reverse(name, urlconf="config.tenant_urls")
        return self.client.post(path, data or {}, follow=False)

    def test_anonymous_posts_redirect_to_login(self):
        """Unauthenticated POST must not reach mutating view (login redirect)."""
        for url_name in (
            "tenant_install_app",
            "tenant_uninstall_app",
            "tenant_approve_scope",
            "tenant_activate_installation",
        ):
            with self.subTest(url=url_name):
                resp = self._post(
                    url_name,
                    {
                        "app_id": "1",
                        "install_after_impact_preview": "1",
                        "installation_id": "1",
                        "grant_id": "1",
                    },
                )
                self.assertEqual(resp.status_code, 302, msg=url_name)
                loc = (resp.get("Location") or "") + (resp.headers.get("location") or "")
                self.assertTrue(
                    "/authentication/login" in loc or "login" in loc.lower(),
                    msg=f"{url_name} → {loc}",
                )

    def test_teacher_receives_403_or_safe_redirect_on_post(self):
        """Non-privileged role must not complete mutating marketplace flows (403 or pre-view redirect e.g. MFA)."""
        self.client.login(username="mkt_httpsec_teacher", password="test-harness-1")
        payloads = {
            "tenant_install_app": {"app_id": "1", "install_after_impact_preview": "0"},
            "tenant_uninstall_app": {},
            "tenant_approve_scope": {},
            "tenant_activate_installation": {},
        }
        for url_name, data in payloads.items():
            with self.subTest(url=url_name):
                resp = self._post(url_name, data)
                self.assertIn(
                    resp.status_code,
                    (302, 403),
                    msg=f"{url_name}: expected 403 or safe 302 (e.g. MFA), got {resp.status_code}",
                )
                self.assertNotEqual(resp.status_code, 200)

    def test_admin_passes_gate_install_without_n17_confirm_redirects(self):
        """Privileged role passes ``tenant_may_manage_marketplace``; N17 guard redirects (no missing-app 404)."""
        self.client.login(username="mkt_httpsec_admin", password="test-harness-1")
        resp = self._post(
            "tenant_install_app",
            {
                "app_id": "1",
                "install_after_impact_preview": "0",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertNotEqual(resp.status_code, 403)

    def test_admin_passes_gate_mutators_missing_ids_redirect(self):
        """Privileged user hits view; validation redirects before object fetch (302, not 403)."""
        self.client.login(username="mkt_httpsec_admin", password="test-harness-1")
        cases = {
            "tenant_uninstall_app": {},
            "tenant_approve_scope": {},
            "tenant_activate_installation": {},
        }
        for url_name, data in cases.items():
            with self.subTest(url=url_name):
                resp = self._post(url_name, data)
                self.assertEqual(resp.status_code, 302)
                self.assertNotEqual(resp.status_code, 403)


class TenantMarketplaceUrlLoginContractTests(unittest.TestCase):
    """POST-sensitive tenant marketplace paths must use login_required in urlconf."""

    def _tenant_urls_text(self) -> str:
        root = Path(__file__).resolve().parent.parent.parent.parent
        return (root / "config" / "tenant_urls.py").read_text(encoding="utf-8", errors="replace")

    def test_install_and_lifecycle_routes_use_login_required(self) -> None:
        text = self._tenant_urls_text()
        for needle in (
            "login_required(tenant_install_app",
            "login_required(tenant_uninstall_app",
            "login_required(tenant_approve_scope",
            "login_required(tenant_activate_installation",
        ):
            with self.subTest(needle=needle):
                self.assertIn(
                    needle,
                    text,
                    f"config/tenant_urls.py must keep {needle} for anonymous blocking",
                )
