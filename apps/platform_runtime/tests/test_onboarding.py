"""School activation checklist from real tenant models."""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.academics.models import AcademicYear, Department
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School
from apps.platform_runtime.models import SchoolOnboardingProgress
from apps.platform_runtime.onboarding import (
    get_onboarding_steps,
    get_school_onboarding_progress,
    get_school_onboarding_steps,
    mark_school_onboarding_step_complete,
)

_T_HOST = "onb-eng.runmycampus.com"


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
        self.assertEqual(prog["total"], 11)
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
            "data_migration",
            "guided_configuration",
            "plan_entitlements",
        ):
            self.assertIn(expect, keys, msg=f"missing {expect}")
        prog = get_school_onboarding_progress(self.school)
        # 4/11 weight-complete rows ≈ 36% with default weights
        self.assertGreaterEqual(prog["percent"], 35)

    def test_step_links_use_tenant_reverses(self):
        s = self.school
        for row in get_school_onboarding_steps(s):
            if not row.get("done") and row.get("link"):
                self.assertTrue(str(row["link"]).startswith(("/", "http")))

    def test_onboarding_page_resolves(self):
        name = "siteconfig:onboarding"
        path = reverse(name, urlconf="config.tenant_urls")
        self.assertTrue(path.startswith("/siteconfig/"))

    def test_get_onboarding_steps_alias(self):
        s = self.school
        a = get_onboarding_steps(s)
        b = get_school_onboarding_steps(s)
        self.assertEqual(len(a), len(b))
        for x, y in zip(a, b):
            self.assertEqual(x.get("key"), y.get("key"))

    def test_mark_step_persists_and_increases_progress(self):
        s = School.objects.create(
            name="Mark Me",
            slug="onb-mark",
            subdomain="onb-mark",
            is_active=True,
        )
        self.assertEqual(SchoolOnboardingProgress.objects.filter(school_id=s.id).count(), 0)
        mark_school_onboarding_step_complete(s, "ccc")
        rec = SchoolOnboardingProgress.objects.get(school_id=s.id)
        self.assertIn("ccc", rec.completed_steps)
        self.assertEqual(rec.last_step, "ccc")
        prog = get_school_onboarding_progress(s)
        self.assertGreater(prog["percent"], 0)
        row = next(x for x in prog["steps"] if x.get("key") == "ccc")
        self.assertTrue(row.get("done"))
        self.assertTrue(row.get("manually_completed"))


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class OnboardingEngineCoreHttpTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="HTTP Onb",
            slug="onb-eng",
            subdomain="onb-eng",
            is_active=True,
        )
        cls.perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def test_onboarding_checklist_renders_markers(self):
        u = User.objects.create_user(
            username="onb_http",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="onb_http", password="x" * 8)
        path = reverse("siteconfig:onboarding", urlconf="config.tenant_urls")
        r = c.get(path)
        self.assertEqual(r.status_code, 200, msg=r.content[:800])
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn("data-rmc-onboarding-engine", body)
        self.assertIn("/siteconfig/onboarding/step/", body)

    def test_step_page_and_post_mark(self):
        u = User.objects.create_user(
            username="onb_http2",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="onb_http2", password="x" * 8)
        p = reverse(
            "siteconfig:onboarding_step",
            kwargs={"step_key": "ccc"},
            urlconf="config.tenant_urls",
        )
        r = c.get(p)
        self.assertEqual(r.status_code, 200, msg=r.content[:800])
        self.assertIn("data-rmc-onboarding-step", r.content.decode())
        post_url = reverse(
            "siteconfig:onboarding_step_complete",
            urlconf="config.tenant_urls",
        )
        r2 = c.post(
            post_url,
            {"step_key": "ccc"},
        )
        self.assertIn(r2.status_code, (200, 302, 301))
        if r2.status_code == 302:
            self.assertTrue(
                r2["Location"].endswith("/siteconfig/onboarding/")
                or "onboarding" in r2["Location"],
            )
        self.assertTrue(
            SchoolOnboardingProgress.objects.filter(
                school_id=self.school.id
            ).exists()
        )


class OnboardingTemplateMarkersTests(TestCase):
    def test_school_onboarding_card_partial_has_markers(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent.parent
        p = root / "templates" / "accounts" / "school_onboarding_card.html"
        t = p.read_text(encoding="utf-8", errors="replace")
        p2 = (
            root / "templates" / "siteconfig" / "onboarding.html"
        ).read_text(encoding="utf-8", errors="replace")
        self.assertIn("data-rmc-onboarding-engine", p2)
        for needle in (
            'data-rmc-onboarding="school-activation"',
            "data-rmc-onboarding-progress=",
            "data-rmc-onboarding-steps",
            "data-rmc-onboarding-next-action",
        ):
            self.assertIn(needle, t)
