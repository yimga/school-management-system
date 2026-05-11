"""
RLS mode isolation: unset GUC => deny; set app.current_school_id => only that school; bypass => allow.
Requires PostgreSQL and USE_DJANGO_TENANTS=False. Tag: tenants_rls.
"""

import unittest

from django.db import connection
from django.test import TestCase, override_settings, tag


@tag("tenants_rls")
@unittest.skipIf(
    connection.vendor != "postgresql", "RLS isolation tests require PostgreSQL"
)
@override_settings(USE_DJANGO_TENANTS=False)
class TenantIsolationRlsModeTests(TestCase):
    """With RLS default-deny, unset context must return 0 rows; set context restricts to that school."""

    def setUp(self):
        from apps.schools.models import School, SchoolMembership
        from apps.schools.rls_context import rls_school, rls_bypass

        self.School = School
        self.SchoolMembership = SchoolMembership
        self.rls_school = rls_school
        self.rls_bypass = rls_bypass
        self.school_a = School.objects.create(
            name="School A",
            slug="school-a-rls",
            subdomain="school-a-rls",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="School B",
            slug="school-b-rls",
            subdomain="school-b-rls",
            is_active=True,
        )

    def _reset_guc(self):
        with connection.cursor() as c:
            c.execute("RESET app.current_school_id")
            c.execute("RESET app.rls_bypass")

    def tearDown(self):
        self._reset_guc()

    def test_unset_context_denies_rows(self):
        """With no GUC set, RLS default-deny should return 0 rows for tenant-scoped table."""
        self._reset_guc()
        from apps.schools.models import SchoolMembership

        count = SchoolMembership.objects.count()
        self.assertEqual(
            count, 0, "Unset app.current_school_id must deny all rows (default-deny)"
        )

    def test_set_school_id_restricts_to_that_school(self):
        """Setting app.current_school_id to school A, only A's rows are visible."""
        from apps.schools.models import SchoolMembership
        from apps.accounts.models import User

        user = User.objects.create_user(username="rlsuser", password="test")
        # FORCE RLS (schools 0048) rejects cross-tenant inserts without bypass.
        with self.rls_bypass():
            SchoolMembership.objects.create(
                user=user, school=self.school_a, role=User.Role.ADMIN, is_primary=True
            )
            SchoolMembership.objects.create(
                user=user, school=self.school_b, role=User.Role.ADMIN, is_primary=False
            )

        with self.rls_school(self.school_a.id):
            ids = list(SchoolMembership.objects.values_list("id", flat=True))
            self.assertGreater(len(ids), 0)
            for m in SchoolMembership.objects.all():
                self.assertEqual(m.school_id, self.school_a.id)

        with self.rls_school(self.school_b.id):
            for m in SchoolMembership.objects.all():
                self.assertEqual(m.school_id, self.school_b.id)

    def test_bypass_allows_all_rows(self):
        """Setting app.rls_bypass = 'on' allows seeing all tenant-scoped rows."""
        from apps.schools.models import SchoolMembership
        from apps.accounts.models import User

        user = User.objects.create_user(username="rlsbypass", password="test")
        with self.rls_bypass():
            SchoolMembership.objects.create(
                user=user, school=self.school_a, role=User.Role.ADMIN, is_primary=True
            )
            SchoolMembership.objects.create(
                user=user, school=self.school_b, role=User.Role.ADMIN, is_primary=False
            )

            count = SchoolMembership.objects.count()
            self.assertGreaterEqual(count, 2)
