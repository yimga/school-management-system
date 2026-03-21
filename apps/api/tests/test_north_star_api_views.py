"""North-star internal APIs: event catalog, wedge playbook, package impact."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.schools.models import School

User = get_user_model()


class NorthStarApiViewsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="NS API",
            slug="ns-api",
            subdomain="ns-api",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="nsstaff",
            email="ns@test.edu",
            password="x",
            is_staff=True,
        )

    def test_event_catalog_includes_provisioning_events(self):
        c = Client()
        c.force_login(self.user)
        r = c.get(reverse("api:api-north-star-event-catalog"))
        self.assertEqual(r.status_code, 200)
        ev = r.json()["events"]
        self.assertIn("provisioning_started", ev)
        self.assertIn("learning_wedge_pack_applied", ev)
        self.assertIn("learning_wedge_pack_rolled_back", ev)
        self.assertIn("marketplace_app_installed", ev)
        self.assertIn("celery_task_started", ev)

    def test_wedge_playbook(self):
        c = Client()
        c.force_login(self.user)
        r = c.get(reverse("api:api-north-star-wedge-playbook"))
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("delivery_modes", d)
        self.assertIn("substitute_interop", d)

    def test_package_impact_requires_school(self):
        c = Client()
        c.force_login(self.user)
        r = c.get(reverse("api:api-north-star-package-impact") + "?package_id=foo")
        self.assertEqual(r.status_code, 400)

    def test_package_impact_with_school_no_version(self):
        c = Client()
        c.force_login(self.user)
        r = c.get(
            reverse("api:api-north-star-package-impact")
            + "?package_id=unknown-pkg&school_id=%s" % self.school.pk
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["preview_available"])
        self.assertIn("dependency_graph", body)
        self.assertIn("upstream_package_ids", body["dependency_graph"])
        self.assertIn("downstream_package_ids", body["dependency_graph"])

    def test_package_impact_dependency_graph_reverse_edges(self):
        from apps.packages.models import PackageVersion

        PackageVersion.objects.create(
            package_id="ns-parent",
            version="1.0.0",
            dependencies=[],
            payload_sections={"theme": {}},
        )
        PackageVersion.objects.create(
            package_id="ns-child",
            version="1.0.0",
            dependencies=["ns-parent"],
            payload_sections={"theme": {}},
        )
        c = Client()
        c.force_login(self.user)
        r = c.get(
            reverse("api:api-north-star-package-impact")
            + "?package_id=ns-child&school_id=%s" % self.school.pk
        )
        self.assertEqual(r.status_code, 200)
        g = r.json()["dependency_graph"]
        self.assertIn("ns-parent", g["upstream_package_ids"])
        r2 = c.get(
            reverse("api:api-north-star-package-impact")
            + "?package_id=ns-parent&school_id=%s" % self.school.pk
        )
        self.assertIn("ns-child", r2.json()["dependency_graph"]["downstream_package_ids"])

    def test_rum_web_vitals_summary_staff_200(self):
        from apps.platform_runtime.events import emit_platform_event

        emit_platform_event(
            "rum_web_vitals",
            {
                "path": "/x",
                "metrics": {"lcp": 2100.0},
                "navigation_type": "",
            },
            tenant_id="",
        )
        c = Client()
        c.force_login(self.user)
        r = c.get(reverse("api:api-north-star-rum-web-vitals"))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["beacon_count"], 1)
        self.assertIn("metrics", body)
        self.assertIn("version", body)
        self.assertIn("rum_ingest_configured", body)

    def test_rum_web_vitals_summary_non_staff_forbidden(self):
        plain = User.objects.create_user(
            username="norumm",
            email="nr@test.edu",
            password="x",
            is_staff=False,
        )
        c = Client()
        c.force_login(plain)
        r = c.get(reverse("api:api-north-star-rum-web-vitals"))
        self.assertEqual(r.status_code, 403)

    def test_upcoming_deadlines_requires_school(self):
        c = Client()
        c.force_login(self.user)
        r = c.get(reverse("api:api-north-star-upcoming-deadlines"))
        self.assertEqual(r.status_code, 400)
        err = (r.json().get("error") or "").lower()
        self.assertIn("school", err)

    def test_upcoming_deadlines_includes_grading_line(self):
        today = date.today()
        year = AcademicYear.objects.create(
            school=self.school,
            name="API-Y1",
            start_date=today - timedelta(days=200),
            end_date=today + timedelta(days=200),
            is_active=True,
        )
        term = Term.objects.create(
            school=self.school,
            academic_year=year,
            name="FIRST",
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=120),
            is_active=True,
            position=1,
        )
        dept = Department.objects.create(
            school=self.school, name="Science", code="SCI-NS-UDL"
        )
        spec = Specialty.objects.create(
            school=self.school,
            department=dept,
            name="General",
            code="GEN-NS-UDL",
        )
        classroom = Classroom.objects.create(
            school=self.school,
            academic_year=year,
            department=dept,
            name="C-API",
            code="CAPI-NS-UDL",
        )
        subject = Subject.objects.create(school=self.school, name="Math-NS-UDL")
        SubjectAssignment.objects.create(
            school=self.school,
            academic_year=year,
            term=term,
            classroom=classroom,
            specialty=spec,
            subject=subject,
            grading_deadline_at=timezone.now() + timedelta(days=3),
        )
        c = Client()
        c.force_login(self.user)
        base = reverse("api:api-north-star-upcoming-deadlines")
        r = c.get(f"{base}?school_id={self.school.pk}")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["school_id"], str(self.school.pk))
        self.assertGreaterEqual(body["count"], 1)
        kinds = {e.get("kind") for e in body["events"]}
        self.assertIn("grading_deadline", kinds)

    def test_package_impact_preview_when_package_version_exists(self):
        from apps.packages.models import PackageVersion

        PackageVersion.objects.create(
            package_id="demo-impact",
            version="1.0.0",
            payload_sections={"workflow": {"packs": [{"code": "x"}]}},
        )
        c = Client()
        c.force_login(self.user)
        r = c.get(
            reverse("api:api-north-star-package-impact")
            + "?package_id=demo-impact&school_id=%s" % self.school.pk
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["preview_available"])
        self.assertIn("preview", body)
        self.assertIn("dependency_graph", body)
