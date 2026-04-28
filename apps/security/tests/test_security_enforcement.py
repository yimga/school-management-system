"""SLICE 10 — tenant isolation and access enforcement (deterministic checks)."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission as FeaturePermission, User
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.schools.tenant_access import (
    has_school_permission,
    safe_queryset_for_school,
    user_belongs_to_school,
)

_T_HOST = "ns-sec1.runmycampus.com"
_MGR_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _T_HOST, _MGR_HOST]
)
class TenantAccessUnitTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(
            name="A",
            slug="ns-sec1",
            subdomain="ns-sec1",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="B",
            slug="other-sec",
            subdomain="other-sec",
            is_active=True,
        )
        self.sa = StudentProfile.objects.create(
            school=self.school_a,
            first_name="A",
            last_name="One",
            student_code="A-1",
            is_active=True,
        )
        self.sb = StudentProfile.objects.create(
            school=self.school_b,
            first_name="B",
            last_name="Two",
            student_code="B-1",
            is_active=True,
        )

    def test_safe_queryset_excludes_other_tenant(self):
        qs = safe_queryset_for_school(StudentProfile.objects.all(), self.school_a)
        self.assertEqual(set(qs.values_list("pk", flat=True)), {self.sa.pk})

    def test_safe_queryset_none_without_school(self):
        self.assertEqual(safe_queryset_for_school(StudentProfile.objects.all(), None).count(), 0)

    def test_has_school_permission_membership_and_manage(self):
        perm, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        u = User.objects.create_user(
            username=f"m_{uuid.uuid4().hex[:10]}",
            password="y" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(perm)
        SchoolMembership.objects.create(
            user=u,
            school=self.school_a,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.assertTrue(has_school_permission(u, self.school_a, "export"))
        self.assertFalse(has_school_permission(u, self.school_b, "export"))

    def test_superuser_passes_without_membership(self):
        su = User.objects.create_user(
            username=f"s_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            is_superuser=True,
            is_staff=True,
        )
        self.assertTrue(has_school_permission(su, self.school_a, "admin"))

    def test_user_belongs_requires_membership_for_non_super(self):
        u = User.objects.create_user(username=f"p_{uuid.uuid4().hex[:8]}", password="y" * 8)
        self.assertFalse(user_belongs_to_school(u, self.school_a))


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _T_HOST, _MGR_HOST]
)
class ComplianceExportEnforcementTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.perm, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        cls.school = School.objects.create(
            name="Compliance Slice10",
            slug="ns-sec1",
            subdomain="ns-sec1",
            is_active=True,
        )

    def test_manage_without_membership_gets_403_list(self):
        u = User.objects.create_user(
            username=f"x_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm)
        client = Client(HTTP_HOST=_T_HOST)
        client.force_login(u)
        url = reverse("siteconfig:compliance_exports", urlconf="config.tenant_urls")
        self.assertEqual(client.get(url).status_code, 403)


@override_settings(ALLOWED_HOSTS=["*", _MGR_HOST])
class SecuritySurfaceDashboardTests(TestCase):
    def test_super_sees_marker_and_staff_blocked(self):
        super_u = User.objects.create_user(
            username=f"su_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            is_staff=True,
            is_superuser=True,
        )
        staff = User.objects.create_user(
            username=f"st_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            is_staff=True,
            is_superuser=False,
        )
        url = reverse("super:security_surface_dashboard")
        c = Client(HTTP_HOST=_MGR_HOST)
        c.force_login(super_u)
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-security-surface="1"', body)

        c.force_login(staff)
        denied = c.get(url)
        self.assertIn(denied.status_code, (302, 403))
