"""Quarantine resolution workspace — guidance + operator actions."""

from django.test import SimpleTestCase, TestCase

from apps.automation.models import MigrationQuarantineRecord, MigrationRun
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.quarantine_resolution import (
    apply_quarantine_action,
    enrich_quarantine_row,
    infer_field_flags,
    pending_quarantine_count,
)
from apps.migration_cloud.repair import unresolved_issue_count
from apps.schools.models import School


class InferFieldFlagsTests(SimpleTestCase):
    def test_missing_required_flags_empty_admission(self):
        flags = infer_field_flags(
            "missing_required",
            "missing external_id",
            {"full_name": "Jane Doe"},
        )
        self.assertTrue(any(f["state"] == "missing" for f in flags))

    def test_invalid_ref_flags_class_confusion(self):
        flags = infer_field_flags(
            "invalid_ref",
            "no classroom for section Form Two",
            {"grade_level": "Form Two"},
        )
        self.assertTrue(any(f["state"] == "confused" for f in flags))


class QuarantineActionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Q School", subdomain="q-school")
        self.bundle = MigrationBundle.objects.create(
            label="q-bundle",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="q-bundle",
            status=BundleStatus.APPLIED,
            school=self.school,
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )
        self.record = MigrationQuarantineRecord.objects.create(
            school=self.school,
            migration_run=self.run,
            domain="students",
            row_index=3,
            issue_class="source_deletion",
            payload={"error": "held", "source_row": {"full_name": "X"}},
        )

    def test_dismiss_informational_clears_pending(self):
        outcome = apply_quarantine_action(
            bundle=self.bundle,
            user=None,
            action="dismiss_informational",
        )
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["updated"], 1)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, MigrationQuarantineRecord.Status.REPAIRED)
        self.assertEqual(pending_quarantine_count(self.bundle), 0)

    def test_unresolved_issue_count_uses_pending_rows(self):
        self.bundle.mapping_summary = {"apply_totals": {"quarantined": 99}}
        self.bundle.save(update_fields=["mapping_summary"])
        self.assertEqual(unresolved_issue_count(self.bundle), 1)

    def test_enrich_includes_tone_and_guidance(self):
        row = enrich_quarantine_row(self.record)
        self.assertEqual(row["tone"], "info")
        self.assertTrue(row["guidance_headline"])
        self.assertFalse(row["needs_action"])

    def test_waive_marks_repaired(self):
        self.record.issue_class = "missing_required"
        self.record.save(update_fields=["issue_class"])
        outcome = apply_quarantine_action(
            bundle=self.bundle,
            user=None,
            action="waive",
            record_ids=[self.record.pk],
            note="skip junk row",
        )
        self.assertEqual(outcome["updated"], 1)
        self.record.refresh_from_db()
        self.assertTrue(self.record.resolution_payload.get("operator_waive"))

    def test_dismiss_action_needed_without_note_applies_default(self):
        self.record.issue_class = "missing_required"
        self.record.save(update_fields=["issue_class"])
        outcome = apply_quarantine_action(
            bundle=self.bundle,
            user=None,
            action="dismiss",
            record_ids=[self.record.pk],
        )
        self.assertEqual(outcome["updated"], 1)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, MigrationQuarantineRecord.Status.REPAIRED)
        self.assertTrue(self.record.resolution_payload.get("operator_dismissed"))

    def test_dismiss_action_needed_with_note_succeeds(self):
        self.record.issue_class = "missing_required"
        self.record.save(update_fields=["issue_class"])
        outcome = apply_quarantine_action(
            bundle=self.bundle,
            user=None,
            action="dismiss",
            record_ids=[self.record.pk],
            note="operator override",
        )
        self.assertEqual(outcome["updated"], 1)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, MigrationQuarantineRecord.Status.REPAIRED)
