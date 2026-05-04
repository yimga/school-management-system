"""Implementation command center — checklist and access control."""

from datetime import date, timedelta

from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Term
from apps.finance.models import PaymentGatewayHealthSnapshot
from apps.platform_runtime.views_operational_center import implementation_command_center
from apps.schools.models import School


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class ImplementationCommandCenterTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Impl School",
            slug="impl-school",
            subdomain="impl-school",
            country_code="CM",
            is_active=True,
            features={"finance": True, "offline_sync": True, "reports": True},
        )
        cls.superuser = User.objects.create_user(
            username="impl_super",
            password="x" * 8,
            is_superuser=True,
        )
        ay = AcademicYear.objects.create(
            school=cls.school,
            name="2025/26",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=300),
            is_active=True,
        )
        Term.objects.create(
            school=cls.school,
            academic_year=ay,
            name="T1",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=120),
            is_active=True,
        )
        dept = Department.objects.create(
            school=cls.school,
            name="Main",
            code="dep-impl-1",
        )
        Classroom.objects.create(
            school=cls.school,
            academic_year=ay,
            department=dept,
            name="Form 1A",
            code="cls-impl-1",
        )
        PaymentGatewayHealthSnapshot.objects.create(
            school=cls.school,
            rail_code="test",
            status=PaymentGatewayHealthSnapshot.Status.EXTERNAL_REQUIRED,
            message="PSP onboarding required",
        )

    def test_superuser_sees_checklist(self):
        c = Client()
        self.assertTrue(c.login(username="impl_super", password="x" * 8))
        url = reverse("platform_runtime:implementation_command_center")
        r = c.get(
            url,
            {"school_slug": self.school.slug},
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn("Students roster", body)
        self.assertIn("Teachers", body)
        self.assertIn("payment", body.lower())
        self.assertIn("offline", body.lower())
        self.assertIn("Go-live readiness", body)
        self.assertRegex(body, r"/\s*100")

    def test_blockers_json_endpoint(self):
        c = Client()
        self.assertTrue(c.login(username="impl_super", password="x" * 8))
        url = reverse("platform_runtime:implementation_missing_data_blockers_json")
        r = c.get(
            url,
            {"school_slug": self.school.slug},
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(r.status_code, 200)
        payload = r.json()
        self.assertIn("go_live_readiness_score", payload)
        self.assertIn("blockers", payload)

    def test_tenant_admin_staff_allowed(self):
        u = User.objects.create_user(
            username="impl_admin",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        req = RequestFactory().get("/platform-runtime/implementation/")
        req.user = u
        req.school = self.school
        resp = implementation_command_center(req)
        self.assertEqual(resp.status_code, 200)

    def test_teacher_forbidden(self):
        school = self.school
        u = User.objects.create_user(
            username="impl_teacher",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        req = RequestFactory().get("/platform-runtime/implementation/")
        req.user = u
        req.school = school
        resp = implementation_command_center(req)
        self.assertEqual(resp.status_code, 403)

    def test_every_item_has_primary_action(self):
        from apps.platform_runtime.implementation_checklist import (
            build_implementation_checklist,
        )

        data = build_implementation_checklist(self.school)
        self.assertIn(data["go_live_readiness_band"], (
            "blocked",
            "at_risk",
            "progressing",
            "ready",
        ))
        for row in data["items"]:
            pa = row.get("primary_action") or {}
            self.assertTrue(pa.get("label"))
            self.assertTrue(pa.get("url"))
        self.assertTrue(data["primary_next_action"].get("url"))
