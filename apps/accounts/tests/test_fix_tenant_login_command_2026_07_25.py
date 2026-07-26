"""``manage.py fix_tenant_login`` — diagnose + email-independent fix (2026-07-25).

The reported bug: an operator enters username+password on a tenant login and the
page just reloads to the sign-in form (no MFA, no dashboard), with "Invalid
username or password" — but the never-activated login recovery does NOT fire, so
the account is in a state the earlier tooling could neither see nor fix (a usable
password already set, or ``is_active=False``). These MUST-FIRE tests prove the
new command:

* correctly DIAGNOSES each of the three failure states the login backend can hit
  (usable-password + active, inactive, no-usable-password) plus the no-match case;
* FIXES an account email-independently — sets a KNOWN password that actually
  authenticates, and activates an inactive account in the same step;
* refuses the mutating flags without a single explicit target;
* lists a school roster so an operator who doesn't know the owner email can find it.
"""

from __future__ import annotations

import re
from io import StringIO

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership


class FixTenantLoginDiagnoseTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="New Test High School", slug="new-school",
            subdomain="new-school", is_active=True,
        )

    def _member(self, user, **flags):
        return SchoolMembership.objects.create(user=user, school=self.school, **flags)

    def test_diagnoses_active_usable_password_account(self):
        u = User.objects.create_user(
            username="yimgah", email="yimgah@yahoo.com", password="realpass-1234"
        )
        self._member(u, is_school_owner=True, is_primary=True)
        out = StringIO()
        call_command("fix_tenant_login", "--email", "yimgah@yahoo.com", stdout=out)
        text = out.getvalue()
        self.assertIn("USABLE PASSWORD + ACTIVE", text)
        self.assertIn("has_usable_password: True", text)
        self.assertIn("new-school", text)
        self.assertIn("OWNER", text)

    def test_diagnoses_inactive_account(self):
        u = User.objects.create_user(
            username="ghost", email="ghost@x.edu", password="realpass-1234"
        )
        u.is_active = False
        u.save(update_fields=["is_active"])
        out = StringIO()
        call_command("fix_tenant_login", "--email", "ghost@x.edu", stdout=out)
        text = out.getvalue()
        self.assertIn("INACTIVE", text)
        # This is the exact 'reloads to sign-in with no recovery' dead-end.
        self.assertIn("authenticate() returns None", text)

    def test_diagnoses_never_activated_account(self):
        u = User.objects.create_user(
            username="stuck", email="stuck@x.edu", password="seed-pass-1234"
        )
        u.set_unusable_password()
        u.save()
        out = StringIO()
        call_command("fix_tenant_login", "--email", "stuck@x.edu", stdout=out)
        self.assertIn("NO USABLE PASSWORD", out.getvalue())

    def test_no_match_is_reported_clearly(self):
        out = StringIO()
        call_command("fix_tenant_login", "--email", "nobody@nowhere.edu", stdout=out)
        text = out.getvalue()
        self.assertIn("No account matches", text)
        self.assertIn("never created", text)

    def test_resolves_by_username_too(self):
        User.objects.create_user(
            username="byname", email="byname@x.edu", password="realpass-1234"
        )
        out = StringIO()
        call_command("fix_tenant_login", "--email", "BYNAME", stdout=out)  # case-insensitive
        self.assertIn("byname@x.edu", out.getvalue())


class FixTenantLoginFixTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="New Test High School", slug="new-school",
            subdomain="new-school", is_active=True,
        )

    def test_set_password_makes_login_work(self):
        u = User.objects.create_user(
            username="fixme", email="fixme@x.edu", password="seed-pass-1234"
        )
        u.set_unusable_password()  # start from the never-activated state
        u.save()
        out = StringIO()
        call_command(
            "fix_tenant_login", "--email", "fixme@x.edu", "--set-password", stdout=out
        )
        u.refresh_from_db()
        self.assertTrue(u.has_usable_password())
        match = re.search(r"Rmc-[A-Za-z0-9_\-]+", out.getvalue())
        self.assertIsNotNone(match, out.getvalue())
        # The printed password must actually authenticate — by username AND email.
        self.assertIsNotNone(authenticate(username="fixme", password=match.group(0)))
        self.assertIsNotNone(authenticate(username="fixme@x.edu", password=match.group(0)))

    def test_set_password_accepts_a_chosen_value_and_activates(self):
        u = User.objects.create_user(
            username="chosen", email="chosen@x.edu", password="seed-pass-1234"
        )
        u.is_active = False  # inactive AND about to get a chosen password
        u.save(update_fields=["is_active"])
        call_command(
            "fix_tenant_login", "--email", "chosen@x.edu",
            "--set-password", "ChosenPass123!", stdout=StringIO(),
        )
        u.refresh_from_db()
        self.assertTrue(u.is_active)  # activated in the same step
        self.assertIsNotNone(authenticate(username="chosen@x.edu", password="ChosenPass123!"))

    def test_activate_only_flips_active_without_touching_password(self):
        u = User.objects.create_user(
            username="dormant", email="dormant@x.edu", password="known-pass-1234"
        )
        u.is_active = False
        u.save(update_fields=["is_active"])
        # Correct password can't authenticate while inactive...
        self.assertIsNone(authenticate(username="dormant@x.edu", password="known-pass-1234"))
        call_command("fix_tenant_login", "--email", "dormant@x.edu", "--activate", stdout=StringIO())
        u.refresh_from_db()
        self.assertTrue(u.is_active)
        # ...and the ORIGINAL password works again afterwards (password untouched).
        self.assertIsNotNone(authenticate(username="dormant@x.edu", password="known-pass-1234"))

    def test_mutation_requires_email_target(self):
        with self.assertRaises(CommandError):
            call_command("fix_tenant_login", "--school", "new-school", "--set-password", stdout=StringIO())

    def test_requires_some_target(self):
        with self.assertRaises(CommandError):
            call_command("fix_tenant_login", stdout=StringIO())

    def test_ambiguous_identifier_refuses_to_mutate(self):
        # Two accounts share the same email → the mutating path must refuse.
        User.objects.create_user(username="dup1", email="dup@x.edu", password="p1-12345678")
        User.objects.create_user(username="dup2", email="dup@x.edu", password="p2-12345678")
        with self.assertRaises(CommandError):
            call_command(
                "fix_tenant_login", "--email", "dup@x.edu", "--set-password", stdout=StringIO()
            )


class FixTenantLoginRosterTests(TestCase):
    def test_roster_lists_members_with_readiness(self):
        school = School.objects.create(
            name="New Test High School", slug="new-school",
            subdomain="new-school", is_active=True,
        )
        owner = User.objects.create_user(
            username="theowner", email="theowner@x.edu", password="seed-1234"
        )
        owner.set_unusable_password()
        owner.save()
        SchoolMembership.objects.create(
            user=owner, school=school, is_school_owner=True, is_primary=True
        )
        out = StringIO()
        call_command("fix_tenant_login", "--school", "new-school", stdout=out)
        text = out.getvalue()
        self.assertIn("theowner@x.edu", text)
        self.assertIn("OWNER", text)
        self.assertIn("NO USABLE PASSWORD", text)

    def test_unknown_school_slug_errors(self):
        with self.assertRaises(CommandError):
            call_command("fix_tenant_login", "--school", "does-not-exist", stdout=StringIO())


class FixTenantLoginAttachOwnerTests(TestCase):
    """--attach-owner: attach an EXISTING claimed account as owner (email-independent).

    This is the path invite_school_owner refuses for an account whose username
    != email (e.g. username 'yimgah', email 'yimgah@yahoo.com').
    """

    def setUp(self):
        self.school = School.objects.create(
            name="Gilead Tech", slug="gilead-tech",
            subdomain="gilead-tech", is_active=True,
        )
        # An already-claimed account: username is the local-part, NOT the email.
        self.user = User.objects.create_user(
            username="yimgah", email="yimgah@yahoo.com", password="already-set-1234"
        )

    def _is_owner(self):
        return SchoolMembership.objects.filter(
            user=self.user, school=self.school, is_school_owner=True
        ).exists()

    def test_attach_creates_owner_membership(self):
        self.assertFalse(self._is_owner())
        out = StringIO()
        call_command(
            "fix_tenant_login", "--email", "yimgah@yahoo.com",
            "--school", "gilead-tech", "--attach-owner", stdout=out,
        )
        self.assertTrue(self._is_owner())
        self.assertIn("Attached", out.getvalue())

    def test_attach_resolves_school_by_id(self):
        # The operator has the school UUID, not just the slug.
        call_command(
            "fix_tenant_login", "--email", "yimgah@yahoo.com",
            "--school", str(self.school.pk), "--attach-owner", stdout=StringIO(),
        )
        self.assertTrue(self._is_owner())

    def test_attach_is_idempotent(self):
        SchoolMembership.objects.create(
            user=self.user, school=self.school, is_school_owner=True, is_primary=True
        )
        out = StringIO()
        call_command(
            "fix_tenant_login", "--email", "yimgah@yahoo.com",
            "--school", "gilead-tech", "--attach-owner", stdout=out,
        )
        self.assertIn("already an OWNER", out.getvalue())
        self.assertEqual(
            SchoolMembership.objects.filter(user=self.user, school=self.school).count(), 1
        )

    def test_attach_promotes_existing_non_owner_member(self):
        SchoolMembership.objects.create(
            user=self.user, school=self.school, is_school_owner=False
        )
        call_command(
            "fix_tenant_login", "--email", "yimgah@yahoo.com",
            "--school", "gilead-tech", "--attach-owner", stdout=StringIO(),
        )
        self.assertTrue(self._is_owner())

    def test_attach_does_not_steal_primary_from_another_school(self):
        # yimgah already owns another school as primary — attaching gilead-tech
        # must NOT demote that primary.
        other = School.objects.create(
            name="Lycee", slug="lycee", subdomain="lycee", is_active=True
        )
        SchoolMembership.objects.create(
            user=self.user, school=other, is_school_owner=True, is_primary=True
        )
        call_command(
            "fix_tenant_login", "--email", "yimgah@yahoo.com",
            "--school", "gilead-tech", "--attach-owner", stdout=StringIO(),
        )
        self.assertTrue(
            SchoolMembership.objects.get(user=self.user, school=other).is_primary
        )
        self.assertFalse(
            SchoolMembership.objects.get(user=self.user, school=self.school).is_primary
        )

    def test_attach_requires_both_email_and_school(self):
        with self.assertRaises(CommandError):
            call_command(
                "fix_tenant_login", "--school", "gilead-tech", "--attach-owner",
                stdout=StringIO(),
            )

    def test_attach_errors_on_unknown_account(self):
        with self.assertRaises(CommandError):
            call_command(
                "fix_tenant_login", "--email", "nobody@x.edu",
                "--school", "gilead-tech", "--attach-owner", stdout=StringIO(),
            )

    def test_attach_errors_on_inactive_school(self):
        School.objects.filter(pk=self.school.pk).update(is_active=False)
        with self.assertRaises(CommandError):
            call_command(
                "fix_tenant_login", "--email", "yimgah@yahoo.com",
                "--school", "gilead-tech", "--attach-owner", stdout=StringIO(),
            )
