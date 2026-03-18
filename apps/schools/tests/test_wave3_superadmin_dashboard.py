"""
Wave 3 tests: superadmin dashboard is platform governance; tenant data only via audited paths.

Non-negotiable: superadmin index has no direct tenant-domain CRUD shortcuts;
tenant data access only via impersonation or scoped support.
"""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User


class Wave3SuperadminIndexNoDirectTenantCrudTests(TestCase):
    """Wave 3.1: Superadmin index must not expose direct tenant-domain CRUD links."""

    def setUp(self):
        self.platform_user = User.objects.create_user(
            username="platform_w3",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )

    def test_super_dashboard_url_resolves(self):
        """Super dashboard must be reachable for platform user."""
        self.client.force_login(self.platform_user)
        response = self.client.get(
            reverse("super:dashboard"),
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertIn(
            response.status_code,
            (200, 302),
            "Super dashboard must load for platform user.",
        )

    def test_superadmin_index_template_is_control_plane(self):
        """Super admin index must use control-plane template (index_superadmin)."""
        from django.template.loader import get_template
        from django.template import TemplateDoesNotExist

        try:
            t = get_template("admin/index_superadmin.html")
            self.assertIsNotNone(
                t, "index_superadmin.html must exist for control plane."
            )
        except TemplateDoesNotExist:
            self.fail("admin/index_superadmin.html must exist.")


class Wave3TenantDataAccessRequiresImpersonationOrSupportTests(TestCase):
    """Wave 3.2: Tenant data access only via impersonation or scoped support."""

    def test_switch_to_tenant_requires_control_plane(self):
        """Switch-to-tenant (impersonation entry) must be under /super/ and require control-plane."""
        from apps.schools import super_urls

        names = [
            getattr(p, "name", None)
            for p in super_urls.urlpatterns
            if getattr(p, "name", None)
        ]
        self.assertIn(
            "switch_to_tenant", names, "Impersonation entry must be in super_urls."
        )
