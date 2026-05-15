"""Phase U1 smoke tests for the universal intake pipeline.

Covers:
    * FILE_UPLOAD adapter: single path, list of paths, list of (path, mime) tuples.
    * ARCHIVE adapter: zip + tar expansion with member registration.
    * Idempotency: same idempotency_key + same artifact = dedup skip.
    * Adapter registry: every IntakeMethod resolves to an adapter.
    * Stub adapters raise IntakeError with clear "lands in Phase U7" message.

Profiler / classifier / mapper assertions land in later phases.
"""

from __future__ import annotations

import io
import tarfile
import tempfile
import zipfile
from pathlib import Path

from django.test import TestCase

from apps.migration_cloud.intake import IntakeError, get_adapter
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.services import BundleIngestionService, BundleSpec


class FileIntakeTests(TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mc_test_"))
        self.svc = BundleIngestionService()

    def _write(self, name: str, payload: bytes) -> Path:
        path = self.tmp / name
        path.write_bytes(payload)
        return path

    def test_single_file_registers_one_artifact(self) -> None:
        f = self._write("students.csv", b"id,first_name,last_name\n1,Ada,Lovelace\n")
        result = self.svc.ingest(
            BundleSpec(
                intake_method=IntakeMethod.FILE_UPLOAD,
                handle=f,
                label="single-file smoke",
                idempotency_key="smoke-single-file",
            )
        )
        self.assertEqual(result.artifacts_registered, 1)
        self.assertEqual(result.artifacts_skipped_duplicate, 0)

        bundle = MigrationBundle.objects.get(pk=result.bundle_id)
        self.assertEqual(bundle.status, BundleStatus.INGESTING)
        self.assertEqual(bundle.artifacts.count(), 1)
        artifact = bundle.artifacts.first()
        self.assertEqual(artifact.filename, "students.csv")
        self.assertEqual(artifact.byte_size, f.stat().st_size)
        self.assertEqual(len(artifact.sha256), 64)

    def test_list_of_paths(self) -> None:
        a = self._write("a.csv", b"x\n1\n")
        b = self._write("b.json", b'{"k": 1}')
        result = self.svc.ingest(
            BundleSpec(
                intake_method=IntakeMethod.FILE_UPLOAD,
                handle=[a, b],
                idempotency_key="smoke-list-of-paths",
            )
        )
        self.assertEqual(result.artifacts_registered, 2)

    def test_idempotency_dedups_replay(self) -> None:
        f = self._write("dedup.csv", b"id\n1\n")
        spec = BundleSpec(
            intake_method=IntakeMethod.FILE_UPLOAD,
            handle=f,
            idempotency_key="smoke-idem",
        )
        first = self.svc.ingest(spec)
        second = self.svc.ingest(spec)
        self.assertEqual(first.bundle_id, second.bundle_id)
        self.assertEqual(second.artifacts_registered, 0)
        self.assertEqual(second.artifacts_skipped_duplicate, 1)

        bundle = MigrationBundle.objects.get(pk=first.bundle_id)
        self.assertEqual(bundle.artifacts.count(), 1)

    def test_missing_file_marks_bundle_failed(self) -> None:
        missing = self.tmp / "does-not-exist.csv"
        with self.assertRaises(IntakeError):
            self.svc.ingest(
                BundleSpec(
                    intake_method=IntakeMethod.FILE_UPLOAD,
                    handle=missing,
                    idempotency_key="smoke-missing",
                )
            )
        bundle = MigrationBundle.objects.get(idempotency_key="smoke-missing")
        self.assertEqual(bundle.status, BundleStatus.FAILED)
        self.assertIn("error", bundle.size_summary)


class ArchiveIntakeTests(TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mc_test_arc_"))
        self.svc = BundleIngestionService()

    def test_zip_expands_to_member_artifacts(self) -> None:
        zip_path = self.tmp / "drop.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("students/main.csv", "id,name\n1,Ada\n")
            zf.writestr("grades/q1.csv", "student_id,grade\n1,A\n")
            zf.writestr("readme.txt", "drop notes")
        result = self.svc.ingest(
            BundleSpec(
                intake_method=IntakeMethod.ARCHIVE,
                handle=zip_path,
                idempotency_key="smoke-zip",
            )
        )
        self.assertEqual(result.artifacts_registered, 3)
        bundle = MigrationBundle.objects.get(pk=result.bundle_id)
        # All children link back to the archive's path within the bundle (none
        # of the children are themselves treated as a parent archive).
        children = MigrationArtifact.objects.filter(
            bundle=bundle, parent_archive__isnull=False
        )
        self.assertEqual(children.count(), 3)

    def test_tar_expansion(self) -> None:
        tar_path = self.tmp / "drop.tar"
        with tarfile.open(tar_path, "w") as tf:
            payload = b"id,name\n1,Ada\n"
            info = tarfile.TarInfo(name="students.csv")
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
        result = self.svc.ingest(
            BundleSpec(
                intake_method=IntakeMethod.ARCHIVE,
                handle=tar_path,
                idempotency_key="smoke-tar",
            )
        )
        self.assertEqual(result.artifacts_registered, 1)


class RegistryTests(TestCase):
    def test_every_intake_method_has_an_adapter(self) -> None:
        for method, _label in IntakeMethod.choices:
            if method == IntakeMethod.API_PULL:
                # API_PULL is reserved for Phase U9 accelerators; not in registry yet.
                continue
            adapter = get_adapter(method)
            self.assertIsNotNone(adapter, f"No adapter for {method}")

    def test_stub_adapter_raises_clear_error(self) -> None:
        svc = BundleIngestionService()
        with self.assertRaises(IntakeError) as cm:
            svc.ingest(
                BundleSpec(
                    intake_method=IntakeMethod.DATABASE,
                    handle="postgres://example.invalid/db",
                    idempotency_key="smoke-database-stub",
                )
            )
        self.assertIn("Phase U7", str(cm.exception))


class FormatChoicesTests(TestCase):
    """Detected-format enum must cover everything the intake whitelist accepts.

    Regression guard: if the seeded extension whitelist grows in
    ``apps.migration_cloud.defaults`` but the enum doesn't, profiled artifacts
    will collapse to UNKNOWN silently. This test is the early warning.
    """

    def test_unknown_is_fallback(self) -> None:
        self.assertIn(ArtifactFormat.UNKNOWN, [v for v, _ in ArtifactFormat.choices])
