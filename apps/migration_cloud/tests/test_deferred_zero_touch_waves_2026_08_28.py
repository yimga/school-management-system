"""Deferred zero-touch gaps — vendor template registry, guardrail closure, cutover gate (2026-08-28)."""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.migration_cloud.auto_remediate import sync_reconciliation_closure
from apps.migration_cloud.guardrails import compute_observed_totals, evaluate_expected_totals
from apps.migration_cloud.mapping_template_registry import (
    load_profile_template_entry,
    persist_confirmed_connector_mappings,
)
from apps.migration_cloud.mapper import ColumnMapping
from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationBundle,
    MigrationIdMapping,
    ReconciliationClosureStatus,
)
from apps.migration_cloud.models_connectors import (
    ConnectionMethod,
    FieldMappingStatus,
    MigrationConnectorProfile,
    MigrationFieldMapping,
    MigrationSourceConnection,
)
from apps.migration_cloud.models_cutover import (
    CutoverRunbook,
    CutoverRunbookStatus,
    cutover_signoff_pending_for_bundle,
)
from apps.migration_cloud.pipeline import _apply_accelerator_then_map
from apps.migration_cloud.reconciliation import reconcile_bundle
from apps.schools.models import School


class MappingTemplateRegistryTests(TestCase):
    def setUp(self):
        self.profile = MigrationConnectorProfile.objects.create(
            key="powerschool",
            display_name="PowerSchool",
            mapping_template={
                "by_artifact": {
                    "students.csv": {
                        "domain": "students",
                        "canonical_mappings": {
                            "Student_Number": "external_id",
                            "First_Name": "first_name",
                        },
                    }
                }
            },
        )

    def test_load_profile_template_by_artifact(self):
        entry = load_profile_template_entry(
            profile_key="powerschool",
            artifact_path="exports/students.csv",
            domain="students",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry["canonical_mappings"]["Student_Number"], "external_id")

    def test_apply_profile_template_before_universal_mapper(self):
        school = School.objects.create(
            name="Tpl School",
            slug="tpl-school",
            subdomain="tpl-school",
            is_active=True,
            is_approved=True,
            country_code="CM",
            settings={},
        )
        bundle = MigrationBundle.objects.create(
            label="tpl",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="tpl-1",
            status=BundleStatus.PROFILED,
            school=school,
            discovery_summary={"source": {"chosen": "powerschool"}},
        )
        artifact = mock.Mock()
        artifact.path_within_bundle = "students.csv"
        artifact.filename = "students.csv"
        artifact.profile = {
            "columns": [
                {"name": "Student_Number"},
                {"name": "First_Name"},
                {"name": "Custom_Field"},
            ]
        }

        universal = [
            ColumnMapping(
                source_column="Custom_Field",
                canonical_field="custom_fields.custom_field",
                domain="students",
                confidence=0.5,
                method="token",
                transformer=None,
                transformer_options={},
                reasoning="token",
            )
        ]
        with mock.patch(
            "apps.migration_cloud.pipeline.map_artifact",
            return_value=universal,
        ):
            mappings = _apply_accelerator_then_map(
                artifact=artifact,
                domain="students",
                contract=None,
                bundle=bundle,
            )
        by_source = {m.source_column: m for m in mappings}
        self.assertEqual(by_source["Student_Number"].method, "profile_template")
        self.assertEqual(by_source["Student_Number"].canonical_field, "external_id")
        self.assertEqual(by_source["Custom_Field"].method, "token")

    def test_persist_confirmed_connector_mappings(self):
        school = School.objects.create(
            name="Conn School",
            slug="conn-school",
            subdomain="conn-school",
            is_active=True,
            is_approved=True,
            country_code="CM",
            settings={},
        )
        connection = MigrationSourceConnection.objects.create(
            school=school,
            connector_profile=self.profile,
            source_platform_type="powerschool",
            connection_method=ConnectionMethod.FILE_EXPORT,
        )
        MigrationFieldMapping.objects.create(
            school=school,
            source_connection=connection,
            source_entity="students",
            source_field="Student_Number",
            destination_model="students",
            destination_field="external_id",
            status=FieldMappingStatus.CONFIRMED,
        )
        self.assertTrue(
            persist_confirmed_connector_mappings(
                connection=connection,
                entity_type="students",
            )
        )
        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.mapping_template["by_domain"]["students"]["Student_Number"],
            "external_id",
        )


class GuardrailClosureTests(SimpleTestCase):
    def test_sync_blocked_when_financial_guardrail_failed(self):
        bundle = mock.Mock()
        bundle.status = BundleStatus.FAILED
        bundle.pk = 1
        bundle.size_summary = {"financial_guardrail_failed": True}
        bundle.mapping_summary = {}
        bundle.reconciliation_summary = {}
        bundle.reconciliation_status = ""
        with mock.patch(
            "apps.migration_cloud.auto_remediate.pending_quarantine_count",
            return_value=0,
        ), mock.patch(
            "apps.migration_cloud.models_cutover.cutover_signoff_pending_for_bundle",
            return_value=False,
        ):
            status = sync_reconciliation_closure(bundle)
        self.assertEqual(status, ReconciliationClosureStatus.BLOCKED)
        self.assertTrue(bundle.reconciliation_summary["closure"]["financial_guardrail_failed"])

    def test_sync_pending_human_when_cutover_signoff_pending(self):
        bundle = mock.Mock()
        bundle.status = BundleStatus.APPLIED
        bundle.size_summary = {}
        bundle.mapping_summary = {}
        bundle.reconciliation_summary = {}
        bundle.reconciliation_status = ""
        bundle.pk = 42
        with mock.patch(
            "apps.migration_cloud.auto_remediate.pending_quarantine_count",
            return_value=0,
        ), mock.patch(
            "apps.migration_cloud.models_cutover.cutover_signoff_pending_for_bundle",
            return_value=True,
        ):
            status = sync_reconciliation_closure(bundle)
        self.assertEqual(status, ReconciliationClosureStatus.PENDING_HUMAN)
        self.assertTrue(bundle.reconciliation_summary["closure"]["cutover_signoff_pending"])


class CutoverSignoffGateTests(TestCase):
    def test_cutover_signoff_pending_for_real_bundle(self):
        school = School.objects.create(
            name="Cut School",
            slug="cut-school",
            subdomain="cut-school",
            is_active=True,
            is_approved=True,
            country_code="CM",
            settings={},
        )
        bundle = MigrationBundle.objects.create(
            label="live",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="cut-1",
            status=BundleStatus.APPLIED,
            school=school,
            reconciliation_summary={"overall_parity_pct": 100},
        )
        CutoverRunbook.objects.create(
            school=school,
            real_bundle=bundle,
            status=CutoverRunbookStatus.EXECUTED,
        )
        self.assertTrue(cutover_signoff_pending_for_bundle(bundle))

    def test_reconcile_skips_reconciled_when_signoff_pending(self):
        school = School.objects.create(
            name="Cut School 2",
            slug="cut-school-2",
            subdomain="cut-school-2",
            is_active=True,
            is_approved=True,
            country_code="CM",
            settings={},
        )
        bundle = MigrationBundle.objects.create(
            label="live2",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="cut-2",
            status=BundleStatus.APPLIED,
            school=school,
            reconciliation_summary={},
        )
        CutoverRunbook.objects.create(
            school=school,
            real_bundle=bundle,
            status=CutoverRunbookStatus.EXECUTED,
        )
        report = reconcile_bundle(bundle_id=bundle.pk)
        bundle.refresh_from_db()
        self.assertEqual(bundle.status, BundleStatus.APPLIED)
        self.assertTrue(any("Cutover sign-off pending" in n for n in report.notes))


class PayrollGuardrailTotalsTests(TestCase):
    def test_payroll_aggregate_keys_from_bundle_scoped_rows(self):
        school = School.objects.create(
            name="Pay School",
            slug="pay-school",
            subdomain="pay-school",
            is_active=True,
            is_approved=True,
            country_code="CM",
            settings={},
        )
        bundle = MigrationBundle.objects.create(
            label="pay",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="pay-1",
            status=BundleStatus.APPLIED,
            school=school,
            expected_totals={
                "payroll.row_count": "2",
                "payroll.gross_total_amount": "7000.00",
                "payroll.net_total_amount": "5600.00",
            },
        )
        for key, gross, net in (
            ("T1:2025-09", "4000.00", "3200.00"),
            ("T2:2025-09", "3000.00", "2400.00"),
        ):
            MigrationIdMapping.objects.create(
                bundle=bundle,
                school=school,
                domain="payroll",
                legacy_namespace="test",
                legacy_id=key,
                canonical_model="migration_cloud.bundle_scoped",
                canonical_pk=key,
            )
            try:
                from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
            except ImportError:
                self.skipTest("metadata app unavailable")
            DynamicFieldDefinition.objects.get_or_create(
                entity_type="payroll",
                field_key="record",
                school=school,
                defaults={"label": "Record", "data_type": "json"},
            )
            DynamicFieldValue.objects.update_or_create(
                school=school,
                entity_type="payroll",
                entity_id=key,
                field_key="record",
                defaults={
                    "value_json": {
                        "v": {
                            "record": {
                                "gross_amount": gross,
                                "net_amount": net,
                            }
                        }
                    }
                },
            )
        observed = compute_observed_totals(bundle=bundle)
        report = evaluate_expected_totals(bundle=bundle, observed=observed)
        self.assertTrue(report.ok)
        self.assertEqual(observed["payroll.row_count"], "2")
        self.assertEqual(observed["payroll.gross_total_amount"], "7000.00")
