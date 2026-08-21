"""P0-B — companion decrypt must register artifacts + kick advance."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.services.companion_plaintext_ingest import (
    guess_filename_and_method,
    ingest_companion_plaintext,
)


class GuessFilenameTests(SimpleTestCase):
    def test_zip_magic(self):
        name, method = guess_filename_and_method(b"PK\x03\x04" + b"\x00" * 20)
        self.assertTrue(name.endswith(".zip"))
        self.assertEqual(method, IntakeMethod.ARCHIVE)

    def test_pdf_magic(self):
        name, method = guess_filename_and_method(b"%PDF-1.4\n%")
        self.assertTrue(name.endswith(".pdf"))
        self.assertEqual(method, IntakeMethod.FILE_UPLOAD)

    def test_json_object(self):
        name, method = guess_filename_and_method(b'{"students":[]}')
        self.assertTrue(name.endswith(".json"))

    def test_csv_default(self):
        name, method = guess_filename_and_method(b"external_id,first_name\n1,Ada\n")
        self.assertTrue(name.endswith(".csv"))
        self.assertEqual(method, IntakeMethod.FILE_UPLOAD)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="mc-p0b-"))
class IngestCompanionPlaintextTests(TestCase):
    def setUp(self):
        self.bundle = MigrationBundle.objects.create(
            label="companion p0b",
            intake_method=IntakeMethod.FILE_UPLOAD,
            intake_source_uri="companion://test/abc",
            idempotency_key=f"companion:p0b-{self.id()}",
            status=BundleStatus.PENDING,
            schema_name="public",
        )

    def test_registers_artifact_and_advances(self):
        csv_bytes = b"external_id,first_name,last_name\ns1,Ada,Lovelace\n"
        with mock.patch(
            "apps.migration_cloud.services.companion_plaintext_ingest._enqueue_or_inline_advance"
        ) as adv:
            summary = ingest_companion_plaintext(
                bundle=self.bundle, plaintext=csv_bytes
            )
            adv.assert_called_once_with(self.bundle.pk)
        self.assertFalse(summary["replay"])
        self.assertGreaterEqual(summary["artifacts_registered"], 1)
        self.bundle.refresh_from_db()
        self.assertGreaterEqual(self.bundle.artifacts.count(), 1)
        self.assertIn("(decrypted)", self.bundle.intake_source_uri)

    def test_replay_when_artifacts_already_present(self):
        from apps.migration_cloud.models import MigrationArtifact

        MigrationArtifact.objects.create(
            bundle=self.bundle,
            path_within_bundle="already.csv",
            filename="already.csv",
            byte_size=10,
            sha256="a" * 64,
        )
        with mock.patch(
            "apps.migration_cloud.services.companion_plaintext_ingest._enqueue_or_inline_advance"
        ) as adv:
            summary = ingest_companion_plaintext(
                bundle=self.bundle, plaintext=b"external_id\n1\n"
            )
            adv.assert_called_once()
        self.assertTrue(summary["replay"])
        self.assertEqual(summary["artifacts_registered"], 0)

    def test_empty_plaintext_raises(self):
        with self.assertRaises(ValueError):
            ingest_companion_plaintext(bundle=self.bundle, plaintext=b"")

    def test_ingest_summary_has_no_plaintext_fields(self):
        marker = b"NEVER-LOG-THIS-COMPANION-PLAINTEXT-MARKER-XYZ"
        csv = b"external_id,note\n1," + marker + b"\n"
        with mock.patch(
            "apps.migration_cloud.services.companion_plaintext_ingest._enqueue_or_inline_advance"
        ):
            summary = ingest_companion_plaintext(bundle=self.bundle, plaintext=csv)
        self.assertNotIn(marker.decode("ascii"), repr(summary))
        self.assertIn("artifacts_registered", summary)


class DecryptHookWiresIngestTests(SimpleTestCase):
    def test_decrypt_view_calls_ingest_companion_plaintext(self):
        module = Path("apps/migration_cloud/companion_receiver.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ingest_companion_plaintext", module)
        self.assertIn("ingest_after_decrypt_failed", module)
        # Old theatre path that flipped INGESTING without artifacts must be gone.
        self.assertNotIn(
            'bundle.save(update_fields=["intake_source_uri", "status", "started_at", "updated_at"])',
            module,
        )
