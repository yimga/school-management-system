"""DRF ReBAC permission wiring on finance APIs."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from rest_framework.test import force_authenticate

from apps.accounts.drf_rebac import RebacPermission
from apps.accounts.models import Permission
from apps.accounts.rebac import write_tuple
from apps.accounts.rebac_sync import sync_membership_tuples
from apps.finance.api_views import InvoiceViewSet
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class DrfRebacFinanceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Finance ReBAC",
            slug="fin-rebac",
            subdomain="finrebac",
            country_code="US",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="bursar_rebac",
            password="Test1234!",
            role=User.Role.BURSAR,
        )
        perm, _ = Permission.objects.get_or_create(
            code="finance.view",
            defaults={"name": "Finance view"},
        )
        self.user.feature_permissions.add(perm)
        m = SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.BURSAR,
        )
        sync_membership_tuples(m)
        write_tuple(
            school=self.school,
            subject_type="user",
            subject_id=str(self.user.pk),
            relation="can",
            object_type="permission",
            object_id=perm.code,
            source="backfill",
            source_key="test:finance.view",
        )

    def test_invoice_list_rebac_permission_allows_tuple(self):
        factory = RequestFactory()
        request = factory.get("/api/finance/invoices/")
        request.school = self.school
        force_authenticate(request, user=self.user)
        view = InvoiceViewSet.as_view({"get": "list"})
        response = view(request)
        self.assertIn(response.status_code, (200, 404))

    def test_rebac_permission_class_denies_without_tuple(self):
        other = User.objects.create_user(
            username="no_fin",
            password="Test1234!",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=other,
            school=self.school,
            role=User.Role.TEACHER,
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.school = self.school
        perm = RebacPermission("finance.view")
        self.assertFalse(perm.has_permission(request, view=None))
        force_authenticate(request, user=other)
        self.assertFalse(perm.has_permission(request, view=None))
