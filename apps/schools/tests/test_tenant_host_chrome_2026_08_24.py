"""Tenant hosts must never pick operator control-plane chrome."""

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.middleware_minimum_security_strength import (
    MinimumSecurityStrengthMiddleware,
)
from apps.accounts.operator_account_render import render_account_page
from apps.schools.control_plane import use_control_plane_shell
from apps.schools.middleware import UrlConfSwitcherMiddleware
from apps.schools.models import School, SchoolMembership


@override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class TenantHostChromeTests(TestCase):
    def setUp(self):
        self.mw = UrlConfSwitcherMiddleware(lambda r: None)
        self.rf = RequestFactory()

    def _route(self, host):
        request = self.rf.get("/", HTTP_HOST=host)
        self.mw.process_request(request)
        return request

    def test_cloud_subdomain_is_marked_tenant_host(self):
        request = self._route("gilead-tech.runmycampus.com")
        self.assertEqual(request.urlconf, "config.tenant_urls")
        self.assertTrue(request.is_tenant_host)
        self.assertEqual(request.public_host_kind, "tenant")

    def test_tenant_host_never_uses_control_plane_shell(self):
        request = self._route("gilead-tech.runmycampus.com")
        self.assertFalse(use_control_plane_shell(request))

    @override_settings(SINGLE_TENANT=True, USE_DJANGO_TENANTS=False)
    def test_sovereign_ip_never_uses_control_plane_shell(self):
        request = self._route("10.10.20.137:10000")
        self.assertFalse(use_control_plane_shell(request))


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.tenant_urls",
    SECURITY_ENFORCE_MINIMUM_STRENGTH=True,
)
class TenantProfileRenderChromeTests(TestCase):
    """Profile on a tenant subdomain must not ship operator RUNMYCAMPUS topbar chrome."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.school = School.objects.create(
            name="Gilead Tech High",
            slug="gilead-tech",
            subdomain="gilead-tech",
            is_active=True,
        )
        cls.admin = User.objects.create_user(
            username="gilead-admin",
            email="admin@gilead.test",
            password="pass12345678",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=cls.admin,
            school=cls.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def _tenant_client(self) -> Client:
        client = Client(HTTP_HOST="gilead-tech.runmycampus.com")
        client.force_login(self.admin)
        session = client.session
        session["school_id"] = str(self.school.pk)
        session["mfa_verified"] = True
        session.save()
        return client

    def test_render_account_page_uses_tenant_shell_not_control_plane(self):
        request = RequestFactory().get(
            reverse("accounts:user_profile"),
            HTTP_HOST="gilead-tech.runmycampus.com",
        )
        UrlConfSwitcherMiddleware(lambda r: None).process_request(request)
        request.user = self.admin
        request.school = self.school
        self.assertTrue(request.is_tenant_host)
        self.assertFalse(use_control_plane_shell(request))

        response = render_account_page(
            request,
            portal_template="accounts/profile.html",
            body_template="accounts/partials/operator_profile_body.html",
            context={},
            page_title="My profile",
        )
        html = response.content.decode("utf-8", errors="replace")
        self.assertIn("data-rmc-tenant-header-100x", html)
        self.assertNotIn('id="cpSearchInput"', html)
        self.assertNotIn("Search tenants, incidents", html)

    def test_profile_route_via_client_has_tenant_header(self):
        response = self._tenant_client().get(reverse("accounts:user_profile"))
        self.assertEqual(response.status_code, 200, getattr(response, "url", ""))
        html = response.content.decode("utf-8", errors="replace")
        self.assertIn("data-rmc-tenant-header-100x", html)
        self.assertNotIn('id="cpSearchInput"', html)
