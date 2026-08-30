"""Unbounded work on a page open, found on live data (2026-08-30).

A state read of the production instance listed bundle 83 carrying **75,600**
pending quarantine rows. Two things in this module treated "however many there
are" as a budget:

* ``auto_remediate_on_review_open`` runs five queryset passes when the held-review
  page opens, and two of them WRITE (rows are re-landed). At 75,600 rows that
  request burns a worker until the proxy kills it, and a reload burns another.
  Worse than slow: a pass killed mid-flight leaves SOME rows closed and the rest
  held, and tells the operator nothing.
* ``preview_autopilot_decisions`` used ``.iterator()`` specifically so the
  queryset was not held in memory, then appended a dict per row and put it
  straight back. ``--json`` would then serialise all of it.

The counts stay exact in both cases. What is bounded is the WORK (the pass is
refused above a budget) and the per-row DETAIL (sampled, and the omission is
reported -- a truncated sample that reads as the whole set turns a partial answer
into a false complete one).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import MigrationQuarantineRecord, MigrationRun
from apps.migration_cloud.auto_remediate import (
    PREVIEW_ROW_SAMPLE_CAP,
    REVIEW_OPEN_ROW_BUDGET,
    auto_remediate_on_review_open,
    preview_autopilot_decisions,
)
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.schools.models import School

User = get_user_model()


class UnboundedWorkTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Budget School",
            slug="budget-school",
            subdomain="budget-school",
            is_active=True,
            is_approved=True,
        )
        self.bundle = MigrationBundle.objects.create(
            label="budget",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="budget-b1",
            status=BundleStatus.APPLIED,
            school=self.school,
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )

    def _holds(self, count):
        MigrationQuarantineRecord.objects.bulk_create(
            [
                MigrationQuarantineRecord(
                    school=self.school,
                    migration_run=self.run,
                    domain="academics",
                    row_index=i,
                    issue_class="missing_required",
                    payload={
                        "error": "held",
                        "artifact": "a.csv",
                        "source_row": {"n": str(i)},
                        "reason_source": "declared",
                    },
                    status=MigrationQuarantineRecord.Status.PENDING,
                )
                for i in range(count)
            ]
        )

    # ------------------------------------------------------- the page open --
    def test_a_page_open_refuses_a_pass_it_cannot_finish(self):
        self._holds(REVIEW_OPEN_ROW_BUDGET + 1)
        before = MigrationQuarantineRecord.objects.filter(
            status=MigrationQuarantineRecord.Status.PENDING
        ).count()

        results = auto_remediate_on_review_open(self.bundle)

        self.assertTrue(results.get("skipped_over_budget"))
        self.assertEqual(results["auto_resolved_total"], 0)
        self.assertEqual(results["row_budget"], REVIEW_OPEN_ROW_BUDGET)
        # Refused means refused: it must not have closed a partial slice.
        self.assertEqual(
            MigrationQuarantineRecord.objects.filter(
                status=MigrationQuarantineRecord.Status.PENDING
            ).count(),
            before,
        )

    def test_an_ordinary_bundle_is_untouched_by_the_budget(self):
        # Bundle 85 -- the 88-row case the operator actually expects to clear --
        # must behave exactly as before.
        self._holds(88)
        results = auto_remediate_on_review_open(self.bundle)
        self.assertNotIn("skipped_over_budget", results)
        self.assertEqual(results["pending_before"], 88)

    # ---------------------------------------------------------- the preview --
    def test_the_preview_counts_every_row_but_samples_the_detail(self):
        total = PREVIEW_ROW_SAMPLE_CAP + 250
        self._holds(total)

        report = preview_autopilot_decisions(self.bundle)

        # Counts are EXACT -- this is what the state read is read from.
        self.assertEqual(report["pending"], total)
        self.assertEqual(sum(report["counts"].values()), total)
        # Detail is bounded.
        self.assertEqual(report["rows_returned"], PREVIEW_ROW_SAMPLE_CAP)
        self.assertEqual(len(report["rows"]), PREVIEW_ROW_SAMPLE_CAP)
        # And the omission is stated, never silent.
        self.assertEqual(report["rows_truncated"], 250)

    def test_a_small_bundle_reports_no_truncation(self):
        self._holds(12)
        report = preview_autopilot_decisions(self.bundle)
        self.assertEqual(report["pending"], 12)
        self.assertEqual(report["rows_returned"], 12)
        self.assertEqual(report["rows_truncated"], 0)

    def test_pending_no_longer_derives_from_the_sampled_list(self):
        # The specific regression: `"pending": len(rows)` silently became the CAP
        # once the cap existed, so a 75,600-row bundle would have reported 1,000
        # pending and every downstream percentage would have been wrong.
        self._holds(PREVIEW_ROW_SAMPLE_CAP + 1)
        report = preview_autopilot_decisions(self.bundle)
        self.assertNotEqual(report["pending"], report["rows_returned"])
        self.assertEqual(report["pending"], PREVIEW_ROW_SAMPLE_CAP + 1)
