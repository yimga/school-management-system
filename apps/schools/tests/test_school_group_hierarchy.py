"""Multi-campus hierarchy helpers and siteconfig hierarchy page."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission as FeaturePermission
from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.people.models import StudentProfile
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.schools.hierarchy_helpers import (
    get_group_school_summary,
    get_school_descendants,
    hierarchy_link_would_cycle,
)
from apps.schools.models import School, SchoolMembership


_ALLOWED_HOSTS = [
    "testserver",
    "127.0.0.1",
    "localhost",
    "metro-grp.runmycampus.com",
    "north-cg.runmycampus.com",
    "south-cg.runmycampus.com",
    "solo-gr.runmycampus.com",
]


@override_settings(ALLOWED_HOSTS=_ALLOWED_HOSTS)
class SchoolGroupHierarchyTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="Gh",
            slug=f"grp-{uuid.uuid4().hex[:8]}",
            included_features=["core"],
            is_active=True,
        )
        cls.region = RegionConfig.objects.create(
            code=f"L{uuid.uuid4().hex[:6].upper()}",
            name="Ghland",
            timezone="UTC",
            default_currency="USD",
        )
        cls.parent_school = School.objects.create(
            name="Metro District",
            slug="metro-grp",
            subdomain="metro-grp",
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
        )
        cls.child_a = School.objects.create(
            name="North Campus",
            slug="north-cg",
            subdomain="north-cg",
            parent_school=cls.parent_school,
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
        )
        cls.child_b = School.objects.create(
            name="South Campus",
            slug="south-cg",
            subdomain="south-cg",
            parent_school=cls.parent_school,
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        cls.dept = Department.objects.create(name="Sci", code="SC")
        cls.spec = Specialty.objects.create(department=cls.dept, name="G", code="G")
        year = AcademicYear.objects.create(
            name="Y1",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
            school=cls.child_b,
        )
        room = Classroom.objects.create(
            academic_year=year,
            department=cls.dept,
            name="C1",
            code=f"CGB-{uuid.uuid4().hex[:6]}",
            school=cls.child_b,
        )
        for code in ("STU-GB-1", "STU-GB-2"):
            StudentProfile.objects.create(
                first_name="A",
                last_name=code,
                student_code=f"{code}-{uuid.uuid4().hex[:8]}",
                academic_year=year,
                classroom=room,
                specialty=cls.spec,
                school=cls.child_b,
                is_active=True,
            )

    def _admin(self, username, school, **kwargs):
        u = User.objects.create_user(
            username=username,
            password="passwordxx",
            role=User.Role.ADMIN,
            is_staff=True,
            **kwargs,
        )
        u.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.get_or_create(
            user=u, school=school, defaults={"role": User.Role.ADMIN, "is_primary": True}
        )
        return u

    def _force_login_verified(self, client: Client, user: User) -> None:
        TOTPDevice.objects.get_or_create(
            user=user,
            name="default",
            defaults={"confirmed": True},
        )
        client.force_login(user)
        session = client.session
        session["mfa_verified"] = True
        session.save()

    def test_parent_sees_children_on_hierarchy_page(self):
        u = self._admin(f"dadm_{uuid.uuid4().hex[:8]}", self.parent_school)
        c = Client(HTTP_HOST="metro-grp.runmycampus.com")
        self._force_login_verified(c, u)
        url = reverse("siteconfig:school_group_hierarchy", urlconf="config.tenant_urls")
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:600])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("North Campus", body)
        self.assertIn("South Campus", body)
        self.assertIn('data-rmc-school-hierarchy="1"', body)

    def test_child_admin_response_has_no_sibling_name_as_peer_table(self):
        """Campus B admin page must not enumerate sibling campus A as a child-of-parent listing."""
        u = self._admin(f"badm_{uuid.uuid4().hex[:8]}", self.child_b)
        host = "south-cg.runmycampus.com"
        c = Client(HTTP_HOST=host)
        self._force_login_verified(c, u)
        url = reverse("siteconfig:school_group_hierarchy", urlconf="config.tenant_urls")
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertNotIn("North Campus", body)

    def test_teacher_forbidden(self):
        tu = User.objects.create_user(
            username=f"t_{uuid.uuid4().hex[:8]}",
            password="passwordxx",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(user=tu, school=self.child_b, role=User.Role.TEACHER)
        c = Client(HTTP_HOST="south-cg.runmycampus.com")
        c.force_login(tu)
        resp = c.get(
            reverse("siteconfig:school_group_hierarchy", urlconf="config.tenant_urls")
        )
        self.assertEqual(resp.status_code, 403)

    def test_cycle_helper_detects_direct_cycle(self):
        self.assertTrue(hierarchy_link_would_cycle(self.child_a, self.child_a.pk))

    def test_descendant_summary_counts_real_students(self):
        u = self._admin(f"sum_{uuid.uuid4().hex[:8]}", self.child_b)
        summary = get_group_school_summary(self.child_b, u)
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["student_count"], 2)

    def test_single_school_renders(self):
        solo = School.objects.create(
            name="Solo Academy",
            slug="solo-gr",
            subdomain="solo-gr",
            is_active=True,
            plan=self.plan,
            default_region=self.region,
        )
        u = self._admin(f"solo_{uuid.uuid4().hex[:8]}", solo)
        c = Client(HTTP_HOST="solo-gr.runmycampus.com")
        self._force_login_verified(c, u)
        resp = c.get(reverse("siteconfig:school_group_hierarchy", urlconf="config.tenant_urls"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("single-tenant", body)

    def test_superuser_sees_admin_fallback_only_when_superuser(self):
        su = User.objects.create_superuser(
            username=f"su_{uuid.uuid4().hex[:8]}",
            password="passwordxx",
            email="su@example.com",
        )
        su.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.create(
            user=su, school=self.child_b, role=User.Role.ADMIN, is_primary=True
        )
        c = Client(HTTP_HOST="south-cg.runmycampus.com")
        self._force_login_verified(c, su)
        resp = c.get(reverse("siteconfig:school_group_hierarchy", urlconf="config.tenant_urls"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("/admin/schools/school/", body)

    def test_get_descendants_bfs(self):
        d = get_school_descendants(self.parent_school, include_self=False)
        self.assertEqual(d.count(), 2)
