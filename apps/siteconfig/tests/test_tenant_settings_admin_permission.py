"""TenantSettingsAdmin permission gate.

Regression for a production 403: a self-service tenant owner (role=ADMIN,
is_staff=False) hit "Access needs approval" on
/admin/siteconfig/sitesettings/<pk>/change/ on their own tenant host. The
model's ``_is_site_admin`` required ``is_staff`` even though this ModelAdmin is
registered only on the ``tenant_admin_site``, whose ``has_permission`` already
scopes entry to a school-bound admin/owner — and self-service owners are
role-based SchoolMembership users, not Django staff. The fix drops the is_staff
conjunct while keeping the {ADMIN, SUPERADMIN} narrowing.
"""

from types import SimpleNamespace

from django.contrib.admin.sites import AdminSite
from django.test import SimpleTestCase

from apps.siteconfig.admin import TenantSettingsAdmin
from apps.siteconfig.models import SiteSettings


class TenantSettingsAdminPermissionTests(SimpleTestCase):
    def setUp(self):
        self.admin = TenantSettingsAdmin(SiteSettings, AdminSite())

    @staticmethod
    def _user(role="ADMIN", is_staff=False, is_superuser=False):
        return SimpleNamespace(role=role, is_staff=is_staff, is_superuser=is_superuser)

    def test_admin_role_without_is_staff_can_manage_site_settings(self):
        # The reported case: role=ADMIN owner, not Django staff.
        user = self._user(role="ADMIN", is_staff=False)
        self.assertTrue(self.admin._is_site_admin(user))
        self.assertTrue(self.admin.has_change_permission(_req(user)))
        self.assertTrue(self.admin.has_view_permission(_req(user)))
        self.assertTrue(self.admin.has_module_permission(_req(user)))

    def test_superadmin_role_without_is_staff_can_manage(self):
        self.assertTrue(self.admin._is_site_admin(self._user(role="SUPERADMIN", is_staff=False)))

    def test_superuser_can_manage(self):
        self.assertTrue(self.admin._is_site_admin(self._user(role="", is_superuser=True)))

    def test_narrowing_preserved_non_admin_roles_denied(self):
        # is_staff alone is not enough, and broader admin-like roles that CAN
        # reach the tenant admin site (PRINCIPAL/DEAN/IT_ADMIN) still cannot edit
        # core site settings.
        self.assertFalse(self.admin._is_site_admin(self._user(role="TEACHER", is_staff=True)))
        self.assertFalse(self.admin._is_site_admin(self._user(role="PRINCIPAL", is_staff=False)))
        self.assertFalse(self.admin._is_site_admin(self._user(role="", is_staff=False)))


def _req(user):
    return SimpleNamespace(user=user)
