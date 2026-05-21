"""v3.40.0 Agent 15 — Migration data retention purge command + audit task tests.

Coverage (~12 tests):
  * Dry-run (default) lists candidates without deletion
  * N < 90 days → CommandError before any work
  * --apply without counsel-token → SystemExit(1)
  * --apply with valid token + phrase → bundles purged, audit event emitted
  * Audit event payload PII-free
  * Bundles outside tenant scope NOT touched (tenant isolation)
  * Bundles within N days NOT touched
  * Floor configurable via setting
  * Beat task runs in dry-run only (asserts no DB mutation)
  * Beat task emits info-level alert when bundles eligible
"""
from __future__ import annotations

import datetime as _dt
import io
from unittest import mock

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.migration_cloud.models import CompanionCiphertextBlob
from apps.migration_cloud.models_audit import (
    MigrationCloudAuditEvent,
    MigrationCloudAuditEventType,
)
from apps.migration_cloud.tasks_retention import (
    purge_completed_migration_bundles_audit_task,
)
from apps.schools.models import School


_VALID_TOKEN = "x" * 40
_PHRASE = "I AFFIRM MIGRATION DATA RETENTION PURGE"


def _make_school(slug: str) -> School:
    return School.objects.create(
        slug=slug,
        name=f"Test {slug}",
        subdomain=slug,
        is_active=True,
    )


def _make_old_blob(school: School, *, days_old: int, decrypted: bool = True) -> CompanionCiphertextBlob:
    """Create a CompanionCiphertextBlob with received_at in the past."""
    blob = CompanionCiphertextBlob.objects.create(
        tenant=school,
        ciphertext_sha256="a" * 64,
        byte_size=1024,
    )
    blob.blob_file.save(
        f"test-{blob.pk}.bin",
        ContentFile(b"x" * 1024),
        save=True,
    )
    # Backdate received_at to N days ago.
    backdate = timezone.now() - _dt.timedelta(days=days_old)
    if decrypted:
        CompanionCiphertextBlob.objects.filter(pk=blob.pk).update(
            received_at=backdate,
            decrypted_at=backdate + _dt.timedelta(hours=1),
        )
    else:
        CompanionCiphertextBlob.objects.filter(pk=blob.pk).update(
            received_at=backdate,
        )
    blob.refresh_from_db()
    return blob


class RetentionPurgeCommandTests(TestCase):

    def setUp(self):
        self.tenant_a = _make_school("tenant-a-15")
        self.tenant_b = _make_school("tenant-b-15")

    def test_below_floor_raises_command_error(self):
        with self.assertRaises(CommandError):
            call_command(
                "purge_completed_migration_bundles",
                "--tenant=tenant-a-15",
                "--older-than-days=30",
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )

    def test_floor_configurable_via_setting(self):
        # With floor set to 30, --older-than-days=30 should be allowed.
        with override_settings(MIGRATION_CLOUD_RETENTION_MIN_DAYS=30):
            out = io.StringIO()
            call_command(
                "purge_completed_migration_bundles",
                "--tenant=tenant-a-15",
                "--older-than-days=30",
                stdout=out,
                stderr=io.StringIO(),
            )
            # No exception = success in dry-run mode.

    def test_dry_run_default_lists_candidates_no_deletion(self):
        _make_old_blob(self.tenant_a, days_old=200)
        out = io.StringIO()
        call_command(
            "purge_completed_migration_bundles",
            "--tenant=tenant-a-15",
            "--older-than-days=180",
            stdout=out,
            stderr=io.StringIO(),
        )
        output = out.getvalue()
        self.assertIn("candidates=1", output)
        self.assertIn("DRY-RUN", output)
        # No deletion — byte_size still 1024.
        self.assertEqual(
            CompanionCiphertextBlob.objects.filter(
                tenant=self.tenant_a,
            ).first().byte_size,
            1024,
        )

    @override_settings(MIGRATION_CLOUD_DATA_RETENTION_APPROVAL_TOKEN="")
    def test_apply_without_token_setting_refuses(self):
        _make_old_blob(self.tenant_a, days_old=200)
        with self.assertRaises(SystemExit) as cm:
            call_command(
                "purge_completed_migration_bundles",
                "--tenant=tenant-a-15",
                "--older-than-days=180",
                "--apply",
                f"--counsel-token={_VALID_TOKEN}",
                f"--confirm-phrase={_PHRASE}",
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
        self.assertEqual(cm.exception.code, 1)
        # State unchanged.
        self.assertEqual(
            CompanionCiphertextBlob.objects.filter(
                tenant=self.tenant_a,
            ).first().byte_size,
            1024,
        )

    @override_settings(MIGRATION_CLOUD_DATA_RETENTION_APPROVAL_TOKEN=_VALID_TOKEN)
    def test_apply_with_wrong_token_refuses(self):
        _make_old_blob(self.tenant_a, days_old=200)
        with self.assertRaises(SystemExit) as cm:
            call_command(
                "purge_completed_migration_bundles",
                "--tenant=tenant-a-15",
                "--older-than-days=180",
                "--apply",
                "--counsel-token=WRONG",
                f"--confirm-phrase={_PHRASE}",
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
        self.assertEqual(cm.exception.code, 1)

    @override_settings(MIGRATION_CLOUD_DATA_RETENTION_APPROVAL_TOKEN=_VALID_TOKEN)
    def test_apply_purges_and_emits_audit_event(self):
        _make_old_blob(self.tenant_a, days_old=200)
        out = io.StringIO()
        call_command(
            "purge_completed_migration_bundles",
            "--tenant=tenant-a-15",
            "--older-than-days=180",
            "--apply",
            f"--counsel-token={_VALID_TOKEN}",
            f"--confirm-phrase={_PHRASE}",
            stdout=out,
            stderr=io.StringIO(),
        )
        self.assertIn("APPLIED", out.getvalue())
        # byte_size zeroed.
        self.assertEqual(
            CompanionCiphertextBlob.objects.filter(
                tenant=self.tenant_a,
            ).first().byte_size,
            0,
        )
        # Audit event emitted.
        evt = MigrationCloudAuditEvent.objects.filter(
            event_type=(
                MigrationCloudAuditEventType
                .MIGRATION_DATA_RETENTION_PURGE_APPLIED.value
            ),
        ).first()
        self.assertIsNotNone(evt)
        payload = evt.payload_summary or {}
        # PII-free assertions.
        self.assertIn("tenant_prefix", payload)
        self.assertIn("bundles_purged_count", payload)
        self.assertIn("bytes_freed", payload)
        self.assertNotIn("tenant_slug", payload)
        self.assertNotIn("blob_path", payload)
        self.assertNotIn("file_path", payload)

    @override_settings(MIGRATION_CLOUD_DATA_RETENTION_APPROVAL_TOKEN=_VALID_TOKEN)
    def test_tenant_isolation_other_tenants_untouched(self):
        _make_old_blob(self.tenant_a, days_old=200)
        _make_old_blob(self.tenant_b, days_old=200)
        call_command(
            "purge_completed_migration_bundles",
            "--tenant=tenant-a-15",
            "--older-than-days=180",
            "--apply",
            f"--counsel-token={_VALID_TOKEN}",
            f"--confirm-phrase={_PHRASE}",
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        # Tenant-a blob purged.
        self.assertEqual(
            CompanionCiphertextBlob.objects.filter(
                tenant=self.tenant_a,
            ).first().byte_size,
            0,
        )
        # Tenant-b blob untouched.
        self.assertEqual(
            CompanionCiphertextBlob.objects.filter(
                tenant=self.tenant_b,
            ).first().byte_size,
            1024,
        )

    @override_settings(MIGRATION_CLOUD_DATA_RETENTION_APPROVAL_TOKEN=_VALID_TOKEN)
    def test_within_window_blobs_not_touched(self):
        # Blob received 30 days ago must NOT be candidate under 180-day window.
        _make_old_blob(self.tenant_a, days_old=30)
        out = io.StringIO()
        call_command(
            "purge_completed_migration_bundles",
            "--tenant=tenant-a-15",
            "--older-than-days=180",
            "--apply",
            f"--counsel-token={_VALID_TOKEN}",
            f"--confirm-phrase={_PHRASE}",
            stdout=out,
            stderr=io.StringIO(),
        )
        # No candidates → no purge.
        self.assertIn("0 candidate bundles", out.getvalue())
        self.assertEqual(
            CompanionCiphertextBlob.objects.filter(
                tenant=self.tenant_a,
            ).first().byte_size,
            1024,
        )

    @override_settings(MIGRATION_CLOUD_DATA_RETENTION_APPROVAL_TOKEN=_VALID_TOKEN)
    def test_undecrypted_blobs_not_candidates(self):
        # A blob whose decrypted_at is NULL is NOT a completed migration.
        _make_old_blob(self.tenant_a, days_old=200, decrypted=False)
        out = io.StringIO()
        call_command(
            "purge_completed_migration_bundles",
            "--tenant=tenant-a-15",
            "--older-than-days=180",
            stdout=out,
            stderr=io.StringIO(),
        )
        self.assertIn("0 candidate bundles", out.getvalue())


class RetentionAuditTaskTests(TestCase):

    def setUp(self):
        self.tenant_a = _make_school("tenant-audit-15")

    def test_audit_task_returns_summary_dict(self):
        _make_old_blob(self.tenant_a, days_old=200)
        result = purge_completed_migration_bundles_audit_task()
        self.assertIn("tenants_audited", result)
        self.assertIn("tenants_with_candidates", result)
        self.assertIn("total_candidates", result)
        self.assertGreaterEqual(result["tenants_with_candidates"], 1)
        self.assertGreaterEqual(result["total_candidates"], 1)
        # Audit task must NEVER mutate. Blob byte_size still intact.
        self.assertEqual(
            CompanionCiphertextBlob.objects.filter(
                tenant=self.tenant_a,
            ).first().byte_size,
            1024,
        )

    def test_audit_task_emits_info_alert_for_eligible_tenant(self):
        _make_old_blob(self.tenant_a, days_old=200)
        with mock.patch(
            "apps.migration_cloud.alerts.alert"
        ) as mock_alert:
            purge_completed_migration_bundles_audit_task()
            self.assertTrue(mock_alert.called)
            # Verify the severity argument is "info".
            severities = [
                call.kwargs.get("severity")
                for call in mock_alert.call_args_list
            ]
            self.assertIn("info", severities)

    def test_audit_task_no_alert_when_no_candidates(self):
        # No blobs at all in scope.
        with mock.patch(
            "apps.migration_cloud.alerts.alert"
        ) as mock_alert:
            purge_completed_migration_bundles_audit_task()
            # The audit task only alerts when a tenant has candidates;
            # with no old blobs, no alert fires.
            self.assertFalse(mock_alert.called)
