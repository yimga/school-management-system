"""Zero-touch engine wave — review-open autopilot, vendor templates, API parity (2026-08-28)."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.automation.models import MigrationQuarantineRecord, MigrationRun
from apps.automation.quarantine_services import mark_repaired
from apps.migration_cloud.api.viewsets import BundleViewSet
from apps.migration_cloud.auto_remediate import auto_remediate_on_review_open
from apps.migration_cloud.landers._helpers import row_is_pdf_noise_hold
from apps.migration_cloud.mapping_template_registry import (
    VENDOR_MAPPING_TEMPLATE_BUILDERS,
    build_blackbaud_mapping_template,
    build_mapping_template_from_file_map,
)
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.views import maybe_autopilot_held_review
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class VendorTemplateRegistryWaveTests(TestCase):
    def test_all_major_vendors_have_template_builders(self):
        expected = {
            "powerschool",
            "blackbaud",
            "veracross",
            "alma",
            "facts",
            "skyward",
            "oneroster_csv",
        }
        self.assertTrue(expected.issubset(VENDOR_MAPPING_TEMPLATE_BUILDERS.keys()))

    def test_seed_profiles_include_alma_facts_skyward(self):
        from apps.migration_cloud.management.commands.seed_migration_connector_profiles import (
            PROFILES,
        )

        keys = {row["key"] for row in PROFILES}
        self.assertTrue({"alma", "facts", "skyward"}.issubset(keys))

    def test_facts_template_includes_courses_csv(self):
        from apps.migration_cloud.mapping_template_registry import build_facts_mapping_template

        template = build_facts_mapping_template()
        self.assertIn("Courses.csv", template["by_artifact"])

    def test_blackbaud_template_has_students_csv(self):
        template = build_blackbaud_mapping_template()
        keys = {k.lower(): k for k in template["by_artifact"]}
        self.assertIn("students.csv", keys)
        artifact_key = keys["students.csv"]
        self.assertIn(
            "external_id",
            template["by_artifact"][artifact_key]["canonical_mappings"].values(),
        )

    def test_build_from_file_map_matches_powerschool_shape(self):
        sample = {"students.csv": ("students", {"A": "external_id"})}
        built = build_mapping_template_from_file_map(sample)
        self.assertEqual(built["by_domain"]["students"]["A"], "external_id")


class ReviewOpenAutopilotTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Autopilot School",
            slug="autopilot-school",
            subdomain="autopilot-school",
            is_active=True,
            is_approved=True,
            country_code="CM",
            settings={},
        )
        self.admin = User.objects.create_user(
            username="autopilot-admin",
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
            label="autopilot",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="autopilot-b1",
            status=BundleStatus.APPLIED,
            school=self.school,
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )

    def _plant_pdf_noise_row(self) -> MigrationQuarantineRecord:
        row = {"page": "2", "line": "stat summary"}
        self.assertTrue(
            row_is_pdf_noise_hold(
                "academics",
                row,
                "school_stats_2026-01-18.pdf",
            )
        )
        return MigrationQuarantineRecord.objects.create(
            school=self.school,
            migration_run=self.run,
            domain="academics",
            row_index=88,
            issue_class="missing_required",
            payload={
                "error": "missing subject",
                "artifact": "school_stats_2026-01-18.pdf",
                "source_row": row,
            },
        )

    def test_auto_remediate_on_review_open_dismisses_pdf_noise(self):
        self._plant_pdf_noise_row()
        result = auto_remediate_on_review_open(self.bundle, user=self.admin)
        self.assertGreaterEqual(int(result.get("pdf_noise_dismissed") or 0), 1)
        self.assertEqual(
            MigrationQuarantineRecord.objects.filter(
                migration_run=self.run,
                status=MigrationQuarantineRecord.Status.PENDING,
            ).count(),
            0,
        )

    def test_maybe_autopilot_redirects_when_rows_close(self):
        self._plant_pdf_noise_row()
        request = RequestFactory().get("/held/")
        request.user = self.admin
        response = maybe_autopilot_held_review(request, self.bundle, user=self.admin)
        self.assertIsNotNone(response)
        self.assertIn("autopilot_done=", response.url)

    def test_reopen_auto_restores_auto_dismissed_row(self):
        rec = self._plant_pdf_noise_row()
        mark_repaired(rec, {"auto_dismissed": True, "auto_pdf_noise": True})
        from apps.migration_cloud.quarantine_resolution import apply_quarantine_action

        outcome = apply_quarantine_action(
            bundle=self.bundle,
            user=self.admin,
            action="reopen_auto",
            record_ids=[rec.pk],
        )
        self.assertEqual(outcome.get("updated"), 1)
        rec.refresh_from_db()
        self.assertEqual(rec.status, MigrationQuarantineRecord.Status.PENDING)


class QuarantineAPIParityTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.school = School.objects.create(
            name="API School",
            slug="api-school",
            subdomain="api-school",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username="api-admin",
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
            label="api",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="api-b1",
            status=BundleStatus.APPLIED,
            school=self.school,
            reconciliation_status="PENDING_HUMAN",
        )

    def test_quarantine_list_includes_closure_fields(self):
        view = BundleViewSet.as_view({"get": "quarantine_list"})
        request = self.factory.get(
            f"/api/v1/bundles/{self.bundle.pk}/quarantine/",
        )
        force_authenticate(request, user=self.admin)
        request.school = self.school
        request.public_host_kind = "tenant"
        response = view(request, pk=self.bundle.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("reconciliation_status", response.data)
        self.assertIn("pdf_noise_candidates", response.data)
        self.assertIn("page", response.data)

    def test_run_autopilot_action_via_api(self):
        view = BundleViewSet.as_view({"post": "quarantine_resolve"})
        request = self.factory.post(
            f"/api/v1/bundles/{self.bundle.pk}/quarantine/resolve/",
            {"action": "run_autopilot"},
            format="json",
        )
        force_authenticate(request, user=self.admin)
        request.school = self.school
        request.public_host_kind = "tenant"
        with mock.patch(
            "apps.migration_cloud.auto_remediate.auto_remediate_on_review_open",
            return_value={"auto_resolved_total": 0, "pending_after": 0},
        ):
            response = view(request, pk=self.bundle.pk)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data.get("ok"), response.data)
        self.assertEqual(response.data.get("action"), "run_autopilot")
