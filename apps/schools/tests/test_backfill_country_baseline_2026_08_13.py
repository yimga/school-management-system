"""GAP-1 closure — the platform-wide country-baseline backfill command.

Existing tenants (provisioned before the country-baseline feature) never re-enter
Phase B, so they miss the newer country layers. `backfill_country_baseline` runs
provision_country_baseline over the installed base, idempotently. These tests pin
that a real run fills the baseline and that --dry-run changes nothing.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.academics.models import SpecialtySubject, Subject
from apps.schools.models import School


class BackfillCountryBaselineCommandTests(TestCase):
    def test_backfill_fills_the_baseline_on_an_existing_school(self):
        school = School.objects.create(
            name="Backfill Co", subdomain="bf-cmd", country_code="CM", is_active=True
        )
        out = StringIO()
        call_command("backfill_country_baseline", "--school", "bf-cmd", stdout=out)

        # provision_country_baseline seeded the country subjects + curriculum.
        self.assertTrue(Subject.objects.filter(school=school).exists())
        self.assertTrue(SpecialtySubject.objects.filter(school=school).exists())
        self.assertIn("OK", out.getvalue())

    def test_dry_run_changes_nothing(self):
        school = School.objects.create(
            name="DryRun Co", subdomain="dr-cmd", country_code="CM", is_active=True
        )
        out = StringIO()
        call_command("backfill_country_baseline", "--school", "dr-cmd", "--dry-run", stdout=out)

        self.assertEqual(Subject.objects.filter(school=school).count(), 0)
        self.assertEqual(SpecialtySubject.objects.filter(school=school).count(), 0)
        self.assertIn("dry-run", out.getvalue().lower())

    def test_backfill_is_idempotent(self):
        school = School.objects.create(
            name="Idem Co", subdomain="idem-cmd", country_code="CM", is_active=True
        )
        call_command("backfill_country_baseline", "--school", "idem-cmd", stdout=StringIO())
        links = SpecialtySubject.objects.filter(school=school).count()
        subjects = Subject.objects.filter(school=school).count()
        call_command("backfill_country_baseline", "--school", "idem-cmd", stdout=StringIO())
        self.assertEqual(SpecialtySubject.objects.filter(school=school).count(), links)
        self.assertEqual(Subject.objects.filter(school=school).count(), subjects)
