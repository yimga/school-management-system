"""Seal: malware scanning covers EVERY intake method, not just self-serve upload.

The AV gate lived only in services/intake_pipeline._validate_export_upload (the
self-serve HTTP path). Operator FILE_UPLOAD, URL/SFTP/S3, API_PULL, EMAIL,
DATABASE, ACCESS_DB and PDF reached the parser with no scan. capture_artifact_blob
-- the one chokepoint that captures the bytes every intake method will actually
apply -- now malware-scans them: unset scanner is a logged no-op; a DETECTION
quarantines the artifact and skips the blob (never store/apply malware).
"""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from apps.migration_cloud.artifact_blob_store import (
    _artifact_bytes_av_clean,
    capture_artifact_blob,
)
from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationArtifactBlob,
    MigrationBundle,
)
from apps.schools.models import School

_SCAN = "apps.security.upload_validation.scan_for_malware"


class _FakeArtifact:
    def __init__(self):
        self.pk = 1
        self.quarantined = False
        self.quarantine_reason = ""

    def save(self, **kwargs):
        pass


class ArtifactAvDecisionTests(SimpleTestCase):
    def test_unset_scanner_is_noop_clean(self):
        with override_settings(UPLOAD_MALWARE_SCANNER=None):
            self.assertTrue(_artifact_bytes_av_clean(_FakeArtifact(), b"anything"))

    def test_detection_quarantines_and_blocks(self):
        art = _FakeArtifact()
        with override_settings(UPLOAD_MALWARE_SCANNER="x"), \
                mock.patch(_SCAN, return_value=(False, "Win.Test.EICAR")):
            self.assertFalse(_artifact_bytes_av_clean(art, b"malware"))
        self.assertTrue(art.quarantined)
        self.assertIn("malware scan", art.quarantine_reason)

    def test_clean_bytes_pass(self):
        art = _FakeArtifact()
        with override_settings(UPLOAD_MALWARE_SCANNER="x"), \
                mock.patch(_SCAN, return_value=(True, "clean")):
            self.assertTrue(_artifact_bytes_av_clean(art, b"ok"))
        self.assertFalse(art.quarantined)

    def test_scanner_error_fails_open(self):
        with override_settings(UPLOAD_MALWARE_SCANNER="x"), \
                mock.patch(_SCAN, side_effect=RuntimeError("scanner down")):
            self.assertTrue(_artifact_bytes_av_clean(_FakeArtifact(), b"x"))


class ArtifactAvWiringTests(TestCase):
    def test_capture_quarantines_malicious_artifact(self):
        school = School.objects.create(
            name="Av", slug="av-seal", subdomain="av-seal",
            is_active=True, country_code="CM",
        )
        bundle = MigrationBundle.objects.create(
            label="av", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="av-1", status=BundleStatus.MAPPED, school=school,
        )
        artifact = MigrationArtifact.objects.create(
            bundle=bundle, path_within_bundle="roster.csv", filename="roster.csv",
            mime_type="text/csv", byte_size=7, sha256="0" * 64, encoding="utf-8",
            locale_hints={}, profile={},
        )
        payload = SimpleNamespace(content_opener=lambda: io.BytesIO(b"malware"))
        with override_settings(
            UPLOAD_MALWARE_SCANNER="x",
            MIGRATION_CLOUD_ARTIFACT_BLOB_STORE_ENABLED=True,
        ), mock.patch(_SCAN, return_value=(False, "Win.Test.EICAR")):
            stored = capture_artifact_blob(artifact, payload)
        self.assertFalse(stored)
        artifact.refresh_from_db()
        self.assertTrue(artifact.quarantined)
        # No blob was stored for the malicious artifact.
        self.assertEqual(
            MigrationArtifactBlob.objects.filter(artifact=artifact).count(), 0,
        )

    def test_capture_stores_clean_artifact(self):
        school = School.objects.create(
            name="Av2", slug="av-seal-2", subdomain="av-seal-2",
            is_active=True, country_code="CM",
        )
        bundle = MigrationBundle.objects.create(
            label="av2", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="av-2", status=BundleStatus.MAPPED, school=school,
        )
        artifact = MigrationArtifact.objects.create(
            bundle=bundle, path_within_bundle="ok.csv", filename="ok.csv",
            mime_type="text/csv", byte_size=5, sha256="1" * 64, encoding="utf-8",
            locale_hints={}, profile={},
        )
        payload = SimpleNamespace(content_opener=lambda: io.BytesIO(b"a,b\n1"))
        with override_settings(
            UPLOAD_MALWARE_SCANNER="x",
            MIGRATION_CLOUD_ARTIFACT_BLOB_STORE_ENABLED=True,
        ), mock.patch(_SCAN, return_value=(True, "clean")):
            stored = capture_artifact_blob(artifact, payload)
        self.assertTrue(stored)
        artifact.refresh_from_db()
        self.assertFalse(artifact.quarantined)
        self.assertEqual(
            MigrationArtifactBlob.objects.filter(artifact=artifact).count(), 1,
        )
