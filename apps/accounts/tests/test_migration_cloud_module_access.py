"""Tenant admins + superadmins can reach the Migration Cloud connector module.

Regression for the owner-reported lockout: ``migration_cloud_connector`` was missing from
``MODULE_ACCESS_DEFAULTS``, so ``can_access_module()`` default-denied it for everyone except
a Django ``is_superuser`` — walling tenant ADMIN / IT_ADMIN / owner (and a non-superuser
SUPERADMIN role) out of their own import wizard with an "Access required" page. Mirrors the
earlier ``setup_studio`` fix (see ``test_setup_studio_module_access.py``).
"""

from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.permissions import MODULE_ACCESS_DEFAULTS, can_access_module

MODULE = "migration_cloud_connector"


class MigrationCloudModuleAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="mc_admin", password="testpass123",
            role=User.Role.ADMIN, is_superuser=False,
        )
        self.it_admin = User.objects.create_user(
            username="mc_it", password="testpass123",
            role="IT_ADMIN", is_superuser=False,
        )
        self.superadmin = User.objects.create_user(
            username="mc_super", password="testpass123",
            role=User.Role.SUPERADMIN, is_staff=True, is_superuser=False,
        )
        self.teacher = User.objects.create_user(
            username="mc_teacher", password="testpass123",
            role=User.Role.TEACHER, is_superuser=False,
        )

    def test_module_is_registered(self):
        self.assertIn(MODULE, MODULE_ACCESS_DEFAULTS)

    def test_admin_can_read_and_write(self):
        self.assertTrue(can_access_module(self.admin, MODULE, action="read"))
        self.assertTrue(can_access_module(self.admin, MODULE, action="write"))

    def test_it_admin_can_read(self):
        self.assertTrue(can_access_module(self.it_admin, MODULE, action="read"))

    def test_superadmin_role_can_access(self):
        # Non-superuser SUPERADMIN role — the owner-reported case.
        self.assertTrue(can_access_module(self.superadmin, MODULE, action="read"))

    def test_teacher_denied(self):
        self.assertFalse(can_access_module(self.teacher, MODULE, action="read"))

    def test_superadmin_role_has_godmode_on_unregistered_module(self):
        # The top admin is never locked out — even a module not yet in the map...
        self.assertTrue(
            can_access_module(self.superadmin, "some_unregistered_module_xyz", "read")
        )
        # ...while a plain ADMIN still gets the safe default-deny on an unknown module.
        self.assertFalse(
            can_access_module(self.admin, "some_unregistered_module_xyz", "read")
        )

    def test_finance_privileged_tier_gates_the_banner(self):
        # The finance "not enabled" banner is suppressed for anyone module_access says is
        # finance-privileged. Admin + SUPERADMIN qualify; a plain teacher does not.
        self.assertTrue(can_access_module(self.admin, "finance", action="read"))
        self.assertTrue(can_access_module(self.superadmin, "finance", action="read"))
        self.assertFalse(can_access_module(self.teacher, "finance", action="read"))


class TenantNamespaceLockoutRegressionTests(TestCase):
    """Every tenant-host URL namespace resolved by ModuleAccessMiddleware must be a key in
    MODULE_ACCESS_DEFAULTS, or it default-denies for all non-superusers. These namespaces
    were each MISSING (or mis-keyed) and locked legitimate roles out of their own surfaces.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username="ns_admin", password="testpass123",
            role=User.Role.ADMIN, is_superuser=False,
        )
        self.student = User.objects.create_user(
            username="ns_student", password="testpass123",
            role=User.Role.STUDENT, is_superuser=False,
        )
        self.parent = User.objects.create_user(
            username="ns_parent", password="testpass123",
            role=User.Role.PARENT, is_superuser=False,
        )

    def test_admin_config_namespaces_registered_and_open_to_admin(self):
        # apicenter is the REAL namespace (the old "api_center" key was dead/mis-keyed).
        for module in ("template_marketplace", "automation", "marketplace", "apicenter"):
            self.assertIn(module, MODULE_ACCESS_DEFAULTS, module)
            self.assertTrue(can_access_module(self.admin, module, "read"), module)
            self.assertTrue(can_access_module(self.admin, module, "write"), module)

    def test_dead_api_center_key_replaced_by_apicenter(self):
        # The mis-keyed name must be gone; the namespace the middleware actually resolves wins.
        self.assertNotIn("api_center", MODULE_ACCESS_DEFAULTS)
        self.assertIn("apicenter", MODULE_ACCESS_DEFAULTS)

    def test_community_event_hub_open_to_all_authenticated(self):
        # school_events (mounted at /events/) is community-facing: students/parents self-register.
        self.assertIn("school_events", MODULE_ACCESS_DEFAULTS)
        for user in (self.admin, self.student, self.parent):
            self.assertTrue(can_access_module(user, "school_events", "read"), user.role)
            self.assertTrue(can_access_module(user, "school_events", "write"), user.role)

    def test_nested_compliance_reporting_inherits_parent_module(self):
        # ModuleAccessMiddleware collapses "compliance:compliance_reporting" -> "compliance",
        # so a compliance-authorized admin reaches /compliance/reports/ (was fail-closed).
        self.assertTrue(can_access_module(self.admin, "compliance", "read"))
