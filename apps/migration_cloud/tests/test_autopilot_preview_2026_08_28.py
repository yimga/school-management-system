"""The autopilot preview must agree with the autopilot (2026-08-28).

A preview of a rules engine is a second implementation of that engine, and a
second implementation drifts. What keeps this one honest is not that it shares
code -- it is ``test_preview_agrees_with_the_real_pass``, which runs the preview,
then runs the real thing on the same bundle, and requires every ``auto_close``
prediction to have actually happened.

The preview also has to write nothing. It is meant to be run against production
to answer "will these rows clear?", and an answer that changes the thing it is
measuring is not an answer.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.automation.models import MigrationQuarantineRecord, MigrationRun
from apps.migration_cloud.auto_remediate import (
    auto_remediate_on_review_open,
    preview_autopilot_decisions,
)
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class AutopilotPreviewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Preview School",
            slug="preview-school",
            subdomain="preview-school",
            is_active=True,
            is_approved=True,
        )
        self.admin = User.objects.create_user(
            username="preview-admin", password="x", role=User.Role.ADMIN
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.bundle = MigrationBundle.objects.create(
            label="preview",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="preview-b1",
            status=BundleStatus.APPLIED,
            school=self.school,
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )

    def _hold(self, *, domain, issue_class, row, artifact="x.csv", reason_source="declared"):
        return MigrationQuarantineRecord.objects.create(
            school=self.school,
            migration_run=self.run,
            domain=domain,
            row_index=1,
            issue_class=issue_class,
            payload={
                "error": "held",
                "artifact": artifact,
                "source_row": row,
                "reason_source": reason_source,
            },
        )

    def _populate(self):
        """One row per outcome the preview can report."""
        self.noise = self._hold(
            domain="academics",
            issue_class="missing_required",
            row={"page": "2", "line": "stat summary"},
            artifact="school_stats_2026-01-18.pdf",
        )
        self.informational = self._hold(
            domain="students", issue_class="source_deletion", row={"external_id": "S-9"}
        )
        self.money = self._hold(
            domain="finance",
            issue_class="missing_required",
            row={"invoice_number": "INV-1", "amount": "450000"},
            artifact="fees.pdf",
        )
        self.enrichable = self._hold(
            domain="academics",
            issue_class="missing_required",
            row={"subject_code": "MATH"},
            artifact="subjects.csv",
        )
        self.unreplayable = self._hold(
            domain="students", issue_class="invalid_ref", row={}
        )

    def test_each_class_lands_in_the_outcome_it_should(self):
        self._populate()
        by_id = {r["record_id"]: r for r in preview_autopilot_decisions(self.bundle)["rows"]}

        self.assertEqual(by_id[self.noise.pk]["outcome"], "auto_close")
        self.assertEqual(by_id[self.informational.pk]["outcome"], "auto_close")
        self.assertEqual(by_id[self.enrichable.pk]["outcome"], "auto_replay")
        self.assertEqual(
            by_id[self.money.pk]["outcome"],
            "needs_person",
            "a finance row off a PDF carrying real fields is not page furniture",
        )
        self.assertEqual(
            by_id[self.unreplayable.pk]["outcome"],
            "needs_person",
            "a row whose source was never kept cannot be replayed",
        )

    def test_a_replay_is_never_reported_as_a_certain_close(self):
        # The whole point: an attempted re-land can fail and leave the row held.
        # Folding these into "will clear" is the over-claim the preview exists
        # to stop, so the two buckets must stay separate.
        self._populate()
        report = preview_autopilot_decisions(self.bundle)
        self.assertEqual(report["counts"]["auto_close"], 2)
        self.assertEqual(report["counts"]["auto_replay"], 1)
        self.assertEqual(report["counts"]["needs_person"], 2)

    def test_the_preview_writes_nothing(self):
        self._populate()
        before = list(
            MigrationQuarantineRecord.objects.filter(migration_run=self.run)
            .order_by("pk")
            .values_list("pk", "status")
        )
        bundle_before = (self.bundle.mapping_summary, self.bundle.reconciliation_status)

        preview_autopilot_decisions(self.bundle)

        self.bundle.refresh_from_db()
        after = list(
            MigrationQuarantineRecord.objects.filter(migration_run=self.run)
            .order_by("pk")
            .values_list("pk", "status")
        )
        self.assertEqual(before, after, "the preview resolved a row")
        self.assertEqual(
            bundle_before,
            (self.bundle.mapping_summary, self.bundle.reconciliation_status),
            "the preview wrote to the bundle",
        )

    def test_preview_agrees_with_the_real_pass(self):
        """The anti-drift seal. Predict, then run, then compare."""
        self._populate()
        predicted = preview_autopilot_decisions(self.bundle)
        will_close = {
            r["record_id"] for r in predicted["rows"] if r["outcome"] == "auto_close"
        }
        will_stay = {
            r["record_id"] for r in predicted["rows"] if r["outcome"] == "needs_person"
        }
        self.assertTrue(will_close and will_stay, "fixture must exercise both")

        auto_remediate_on_review_open(self.bundle, user=self.admin)

        still_pending = set(
            MigrationQuarantineRecord.objects.filter(
                migration_run=self.run,
                status=MigrationQuarantineRecord.Status.PENDING,
            ).values_list("pk", flat=True)
        )
        self.assertFalse(
            will_close & still_pending,
            "the preview promised these would close and they did not",
        )
        self.assertEqual(
            will_stay & still_pending,
            will_stay,
            "the preview said these need a person and autopilot took them anyway",
        )

    def test_it_counts_decisions_resting_on_a_guessed_class(self):
        self._hold(
            domain="academics",
            issue_class="missing_required",
            row={"page": "2"},
            artifact="stats.pdf",
            reason_source="fallback",
        )
        report = preview_autopilot_decisions(self.bundle)
        self.assertEqual(report["auto_decided_on_guessed_class"], 1)

    def test_the_command_runs_and_stays_read_only(self):
        self._populate()
        call_command("preview_quarantine_autopilot", "--bundle-id", str(self.bundle.pk))
        self.assertEqual(
            MigrationQuarantineRecord.objects.filter(
                migration_run=self.run,
                status=MigrationQuarantineRecord.Status.PENDING,
            ).count(),
            5,
        )

    def test_an_empty_queue_reports_nothing_to_do(self):
        report = preview_autopilot_decisions(self.bundle)
        self.assertEqual(report["pending"], 0)
        self.assertEqual(report["counts"]["auto_close"], 0)
