"""People directory remediation — enrollment sync + guardian promote."""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.metadata.models import DynamicFieldValue
from apps.migration_cloud.enrollment_sync import sync_all_enrollments_for_school
from apps.migration_cloud.guardian_directory import promote_unlinked_guardian_hints
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School


def _school(tag: str) -> School:
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"School {slug}",
        slug=slug,
        subdomain=slug,
        country_code="CM",
    )


class SyncAllEnrollmentsTests(TestCase):
    def test_dry_run_counts_students_with_academic_year(self):
        from apps.academics.models import AcademicYear

        school = _school("bulk-sync")
        year = AcademicYear.objects.create(
            school=school,
            name="2025-2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
        )
        StudentProfile.objects.create(
            school=school,
            first_name="A",
            last_name="One",
            student_code="S-1",
            academic_year=year,
        )
        StudentProfile.objects.create(
            school=school,
            first_name="B",
            last_name="Two",
            student_code="S-2",
        )
        summary = sync_all_enrollments_for_school(school, dry_run=True)
        self.assertEqual(summary["examined"], 2)
        self.assertEqual(summary["synced"], 1)
        self.assertEqual(summary["skipped"], 1)


class GuardianPromoteDryRunTests(TestCase):
    def test_dry_run_reports_would_promote_without_writing(self):
        school = _school("guard-dry")
        student = StudentProfile.objects.create(
            school=school,
            first_name="Child",
            last_name="One",
            student_code="C-1",
        )
        DynamicFieldValue.objects.create(
            school=school,
            entity_type="student",
            entity_id=str(student.pk),
            field_key="parent_name",
            value_json={"v": "Jane Parent"},
        )
        before = StudentGuardian.objects.filter(student__school=school).count()
        summary = promote_unlinked_guardian_hints(school=school, dry_run=True)
        after = StudentGuardian.objects.filter(student__school=school).count()
        self.assertEqual(summary["would_promote"], 1)
        self.assertEqual(before, after)
