"""Tenant API guard host boundary — staff cannot bypass on tenant hosts."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.schools.models import School, SchoolMembership
from apps.schools.tenant_api_guards import user_may_operate_on_school

User = get_user_model()


class TenantApiGuardsStaffHostTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.school_a = School.objects.create(
            name=f"Guard A {uid}",
            slug=f"ga-{uid}",
            subdomain=f"ga{uid}",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name=f"Guard B {uid}",
            slug=f"gb-{uid}",
            subdomain=f"gb{uid}",
            is_active=True,
        )
        cls.staff_no_membership = User.objects.create_user(
            username=f"staff_guard_{uid}",
            password="Test1234",
            role="ADMIN",
            is_staff=True,
        )
        cls.member = User.objects.create_user(
            username=f"member_guard_{uid}",
            password="Test1234",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=cls.member,
            school=cls.school_a,
            role="ADMIN",
            is_primary=True,
        )

    def _req(self, user, *, host_kind: str, school=None):
        rf = RequestFactory()
        request = rf.get("/api/v1/example/")
        request.user = user
        request.public_host_kind = host_kind
        request.school = school
        request.session = {}
        return request

    def test_staff_on_tenant_host_denied_without_membership(self):
        request = self._req(
            self.staff_no_membership,
            host_kind="tenant",
            school=self.school_b,
        )
        self.assertFalse(user_may_operate_on_school(request, self.school_b))

    def test_staff_on_manager_host_allowed_for_control_plane(self):
        self.staff_no_membership.is_superuser = True
        self.staff_no_membership.save(update_fields=["is_superuser"])
        request = self._req(
            self.staff_no_membership,
            host_kind="manager",
            school=self.school_b,
        )
        self.assertTrue(user_may_operate_on_school(request, self.school_b))

    def test_member_on_tenant_host_allowed_for_own_school(self):
        request = self._req(
            self.member,
            host_kind="tenant",
            school=self.school_a,
        )
        self.assertTrue(user_may_operate_on_school(request, self.school_a))
