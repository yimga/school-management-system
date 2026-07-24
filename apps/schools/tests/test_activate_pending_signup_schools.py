"""Platform-wide recovery CLI for verified-but-inactive signup schools."""

from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.schools.models import School, SignupVerification


class ActivatePendingSignupSchoolsCommandTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Stuck School",
            slug="stuck-school",
            subdomain="stuck-school",
            is_active=False,
        )
        SignupVerification.objects.create(
            school=self.school,
            email="owner@stuck.test",
            expires_at=timezone.now() + timezone.timedelta(days=2),
            verified_at=timezone.now(),
        )

    def test_dry_run_lists_verified_inactive_without_provisioning(self):
        out = StringIO()
        with mock.patch(
            "apps.schools.tasks.provision_school_sync"
        ) as provision:
            call_command(
                "activate_pending_signup_schools",
                "--all-verified-inactive",
                "--dry-run",
                stdout=out,
            )
            provision.assert_not_called()
        self.assertIn("stuck-school", out.getvalue())
        self.assertIn("DRY-RUN", out.getvalue())

    def test_all_verified_inactive_provisions_matching_schools(self):
        with mock.patch(
            "apps.schools.tasks.provision_school_sync"
        ) as provision:
            call_command(
                "activate_pending_signup_schools",
                "--all-verified-inactive",
            )
        provision.assert_called_once_with(
            str(self.school.pk), contact_email="owner@stuck.test"
        )

    def test_slug_filter_skips_unlisted_schools(self):
        other = School.objects.create(
            name="Other",
            slug="other-school",
            subdomain="other-school",
            is_active=False,
        )
        SignupVerification.objects.create(
            school=other,
            email="other@stuck.test",
            expires_at=timezone.now() + timezone.timedelta(days=2),
            verified_at=timezone.now(),
        )
        with mock.patch(
            "apps.schools.tasks.provision_school_sync"
        ) as provision:
            call_command(
                "activate_pending_signup_schools",
                "--slug=stuck-school",
            )
        provision.assert_called_once_with(
            str(self.school.pk), contact_email="owner@stuck.test"
        )
