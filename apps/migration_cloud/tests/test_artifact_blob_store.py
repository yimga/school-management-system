"""gap #2: per-artifact content store (Phase U5) — MigrationArtifactBlob.

The store captures each artifact's source bytes encrypted-at-rest at ingest so
archive members + multi-file / remote / OAuth-folder pulls (which have no single
top-level local path) can be profiled + applied instead of silently resolving to
zero rows.

Security-critical + behavioural assertions here:
  * The source bytes round-trip via the store (decrypt on read) …
  * … but are NOT present in clear text in the raw DB column (encrypted at rest).
  * A blob-backed ARCHIVE MEMBER now resolves a stream (profiler) + yields rows
    (orchestrator) — the exact case that previously applied nothing.
  * The inline size cap skips oversized artifacts (no PII in the log).
  * Retention: the daily sweep purges expired blobs but keeps artifact metadata;
    reconcile drops a bundle's source blobs on demand.
  * The master switch makes capture a no-op; a sha256 mismatch is ignored on read.
"""

from __future__ import annotations

import hashlib
import io
import types

from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationArtifactBlob,
    MigrationBundle,
)

_BLOB_TABLE = "migration_cloud_migrationartifactblob"


def _payload(data: bytes):
    """Minimal stand-in for ArtifactPayload — the store only reads content_opener."""
    return types.SimpleNamespace(content_opener=lambda: io.BytesIO(data))


def _raw_blob_payload(pk: int) -> bytes:
    with connection.cursor() as cur:
        cur.execute(f"SELECT payload FROM {_BLOB_TABLE} WHERE id = %s", [pk])  # noqa: S608 — constant table name
        row = cur.fetchone()
    if not row or row[0] is None:
        return b""
    val = row[0]
    if isinstance(val, memoryview):
        val = val.tobytes()
    return bytes(val)


class _Fixtures(TestCase):
    def _bundle(self, key: str, **kwargs) -> MigrationBundle:
        return MigrationBundle.objects.create(
            label=kwargs.pop("label", "blob bundle"),
            intake_method=kwargs.pop("intake_method", IntakeMethod.FILE_UPLOAD),
            idempotency_key=key,
            status=kwargs.pop("status", BundleStatus.INGESTING),
            **kwargs,
        )

    def _artifact(
        self,
        bundle: MigrationBundle,
        *,
        filename: str = "students.csv",
        path: str | None = None,
        fmt: str = ArtifactFormat.CSV,
        parent: MigrationArtifact | None = None,
    ) -> MigrationArtifact:
        return MigrationArtifact.objects.create(
            bundle=bundle,
            parent_archive=parent,
            path_within_bundle=path or filename,
            filename=filename,
            detected_format=fmt,
            byte_size=0,
            sha256="0" * 64,
        )


class CaptureAndEncryptionTests(_Fixtures):
    def test_capture_round_trips_but_encrypted_at_rest(self):
        marker = b"SECRET_STUDENT_ADA_LOVELACE_1815"
        data = b"name,dob\nAda Lovelace," + marker + b"\n"
        bundle = self._bundle("blob-round-trip")
        artifact = self._artifact(bundle)

        wrote = store.capture_artifact_blob(artifact, _payload(data))
        self.assertTrue(wrote)

        blob = MigrationArtifactBlob.objects.get(artifact=artifact)
        self.assertEqual(blob.byte_size, len(data))
        self.assertEqual(blob.sha256, hashlib.sha256(data).hexdigest())

        # Round-trips via the store (decrypts on read).
        stream, encoding = store.open_artifact_blob_stream(artifact)
        self.assertIsNotNone(stream)
        self.assertEqual(stream.read(), data)

        # …but the raw column must NOT contain the plaintext PII, and MUST look
        # like a Fernet token (urlsafe-base64 "gAAAA…").
        raw = _raw_blob_payload(blob.pk)
        self.assertNotIn(marker, raw)
        self.assertNotIn(b"Ada Lovelace", raw)
        self.assertIn(b"gAAAA", raw)

    def test_sha256_mismatch_ignored_on_read(self):
        data = b"col\nval\n"
        bundle = self._bundle("blob-sha-mismatch")
        artifact = self._artifact(bundle)
        self.assertTrue(store.capture_artifact_blob(artifact, _payload(data)))

        # Corrupt the recorded digest → read must refuse the blob (fall back).
        MigrationArtifactBlob.objects.filter(artifact=artifact).update(sha256="f" * 64)
        stream, encoding = store.open_artifact_blob_stream(artifact)
        self.assertIsNone(stream)
        self.assertEqual(encoding, "")

    @override_settings(MIGRATION_CLOUD_ARTIFACT_BLOB_STORE_ENABLED=False)
    def test_flag_off_capture_is_noop(self):
        bundle = self._bundle("blob-flag-off")
        artifact = self._artifact(bundle)
        wrote = store.capture_artifact_blob(artifact, _payload(b"x,y\n1,2\n"))
        self.assertFalse(wrote)
        self.assertFalse(MigrationArtifactBlob.objects.filter(artifact=artifact).exists())

    @override_settings(MIGRATION_CLOUD_ARTIFACT_BLOB_MAX_INLINE_BYTES=8)
    def test_size_cap_skips_oversized_inline(self):
        bundle = self._bundle("blob-oversized")
        artifact = self._artifact(bundle)
        wrote = store.capture_artifact_blob(artifact, _payload(b"0123456789" * 4))  # 40 > 8
        self.assertFalse(wrote)
        self.assertFalse(MigrationArtifactBlob.objects.filter(artifact=artifact).exists())

    @override_settings(MIGRATION_CLOUD_ARTIFACT_BLOB_MAX_INLINE_BYTES=8)
    def test_size_cap_allows_exactly_at_cap(self):
        bundle = self._bundle("blob-at-cap")
        artifact = self._artifact(bundle)
        wrote = store.capture_artifact_blob(artifact, _payload(b"12345678"))  # == 8
        self.assertTrue(wrote)


class ArchiveMemberReadableTests(_Fixtures):
    def test_archive_member_now_resolves_bytes(self):
        """The core win: an archive member (no top-level path) becomes readable."""
        data = b"student,grade\nAda,A\nGrace,B\n"
        bundle = self._bundle("blob-archive", intake_method=IntakeMethod.ARCHIVE)
        parent = self._artifact(
            bundle, filename="roster.zip", path="roster.zip", fmt=ArtifactFormat.ARCHIVE
        )
        member = self._artifact(
            bundle,
            filename="students.csv",
            path="roster.zip/students.csv",
            fmt=ArtifactFormat.CSV,
            parent=parent,
        )
        self.assertIsNotNone(member.parent_archive_id)

        self.assertTrue(store.capture_artifact_blob(member, _payload(data)))

        stream, encoding = store.open_artifact_blob_stream(member)
        self.assertIsNotNone(stream)
        self.assertEqual(stream.read(), data)

    def test_profiler_resolve_stream_uses_blob_for_archive_member(self):
        from apps.migration_cloud import profiler

        data = b"first,last\nAda,Lovelace\n"
        bundle = self._bundle("blob-profiler", intake_method=IntakeMethod.ARCHIVE)
        parent = self._artifact(
            bundle, filename="roster.zip", path="roster.zip", fmt=ArtifactFormat.ARCHIVE
        )
        member = self._artifact(
            bundle,
            filename="people.csv",
            path="roster.zip/people.csv",
            parent=parent,
        )
        self.assertTrue(store.capture_artifact_blob(member, _payload(data)))

        stream, encoding = profiler._resolve_stream(member)
        self.assertIsNotNone(stream)
        try:
            self.assertEqual(stream.read(), data)
        finally:
            stream.close()

    def test_orchestrator_yields_rows_from_blob(self):
        """No intake_source_uri → the ONLY readable path is the blob."""
        from apps.migration_cloud.orchestrator import _ArtifactJob, _iter_canonical_rows

        data = b"name,age\nAda,36\nGrace,45\n"
        bundle = self._bundle("blob-orchestrator", intake_method=IntakeMethod.ARCHIVE)
        parent = self._artifact(
            bundle, filename="roster.zip", path="roster.zip", fmt=ArtifactFormat.ARCHIVE
        )
        member = self._artifact(
            bundle, filename="students.csv", path="roster.zip/students.csv", parent=parent
        )
        self.assertEqual(bundle.intake_source_uri, "")  # no top-level local file
        self.assertTrue(store.capture_artifact_blob(member, _payload(data)))

        job = _ArtifactJob(
            artifact=member,
            domain="students",
            mappings=[
                {"source_column": "name", "canonical_field": "full_name"},
                {"source_column": "age", "canonical_field": "years"},
            ],
        )
        rows = list(_iter_canonical_rows(job))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["full_name"], "Ada")
        self.assertEqual(rows[0]["years"], "36")
        self.assertEqual(rows[1]["full_name"], "Grace")


class RetentionTests(_Fixtures):
    def test_purge_sweep_deletes_expired_keeps_metadata(self):
        bundle = self._bundle("blob-purge")
        artifact = self._artifact(bundle)
        self.assertTrue(store.capture_artifact_blob(artifact, _payload(b"a,b\n1,2\n")))

        # Force the blob past its retention window.
        past = timezone.now() - timezone.timedelta(days=1)
        MigrationArtifactBlob.objects.filter(artifact=artifact).update(expires_at=past)

        result = store.purge_expired_artifact_blobs()
        self.assertEqual(result["deleted"], 1)
        self.assertFalse(MigrationArtifactBlob.objects.filter(artifact=artifact).exists())
        # Metadata (the artifact row) survives — the audit trail is retained.
        self.assertTrue(MigrationArtifact.objects.filter(pk=artifact.pk).exists())

    def test_purge_leaves_unexpired_blobs(self):
        bundle = self._bundle("blob-purge-fresh")
        artifact = self._artifact(bundle)
        self.assertTrue(store.capture_artifact_blob(artifact, _payload(b"a,b\n1,2\n")))
        result = store.purge_expired_artifact_blobs()
        self.assertEqual(result["deleted"], 0)
        self.assertTrue(MigrationArtifactBlob.objects.filter(artifact=artifact).exists())

    def test_delete_blobs_for_bundle_drops_source_keeps_metadata(self):
        bundle = self._bundle("blob-reconcile")
        a1 = self._artifact(bundle, filename="students.csv", path="students.csv")
        a2 = self._artifact(bundle, filename="grades.csv", path="grades.csv")
        self.assertTrue(store.capture_artifact_blob(a1, _payload(b"x\n1\n")))
        self.assertTrue(store.capture_artifact_blob(a2, _payload(b"y\n2\n")))

        deleted = store.delete_blobs_for_bundle(bundle)
        self.assertEqual(deleted, 2)
        self.assertFalse(MigrationArtifactBlob.objects.filter(artifact__bundle=bundle).exists())
        self.assertEqual(MigrationArtifact.objects.filter(bundle=bundle).count(), 2)

    @override_settings(MIGRATION_CLOUD_ARTIFACT_BLOB_DELETE_ON_RECONCILE=False)
    def test_delete_on_reconcile_disabled_is_noop(self):
        bundle = self._bundle("blob-reconcile-off")
        artifact = self._artifact(bundle)
        self.assertTrue(store.capture_artifact_blob(artifact, _payload(b"x\n1\n")))
        self.assertEqual(store.delete_blobs_for_bundle(bundle), 0)
        self.assertTrue(MigrationArtifactBlob.objects.filter(artifact=artifact).exists())

    def test_reconcile_bundle_drops_blobs_end_to_end(self):
        """reconcile_bundle → RECONCILED must drop the bundle's source blobs."""
        from apps.migration_cloud import reconciliation

        bundle = self._bundle("blob-reconcile-e2e", status=BundleStatus.APPLIED)
        artifact = self._artifact(bundle)
        self.assertTrue(store.capture_artifact_blob(artifact, _payload(b"x\n1\n")))

        report = reconciliation.reconcile_bundle(bundle_id=bundle.pk)
        self.assertIsNotNone(report)
        bundle.refresh_from_db()
        self.assertEqual(bundle.status, BundleStatus.RECONCILED)
        self.assertFalse(MigrationArtifactBlob.objects.filter(artifact=artifact).exists())
        # Artifact metadata retained.
        self.assertTrue(MigrationArtifact.objects.filter(pk=artifact.pk).exists())
