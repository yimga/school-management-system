"""The three things the production state read left open (2026-08-30).

1. Bundle 83's 75,600 rows had nowhere to go once the page-open pass started
   refusing them. A guard that makes large bundles unresolvable is the original
   bug wearing a politer face, so the budget now belongs to the TRIGGER
   (``enforce_row_budget``) and a batch command runs the same five rules outside
   a request.

2. Bundles 81 and 78 needed the same read, and running the single-bundle form
   once per bundle is how an operator ends up reading screens of logs to compare
   four numbers. ``--all`` does the sweep.

3. The zero-yield blind spot. Bundle 85's PDF produced no records and 88
   dismissals; once autopilot closes them the bundle reads APPLIED with an empty
   queue and NOTHING says that file contributed nothing. Nothing stores
   records-created-per-artifact, but it is derivable: every discovered row either
   lands or is quarantined, so quarantined >= row_count means nothing landed.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.automation.models import MigrationQuarantineRecord, MigrationRun
from apps.migration_cloud.auto_remediate import (
    REVIEW_OPEN_ROW_BUDGET,
    auto_remediate_on_review_open,
)
from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.quarantine_profile import artifact_yield_overview
from apps.schools.models import School

ARTIFACT = "school_stats_2026-01-18.pdf"


class OpenItemsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Yield School",
            slug="yield-school",
            subdomain="yield-school",
            is_active=True,
            is_approved=True,
        )
        self.bundle = MigrationBundle.objects.create(
            label="yield",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="yield-b1",
            status=BundleStatus.APPLIED,
            school=self.school,
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )

    def _artifact(self, path, *, row_count, fmt="pdf"):
        return MigrationArtifact.objects.create(
            bundle=self.bundle,
            path_within_bundle=path,
            filename=path,
            detected_format=fmt,
            row_count=row_count,
            sha256="0" * 64,
        )

    def _holds(self, count, *, artifact=ARTIFACT, status=None, issue="missing_required"):
        status = status or MigrationQuarantineRecord.Status.PENDING
        MigrationQuarantineRecord.objects.bulk_create(
            [
                MigrationQuarantineRecord(
                    school=self.school,
                    migration_run=self.run,
                    domain="academics",
                    row_index=i,
                    issue_class=issue,
                    payload={
                        "error": "held",
                        "artifact": artifact,
                        "source_row": {"n": str(i)},
                        "reason_source": "declared",
                    },
                    status=status,
                )
                for i in range(count)
            ]
        )

    # ------------------------------------------------ 3. zero-yield blind spot --
    def test_an_artifact_whose_every_row_was_held_produced_nothing(self):
        self._artifact(ARTIFACT, row_count=88)
        self._holds(88)

        rows = {r["artifact"]: r for r in artifact_yield_overview(self.bundle)}
        self.assertTrue(rows[ARTIFACT]["produced_nothing"])
        self.assertEqual(rows[ARTIFACT]["rows_discovered"], 88)
        self.assertEqual(rows[ARTIFACT]["held_total"], 88)

    def test_it_stays_true_after_autopilot_dismisses_them(self):
        # The whole point. Once the queue is empty this is the only thing left
        # that knows the file contributed nothing.
        self._artifact(ARTIFACT, row_count=88)
        self._holds(88, status=MigrationQuarantineRecord.Status.REPAIRED)

        rows = {r["artifact"]: r for r in artifact_yield_overview(self.bundle)}
        self.assertTrue(rows[ARTIFACT]["produced_nothing"])
        self.assertEqual(rows[ARTIFACT]["held_pending"], 0)
        self.assertEqual(rows[ARTIFACT]["held_resolved"], 88)

    def test_an_artifact_that_landed_most_of_its_rows_is_not_accused(self):
        self._artifact("students.csv", row_count=500, fmt="csv")
        self._holds(3, artifact="students.csv")
        rows = {r["artifact"]: r for r in artifact_yield_overview(self.bundle)}
        self.assertFalse(rows["students.csv"]["produced_nothing"])

    def test_an_unknown_row_count_is_not_read_as_zero(self):
        # row_count is null for archives and binaries. Unknown is not zero, and an
        # unanswerable question must not be answered with an accusation.
        self._artifact("photos.zip", row_count=None, fmt="archive")
        rows = {r["artifact"]: r for r in artifact_yield_overview(self.bundle)}
        self.assertFalse(rows["photos.zip"]["produced_nothing"])

    def test_the_profile_command_says_so(self):
        self._artifact(ARTIFACT, row_count=88)
        self._holds(88)
        out = StringIO()
        call_command("profile_bundle_quarantine", "--bundle-id", self.bundle.pk, stdout=out)
        text = out.getvalue()
        self.assertIn("Produced NO records", text)
        self.assertIn(ARTIFACT, text)

    def test_a_derived_report_is_not_listed_as_a_failure(self):
        """Bundle 85 shipped the SAME stats report twice, 7 seconds apart:

            school_stats_...22_47_25.pdf    row_count=88  held=88
            school_stats_...22_47_32.xlsx   row_count=40  held=0

        The xlsx holds nothing because it was detected as a derived report and
        skipped -- report_lander lands zero records on purpose. It contributed
        nothing, but so does every report, and putting it in the same list as a
        mapping failure is how a warning list becomes noise nobody reads.
        """
        art = self._artifact("school_stats.xlsx", row_count=40, fmt="xlsx")
        art.assigned_domain = "reports"
        art.save(update_fields=["assigned_domain"])

        rows = {r["artifact"]: r for r in artifact_yield_overview(self.bundle)}
        row = rows["school_stats.xlsx"]
        self.assertTrue(row["skipped_as_report"])
        self.assertFalse(row["produced_nothing"], "a report is not a failure")

    def test_the_two_answers_appear_in_different_sections(self):
        # The failure and the by-design zero, side by side, as in bundle 85.
        self._artifact(ARTIFACT, row_count=88)
        self._holds(88)
        report = self._artifact("school_stats.xlsx", row_count=40, fmt="xlsx")
        report.assigned_domain = "reports"
        report.save(update_fields=["assigned_domain"])

        out = StringIO()
        call_command("profile_bundle_quarantine", "--bundle-id", self.bundle.pk, stdout=out)
        text = out.getvalue()
        self.assertIn("Produced NO records", text)
        self.assertIn("Skipped as derived reports", text)
        # The report must not be under the failure heading.
        failure_section = text.split("Produced NO records", 1)[1].split("Skipped as", 1)[0]
        self.assertNotIn("school_stats.xlsx", failure_section)

    def test_an_unreadable_artifact_gets_its_own_answer(self):
        art = self._artifact("scan.pdf", row_count=0)
        art.quarantined = True
        art.quarantine_reason = "no working reader for this format"
        art.save(update_fields=["quarantined", "quarantine_reason"])

        rows = {r["artifact"]: r for r in artifact_yield_overview(self.bundle)}
        self.assertTrue(rows["scan.pdf"]["unreadable"])
        out = StringIO()
        call_command("profile_bundle_quarantine", "--bundle-id", self.bundle.pk, stdout=out)
        self.assertIn("Could not be read at all", out.getvalue())

    # -------------------------------------------------------- 1. batch path --
    def test_the_batch_path_can_do_what_a_page_open_refuses(self):
        self._artifact(ARTIFACT, row_count=REVIEW_OPEN_ROW_BUDGET + 10)
        self._holds(REVIEW_OPEN_ROW_BUDGET + 10)

        # The page open refuses...
        refused = auto_remediate_on_review_open(self.bundle)
        self.assertTrue(refused.get("skipped_over_budget"))

        # ...and the batch path, which has no request to be killed by, does not.
        ran = auto_remediate_on_review_open(self.bundle, enforce_row_budget=False)
        self.assertNotIn("skipped_over_budget", ran)
        self.assertGreater(ran["auto_resolved_total"], 0)

    def test_the_batch_command_runs_and_reports_what_is_left(self):
        self._artifact(ARTIFACT, row_count=REVIEW_OPEN_ROW_BUDGET + 10)
        self._holds(REVIEW_OPEN_ROW_BUDGET + 10)
        out = StringIO()
        call_command(
            "remediate_quarantine_batch", "--bundle-id", self.bundle.pk, stdout=out
        )
        text = out.getvalue()
        self.assertIn("resolved", text)
        self.assertEqual(
            MigrationQuarantineRecord.objects.filter(
                status=MigrationQuarantineRecord.Status.PENDING
            ).count(),
            0,
        )

    def test_the_batch_dry_run_changes_nothing(self):
        self._artifact(ARTIFACT, row_count=20)
        self._holds(20)
        before = MigrationQuarantineRecord.objects.filter(
            status=MigrationQuarantineRecord.Status.PENDING
        ).count()
        out = StringIO()
        call_command(
            "remediate_quarantine_batch",
            "--bundle-id",
            self.bundle.pk,
            "--dry-run",
            stdout=out,
        )
        self.assertIn("Nothing was changed", out.getvalue())
        self.assertEqual(
            MigrationQuarantineRecord.objects.filter(
                status=MigrationQuarantineRecord.Status.PENDING
            ).count(),
            before,
        )

    # ---------------------------------------------------- 2. the --all sweep --
    def test_all_lists_every_holding_bundle_in_one_pass(self):
        self._artifact(ARTIFACT, row_count=88)
        self._holds(88)
        quiet = MigrationBundle.objects.create(
            label="quiet",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="yield-b2",
            status=BundleStatus.APPLIED,
            school=self.school,
        )
        out = StringIO()
        call_command("preview_quarantine_autopilot", "--all", stdout=out)
        text = out.getvalue()
        self.assertIn(str(self.bundle.pk), text)
        # A bundle holding nothing is not worth a line.
        self.assertNotIn(f"  {quiet.pk}  ", text)

    def test_all_is_read_only(self):
        self._artifact(ARTIFACT, row_count=88)
        self._holds(88)
        before = MigrationQuarantineRecord.objects.filter(
            status=MigrationQuarantineRecord.Status.PENDING
        ).count()
        call_command("preview_quarantine_autopilot", "--all", stdout=StringIO())
        self.assertEqual(
            MigrationQuarantineRecord.objects.filter(
                status=MigrationQuarantineRecord.Status.PENDING
            ).count(),
            before,
        )
