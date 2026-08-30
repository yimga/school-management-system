"""A --bundle-id command must be able to say which ids exist (2026-08-30).

Reported from a Render shell: `profile_bundle_quarantine --bundle-id 8` answered
`CommandError: Bundle 8 not found` and stopped. That is a dead end. The two
places these commands actually run -- a Render shell and an appliance -- are
exactly the two places where the operator has no psql prompt to go and look, so
a command that refuses an id owes them the ids that would have worked.

It also has to keep failing. Printing the list is a courtesy; the exit code is a
contract, and an `&&` chain must not carry on as though it had profiled
something. Both halves are pinned here.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.automation.models import MigrationQuarantineRecord, MigrationRun
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.quarantine_resolution import (
    format_bundle_choices,
    recent_bundles_overview,
)
from apps.schools.models import School

User = get_user_model()

COMMANDS = ("profile_bundle_quarantine", "preview_quarantine_autopilot")


class BundleDiscoveryTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Discovery School",
            slug="discovery-school",
            subdomain="discovery-school",
            is_active=True,
            is_approved=True,
        )
        self.bundle = MigrationBundle.objects.create(
            label="real-intake",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="discovery-b1",
            status=BundleStatus.APPLIED,
            school=self.school,
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )

    def _hold(self):
        return MigrationQuarantineRecord.objects.create(
            school=self.school,
            migration_run=self.run,
            domain="academics",
            row_index=1,
            issue_class="missing_required",
            payload={"error": "held", "artifact": "a.csv", "source_row": {"a": "1"}},
            status=MigrationQuarantineRecord.Status.PENDING,
        )

    # ------------------------------------------------------------------ ids --
    def test_a_missing_bundle_still_fails_but_names_the_ids_that_exist(self):
        for name in COMMANDS:
            with self.subTest(command=name):
                out = StringIO()
                # The id the operator actually typed on Render.
                with self.assertRaises(CommandError) as caught:
                    call_command(name, "--bundle-id", 999999, stdout=out)
                # Still an error -- the exit code is the contract.
                self.assertIn("999999", str(caught.exception))
                # ...but no longer a dead end.
                self.assertIn(str(self.bundle.pk), out.getvalue())
                self.assertIn("real-intake", out.getvalue())

    def test_no_bundle_id_lists_instead_of_erroring(self):
        for name in COMMANDS:
            with self.subTest(command=name):
                out = StringIO()
                call_command(name, stdout=out)  # must NOT raise
                self.assertIn(str(self.bundle.pk), out.getvalue())

    def test_an_empty_database_says_wrong_environment_not_wrong_id(self):
        # The distinction that matters on Render: zero bundles anywhere means the
        # operator is on the wrong instance, and no id would ever have worked.
        MigrationBundle.objects.all().delete()
        text = format_bundle_choices()
        self.assertIn("wrong environment", text)
        self.assertNotIn("newest first", text)

    # --------------------------------------------------------------- content --
    def test_the_list_carries_the_held_count_so_it_doubles_as_triage(self):
        self._hold()
        rows = recent_bundles_overview()
        row = next(r for r in rows if r["id"] == self.bundle.pk)
        self.assertEqual(row["held"], 1)
        self.assertEqual(row["school"], "Discovery School")
        self.assertEqual(row["label"], "real-intake")
        self.assertIn(str(self.bundle.pk), format_bundle_choices())

    def test_newest_first_and_capped(self):
        for i in range(4):
            MigrationBundle.objects.create(
                label=f"extra-{i}",
                intake_method=IntakeMethod.FILE_UPLOAD,
                idempotency_key=f"discovery-extra-{i}",
                status=BundleStatus.APPLIED,
                school=self.school,
            )
        rows = recent_bundles_overview(limit=3)
        self.assertEqual(len(rows), 3)
        ids = [r["id"] for r in rows]
        self.assertEqual(ids, sorted(ids, reverse=True), "newest first")

    def test_a_nonsense_limit_does_not_crash_the_recovery_path(self):
        # This runs when something has ALREADY gone wrong; it must not add a
        # second failure on top of the one being diagnosed.
        for bad in (0, -5, None, "seven"):
            with self.subTest(limit=bad):
                self.assertTrue(len(recent_bundles_overview(limit=bad)) >= 1)
