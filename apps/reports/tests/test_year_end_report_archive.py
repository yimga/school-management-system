"""Year-end report archive + immutable transcript freeze contract."""

from datetime import date

from django.test import TestCase

from apps.academics.models import AcademicYear, Term
from apps.academics.year_close import (
    batch_freeze_transcripts,
    execute_year_close,
    lock_source_year,
    run_year_close_dry_run,
)
from apps.people.models import StudentProfile
from apps.registries.models import CountryRegistry
from apps.reports.models import TermPublishStatus
from apps.schools.models import School


class YearEndReportArchiveTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Report School",
            slug="report-school",
            subdomain="report-school",
            country_code="CM",
            is_active=True,
        )
        self.source = AcademicYear.objects.create(
            school=self.school,
            name="2024-2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 6, 30),
        )
        self.target = AcademicYear.objects.create(
            school=self.school,
            name="2025-2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.source,
            name="First",
            start_date=date(2024, 9, 1),
            end_date=date(2024, 12, 15),
            position=1,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Archive",
            last_name="Student",
            student_code="ARC-001",
            academic_year=self.source,
            is_active=True,
        )

    def test_dry_run_includes_scorecard(self):
        result = run_year_close_dry_run(self.school, self.source, self.target)
        self.assertIn("blockers", result)
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["ok"])
        codes = {b["code"] for b in result["blockers"]}
        self.assertIn("terms_unpublished", codes)

    def test_dry_run_ok_when_terms_published(self):
        TermPublishStatus.objects.create(
            academic_year=self.source,
            term=self.term,
            classroom=None,
            is_published=True,
        )
        result = run_year_close_dry_run(self.school, self.source, self.target)
        self.assertTrue(result["ok"])
        self.assertEqual(result["blockers"], [])

    def test_lock_source_year_is_idempotent(self):
        first = lock_source_year(self.school, self.source)
        self.assertTrue(first["ok"])
        self.assertFalse(first["already_locked"])
        self.source.refresh_from_db()
        self.assertTrue(self.source.is_locked)

        second = lock_source_year(self.school, self.source)
        self.assertTrue(second["already_locked"])

    def test_execute_year_close_locks_source_year(self):
        TermPublishStatus.objects.create(
            academic_year=self.source,
            term=self.term,
            classroom=None,
            is_published=True,
        )
        result = execute_year_close(
            self.school,
            self.source,
            self.target,
            dry_run=False,
            freeze_transcripts=False,
            lock_on_success=True,
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["dry_run"])
        self.assertTrue(result["steps"]["lock"]["ok"])
        self.source.refresh_from_db()
        self.assertTrue(self.source.is_locked)

    def test_batch_freeze_transcripts_best_effort_per_student(self):
        result = batch_freeze_transcripts(self.school, self.source)
        self.assertIn("created", result)
        self.assertIn("errors", result)
        self.assertGreaterEqual(result["created"] + result["errors"], 1)
