"""Wave 7 (v2.80): First-school operating proof readiness preflight."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.schools.models import School
from apps.schools.first_school_readiness import (
    assess_first_school_readiness,
    FirstSchoolReadinessReport,
)


class FirstSchoolReadinessTests(TestCase):
    """Tests use a known slug rather than asserting "zero schools" because
    the test DB (kept across runs and shared with seed migrations) may
    contain unrelated schools. We assert per-tenant readiness, not platform totals.
    """

    def test_returns_a_report_dataclass(self):
        report = assess_first_school_readiness()
        self.assertIsInstance(report, FirstSchoolReadinessReport)
        self.assertGreaterEqual(report.schools_total, 0)

    def test_school_with_no_setup_lists_every_criterion_as_missing(self):
        School.objects.create(name="Empty", slug="empty-w7", subdomain="empty-w7-sub")
        report = assess_first_school_readiness()
        not_ready_by_slug = {
            t["slug"]: t for t in report.tenants_not_ready
        }
        self.assertIn("empty-w7", not_ready_by_slug, "Our test tenant must appear in not-ready list.")
        missing = not_ready_by_slug["empty-w7"]["missing"]
        self.assertIn("academic_year", missing)
        self.assertIn("term", missing)
        self.assertIn("classroom", missing)
        self.assertIn("active_teacher", missing)
        self.assertIn("active_student", missing)

    def test_fully_set_up_school_is_ready(self):
        from apps.academics.models import AcademicYear, Term, Classroom
        from apps.people.models import StudentProfile, TeacherProfile, Department

        User = get_user_model()
        school = School.objects.create(
            name="Ready School", slug="ready", subdomain="ready-sub"
        )
        year = AcademicYear.objects.create(
            school=school, name="2025/2026", start_date="2025-09-01", end_date="2026-06-30"
        )
        Term.objects.create(
            school=school, academic_year=year, name="Term 1",
            start_date="2025-09-01", end_date="2025-12-15",
        )
        dept = Department.objects.create(school=school, name="Default")
        Classroom.objects.create(
            school=school, name="Form 1", academic_year=year,
            department=dept, code="FORM-1-W7",
        )
        teacher_user = User.objects.create_user(
            username="teacher_ready", email="tr@example.com", password="pwd"
        )
        TeacherProfile.objects.create(school=school, user=teacher_user, is_active=True)
        StudentProfile.objects.create(
            school=school, first_name="A", last_name="B", is_active=True
        )
        report = assess_first_school_readiness()
        self.assertTrue(report.ready, f"Should be ready; not-ready details: {report.tenants_not_ready!r}")
        self.assertEqual(report.schools_operating_ready, 1)
        self.assertIn("ready", report.tenants_ready)

    def test_issue_count_zero_when_ready(self):
        """When at least one tenant is operating-ready, issue_count is 0."""
        # Re-use scaffolding from the previous test by re-creating it.
        from apps.academics.models import AcademicYear, Term, Classroom
        from apps.people.models import StudentProfile, TeacherProfile, Department

        User = get_user_model()
        school = School.objects.create(
            name="Ready 2", slug="ready-2", subdomain="ready-2-sub"
        )
        year = AcademicYear.objects.create(
            school=school, name="2025/2026", start_date="2025-09-01", end_date="2026-06-30"
        )
        Term.objects.create(
            school=school, academic_year=year, name="Term A",
            start_date="2025-09-01", end_date="2025-12-15",
        )
        dept_a = Department.objects.create(school=school, name="Default A")
        Classroom.objects.create(
            school=school, name="Form A", academic_year=year,
            department=dept_a, code="FORM-A-W7",
        )
        teacher_user = User.objects.create_user(
            username="teacher_ready2", email="tr2@example.com", password="pwd"
        )
        TeacherProfile.objects.create(school=school, user=teacher_user, is_active=True)
        StudentProfile.objects.create(
            school=school, first_name="C", last_name="D", is_active=True
        )
        report = assess_first_school_readiness()
        self.assertEqual(report.issue_count(), 0)
