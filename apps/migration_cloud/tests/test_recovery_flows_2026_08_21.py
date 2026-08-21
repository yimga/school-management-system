"""Recovery hub — wedged apply, bulk quarantine clear, abandon, remediator matrix."""

from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.automation.models import MigrationQuarantineRecord, MigrationRun
from apps.migration_cloud.live_import_attention import compose_live_import, remediator_for
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.quarantine_resolution import apply_quarantine_action, pending_quarantine_count
from apps.migration_cloud.repair import repair_readiness, tenant_apply_stuck
from apps.schools.models import School


class TenantApplyStuckTests(SimpleTestCase):
    def test_tenant_apply_stuck_false_for_reconciled(self):
        bundle = MigrationBundle(status=BundleStatus.RECONCILED)
        with patch("apps.migration_cloud.repair._apply_rows", return_value=[]):
            self.assertFalse(tenant_apply_stuck(bundle))


class RemediatorMatrixTests(SimpleTestCase):
    def test_held_remediator_offers_clear_queue(self):
        bundle = MigrationBundle(status=BundleStatus.APPLIED)
        payload = remediator_for(bundle, issues=42, flight={"in_flight": False})
        self.assertIsNotNone(payload)
        self.assertTrue(payload.get("show_clear_queue"))
        self.assertTrue(payload.get("held_review"))

    def test_aborted_remediator_points_to_start_fresh(self):
        bundle = MigrationBundle(status=BundleStatus.ABORTED)
        payload = remediator_for(bundle, issues=0, flight={})
        self.assertIsNotNone(payload)
        self.assertTrue(payload.get("show_start_fresh"))


class BulkQuarantineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Recovery School", subdomain="recovery-school")
        self.bundle = MigrationBundle.objects.create(
            label="recovery-bundle",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="recovery-bundle",
            status=BundleStatus.APPLIED,
            school=self.school,
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )

    def _record(self, issue_class: str, row_index: int) -> MigrationQuarantineRecord:
        return MigrationQuarantineRecord.objects.create(
            school=self.school,
            migration_run=self.run,
            domain="students",
            row_index=row_index,
            issue_class=issue_class,
            payload={"error": "held", "source_row": {"full_name": f"Row {row_index}"}},
        )

    def test_clear_queue_empties_mixed_pending(self):
        self._record("source_deletion", 1)
        self._record("missing_required", 2)
        self._record("invalid_ref", 3)
        self.assertEqual(pending_quarantine_count(self.bundle), 3)
        outcome = apply_quarantine_action(
            bundle=self.bundle,
            user=None,
            action="clear_queue",
            note="Bulk clear test",
        )
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["pending_remaining"], 0)
        self.assertEqual(pending_quarantine_count(self.bundle), 0)

    def test_waive_all_pending(self):
        self._record("lander_error", 10)
        self._record("lander_error", 11)
        outcome = apply_quarantine_action(
            bundle=self.bundle,
            user=None,
            action="waive_all_pending",
            note="Skip all",
        )
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["updated"], 2)
        self.assertEqual(pending_quarantine_count(self.bundle), 0)


class RepairReadinessWedgedTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Wedge School", subdomain="wedge-school")
        self.bundle = MigrationBundle.objects.create(
            label="wedge",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="wedge",
            status=BundleStatus.APPLYING,
            school=self.school,
            updated_at=timezone.now() - timedelta(minutes=10),
        )

    def test_applying_wedged_is_repairable(self):
        with patch("apps.migration_cloud.repair.tenant_apply_stuck", return_value=True):
            with patch("apps.migration_cloud.repair.live_apply_in_flight", return_value=False):
                with patch(
                    "apps.migration_cloud.tenant_schema_readiness.assess_tenant_schema_readiness",
                    return_value=type("R", (), {"ready": True, "missing_labels": []})(),
                ):
                    with patch(
                        "apps.migration_cloud.schema_binding.ensure_bundle_schema_name",
                        return_value="",
                    ):
                        readiness = repair_readiness(self.bundle)
        self.assertTrue(readiness.repairable)


class ComposeLiveImportAttentionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Live School", subdomain="live-school")
        self.bundle = MigrationBundle.objects.create(
            label="live",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="live",
            status=BundleStatus.APPLIED,
            school=self.school,
            mapping_summary={"apply_totals": {"created": 1, "updated": 0, "quarantined": 2}},
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )
        MigrationQuarantineRecord.objects.create(
            school=self.school,
            migration_run=self.run,
            domain="students",
            row_index=1,
            issue_class="duplicate",
            payload={"error": "dup"},
        )

    def test_needs_attention_when_held_rows(self):
        flight = {"in_flight": False, "phase": "", "stuck": False}
        live = compose_live_import(self.bundle, flight=flight)
        self.assertTrue(live["issues_open"])
        self.assertGreater(live["issue_count"], 0)
