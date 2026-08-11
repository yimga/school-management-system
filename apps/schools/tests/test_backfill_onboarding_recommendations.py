from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.schools.models import School
from apps.schools.onboarding_recommendations import MANIFEST_VERSION


class BackfillOnboardingRecommendationsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Legacy", slug="legacy-backfill", subdomain="legacy-backfill", country_code="CM")

    def test_audit_is_read_only_and_apply_persists(self):
        out = StringIO()
        call_command("backfill_onboarding_recommendations", stdout=out)
        self.school.refresh_from_db()
        # Read-only: the audit must not write. self.school is one of the missing.
        self.assertNotIn("recommendation_manifest", self.school.settings)
        # Count is environment-dependent (migration-seeded schools also lack a
        # manifest), so assert "at least one missing" rather than an exact count.
        self.assertRegex(out.getvalue(), r"missing=[1-9]\d*")
        call_command("backfill_onboarding_recommendations", "--apply", stdout=out)
        self.school.refresh_from_db()
        self.assertIn("recommendation_manifest", self.school.settings)

    def test_apply_upgrades_an_old_manifest(self):
        self.school.settings = {"recommendation_manifest": {"version": 1}}
        self.school.save(update_fields=["settings", "updated_at"])
        call_command("backfill_onboarding_recommendations", "--apply")
        self.school.refresh_from_db()
        self.assertEqual(
            self.school.settings["recommendation_manifest"]["version"],
            MANIFEST_VERSION,
        )
