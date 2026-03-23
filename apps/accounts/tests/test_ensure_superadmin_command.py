"""ensure_superadmin delegates to ensure_superuser with admin/admin."""

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User


class EnsureSuperadminCommandTests(TestCase):
    def test_ensure_superadmin_creates_admin_with_superadmin_role(self):
        call_command("ensure_superadmin", verbosity=0)
        u = User.objects.get(username="admin")
        self.assertTrue(u.is_superuser)
        self.assertTrue(u.check_password("admin"))
        self.assertEqual((u.role or "").upper(), "SUPERADMIN")
