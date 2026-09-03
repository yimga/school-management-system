"""School token resolution for remediate_inverted_academic_catalog."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.schools.models import School


class RemediateInvertedAcademicCatalogSchoolLookupTests(TestCase):
    def test_subdomain_lookup_does_not_require_uuid_pk(self):
        school = School.objects.create(
            name="Lookup School",
            subdomain="gilead-school",
            slug="gilead-school",
            country_code="CM",
        )
        out = StringIO()
        call_command(
            "remediate_inverted_academic_catalog",
            school="gilead-school",
            dry_run=True,
            stdout=out,
        )
        body = out.getvalue()
        self.assertIn(school.name, body)
        self.assertIn("Dry run", body)
