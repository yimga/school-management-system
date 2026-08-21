"""Tenant schema readiness gate — blocks apply/repair when tenant columns drift."""

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.migration_cloud.tenant_schema_readiness import (
    TenantSchemaReadiness,
    assess_tenant_schema_readiness,
    format_schema_drift_reason,
    post_apply_step_error,
    schema_drift_summary_patch,
)


class TenantSchemaReadinessTests(SimpleTestCase):
    def test_format_reason_lists_missing_columns(self):
        readiness = TenantSchemaReadiness(
            schema_name="tenant_gilead",
            ready=False,
            missing_labels=(
                "academics_academicyear.is_soft_closed",
                "people_studentprofile.search_index",
            ),
        )
        reason = format_schema_drift_reason(readiness)
        self.assertIn("is_soft_closed", reason)
        self.assertIn("search_index", reason)
        self.assertIn("tenant migrations", reason.lower())

    def test_summary_patch_carries_drift_metadata(self):
        readiness = TenantSchemaReadiness(
            schema_name="tenant_gilead",
            ready=False,
            missing_labels=("people_teacherprofile.merged_into_id",),
            repair_attempted=True,
        )
        patch = schema_drift_summary_patch(readiness)
        self.assertIn("tenant_schema_drift", patch)
        self.assertEqual(
            patch["tenant_schema_drift"]["missing_columns"],
            ["people_teacherprofile.merged_into_id"],
        )

    def test_post_apply_step_error_flags_programming_error(self):
        from django.db.utils import ProgrammingError

        exc = ProgrammingError('column "search_index" does not exist')
        payload = post_apply_step_error(exc)
        self.assertEqual(payload["error"], "tenant_schema_drift")

    @mock.patch("django.db.connection")
    @mock.patch("django_tenants.utils.schema_context")
    @mock.patch("apps.schools.tenant_schema_guard.missing_tenant_columns")
    @mock.patch("apps.schools.tenant_schema_guard.run_tenant_column_repairs")
    @mock.patch("apps.schools.tenant_schema_guard.ensure_models_columns")
    def test_assess_repairs_then_rechecks(
        self,
        ensure_models_columns,
        run_repairs,
        missing_columns,
        schema_context,
        db_connection,
    ):
        schema_context.return_value.__enter__ = mock.Mock(return_value=None)
        schema_context.return_value.__exit__ = mock.Mock(return_value=False)
        db_connection.schema_editor.return_value.__enter__ = mock.Mock(
            return_value=mock.Mock()
        )
        db_connection.schema_editor.return_value.__exit__ = mock.Mock(return_value=False)
        missing_columns.side_effect = [
            [
                (
                    "people",
                    "StudentProfile",
                    "people_studentprofile",
                    "search_index",
                )
            ],
            [],
        ]
        ensure_models_columns.return_value = ["people_studentprofile.search_index"]

        result = assess_tenant_schema_readiness("tenant_gilead", attempt_repair=True)

        self.assertTrue(result.ready)
        run_repairs.assert_called_once()
        ensure_models_columns.assert_called_once()
        self.assertIn("people_studentprofile.search_index", result.repaired_labels)

    @mock.patch("django.db.connection")
    @mock.patch("django_tenants.utils.schema_context")
    @mock.patch("apps.schools.tenant_schema_guard.missing_tenant_columns")
    @mock.patch("apps.schools.tenant_schema_guard.run_tenant_column_repairs")
    @mock.patch("apps.schools.tenant_schema_guard.ensure_models_columns")
    def test_assess_still_not_ready_when_repair_insufficient(
        self,
        ensure_models_columns,
        run_repairs,
        missing_columns,
        schema_context,
        db_connection,
    ):
        schema_context.return_value.__enter__ = mock.Mock(return_value=None)
        schema_context.return_value.__exit__ = mock.Mock(return_value=False)
        db_connection.schema_editor.return_value.__enter__ = mock.Mock(
            return_value=mock.Mock()
        )
        db_connection.schema_editor.return_value.__exit__ = mock.Mock(return_value=False)
        ensure_models_columns.return_value = []
        drift = [
            (
                "academics",
                "AcademicYear",
                "academics_academicyear",
                "is_soft_closed",
            )
        ]
        missing_columns.side_effect = [drift, drift]

        result = assess_tenant_schema_readiness("tenant_gilead", attempt_repair=True)

        self.assertFalse(result.ready)
        self.assertEqual(
            result.missing_labels,
            ("academics_academicyear.is_soft_closed",),
        )


class RepairReadinessSchemaGateTests(SimpleTestCase):
    @mock.patch("apps.migration_cloud.tenant_schema_readiness.assess_tenant_schema_readiness")
    @mock.patch("apps.migration_cloud.schema_binding.ensure_bundle_schema_name")
    @mock.patch("apps.migration_cloud.repair._financial_guardrail_locked", return_value=False)
    @mock.patch("apps.migration_cloud.repair._has_unresolved_issues", return_value=True)
    @mock.patch("apps.migration_cloud.repair._has_finance", return_value=False)
    def test_repair_blocked_on_schema_drift(
        self,
        _finance,
        _issues,
        _guardrail,
        ensure_schema,
        assess,
    ):
        from apps.migration_cloud.models import BundleStatus
        from apps.migration_cloud.repair import repair_readiness

        bundle = SimpleNamespace(
            status=BundleStatus.APPLIED,
            apply_atomic=False,
            mapping_summary={"apply_totals": {"quarantined": 442}},
            reconciliation_summary={},
            size_summary={},
        )
        ensure_schema.return_value = "tenant_gilead"
        assess.return_value = TenantSchemaReadiness(
            schema_name="tenant_gilead",
            ready=False,
            missing_labels=("people_studentprofile.search_index",),
        )

        readiness = repair_readiness(bundle)

        self.assertFalse(readiness.repairable)
        self.assertIn("tenant_schema_drift", readiness.blockers)
        self.assertIn("search_index", readiness.reason)


class ReadinessForBundleTests(SimpleTestCase):
    def test_readiness_for_bundle_uses_cached_drift_from_size_summary(self):
        from apps.migration_cloud.tenant_schema_readiness import readiness_for_bundle

        bundle = SimpleNamespace(
            size_summary={
                "tenant_schema_drift": {
                    "missing_columns": [
                        "people_teacherprofile.merged_into_id",
                        "people_studentprofile.search_index",
                    ],
                    "repaired_columns": [],
                    "repair_attempted": True,
                }
            },
        )
        with mock.patch(
            "apps.migration_cloud.schema_binding.ensure_bundle_schema_name",
            return_value="tenant_gilead",
        ):
            readiness = readiness_for_bundle(bundle, attempt_repair=False)

        self.assertIsNotNone(readiness)
        self.assertFalse(readiness.ready)
        self.assertEqual(len(readiness.missing_labels), 2)
        self.assertTrue(readiness.repair_attempted)
