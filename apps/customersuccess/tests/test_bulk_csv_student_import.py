"""Wave R-E (v3.96.0 — 2026-05-26) — Bulk CSV student import kernel tests."""

from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase, TestCase

from apps.customersuccess.bulk_csv_student_import import (
    BulkImportApplyResult,
    apply_bulk_csv,
    parse_and_validate_csv,
)
from apps.people.models import StudentProfile


_GOOD_CSV = (
    "external_id,first_name,last_name,date_of_birth,email,grade_level\n"
    "STU-1,Ada,Lovelace,2010-12-10,ada@school.test,8\n"
    "STU-2,Charles,Babbage,2009-06-22,charles@school.test,9\n"
)


class HeaderParseTests(SimpleTestCase):

    def test_empty_csv_returns_error(self):
        out = parse_and_validate_csv("")
        self.assertFalse(out.is_valid)
        self.assertTrue(any(e.reason == "empty_csv" for e in out.errors))

    def test_required_headers_present(self):
        out = parse_and_validate_csv(_GOOD_CSV)
        self.assertTrue(out.is_valid)
        self.assertIn("external_id", out.detected_header_columns)

    def test_header_normalisation(self):
        text = (
            "External ID,First Name,Last Name\n"
            "STU-1,Ada,Lovelace\n"
        )
        out = parse_and_validate_csv(text)
        self.assertTrue(out.is_valid)
        self.assertEqual(out.rows[0].external_id, "STU-1")

    def test_unknown_columns_reported_not_fatal(self):
        text = (
            "external_id,first_name,last_name,horoscope\n"
            "STU-1,Ada,Lovelace,Sagittarius\n"
        )
        out = parse_and_validate_csv(text)
        self.assertTrue(out.is_valid)
        self.assertIn("horoscope", out.rejected_header_columns)

    def test_missing_required_header(self):
        text = "external_id,first_name\nSTU-1,Ada\n"
        out = parse_and_validate_csv(text)
        self.assertFalse(out.is_valid)
        self.assertTrue(any(
            e.field == "last_name" and e.reason == "required_header_missing"
            for e in out.errors
        ))


class RowValidationTests(SimpleTestCase):

    def test_happy_path(self):
        out = parse_and_validate_csv(_GOOD_CSV)
        self.assertEqual(len(out.rows), 2)
        self.assertEqual(out.rows[0].date_of_birth, date(2010, 12, 10))

    def test_invalid_email(self):
        text = (
            "external_id,first_name,last_name,email\n"
            "STU-1,Ada,Lovelace,not-an-email\n"
        )
        out = parse_and_validate_csv(text)
        self.assertFalse(out.is_valid)
        self.assertTrue(any(
            e.field == "email" and e.reason == "invalid_email"
            for e in out.errors
        ))

    def test_invalid_dob_format(self):
        text = (
            "external_id,first_name,last_name,date_of_birth\n"
            "STU-1,Ada,Lovelace,10/12/2010\n"
        )
        out = parse_and_validate_csv(text)
        self.assertFalse(out.is_valid)
        self.assertTrue(any(
            e.field == "date_of_birth" for e in out.errors
        ))

    def test_invalid_external_id_format(self):
        text = (
            "external_id,first_name,last_name\n"
            "STU 1 with space,Ada,Lovelace\n"
        )
        out = parse_and_validate_csv(text)
        self.assertFalse(out.is_valid)

    def test_missing_required_name(self):
        text = (
            "external_id,first_name,last_name\n"
            "STU-1,,Lovelace\n"
        )
        out = parse_and_validate_csv(text)
        self.assertFalse(out.is_valid)

    def test_duplicate_external_ids_detected(self):
        text = (
            "external_id,first_name,last_name\n"
            "STU-1,Ada,Lovelace\n"
            "STU-1,Augusta,King\n"
        )
        out = parse_and_validate_csv(text)
        self.assertFalse(out.is_valid)
        self.assertIn("STU-1", out.duplicate_external_ids)

    def test_blank_rows_skipped(self):
        text = (
            "external_id,first_name,last_name\n"
            "STU-1,Ada,Lovelace\n"
            ",,\n"
            "STU-2,Charles,Babbage\n"
        )
        out = parse_and_validate_csv(text)
        self.assertEqual(len(out.rows), 2)


class DefaultDbRunnerTests(TestCase):
    databases = {"default"}

    def test_default_runner_creates_student_profile(self):
        from apps.schools.models import School

        school = School.objects.create(
            name="Import School",
            slug="import-school",
            subdomain="import-school",
            is_active=True,
        )
        validated = parse_and_validate_csv(_GOOD_CSV)
        out = apply_bulk_csv(school_id=school.pk, validated=validated)
        self.assertEqual(out.created, 2)
        self.assertEqual(
            StudentProfile.objects.filter(school=school, is_active=True).count(),
            2,
        )


class ApplyBulkCSVTests(SimpleTestCase):

    def test_validation_failure_short_circuits(self):
        text = "external_id,first_name,last_name\nSTU 1,Ada,Lovelace\n"
        validated = parse_and_validate_csv(text)
        out = apply_bulk_csv(school_id=1, validated=validated)
        self.assertEqual(out.created, 0)
        self.assertTrue(out.errors)

    def test_runner_seam(self):
        captured = {}

        def fake_runner(*, school_id, rows):
            captured["school_id"] = school_id
            captured["row_count"] = len(rows)
            return BulkImportApplyResult(created=len(rows))

        validated = parse_and_validate_csv(_GOOD_CSV)
        out = apply_bulk_csv(
            school_id=99, validated=validated, db_runner=fake_runner,
        )
        self.assertEqual(out.created, 2)
        self.assertEqual(captured["school_id"], 99)
        self.assertEqual(captured["row_count"], 2)
