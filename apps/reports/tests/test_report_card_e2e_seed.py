"""Server-side proof for report-card Playwright seed (metric #4)."""

from io import StringIO
from pathlib import Path

from django.core.management.color import no_style
from django.test import TestCase
from django.urls import reverse

from apps.reports.models import ReportDocumentHash
from apps.reports.report_card_e2e_seed import seed_report_card_e2e
from apps.schools.models import School


class ReportCardE2ESeedTests(TestCase):
    def test_seed_writes_fixture_and_hash_verifies(self):
        school = School.objects.create(
            name="Seed School",
            slug="seed-report-school",
            subdomain="seed-report-school",
            is_active=True,
        )
        fixture = seed_report_card_e2e(
            school_slug=school.slug,
            username_prefix="demo",
            password="Test1234",
            stdout=StringIO(),
            style=no_style(),
        )
        self.assertTrue(Path("var/e2e_report_card_fixture.json").is_file())
        self.assertEqual(fixture["school_slug"], school.slug)
        self.assertEqual(len(fixture["sha256_hash"]), 64)

        row = ReportDocumentHash.objects.get(sha256_hash=fixture["sha256_hash"])
        self.assertEqual(row.report_card.student_id, fixture["student_id"])

        verify_resp = self.client.get(
            reverse("reports:verify_report_hash"),
            {"hash": fixture["sha256_hash"]},
        )
        self.assertEqual(verify_resp.status_code, 200)
        self.assertTrue(verify_resp.json().get("verified"))
