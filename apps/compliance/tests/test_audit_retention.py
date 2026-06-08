import tempfile
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.compliance.audit_retention import (
    create_archive,
    purge_verified_archive,
    verify_archive,
)
from apps.compliance.models_audit import (
    AccessLog,
    AuditArchiveRecord,
    AuditLegalHold,
    AuditLog,
)


class AuditRetentionTests(TestCase):
    def setUp(self):
        self.archive_dir = tempfile.TemporaryDirectory()
        self.settings = override_settings(
            AUDIT_ARCHIVE_ROOT=self.archive_dir.name,
            AUDIT_ARCHIVE_SIGNING_KEY="archive-signing-test-key",
            AUDIT_RETENTION_APPROVAL_TOKEN="approved-for-test",
        )
        self.settings.enable()
        self.cutoff = timezone.now() - timedelta(days=30)

    def tearDown(self):
        self.settings.disable()
        self.archive_dir.cleanup()

    def _old_audit(self, object_id):
        row = AuditLog.objects.create(
            action=AuditLog.Action.VIEW,
            model_name="Student",
            object_id=str(object_id),
            app_label="students",
            sensitivity=AuditLog.Sensitivity.HIGH,
        )
        AuditLog.objects.filter(pk=row.pk).update(
            timestamp=self.cutoff - timedelta(days=1)
        )
        row.refresh_from_db()
        return row

    def test_append_only_rows_are_archived_verified_and_exactly_purged(self):
        archived = self._old_audit("old")
        recent = self._old_audit("recent")
        AuditLog.objects.filter(pk=recent.pk).update(timestamp=timezone.now())

        result = create_archive(AuditLog, "timestamp", self.cutoff)

        self.assertEqual(result.eligible_count, 1)
        self.assertEqual(verify_archive(result.archive), [str(archived.pk)])
        deleted = purge_verified_archive(
            result.archive,
            AuditLog,
            approval_token="approved-for-test",
        )
        self.assertEqual(deleted, 1)
        self.assertFalse(AuditLog.objects.filter(pk=archived.pk).exists())
        self.assertTrue(AuditLog.objects.filter(pk=recent.pk).exists())
        result.archive.refresh_from_db()
        self.assertEqual(result.archive.status, AuditArchiveRecord.Status.PURGED)

    def test_invalid_approval_never_deletes(self):
        row = self._old_audit("protected")
        archive = create_archive(AuditLog, "timestamp", self.cutoff).archive

        with self.assertRaises(PermissionDenied):
            purge_verified_archive(
                archive, AuditLog, approval_token="wrong-token"
            )

        self.assertTrue(AuditLog.objects.filter(pk=row.pk).exists())

    def test_tampered_archive_never_deletes(self):
        row = self._old_audit("tamper")
        archive = create_archive(AuditLog, "timestamp", self.cutoff).archive
        path = Path(self.archive_dir.name) / archive.relative_path
        path.write_bytes(path.read_bytes() + b"tampered")

        with self.assertRaises(PermissionDenied):
            purge_verified_archive(
                archive,
                AuditLog,
                approval_token="approved-for-test",
            )

        self.assertTrue(AuditLog.objects.filter(pk=row.pk).exists())

    def test_active_legal_hold_excludes_exact_record(self):
        held = self._old_audit("held")
        eligible = self._old_audit("eligible")
        AuditLegalHold.objects.create(
            name="Investigation",
            reason="Preserve evidence",
            model_label=AuditLog._meta.label,
            object_id=str(held.pk),
        )

        result = create_archive(AuditLog, "timestamp", self.cutoff)

        self.assertEqual(result.eligible_count, 1)
        self.assertEqual(result.held_count, 1)
        self.assertEqual(verify_archive(result.archive), [str(eligible.pk)])

    def test_hold_added_after_archive_blocks_purge(self):
        row = self._old_audit("late-hold")
        archive = create_archive(AuditLog, "timestamp", self.cutoff).archive
        AuditLegalHold.objects.create(
            name="Late investigation",
            reason="Purge must re-check holds",
            model_label=AuditLog._meta.label,
            object_id=str(row.pk),
        )

        with self.assertRaises(PermissionDenied):
            purge_verified_archive(
                archive,
                AuditLog,
                approval_token="approved-for-test",
            )

        self.assertTrue(AuditLog.objects.filter(pk=row.pk).exists())

    def test_date_range_hold_excludes_matching_records(self):
        held = self._old_audit("range-held")
        outside = self._old_audit("range-outside")
        AuditLog.objects.filter(pk=outside.pk).update(
            timestamp=self.cutoff - timedelta(days=10)
        )
        AuditLegalHold.objects.create(
            name="Incident date range",
            reason="Preserve the incident window",
            model_label=AuditLog._meta.label,
            starts_at=self.cutoff - timedelta(days=2),
            ends_at=self.cutoff,
        )

        result = create_archive(AuditLog, "timestamp", self.cutoff)

        self.assertEqual(result.eligible_count, 1)
        self.assertEqual(result.held_count, 1)
        self.assertEqual(verify_archive(result.archive), [str(outside.pk)])
        self.assertTrue(AuditLog.objects.filter(pk=held.pk).exists())

    def test_non_append_only_target_uses_same_verified_contract(self):
        row = AccessLog.objects.create(
            access_type=AccessLog.AccessType.API,
            resource="/test",
            status=AccessLog.Status.SUCCESS,
            timestamp=self.cutoff - timedelta(days=1),
        )
        archive = create_archive(AccessLog, "timestamp", self.cutoff).archive

        deleted = purge_verified_archive(
            archive,
            AccessLog,
            approval_token="approved-for-test",
        )

        self.assertEqual(deleted, 1)
        self.assertFalse(AccessLog.objects.filter(pk=row.pk).exists())
