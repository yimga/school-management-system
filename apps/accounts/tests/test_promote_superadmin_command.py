"""Tests for the ``promote_superadmin`` management command.

Guards the one-step promotion that fixes the "role=SUPERADMIN but is_staff/
is_superuser=False -> login/MFA loop" class of access bug.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

User = get_user_model()


class PromoteSuperadminCommandTests(TestCase):
    def _run(self, *args):
        out = StringIO()
        call_command("promote_superadmin", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_promotes_role_only_user_sets_all_three_flags(self):
        user = User.objects.create_user(
            username="yimgah_test",
            email="yimgah_test@example.com",
            password="x",
            role=User.Role.SUPERADMIN,  # RBAC role set, Django flags NOT
        )
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        self._run("yimgah_test")

        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertEqual(user.role, User.Role.SUPERADMIN)

    def test_sets_role_when_only_flags_were_missing_role(self):
        user = User.objects.create_user(
            username="flagsonly", email="flagsonly@example.com", password="x"
        )
        # default role is PARENT
        self.assertEqual(user.role, User.Role.PARENT)

        self._run("flagsonly")

        user.refresh_from_db()
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.role, User.Role.SUPERADMIN)

    def test_case_insensitive_username_lookup(self):
        User.objects.create_user(
            username="MixedCase", email="mixed@example.com", password="x"
        )
        self._run("mixedcase")
        self.assertTrue(User.objects.get(username="MixedCase").is_superuser)

    def test_email_lookup(self):
        User.objects.create_user(
            username="byemail", email="Find.Me@example.com", password="x"
        )
        self._run("--email", "find.me@example.com")
        self.assertTrue(User.objects.get(username="byemail").is_superuser)

    def test_dry_run_persists_nothing(self):
        User.objects.create_user(
            username="dry", email="dry@example.com", password="x"
        )
        out = self._run("dry", "--dry-run")
        self.assertIn("Dry run", out)
        user = User.objects.get(username="dry")
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

    def test_idempotent_when_already_superadmin(self):
        # create_superuser sets the Django flags but leaves role=PARENT, so the
        # FIRST run legitimately promotes the role; the SECOND run is the no-op.
        User.objects.create_user(
            username="already", email="already@example.com", password="x"
        )
        self._run("already")  # first run promotes
        out = self._run("already")  # second run should be a no-op
        self.assertIn("nothing to do", out.lower())

    def test_missing_user_raises_commanderror(self):
        with self.assertRaises(CommandError):
            self._run("does_not_exist")

    def test_no_selector_raises_commanderror(self):
        with self.assertRaises(CommandError):
            self._run()

    def test_reports_membership_note(self):
        from apps.schools.models import School, SchoolMembership

        school = School.objects.create(name="Test High", slug="test-high")
        user = User.objects.create_user(
            username="member", email="member@example.com", password="x"
        )
        SchoolMembership.objects.create(user=user, school=school, role="ADMIN")

        out = self._run("member")
        self.assertIn("SchoolMembership", out)
        user.refresh_from_db()
        self.assertTrue(user.is_superuser)
