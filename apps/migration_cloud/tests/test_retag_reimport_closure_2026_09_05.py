"""Retag/re-import service, classroom backfill, and review-page wiring."""
from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.accounts.models import User
from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.retag_reimport import (
    bundle_needs_reimport_after_retag,
    retag_and_reimport_bundle,
)
from apps.migration_cloud.student_placement_backfill import (
    _class_label_for_student,
    backfill_student_classrooms_for_school,
)
from apps.migration_cloud.views_tenant_upload import TenantMigrationReviewView
from apps.schools.models import School, SchoolMembership

_MOCK_REVERSE = mock.patch(
    "apps.migration_cloud.views_tenant_upload._connector_reverse",
    side_effect=lambda request, name, **kwargs: f"/mock/{name}/",
)


class BundleNeedsReimportTests(SimpleTestCase):
    def test_staff_applied_as_custom_fields(self):
        bundle = mock.Mock(spec=MigrationBundle)
        bundle.status = BundleStatus.APPLIED
        bundle.discovery_summary = {
            "per_artifact_domain": {
                "telephone.xlsx": {"domain": "custom_fields"},
            }
        }
        art = mock.Mock()
        art.quarantined = False
        art.assigned_domain = "staff"
        art.path_within_bundle = "telephone.xlsx"
        art.filename = "telephone.xlsx"
        bundle.artifacts.filter.return_value = [art]
        with mock.patch(
            "apps.migration_cloud.catalog_preflight.assess_bundle_catalog_routing",
            return_value={"artifacts": []},
        ):
            self.assertTrue(bundle_needs_reimport_after_retag(bundle))


class RetagReimportServiceTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Reimport {uid}",
            slug=f"reimport-{uid}",
            subdomain=f"ri{uid}",
            is_active=True,
        )
        self.bundle = MigrationBundle.objects.create(
            school=self.school,
            status=BundleStatus.APPLIED,
            idempotency_key=f"reimport-{uuid.uuid4().hex[:16]}",
            discovery_summary={"per_artifact_domain": {}},
        )

    def test_force_reimport_when_not_repairable(self):
        with (
            mock.patch(
                "apps.migration_cloud.retag_reimport.apply_catalog_retags",
                return_value=1,
            ),
            mock.patch("apps.migration_cloud.retag_reimport.refresh_inference"),
            mock.patch(
                "apps.migration_cloud.retag_reimport.repair_readiness",
                return_value=mock.Mock(repairable=False, reason="applied", blockers=[]),
            ),
            mock.patch(
                "apps.migration_cloud.retag_reimport.force_reimport_applied_bundle",
                return_value=mock.Mock(ok=True, message="queued", blockers=[]),
            ) as force,
        ):
            result = retag_and_reimport_bundle(self.bundle, off_http=True)
        force.assert_called_once()
        self.assertTrue(result.ok)


class StudentPlacementBackfillTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Placement {uid}",
            slug=f"place-{uid}",
            subdomain=f"pl{uid}",
            is_active=True,
        )

    def test_class_label_from_custom_attributes(self):
        from apps.people.models import StudentProfile

        student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Lovelace",
            custom_attributes={"class_source": "Form One"},
        )
        self.assertEqual(_class_label_for_student(student), "Form One")

    def test_backfill_invokes_link_for_unplaced_student(self):
        from apps.people.models import StudentProfile

        StudentProfile.objects.create(
            school=self.school,
            first_name="Grace",
            last_name="Hopper",
            custom_attributes={"class_source": "Form One"},
        )
        with mock.patch(
            "apps.migration_cloud.landers.student_lander._link_student_classroom",
        ) as link:
            summary = backfill_student_classrooms_for_school(self.school, dry_run=False)
        link.assert_called_once()
        self.assertEqual(summary["examined"], 1)
        self.assertEqual(summary["skipped"], 1)


class BundleReviewRetagUiTests(TestCase):
    def setUp(self):
        slug = f"retag-ui-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name="Retag UI School",
            slug=slug,
            subdomain=slug,
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"retag-ui-{uuid.uuid4().hex[:8]}",
            password="x",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.bundle = MigrationBundle.objects.create(
            school=self.school,
            label="mis-tagged-staff",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"retag-ui-{uuid.uuid4().hex}",
            status=BundleStatus.APPLIED,
            discovery_summary={
                "per_artifact_domain": {
                    "telephone.xlsx": {"domain": "custom_fields"},
                }
            },
        )
        MigrationArtifact.objects.create(
            bundle=self.bundle,
            filename="telephone.xlsx",
            path_within_bundle="telephone.xlsx",
            assigned_domain="staff",
            quarantined=False,
        )
        self.factory = RequestFactory()

    def _get_review(self):
        request = self.factory.get(
            "/school/setup/migration-cloud/bundle/review/",
            HTTP_SEC_FETCH_DEST="document",
        )
        request.user = self.admin
        request.school = self.school
        request.session = {}
        request._messages = FallbackStorage(request)
        return TenantMigrationReviewView.as_view()(request, bundle_id=self.bundle.pk)

    @_MOCK_REVERSE
    def test_reimport_banner_emits_post_action(self, _reverse):
        response = self._get_review()
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('value="retag_reimport"', html)
        self.assertIn("Record types were corrected but data has not been re-imported yet", html)

    @_MOCK_REVERSE
    def test_post_import_closure_button_when_graph_incomplete(self, _reverse):
        readiness = mock.Mock(
            ready_for_grades=False,
            ready_for_timetable_view=True,
        )
        with mock.patch(
            "apps.migration_cloud.views_tenant_upload._build_teaching_graph_readiness",
            return_value=readiness,
        ):
            response = self._get_review()
        html = response.content.decode()
        self.assertIn('value="post_import_closure"', html)
        self.assertIn("Connect classrooms, enrollments, and teaching grid", html)
