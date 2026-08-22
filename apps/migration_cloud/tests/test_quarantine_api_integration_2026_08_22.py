"""DB-backed REST quarantine API integration — tenant admin + cross-tenant isolation."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.automation.models import MigrationQuarantineRecord, MigrationRun
from apps.migration_cloud.api.viewsets import BundleViewSet
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class QuarantineAPIIntegrationTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.school_a = School.objects.create(
            name="Quarantine A",
            slug="q-api-a",
            subdomain="q-api-a",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="Quarantine B",
            slug="q-api-b",
            subdomain="q-api-b",
            is_active=True,
        )
        self.bundle_a = MigrationBundle.objects.create(
            label="A",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="q-api-a",
            status=BundleStatus.APPLIED,
            school=self.school_a,
        )
        self.bundle_b = MigrationBundle.objects.create(
            label="B",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="q-api-b",
            status=BundleStatus.APPLIED,
            school=self.school_b,
        )
        self.run_a = MigrationRun.objects.create(
            school=self.school_a,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle_a.pk},
        )
        self.record_a = MigrationQuarantineRecord.objects.create(
            school=self.school_a,
            migration_run=self.run_a,
            domain="students",
            row_index=1,
            issue_class="missing_required",
            payload={"error": "held", "source_row": {"full_name": "Jane"}},
        )

        self.member = User.objects.create_user(
            username="q-api-teacher",
            password="x",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=self.member,
            school=self.school_a,
            role=User.Role.TEACHER,
            is_primary=True,
        )

        self.admin = User.objects.create_user(
            username="q-api-admin",
            password="x",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school_a,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def _tenant_request(self, user, method, path, data=None):
        if method == "get":
            request = self.factory.get(path)
        else:
            request = self.factory.post(path, data or {}, format="json")
        force_authenticate(request, user=user)
        request.school = self.school_a
        request.public_host_kind = "tenant"
        return request

    def test_non_admin_quarantine_list_forbidden(self):
        view = BundleViewSet.as_view({"get": "quarantine_list"})
        request = self._tenant_request(
            self.member,
            "get",
            f"/api/v1/bundles/{self.bundle_a.pk}/quarantine/",
        )
        response = view(request, pk=self.bundle_a.pk)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_quarantine_list_returns_pending_rows(self):
        view = BundleViewSet.as_view({"get": "quarantine_list"})
        request = self._tenant_request(
            self.admin,
            "get",
            f"/api/v1/bundles/{self.bundle_a.pk}/quarantine/",
        )
        response = view(request, pk=self.bundle_a.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pending"], 1)
        self.assertEqual(len(response.data["rows"]), 1)

    def test_cross_tenant_bundle_is_not_found(self):
        view = BundleViewSet.as_view({"get": "quarantine_list"})
        request = self._tenant_request(
            self.admin,
            "get",
            f"/api/v1/bundles/{self.bundle_b.pk}/quarantine/",
        )
        response = view(request, pk=self.bundle_b.pk)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_admin_quarantine_resolve_forbidden(self):
        view = BundleViewSet.as_view({"post": "quarantine_resolve"})
        request = self._tenant_request(
            self.member,
            "post",
            f"/api/v1/bundles/{self.bundle_a.pk}/quarantine/resolve/",
            {"action": "dismiss", "record_ids": [self.record_a.pk]},
        )
        response = view(request, pk=self.bundle_a.pk)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_dismiss_action_clears_pending(self):
        view = BundleViewSet.as_view({"post": "quarantine_resolve"})
        request = self._tenant_request(
            self.admin,
            "post",
            f"/api/v1/bundles/{self.bundle_a.pk}/quarantine/resolve/",
            {"action": "dismiss", "record_ids": [self.record_a.pk]},
        )
        response = view(request, pk=self.bundle_a.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get("ok"))
        self.record_a.refresh_from_db()
        self.assertEqual(self.record_a.status, MigrationQuarantineRecord.Status.REPAIRED)

    def test_auto_retry_queues_repair_when_queue_reimport(self):
        view = BundleViewSet.as_view({"post": "quarantine_resolve"})
        request = self._tenant_request(
            self.admin,
            "post",
            f"/api/v1/bundles/{self.bundle_a.pk}/quarantine/resolve/",
            {"action": "dismiss_informational"},
        )
        with mock.patch(
            "apps.migration_cloud.quarantine_resolution.apply_quarantine_action",
            return_value={"ok": True, "queue_reimport": True},
        ):
            with mock.patch(
                "apps.migration_cloud.repair.repair_bundle",
                return_value=mock.Mock(queued=True, ran=False, message="queued"),
            ) as repair_mock:
                response = view(request, pk=self.bundle_a.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        repair_mock.assert_called_once_with(bundle_id=self.bundle_a.pk, off_http=True)
        self.assertTrue(response.data.get("retry_queued"))
