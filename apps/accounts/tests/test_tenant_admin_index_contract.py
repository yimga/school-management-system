"""Tenant /admin/ index must ship Admin OS Discover — never the empty Raw CRUD shell."""

from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from config.admin import tenant_admin_site


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class TenantAdminIndexContractTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Catalog School",
            slug="catalog-school",
            subdomain="catalog-school",
            is_active=True,
        )
        self.owner = User.objects.create_user(
            username="catalog_owner",
            password="testpass123",
            role=User.Role.ADMIN,
            is_staff=False,
            is_superuser=False,
        )
        SchoolMembership.objects.create(
            user=self.owner,
            school=self.school,
            role=User.Role.ADMIN,
            is_school_owner=True,
            is_primary=True,
        )

    def _request(self):
        request = self.factory.get("/admin/")
        request.user = self.owner
        request.school = self.school
        request.public_host_kind = "tenant"
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    def test_owner_without_is_staff_index_is_intelligent_catalog(self):
        request = self._request()
        self.assertTrue(tenant_admin_site.has_permission(request))
        response = tenant_admin_site.index(request)
        response.render()
        html = response.content.decode("utf-8", errors="replace")

        self.assertNotIn("Raw model CRUD", html)
        self.assertIn("data-rmc-admin-archetype=\"discover\"", html)
        self.assertIn("data-rmc-admin-discover=\"1\"", html)
        self.assertIn("2026-08-09-v17.1", html)
        self.assertIn("Model catalog", html)
        self.assertIn("rmc-admin-discover-canvas", html)

    def test_admin_index_ships_tenant_tools_rail(self):
        """The tenant /admin/ (Unfold) shell must carry the SAME RBAC-aware Tools
        edge-tray as the portal Admin Home — the "both surfaces consistent"
        requirement. Renders the whole shell so a broken include would fail here,
        not just a source-string canary."""
        request = self._request()
        response = tenant_admin_site.index(request)
        response.render()
        html = response.content.decode("utf-8", errors="replace")
        self.assertIn('id="page-data-rmc-tenant-tools"', html)
        self.assertIn("rmc-operator-tools-tray.js", html)
        self.assertIn("rmc-operator-tools-tray.css", html)
        # Assist-dock registry island must ride along so the tray JS resolves chips.
        self.assertIn("page-data-rmc-assist-dock-registry", html)
        # Operator (manager) tools island must NOT appear on the tenant host.
        self.assertNotIn('id="page-data-rmc-operator-tools"', html)

    def test_anonymous_has_no_permission(self):
        request = self._request()
        request.user = AnonymousUser()
        self.assertFalse(tenant_admin_site.has_permission(request))
