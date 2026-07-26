"""End-to-end: imported records must be VISIBLE in the tenant school.

The tenant's promise is that data they IMPORT shows up in their school — a
students upload appears under Students, a courses upload under Subjects, staff
under Teachers, and so on. ``reconciliation`` proves this automatically via
``verification.verify_landed_counts``, which re-queries the SAME school-scoped
concrete models the tenant list views read (``StudentProfile.objects.filter(
school=…)``, ``Subject.objects.filter(school=…)``). If a domain lands rows but
is NOT in ``verification._DOMAIN_MODELS``, the platform can never prove those
rows are visible — a silent gap.

These tests land real rows through the PRODUCTION landers, then assert both:
  (a) the rows are present in their concrete model, scoped to the school (what
      the tenant list view queries), and
  (b) ``verify_landed_counts`` sees them per domain (the visibility proof),

so a wrong-school / rolled-back / unverified-domain regression is caught. The
subjects (``academics``) case is the regression guard for the coverage gap where
imported courses landed correctly but were never verified as visible.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase

from apps.academics.models import Subject
from apps.migration_cloud.landers.academics_lander import AcademicsLander
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.student_lander import StudentLander
from apps.migration_cloud.verification import (
    domains_with_verification,
    verify_landed_counts,
)
from apps.people.models import StudentProfile
from apps.schools.models import School


class ImportVisibleE2ETests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Import Visible School",
            slug="import-visible-school",
            subdomain="import-visible-school",
            is_active=True,
            country_code="CM",
        )

    def _ctx(self):
        return LanderContext(
            school=self.school,
            bundle_id=1,
            artifact_id=1,
            dry_run=False,
            schema_name="",
        )

    def _bundle(self):
        # verify_landed_counts reads only .school + .schema_name; "" => query the
        # current (test) schema, matching the tenant list views' own queryset.
        return SimpleNamespace(school=self.school, schema_name="")

    def test_students_land_and_are_visible(self):
        rows = [
            {"external_id": "PS-1", "first_name": "Ada", "last_name": "Lovelace",
             "admission_number": "ADM-1", "enrollment_status": "active"},
            {"external_id": "PS-2", "first_name": "Alan", "last_name": "Turing",
             "admission_number": "ADM-2", "enrollment_status": "active"},
        ]
        res = StudentLander().land(canonical_rows=iter(rows), ctx=self._ctx())
        self.assertEqual(res.created, 2, res.errors)
        # (a) present in the concrete model, scoped to the school (the list view's query)
        self.assertEqual(StudentProfile.objects.filter(school=self.school).count(), 2)
        # (b) the visibility re-query proves it
        self.assertEqual(verify_landed_counts(self._bundle()).get("students"), 2)

    def test_subjects_land_and_are_visible(self):
        rows = [
            {"subject_code": "MATH101", "subject_name": "Mathematics"},
            {"subject_code": "ENG101", "subject_name": "English"},
        ]
        res = AcademicsLander().land(canonical_rows=iter(rows), ctx=self._ctx())
        self.assertEqual(res.created, 2, res.errors)
        self.assertEqual(Subject.objects.filter(school=self.school).count(), 2)
        # academics visibility proof — REGRESSION GUARD for the _DOMAIN_MODELS gap
        # where imported subjects landed but could never be proven visible.
        self.assertEqual(verify_landed_counts(self._bundle()).get("academics"), 2)

    def test_subjects_domain_is_verified(self):
        # Subjects (academics) MUST be in the verified set — else an import that
        # lands them can never be proven visible in the school.
        self.assertIn("academics", domains_with_verification())
