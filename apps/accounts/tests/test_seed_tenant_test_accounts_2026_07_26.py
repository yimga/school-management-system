"""``manage.py seed_tenant_test_accounts`` — one-command tenant test seeding.

Proves: an existing account is attached as OWNER by email (without demoting an
existing primary or touching its password); teacher1/parent1 are created with role
+ SchoolMembership + a working Test1234 password; and the command is idempotent.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.schools.models import School, SchoolMembership

User = get_user_model()


class SeedTenantTestAccountsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Gilead Tech", slug="gilead-tech", subdomain="gilead-tech", is_active=True
        )
        # An already-claimed owner account whose username != email.
        self.owner = User.objects.create_user(
            username="yimgah", email="yimgah@yahoo.com", password="already-set-1234"
        )

    def _run(self, **extra):
        out = StringIO()
        args = ["--slug", "gilead-tech", "--owner-email", "yimgah@yahoo.com"]
        call_command("seed_tenant_test_accounts", *args, stdout=out, **extra)
        return out.getvalue()

    def test_attaches_owner_and_creates_teacher_parent(self):
        text = self._run()
        # Owner attached.
        self.assertTrue(
            SchoolMembership.objects.filter(
                user=self.owner, school=self.school, is_school_owner=True
            ).exists()
        )
        # Teacher + parent created with role + membership.
        teacher = User.objects.get(username="teacher1")
        parent = User.objects.get(username="parent1")
        self.assertEqual(teacher.role, User.Role.TEACHER)
        self.assertEqual(parent.role, User.Role.PARENT)
        self.assertTrue(SchoolMembership.objects.filter(user=teacher, school=self.school).exists())
        self.assertTrue(SchoolMembership.objects.filter(user=parent, school=self.school).exists())
        # Passwords actually authenticate.
        self.assertIsNotNone(authenticate(username="teacher1", password="Test1234"))
        self.assertIsNotNone(authenticate(username="parent1", password="Test1234"))
        self.assertIn("Test1234", text)

    def test_owner_password_untouched(self):
        self._run()
        # The owner's ORIGINAL password still works — attach never resets it.
        self.assertIsNotNone(authenticate(username="yimgah", password="already-set-1234"))

    def test_owner_primary_not_stolen_from_another_school(self):
        other = School.objects.create(name="Lycee", slug="lycee", subdomain="lycee", is_active=True)
        SchoolMembership.objects.create(
            user=self.owner, school=other, is_school_owner=True, is_primary=True
        )
        self._run()
        self.assertTrue(SchoolMembership.objects.get(user=self.owner, school=other).is_primary)
        self.assertFalse(SchoolMembership.objects.get(user=self.owner, school=self.school).is_primary)

    def test_idempotent(self):
        self._run()
        self._run()
        self.assertEqual(User.objects.filter(username="teacher1").count(), 1)
        self.assertEqual(
            SchoolMembership.objects.filter(user__username="teacher1", school=self.school).count(), 1
        )

    def test_unknown_owner_email_errors(self):
        with self.assertRaises(CommandError):
            call_command(
                "seed_tenant_test_accounts", "--slug", "gilead-tech",
                "--owner-email", "nobody@nowhere.edu", stdout=StringIO(),
            )

    def test_inactive_school_errors(self):
        School.objects.filter(pk=self.school.pk).update(is_active=False)
        with self.assertRaises(CommandError):
            call_command("seed_tenant_test_accounts", "--slug", "gilead-tech", stdout=StringIO())
