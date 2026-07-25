"""Operator remediation command for owners stranded with no usable password.

MUST-FIRE coverage for ``manage.py recover_unactivated_owners``:
* the read-only report surfaces a stranded owner platform-wide;
* ``--set-temp-password`` restores a usable password so the owner can sign in
  (email-INDEPENDENT — the recovery path that works even when the mail relay is
  down, which is the whole reason owners were stranded);
* an owner who already has a usable password is never listed or touched;
* ``--set-temp-password`` refuses to run unscoped (no accidental mass reset).
"""

from __future__ import annotations

import re
from io import StringIO

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership


class RecoverUnactivatedOwnersCommandTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="New School", slug="new-school", subdomain="new-school", is_active=True
        )
        self.owner = User.objects.create_user(
            username="newowner", email="owner@new.edu", password="seed-pass-1234"
        )
        self.owner.set_unusable_password()
        self.owner.save()
        SchoolMembership.objects.create(
            user=self.owner, school=self.school, is_school_owner=True, is_primary=True
        )

    def test_report_lists_stranded_owner(self):
        out = StringIO()
        call_command("recover_unactivated_owners", stdout=out)
        text = out.getvalue()
        self.assertIn("Found 1 stranded", text)
        self.assertIn("newowner", text)
        self.assertIn("new-school", text)

    def test_set_temp_password_restores_login(self):
        out = StringIO()
        call_command(
            "recover_unactivated_owners",
            "--email", "owner@new.edu",
            "--set-temp-password",
            stdout=out,
        )
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.has_usable_password())
        # The printed temp password must actually authenticate the owner.
        match = re.search(r"Rmc-[A-Za-z0-9_\-]+", out.getvalue())
        self.assertIsNotNone(match, out.getvalue())
        self.assertIsNotNone(
            authenticate(username="newowner", password=match.group(0))
        )

    def test_target_by_school_slug(self):
        out = StringIO()
        call_command(
            "recover_unactivated_owners",
            "--school", "new-school",
            "--set-temp-password",
            stdout=out,
        )
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.has_usable_password())

    def test_owner_with_usable_password_is_not_listed(self):
        self.owner.set_password("already-activated-1234")
        self.owner.save()
        out = StringIO()
        call_command("recover_unactivated_owners", stdout=out)
        self.assertIn("No stranded owners", out.getvalue())

    def test_set_temp_password_refuses_unscoped(self):
        with self.assertRaises(CommandError):
            call_command("recover_unactivated_owners", "--set-temp-password", stdout=StringIO())

    def test_all_flag_allows_unscoped_temp_password(self):
        out = StringIO()
        call_command(
            "recover_unactivated_owners", "--all", "--set-temp-password", stdout=out
        )
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.has_usable_password())
