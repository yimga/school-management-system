"""IntegrationMarketplaceAdmin permission gate for tenant owners.

Regression for production 403 on /admin/integrations_marketplace/integration/
when the user is a school owner (is_school_owner=True) but not Django is_staff.
"""

from types import SimpleNamespace
from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.test import SimpleTestCase

from apps.integrations_marketplace.admin import IntegrationMarketplaceAdmin
from apps.integrations_marketplace.models import Integration


def _req(user, school=None):
    return SimpleNamespace(user=user, school=school or SimpleNamespace(pk=1))


class IntegrationMarketplaceAdminPermissionTests(SimpleTestCase):
    def setUp(self):
        self.admin = IntegrationMarketplaceAdmin(Integration, AdminSite())
        self.school = SimpleNamespace(pk=1, slug="gilead-tech")

    def test_superuser_can_access_integration_changelist(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_active=True,
            is_superuser=True,
            is_staff=False,
            pk=1,
            role="ADMIN",
        )
        req = _req(user, self.school)
        self.assertTrue(self.admin.has_module_permission(req))
        self.assertTrue(self.admin.has_view_permission(req))
        self.assertTrue(self.admin.has_change_permission(req))

    def test_school_owner_without_is_staff_can_access(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_active=True,
            is_superuser=False,
            is_staff=False,
            pk=42,
            role="ADMIN",
            has_feature_permission=lambda *a, **k: False,
        )
        membership = SimpleNamespace(role="ADMIN", is_school_owner=True)
        with mock.patch(
            "apps.schools.models.SchoolMembership.objects.filter"
        ) as filt:
            filt.return_value.only.return_value.first.return_value = membership
            req = _req(user, self.school)
            self.assertTrue(self.admin.has_module_permission(req))
            self.assertTrue(self.admin.has_view_permission(req))
            self.assertTrue(self.admin.has_change_permission(req))

    def test_anonymous_denied(self):
        req = _req(SimpleNamespace(is_authenticated=False, is_active=False))
        self.assertFalse(self.admin.has_module_permission(req))
