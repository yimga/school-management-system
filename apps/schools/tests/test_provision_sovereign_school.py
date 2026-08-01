"""provision_sovereign_school — turnkey sovereign-tenant bootstrap."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.schools.models import School


class ProvisionSovereignSchoolTests(TestCase):
    def _run(self, **kwargs):
        out, err = StringIO(), StringIO()
        call_command("provision_sovereign_school", stdout=out, stderr=err, **kwargs)
        return out.getvalue() + err.getvalue()

    def test_school_not_found_reports_error(self):
        output = self._run()
        self.assertIn("Sovereign school not found", output)

    def test_dry_run_does_not_write(self):
        School.objects.create(
            name="Gilead Tech High", slug="gilead-tech", subdomain="gilead-tech", is_active=True
        )
        output = self._run(dry_run=True)
        self.assertIn("DRY RUN", output)
        self.assertIn("gilead-tech", output)
        # Nothing was written.
        self.assertNotEqual(School.objects.get(slug="gilead-tech").billing_type, "COMPLIMENTARY")

    def test_full_bootstrap_unlocks_features_and_offline(self):
        school = School.objects.create(
            name="Gilead Tech High", slug="gilead-tech", subdomain="gilead-tech", is_active=True
        )
        self._run()
        school.refresh_from_db()
        self.assertEqual(school.billing_type, "COMPLIMENTARY")
        features = school.features or {}
        self.assertTrue(any(features.values()), "expected feature codes enabled")
        # The offline bundle turns on the offline_mode feature.
        self.assertTrue(features.get("offline_mode"), "expected offline_mode enabled")

    def test_idempotent_second_run(self):
        School.objects.create(
            name="Gilead Tech High", slug="gilead-tech", subdomain="gilead-tech", is_active=True
        )
        self._run()
        # Second run must not error and must keep the school fully provisioned.
        self._run()
        school = School.objects.get(slug="gilead-tech")
        self.assertEqual(school.billing_type, "COMPLIMENTARY")
