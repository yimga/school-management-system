"""triage_signup_school management command."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.schools.models import School, SignupVerification


class TriageSignupSchoolCommandTests(TestCase):
    def test_missing_slug_reports_similar(self):
        School.objects.create(
            name="St Jude",
            slug="st-jude-academy",
            subdomain="st-jude-academy",
            is_active=False,
        )
        out = StringIO()
        call_command("triage_signup_school", "st-jude", stdout=out)
        text = out.getvalue()
        self.assertIn("No school matched", text)
        self.assertIn("st-jude-academy", text)

    def test_verified_inactive_suggests_recovery(self):
        school = School.objects.create(
            name="St Jude",
            slug="st-jude",
            subdomain="st-jude",
            is_active=False,
        )
        SignupVerification.objects.create(
            school=school,
            email="owner@stjude.test",
            expires_at=timezone.now() + timezone.timedelta(days=2),
            verified_at=timezone.now(),
        )
        out = StringIO()
        call_command("triage_signup_school", "st-jude", stdout=out)
        text = out.getvalue()
        self.assertIn("st-jude", text)
        self.assertIn("activate_pending_signup_schools", text)
        self.assertIn("is_active=False", text)
