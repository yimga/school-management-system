"""resend_owner_setup_email: targets active owners, reuses send_welcome_email.

The command must not reimplement email routing (send_welcome_email already routes
unclaimed owners to the onboarding wizard); it just resolves the school + its
active owners and calls that function. These tests lock the recipient resolution
and the dry-run / --email / no-owner branches without sending real mail.
"""
from __future__ import annotations

import uuid
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership


def _school(slug: str) -> School:
    return School.objects.create(
        name=f"{slug} School", slug=slug, subdomain=slug, is_active=True
    )


def _user(email: str) -> User:
    return User.objects.create_user(
        username=f"u-{uuid.uuid4().hex[:8]}", email=email, password="pass12345678",
        role=User.Role.ADMIN,
    )


def _owner(school, user, *, primary=True, suspended=False):
    return SchoolMembership.objects.create(
        user=user, school=school, role=User.Role.ADMIN, is_primary=primary,
        is_school_owner=True,
        suspended_at=timezone.now() if suspended else None,
    )


class ResendOwnerSetupEmailTests(TestCase):
    def setUp(self):
        self.school = _school("gilead-tech")
        self.owner = _user("founder@example.com")
        _owner(self.school, self.owner)

    def _run(self, *args):
        out = StringIO()
        call_command("resend_owner_setup_email", *args, stdout=out)
        return out.getvalue()

    def test_unknown_school_errors(self):
        with self.assertRaises(CommandError):
            self._run("--school", "does-not-exist")

    def test_dry_run_lists_owner_and_sends_nothing(self):
        with mock.patch(
            "apps.schools.welcome_email.send_welcome_email", return_value=True
        ) as send:
            out = self._run("--school", "gilead-tech", "--dry-run")
        self.assertIn("founder@example.com", out)
        self.assertIn("would send", out)
        send.assert_not_called()

    def test_sends_to_active_owner(self):
        with mock.patch(
            "apps.schools.welcome_email.send_welcome_email", return_value=True
        ) as send:
            out = self._run("--school", "gilead-tech")
        send.assert_called_once_with(str(self.school.pk), "founder@example.com")
        self.assertIn("sent/queued", out)

    def test_email_override_targets_one_address(self):
        with mock.patch(
            "apps.schools.welcome_email.send_welcome_email", return_value=True
        ) as send:
            self._run("--school", "gilead-tech", "--email", "someone@else.com")
        send.assert_called_once_with(str(self.school.pk), "someone@else.com")

    def test_suspended_owner_is_not_a_recipient(self):
        # A second, suspended owner must be skipped; only the active owner remains.
        _owner(self.school, _user("suspended@example.com"), primary=False, suspended=True)
        with mock.patch(
            "apps.schools.welcome_email.send_welcome_email", return_value=True
        ) as send:
            self._run("--school", "gilead-tech")
        called = {c.args[1] for c in send.call_args_list}
        self.assertEqual(called, {"founder@example.com"})

    def test_no_active_owner_warns_and_sends_nothing(self):
        school = _school("orphan")
        with mock.patch(
            "apps.schools.welcome_email.send_welcome_email", return_value=True
        ) as send:
            out = self._run("--school", "orphan")
        self.assertIn("no active owner", out)
        send.assert_not_called()

    def test_skipped_when_send_returns_false(self):
        # Mail not configured -> send_welcome_email returns False -> reported skipped.
        with mock.patch(
            "apps.schools.welcome_email.send_welcome_email", return_value=False
        ):
            out = self._run("--school", "gilead-tech")
        self.assertIn("skipped", out)

    def test_loud_preflight_when_mail_not_configured(self):
        # When the Brevo secrets are empty, the operator gets a clear up-front
        # warning naming the two env vars — not a bare "skipped".
        with mock.patch(
            "apps.schools.welcome_email.send_welcome_email", return_value=False
        ), mock.patch(
            "apps.schoolops.email_delivery.transactional_email_configured",
            return_value=False,
        ):
            out = self._run("--school", "gilead-tech")
        self.assertIn("NOT configured", out)
        self.assertIn("EMAIL_HOST_USER", out)
        self.assertIn("set Brevo", out)

    def test_no_preflight_warning_when_mail_configured(self):
        with mock.patch(
            "apps.schools.welcome_email.send_welcome_email", return_value=True
        ), mock.patch(
            "apps.schoolops.email_delivery.transactional_email_configured",
            return_value=True,
        ):
            out = self._run("--school", "gilead-tech")
        self.assertNotIn("NOT configured", out)
        self.assertIn("sent/queued", out)

    def test_dry_run_has_no_preflight_warning(self):
        # Dry-run doesn't send, so it doesn't warn about delivery config.
        with mock.patch(
            "apps.schoolops.email_delivery.transactional_email_configured",
            return_value=False,
        ):
            out = self._run("--school", "gilead-tech", "--dry-run")
        self.assertNotIn("NOT configured", out)
