"""Wave L2 — bulk CSV + clone-from-template + jobs dashboard."""

from __future__ import annotations

import io

from django.test import TestCase

from apps.schools.models import School

from .models import SchoolLifecycleStage
from .services_bulk import apply_rows, parse_csv
from .services_clone import clone_school


class ParseCSVTests(TestCase):
    def test_rejects_empty_input(self):
        result = parse_csv(io.BytesIO(b""))
        self.assertEqual(result.total, 0)
        self.assertTrue(result.header_errors)

    def test_rejects_missing_required_columns(self):
        result = parse_csv(io.BytesIO(b"name\nFoo\n"))
        self.assertEqual(result.total, 0)
        self.assertTrue(result.header_errors)

    def test_parses_minimal_valid_row(self):
        csv = b"name,slug\nAcme,acme-school\n"
        result = parse_csv(io.BytesIO(csv))
        self.assertEqual(result.total, 1)
        self.assertEqual(len(result.valid_rows), 1)
        self.assertEqual(result.rows[0].name, "Acme")
        self.assertEqual(result.rows[0].slug, "acme-school")

    def test_rejects_slug_with_spaces(self):
        csv = b"name,slug\nAcme,bad slug\n"
        result = parse_csv(io.BytesIO(csv))
        self.assertEqual(len(result.invalid_rows), 1)
        self.assertIn("slug", result.invalid_rows[0].errors[0].lower())

    def test_normalizes_slug_to_lowercase(self):
        csv = b"name,slug\nAcme,Acme-School\n"
        result = parse_csv(io.BytesIO(csv))
        self.assertEqual(len(result.valid_rows), 1)
        self.assertEqual(result.valid_rows[0].slug, "acme-school")

    def test_rejects_duplicate_slug_within_file(self):
        csv = b"name,slug\nA,dup-slug\nB,dup-slug\n"
        result = parse_csv(io.BytesIO(csv))
        self.assertEqual(len(result.valid_rows), 1)
        self.assertEqual(len(result.invalid_rows), 1)

    def test_validates_country_code_format(self):
        csv = b"name,slug,country_code\nAcme,acme-c,USA\n"
        result = parse_csv(io.BytesIO(csv))
        self.assertEqual(len(result.invalid_rows), 1)

    def test_normalizes_country_code_to_upper(self):
        csv = b"name,slug,country_code\nAcme,acme-c,us\n"
        result = parse_csv(io.BytesIO(csv))
        self.assertEqual(result.valid_rows[0].country_code, "US")

    def test_validates_sub_system(self):
        csv = b"name,slug,sub_system\nAcme,acme-c,BOGUS\n"
        result = parse_csv(io.BytesIO(csv))
        self.assertEqual(len(result.invalid_rows), 1)

    def test_validates_email_format(self):
        csv = b"name,slug,contact_email\nAcme,acme-c,not-an-email\n"
        result = parse_csv(io.BytesIO(csv))
        self.assertEqual(len(result.invalid_rows), 1)


class ApplyRowsTests(TestCase):
    def test_creates_school_for_valid_row(self):
        csv = b"name,slug\nBulk One,bulk-one\n"
        result = parse_csv(io.BytesIO(csv))
        applied = apply_rows(result.rows)
        self.assertEqual(applied.total_ok, 1)
        self.assertTrue(School.objects.filter(slug="bulk-one").exists())

    def test_records_bulk_attributed_lifecycle_stage(self):
        csv = b"name,slug\nBulk Two,bulk-two\n"
        parsed = parse_csv(io.BytesIO(csv))
        apply_rows(parsed.rows)
        school = School.objects.get(slug="bulk-two")
        stages = SchoolLifecycleStage.objects.filter(school=school)
        # signals fire REQUESTED+PROVISIONED on post_save; apply_rows
        # also calls record_stage with bulk attribution. So we expect
        # at least one row with the bulk source.
        bulk_rows = [s for s in stages if s.payload.get("source") == "bulk_csv"]
        self.assertGreaterEqual(len(bulk_rows), 1)

    def test_marks_new_school_inactive_by_default(self):
        csv = b"name,slug\nGated School,gated-school\n"
        parsed = parse_csv(io.BytesIO(csv))
        apply_rows(parsed.rows)
        school = School.objects.get(slug="gated-school")
        self.assertFalse(school.is_active)

    def test_skips_invalid_rows(self):
        csv = b"name,slug\nOK,ok-school\n,missing-name\n"
        parsed = parse_csv(io.BytesIO(csv))
        applied = apply_rows(parsed.rows)
        self.assertEqual(applied.total_ok, 1)
        self.assertEqual(len(applied.failed), 1)


class CloneSchoolTests(TestCase):
    def setUp(self):
        self.source = School.objects.create(
            name="Source Academy",
            slug="source-academy",
            subdomain="source-academy",
            primary_color="#4F46E5",
            accent_color="#10B981",
            settings={"foo": "bar", "offboarding": {"self_service_status": "requested"}},
        )

    def test_creates_new_school_with_new_slug(self):
        clone = clone_school(
            self.source,
            new_name="Mirror Academy",
            new_slug="mirror-academy",
        )
        self.assertEqual(clone.new_slug, "mirror-academy")
        self.assertEqual(clone.new_name, "Mirror Academy")
        new = School.objects.get(id=clone.new_id)
        self.assertEqual(new.primary_color, "#4F46E5")
        self.assertEqual(new.accent_color, "#10B981")

    def test_strips_offboarding_settings(self):
        clone = clone_school(
            self.source,
            new_name="Mirror2",
            new_slug="mirror2-academy",
        )
        new = School.objects.get(id=clone.new_id)
        self.assertEqual(new.settings.get("foo"), "bar")
        self.assertNotIn("offboarding", new.settings)

    def test_clone_starts_inactive(self):
        clone = clone_school(
            self.source,
            new_name="Mirror3",
            new_slug="mirror3-academy",
        )
        new = School.objects.get(id=clone.new_id)
        self.assertFalse(new.is_active)

    def test_records_lifecycle_stage_with_source_attribution(self):
        clone = clone_school(
            self.source,
            new_name="Mirror4",
            new_slug="mirror4-academy",
        )
        clone_stages = SchoolLifecycleStage.objects.filter(school_id=clone.new_id)
        clone_attributed = [
            s for s in clone_stages if s.payload.get("source") == "clone_school"
        ]
        self.assertEqual(len(clone_attributed), 1)
        self.assertEqual(clone_attributed[0].payload.get("source_slug"), self.source.slug)

    def test_rejects_invalid_slug(self):
        with self.assertRaises(ValueError):
            clone_school(self.source, new_name="X", new_slug="BAD_SLUG")
