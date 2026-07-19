"""S2 — MigrationCloudApplyView requires staff (super) or tenant-admin (portal)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.views import MigrationCloudApplyView
from apps.schools.models import School, SchoolMembership


class MigrationCloudApplyRoleGateTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="Apply Gate School",
            slug="apply-gate-school",
            subdomain="apply-gate-school",
            is_active=True,
        )
        self.bundle = MigrationBundle.objects.create(
            label="apply role gate",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="apply-role-gate",
            status=BundleStatus.MAPPED,
            school=self.school,
        )

    def _fake_result(self):
        return SimpleNamespace(
            bundle_id=self.bundle.pk,
            dry_run=True,
            status="mapped",
            total_created=0,
            total_updated=0,
            total_quarantined=0,
            per_artifact=[],
        )

    def test_teacher_portal_apply_denied(self):
        teacher = User.objects.create_user(
            username="apply_teacher", password="x", role=User.Role.TEACHER
        )
        SchoolMembership.objects.create(
            user=teacher, school=self.school, role=User.Role.TEACHER
        )
        request = self.rf.post(f"/migration/{self.bundle.pk}/apply/")
        request.user = teacher
        request.school = self.school
        resp = MigrationCloudApplyView.as_view()(
            request, bundle_id=self.bundle.pk, shell="portal"
        )
        self.assertEqual(resp.status_code, 403)
        import json

        self.assertEqual(json.loads(resp.content.decode()).get("error"), "forbidden")

    def test_non_staff_super_shell_denied(self):
        user = User.objects.create_user(
            username="apply_civilian", password="x", role=User.Role.TEACHER
        )
        request = self.rf.post(f"/migration/{self.bundle.pk}/apply/")
        request.user = user
        resp = MigrationCloudApplyView.as_view()(
            request, bundle_id=self.bundle.pk, shell="super"
        )
        self.assertEqual(resp.status_code, 403)
        import json

        self.assertEqual(json.loads(resp.content.decode()).get("error"), "forbidden")

    @mock.patch("apps.migration_cloud.orchestrator.apply_bundle")
    def test_staff_super_shell_allowed(self, apply_mock):
        apply_mock.return_value = self._fake_result()
        staff = User.objects.create_user(
            username="apply_staff", password="x", is_staff=True
        )
        request = self.rf.post(f"/migration/{self.bundle.pk}/apply/")
        request.user = staff
        resp = MigrationCloudApplyView.as_view()(
            request, bundle_id=self.bundle.pk, shell="super"
        )
        self.assertEqual(resp.status_code, 200)
        apply_mock.assert_called_once()
