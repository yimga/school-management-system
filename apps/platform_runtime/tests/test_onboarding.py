"""School activation checklist from real tenant models."""

from django.test import TestCase
from django.urls import reverse

from apps.academics.models import AcademicYear, Department
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School
from apps.platform_runtime.onboarding import (
    get_school_onboarding_progress,
    get_school_onboarding_steps,
)


class OnboardingServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Onboarding Test School",
            slug="onb-test",
            subdomain="onb-test",
            is_active=True,
        )
        from datetime import date

        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="Y1",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31),
            is_active=True,
        )
        cls.dept = Department.objects.create(
            school=cls.school, name="Core", code="onbcore"
        )

    def test_empty_school_has_low_progress(self):
        s = School.objects.create(
            name="Empty", slug="onb-empty", subdomain="onb-e", is_active=True
        )
        prog = get_school_onboarding_progress(s)
        self.assertEqual(prog["total"], 8)
        self.assertLessEqual(prog["percent"], 30)

    def test_configured_school_higher_progress(self):
        from datetime import date

        from apps.accounts.models import User

        tu = User.objects.create_user(
            username="t_onb1",
            email="t1@e.test",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(school=self.school, user=tu)
        su = User.objects.create_user(
            username="s_onb1",
            email="s1@e.test",
            password="x" * 8,
            role=User.Role.STUDENT,
        )
        StudentProfile.objects.create(
            school=self.school,
            user=su,
            first_name="A",
            last_name="B",
            date_of_birth=date(2014, 1, 1),
            student_code="st-onb-1",
            is_active=True,
        )
        steps = get_school_onboarding_steps(self.school)
        keys = {r["key"] for r in steps}
        for expect in (
            "academic_year",
            "departments",
            "students",
            "teachers",
            "classes",
        ):
            self.assertIn(expect, keys, msg=f"missing {expect}")
        prog = get_school_onboarding_progress(self.school)
        self.assertGreaterEqual(prog["percent"], 40)

    def test_step_links_use_tenant_reverses(self):
        s = self.school
        for row in get_school_onboarding_steps(s):
            if not row.get("done") and row.get("link"):
                self.assertTrue(str(row["link"]).startswith(("/", "http")))

    def test_onboarding_page_resolves(self):
        name = "siteconfig:onboarding"
        path = reverse(name, urlconf="config.tenant_urls")
        self.assertTrue(path.startswith("/siteconfig/"))


class OnboardingTemplateMarkersTests(TestCase):
    def test_school_onboarding_card_partial_has_markers(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent.parent
        p = root / "templates" / "accounts" / "school_onboarding_card.html"
        t = p.read_text(encoding="utf-8", errors="replace")
        for needle in (
            'data-rmc-onboarding="school-activation"',
            "data-rmc-onboarding-progress=",
            "data-rmc-onboarding-steps",
            "data-rmc-onboarding-next-action",
        ):
            self.assertIn(needle, t)
