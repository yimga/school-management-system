"""Full-bundle rollback — one shared, child-first, HONEST revert for both surfaces.

A rollback must never claim a clean slate it did not deliver. Some domains cannot
be auto-reverted (shared academic scaffold that dependents FK into; an in-place
update that was not snapshotted; a PROTECT-blocked delete), and the caller — tenant
or operator — has to be told exactly which rows were left in place. These tests
prove ``rollback_bundle`` (the shared SoT) and ``rollback_apply`` (its connector
wrapper) both surface a ``not_reverted`` list and only report ``ok`` when the revert
was genuinely complete.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import MigrationRun
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.models_connectors import (
    ImportRunStatus,
    MigrationConnectorProfile,
    MigrationImportRun,
)
from apps.migration_cloud.services.connector_credentials import create_source_connection
from apps.migration_cloud.services.connector_rollback import rollback_apply, rollback_bundle
from apps.schools.models import School

User = get_user_model()


class RollbackBundleHonestyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Rollback Honesty School", slug="rbh-test", subdomain="rbh-test"
        )
        self.user = User.objects.create_user(username="rbh_user", password="unused")
        self.bundle = MigrationBundle.objects.create(
            label="rbh-bundle",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="rbh-key",
            status=BundleStatus.APPLIED,
            school=self.school,
            expected_totals={},
        )

    def _run(self, migration_type, *, created_ids, status=MigrationRun.Status.SUCCESS):
        return MigrationRun.objects.create(
            school=self.school,
            migration_type=migration_type,
            dry_run=False,
            row_count=len(created_ids),
            status=status,
            rollback_snapshot={"created_ids": list(created_ids)},
            execution_summary={"bundle_id": self.bundle.pk},
        )

    def test_confirm_is_required(self):
        result = rollback_bundle(bundle=self.bundle, actor=self.user, confirm=False)
        self.assertFalse(result["applied"])
        self.assertFalse(result["ok"])
        self.assertIn("confirm", result["message"].lower())

    def test_non_automatic_domain_is_reported_in_not_reverted(self):
        # 'structure' provisions shared scaffold that dependents FK into; its
        # handler honestly refuses to auto-delete created scaffold rows.
        self._run("structure", created_ids=[1, 2, 3])
        result = rollback_bundle(bundle=self.bundle, actor=self.user, confirm=True)

        self.assertTrue(result["applied"])
        # It attempted, but the domain could not be auto-reverted -> NOT a clean slate.
        self.assertFalse(result["ok"])
        domains = {d["migration_type"] for d in result["not_reverted"]}
        self.assertIn("structure", domains)
        # And the message says so, honestly.
        self.assertIn("not a clean-slate", result["message"].lower())

    def test_clean_revert_reports_ok_and_empty_not_reverted(self):
        # A run that created nothing reverts cleanly (nothing to delete).
        self._run("students", created_ids=[])
        result = rollback_bundle(bundle=self.bundle, actor=self.user, confirm=True)

        self.assertTrue(result["applied"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["not_reverted"], [])

    def test_landed_run_without_snapshot_is_surfaced(self):
        # A SUCCESS run that kept NO snapshot created rows we cannot auto-revert.
        MigrationRun.objects.create(
            school=self.school,
            migration_type="library",
            dry_run=False,
            row_count=5,
            status=MigrationRun.Status.SUCCESS,
            rollback_snapshot={},  # no snapshot -> not auto-revertible
            execution_summary={"bundle_id": self.bundle.pk},
        )
        result = rollback_bundle(bundle=self.bundle, actor=self.user, confirm=True)
        domains = {d["migration_type"] for d in result["not_reverted"]}
        self.assertIn("library", domains)
        self.assertFalse(result["ok"])

    def test_rollback_apply_wrapper_exposes_not_reverted(self):
        # The connector wrapper delegates to rollback_bundle and preserves the
        # honest not_reverted list + updates the import-run status.
        self._run("structure", created_ids=[7])
        profile, _ = MigrationConnectorProfile.objects.get_or_create(
            key="generic_csv_export",
            defaults={"display_name": "Generic CSV", "certification_status": "production_ready"},
        )
        conn = create_source_connection(
            school=self.school,
            created_by=self.user,
            connector_profile=profile,
            source_platform_type="generic_csv_export",
            source_url="https://sis.example.edu",
            connection_method="file_export",
        )
        import_run = MigrationImportRun.objects.create(
            school=self.school,
            source_connection=conn,
            status=ImportRunStatus.COMPLETED,
            idempotency_key="rbh-apply-key",
            bundle=self.bundle,
            created_counts={"structure": 1},
        )
        result = rollback_apply(import_run=import_run, actor=self.user, confirm=True)
        self.assertIn("not_reverted", result)
        self.assertTrue(any(d["migration_type"] == "structure" for d in result["not_reverted"]))
        import_run.refresh_from_db()
        # Applied but not fully clean -> PARTIAL, not ROLLED_BACK.
        self.assertEqual(import_run.status, ImportRunStatus.PARTIAL)
