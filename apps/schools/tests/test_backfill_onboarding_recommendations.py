from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.schools.models import School


class BackfillOnboardingRecommendationsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Legacy", slug="legacy-backfill", subdomain="legacy-backfill", country_code="CM")

    def test_audit_is_read_only_and_apply_persists(self):
        out = StringIO()
        call_command("backfill_onboarding_recommendations", stdout=out)
        self.school.refresh_from_db()
        self.assertNotIn("recommendation_manifest", self.school.settings)
        self.assertIn("missing=1", out.getvalue())
        call_command("backfill_onboarding_recommendations", "--apply", stdout=out)
        self.school.refresh_from_db()
        self.assertIn("recommendation_manifest", self.school.settings)

    def test_apply_upgrades_an_old_manifest(self):
        self.school.settings = {"recommendation_manifest": {"version": 1}}
        self.school.save(update_fields=["settings", "updated_at"])
        call_command("backfill_onboarding_recommendations", "--apply")
        self.school.refresh_from_db()
        self.assertEqual(
            self.school.settings["recommendation_manifest"]["version"], 2
        )
