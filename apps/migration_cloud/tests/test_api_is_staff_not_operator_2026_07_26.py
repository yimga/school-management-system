"""``is_staff`` must NOT grant cross-tenant Migration Cloud API access.

The platform mints ``is_staff=True`` TENANT ADMINS — ordinary members on their
own subdomain, not platform operators. Keying the cross-tenant operator "super"
shell (and the unfiltered bundle queryset) on bare ``is_staff`` let such a user
read + drive apply/advance/reconcile on EVERY tenant's bundles. Only a genuine
platform operator (control-plane access on the manager/local host) may — the
same predicate the API permission class already enforces.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.migration_cloud.api.helpers import shell_for_request
from apps.migration_cloud.api.viewsets import BundleViewSet
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.schools.models import School

User = get_user_model()


class ApiIsStaffNotOperatorTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school_a = School.objects.create(
            name="Tenant A", slug="iso-tenant-a", subdomain="iso-tenant-a",
            is_active=True, country_code="CM",
        )
        self.school_b = School.objects.create(
            name="Tenant B", slug="iso-tenant-b", subdomain="iso-tenant-b",
            is_active=True, country_code="CM",
        )
        self.bundle_a = MigrationBundle.objects.create(
            label="A", intake_method=IntakeMethod.FILE_UPLOAD, idempotency_key="iso-a",
            status=BundleStatus.MAPPED, school=self.school_a,
        )
        self.bundle_b = MigrationBundle.objects.create(
            label="B", intake_method=IntakeMethod.FILE_UPLOAD, idempotency_key="iso-b",
            status=BundleStatus.MAPPED, school=self.school_b,
        )
        # is_staff tenant admin — NOT a platform operator (no control-plane access).
        self.staff_admin = User.objects.create_user(
            username="iso-staffadmin", email="sa@example.com", password="x", is_staff=True
        )
        # Genuine platform operator (superuser => control-plane access).
        self.operator = User.objects.create_superuser(
            username="iso-operator", email="op@example.com", password="x"
        )

    def _req(self, user, host_kind, school=None):
        req = self.rf.get("/")
        req.user = user
        req.public_host_kind = host_kind
        req.school = school
        return req

    # --- shell routing ----------------------------------------------------
    def test_staff_tenant_admin_gets_portal_shell(self):
        self.assertEqual(
            shell_for_request(self._req(self.staff_admin, "tenant", self.school_a)),
            "portal",
        )

    def test_operator_on_manager_host_gets_super_shell(self):
        self.assertEqual(shell_for_request(self._req(self.operator, "manager")), "super")

    def test_even_operator_off_manager_host_is_not_super(self):
        self.assertEqual(
            shell_for_request(self._req(self.operator, "tenant", self.school_a)),
            "portal",
        )

    # --- cross-tenant queryset -------------------------------------------
    def test_staff_tenant_admin_queryset_scoped_to_own_school(self):
        vs = BundleViewSet()
        vs.request = self._req(self.staff_admin, "tenant", self.school_a)
        ids = set(vs.get_queryset().values_list("pk", flat=True))
        self.assertEqual(ids, {self.bundle_a.pk})  # never bundle_b

    def test_operator_queryset_is_cross_tenant(self):
        vs = BundleViewSet()
        vs.request = self._req(self.operator, "manager")
        ids = set(vs.get_queryset().values_list("pk", flat=True))
        self.assertIn(self.bundle_a.pk, ids)
        self.assertIn(self.bundle_b.pk, ids)
