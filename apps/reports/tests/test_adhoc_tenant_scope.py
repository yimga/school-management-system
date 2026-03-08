from datetime import date

from django.test import TestCase

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department
from apps.people.models import StudentProfile
from apps.reports.adhoc_runner import run_adhoc_report
from apps.reports.bi_models import AdHocReportDefinition
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class AdHocTenantScopeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="adhoc_runner", password="pass12345")
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            slug="adhoc-tenant",
            subdomain="adhoc-tenant",
            name="AdHoc Tenant",
            default_region=self.region,
            timezone=self.region.timezone,
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
            school=self.school,
        )
        self.department = Department.objects.create(name="Science", code="SCI", school=self.school)
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 3A",
            code="F3A",
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            first_name="Ada",
            last_name="Tenant",
            student_code="ADHOC-001",
            academic_year=self.year,
            classroom=self.classroom,
            school=self.school,
            is_active=True,
        )

    def test_global_definition_fails_closed_without_explicit_scope(self):
        definition = AdHocReportDefinition.objects.create(
            name="Global students",
            entity_type="STUDENTS",
            columns=["id", "first_name", "last_name"],
            school=None,
            created_by=self.user,
            output_format="JSON",
        )

        csv_bytes, json_rows, row_count, error = run_adhoc_report(definition, self.user, output_format="JSON")

        self.assertIsNone(csv_bytes)
        self.assertIsNone(json_rows)
        self.assertEqual(row_count, 0)
        self.assertIn("school_id required", error)

    def test_tenant_scoped_definition_returns_only_tenant_rows(self):
        definition = AdHocReportDefinition.objects.create(
            name="Tenant students",
            entity_type="STUDENTS",
            columns=["id", "first_name", "last_name"],
            school=self.school,
            created_by=self.user,
            output_format="JSON",
        )

        csv_bytes, json_rows, row_count, error = run_adhoc_report(definition, self.user, output_format="JSON")

        self.assertIsNone(csv_bytes)
        self.assertIsNone(error)
        self.assertEqual(row_count, 1)
        self.assertEqual(json_rows[0]["first_name"], "Ada")
