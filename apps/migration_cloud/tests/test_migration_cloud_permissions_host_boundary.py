"""Migration Cloud API permissions — operator shell host boundary (batch 1608)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.migration_cloud.api.permissions import (
    MigrationCloudAPIPermission,
    _is_operator_shell_request,
)
from apps.migration_cloud.models import MigrationBundle
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class MigrationCloudPermissionsHostBoundaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.school_a = School.objects.create(
            name=f"MC A {uid}",
            slug=f"mca-{uid}",
            subdomain=f"mca{uid}",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name=f"MC B {uid}",
            slug=f"mcb-{uid}",
            subdomain=f"mcb{uid}",
            is_active=True,
        )
        cls.operator = User.objects.create_user(
            username=f"mc_operator_{uid}",
            password="Test1234",
            role="ADMIN",
            is_staff=True,
            is_superuser=True,
        )
        cls.tenant_member = User.objects.create_user(
            username=f"mc_member_{uid}",
            password="Test1234",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=cls.tenant_member,
            school=cls.school_a,
            role="ADMIN",
            is_primary=True,
        )
        cls.staff_no_membership = User.objects.create_user(
            username=f"mc_staff_{uid}",
            password="Test1234",
            role="ADMIN",
            is_staff=True,
        )
        cls.bundle_a = MigrationBundle.objects.create(
            school=cls.school_a,
            label="Bundle A",
            idempotency_key=f"mc-perm-a-{uid}",
        )
        cls.bundle_b = MigrationBundle.objects.create(
            school=cls.school_b,
            label="Bundle B",
            idempotency_key=f"mc-perm-b-{uid}",
        )

    def _req(self, user, *, host_kind: str, school=None):
        rf = RequestFactory()
        request = rf.get("/migration/api/v1/bundles/")
        request.user = user
        request.public_host_kind = host_kind
        request.school = school
        request.tenant = school
        return request

    def test_operator_shell_requires_manager_or_local_host(self):
        manager_req = self._req(self.operator, host_kind="manager")
        tenant_req = self._req(self.operator, host_kind="tenant", school=self.school_b)
        self.assertTrue(_is_operator_shell_request(manager_req))
        self.assertFalse(_is_operator_shell_request(tenant_req))

    def test_staff_on_tenant_host_without_membership_denied(self):
        perm = MigrationCloudAPIPermission()
        request = self._req(
            self.staff_no_membership,
            host_kind="tenant",
            school=self.school_b,
        )
        self.assertFalse(perm.has_permission(request, SimpleNamespace()))

    def test_staff_on_manager_host_allowed(self):
        perm = MigrationCloudAPIPermission()
        request = self._req(self.operator, host_kind="manager")
        self.assertTrue(perm.has_permission(request, SimpleNamespace()))

    def test_tenant_member_object_permission_matches_own_school(self):
        perm = MigrationCloudAPIPermission()
        request = self._req(
            self.tenant_member,
            host_kind="tenant",
            school=self.school_a,
        )
        view = SimpleNamespace()
        self.assertTrue(
            perm.has_object_permission(request, view, self.bundle_a)
        )
        self.assertFalse(
            perm.has_object_permission(request, view, self.bundle_b)
        )

    def test_pre_tenant_bundle_denied_to_tenant_shell(self):
        uid = uuid.uuid4().hex[:8]
        pre_tenant = MigrationBundle.objects.create(
            school=None,
            label="Pre-tenant",
            idempotency_key=f"mc-pre-{uid}",
        )
        perm = MigrationCloudAPIPermission()
        request = self._req(
            self.tenant_member,
            host_kind="tenant",
            school=self.school_a,
        )
        self.assertFalse(
            perm.has_object_permission(request, SimpleNamespace(), pre_tenant)
        )
