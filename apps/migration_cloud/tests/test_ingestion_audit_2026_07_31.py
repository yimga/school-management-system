"""Ingestion-engine end-to-end audit fixes (2026-07-31).

Each class pins one gap the total-audit surfaced so the "uploaded / connected
data must land and become available in the tenant" contract cannot silently
regress:

  * G1 — the bulk-artifacts API captured metadata but DISCARDED the bytes, so
    apply read zero rows. Now every accepted upload's bytes are captured into the
    blob store and are readable by ``orchestrator._iter_canonical_rows``.
  * G2 — sandbox clone + multi-bundle merge created new artifact rows without
    copying the per-artifact blob (OneToOne on the original pk), so a clone/merge
    apply of a blob-backed artifact landed zero rows. Now the blob is cloned.
  * G3 — the connector import applied only the ~10-row preview SAMPLE. Now it
    re-extracts the FULL dataset when discovery counted more rows than staged.
  * G4 — the ``schedule`` domain was classifiable but had no lander (rows fell to
    the generic custom_fields fallback). Now an explicit DFV lander owns it.
  * G5 — ``fetch_assets_task`` lived in ``celery_tasks.py`` (not autodiscovered),
    so a broker worker silently dropped asset fetches. Now ``apps.ready()``
    registers it.
  * G6 — an artifact that reported bytes but captured none was silently skipped,
    so a MIXED bundle could go green APPLIED with some files contributing zero
    rows. Now such an artifact is quarantined visibly.
  * G7 — the remote-pull path used plain urllib with no retry; the resilient
    fetcher was built but unwired. Now transient failures retry.
"""

from __future__ import annotations

import io
import os
import tempfile
import types
from unittest import mock

from django.test import TestCase

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)


def _bundle(key: str, **kwargs) -> MigrationBundle:
    return MigrationBundle.objects.create(
        label=kwargs.pop("label", "audit bundle"),
        intake_method=kwargs.pop("intake_method", IntakeMethod.FILE_UPLOAD),
        idempotency_key=key,
        status=kwargs.pop("status", BundleStatus.INGESTING),
        **kwargs,
    )


def _artifact(bundle: MigrationBundle, *, path="students.csv", byte_size=0, fmt=ArtifactFormat.CSV):
    return MigrationArtifact.objects.create(
        bundle=bundle,
        path_within_bundle=path,
        filename=path,
        detected_format=fmt,
        byte_size=byte_size,
        sha256="0" * 64,
    )


class BulkArtifactsCaptureTests(TestCase):
    """G1 — bulk-artifacts upload now captures bytes → apply reads real rows."""

    def test_capture_upload_bytes_makes_artifact_applyable(self):
        from apps.migration_cloud.api.bulk_artifacts import _capture_upload_bytes
        from apps.migration_cloud.orchestrator import _ArtifactJob, _iter_canonical_rows

        data = b"name,age\nAda,36\nGrace,45\n"
        bundle = _bundle("g1-capture", intake_method=IntakeMethod.FILE_UPLOAD)
        # No intake_source_uri → the ONLY readable byte source is the blob (the
        # exact case the endpoint previously left empty).
        self.assertEqual(bundle.intake_source_uri, "")
        artifact = _artifact(bundle, byte_size=len(data))

        fd, tmp = tempfile.mkstemp(prefix="g1-", suffix=".csv")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            self.assertTrue(_capture_upload_bytes(artifact, tmp))
        finally:
            os.unlink(tmp)

        # Blob exists and round-trips.
        stream, _enc = store.open_artifact_blob_stream(artifact)
        self.assertIsNotNone(stream)
        self.assertEqual(stream.read(), data)

        # And apply now yields real rows (was zero before the fix).
        job = _ArtifactJob(
            artifact=artifact,
            domain="students",
            mappings=[
                {"source_column": "name", "canonical_field": "full_name"},
                {"source_column": "age", "canonical_field": "years"},
            ],
        )
        rows = list(_iter_canonical_rows(job))
        self.assertEqual([r["full_name"] for r in rows], ["Ada", "Grace"])

    def test_spool_and_hash_matches_sha256_helper(self):
        from apps.migration_cloud.api.bulk_artifacts import _safe_unlink, _spool_and_hash

        payload = b"hello bulk artifact 1234567890" * 8
        upload = types.SimpleNamespace(
            chunks=lambda chunk_size=65536: iter([payload[i:i + 7] for i in range(0, len(payload), 7)]),
            seek=lambda *_a, **_k: None,
        )
        tmp, digest, count, over = _spool_and_hash(upload, cap=10 * 1024 * 1024)
        try:
            self.assertFalse(over)
            self.assertEqual(count, len(payload))
            import hashlib

            self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
            with open(tmp, "rb") as fh:
                self.assertEqual(fh.read(), payload)
        finally:
            _safe_unlink(tmp)

    def test_spool_and_hash_flags_over_cap(self):
        from apps.migration_cloud.api.bulk_artifacts import _safe_unlink, _spool_and_hash

        payload = b"0123456789" * 4  # 40 bytes
        upload = types.SimpleNamespace(
            chunks=lambda chunk_size=65536: iter([payload]),
            seek=lambda *_a, **_k: None,
        )
        tmp, _digest, _count, over = _spool_and_hash(upload, cap=8)
        try:
            self.assertTrue(over)
        finally:
            _safe_unlink(tmp)


class BlobCloneTests(TestCase):
    """G2 — sandbox clone + merge copy the per-artifact blob to the new rows."""

    def test_sandbox_clone_copies_blob(self):
        from apps.migration_cloud.sandbox import clone_bundle_to_sandbox

        data = b"student,grade\nAda,A\nGrace,B\n"
        bundle = _bundle("g2-sandbox", status=BundleStatus.MAPPED)
        artifact = _artifact(bundle, byte_size=len(data))
        self.assertTrue(store.capture_artifact_blob(artifact, _opener_payload(data)))

        clone = clone_bundle_to_sandbox(bundle=bundle)
        clone_artifact = clone.artifacts.get(path_within_bundle="students.csv")
        self.assertNotEqual(clone_artifact.pk, artifact.pk)

        stream, _enc = store.open_artifact_blob_stream(clone_artifact)
        self.assertIsNotNone(stream)
        self.assertEqual(stream.read(), data)

    def test_merge_copies_blob(self):
        from apps.migration_cloud.tier3 import merge_bundles

        data = b"student,grade\nAda,A\n"
        bundle = _bundle("g2-merge", status=BundleStatus.MAPPED)
        artifact = _artifact(bundle, byte_size=len(data))
        self.assertTrue(store.capture_artifact_blob(artifact, _opener_payload(data)))

        parent = merge_bundles(bundles=[bundle], label="merged")
        # merge rewrites the path to ``{child.pk}::<path>``.
        merged_artifact = parent.artifacts.get(
            path_within_bundle=f"{bundle.pk}::students.csv"
        )
        stream, _enc = store.open_artifact_blob_stream(merged_artifact)
        self.assertIsNotNone(stream)
        self.assertEqual(stream.read(), data)


class ConnectorFullExtractTests(TestCase):
    """G3 — connector import re-extracts the FULL dataset, not the preview sample."""

    def _batch(self, *, staged, estimated):
        discovery_run = None
        if estimated is not None:
            discovery_run = types.SimpleNamespace(counts_by_entity={"students": estimated})
        return types.SimpleNamespace(
            staged_rows=staged, entity_type="students", discovery_run=discovery_run
        )

    def test_reextracts_full_when_discovery_saw_more(self):
        from apps.migration_cloud.services import connector_import

        batch = self._batch(staged=[{"i": 0}], estimated=5)
        full = [{"i": i} for i in range(5)]
        with mock.patch(
            "apps.migration_cloud.services.connector_discovery.fetch_all_records",
            return_value=full,
        ) as fetch:
            rows = connector_import._resolve_import_rows(connection=object(), staging_batch=batch)
        fetch.assert_called_once()
        self.assertEqual(len(rows), 5)

    def test_uses_staged_when_no_discovery_count(self):
        from apps.migration_cloud.services import connector_import

        batch = self._batch(staged=[{"i": 0}], estimated=None)
        with mock.patch(
            "apps.migration_cloud.services.connector_discovery.fetch_all_records",
        ) as fetch:
            rows = connector_import._resolve_import_rows(connection=object(), staging_batch=batch)
        fetch.assert_not_called()
        self.assertEqual(rows, [{"i": 0}])

    def test_falls_back_to_staged_when_reextract_fails(self):
        from apps.migration_cloud.services import connector_import

        batch = self._batch(staged=[{"i": 0}], estimated=99)
        with mock.patch(
            "apps.migration_cloud.services.connector_discovery.fetch_all_records",
            side_effect=RuntimeError("network down"),
        ):
            rows = connector_import._resolve_import_rows(connection=object(), staging_batch=batch)
        self.assertEqual(rows, [{"i": 0}])

    def test_never_imports_fewer_than_staged(self):
        from apps.migration_cloud.services import connector_import

        batch = self._batch(staged=[{"i": 0}, {"i": 1}], estimated=99)
        with mock.patch(
            "apps.migration_cloud.services.connector_discovery.fetch_all_records",
            return_value=[],  # re-extract returned nothing → keep the staged floor
        ):
            rows = connector_import._resolve_import_rows(connection=object(), staging_batch=batch)
        self.assertEqual(len(rows), 2)


class ScheduleLanderTests(TestCase):
    """G4 — the schedule domain now has a registered (DFV) lander."""

    def test_schedule_domain_has_a_lander(self):
        from apps.migration_cloud.landers import get_lander

        lander = get_lander("schedule")
        self.assertIsNotNone(lander)
        self.assertEqual(lander.domain, "schedule")

    def test_schedule_lander_preserves_rows_and_quarantines_bad(self):
        from apps.migration_cloud.landers import get_lander
        from apps.migration_cloud.landers.base import LanderContext
        from apps.schools.models import School

        school = School.objects.create(
            name="Sched", slug="sched-audit", subdomain="sched-audit"
        )
        lander = get_lander("schedule")
        ctx = LanderContext(
            school=school, schema_name="", bundle_id=1, artifact_id=1, dry_run=False
        )
        rows = [
            {"section_external_id": "SEC-A", "day_of_week": "Monday", "start_time": "08:30", "room": "R1"},
            {"section_external_id": "SEC-A", "day_of_week": "Tuesday", "start_time": "09:30", "room": "R2"},
            {"day_of_week": "Monday", "start_time": "08:30"},  # missing section → quarantine
        ]
        result = lander.land(canonical_rows=iter(rows), ctx=ctx)
        self.assertEqual(result.created, 2)
        self.assertEqual(result.quarantined, 1)


class CeleryTaskRegistrationTests(TestCase):
    """G5 — fetch_assets_task is registered (apps.ready imports celery_tasks)."""

    def test_fetch_assets_task_is_registered(self):
        from celery import current_app

        self.assertIn("migration_cloud.fetch_assets", current_app.tasks)


class CaptureHonestyTests(TestCase):
    """G6 — an artifact that reported bytes but captured none is quarantined."""

    def test_empty_capture_with_reported_bytes_quarantines(self):
        bundle = _bundle("g6-empty")
        artifact = _artifact(bundle, byte_size=42)  # claims 42 bytes …
        wrote = store.capture_artifact_blob(artifact, _opener_payload(b""))  # … but none arrive
        self.assertFalse(wrote)
        artifact.refresh_from_db()
        self.assertTrue(artifact.quarantined)
        self.assertIn("could not be captured", artifact.quarantine_reason)

    def test_no_opener_with_reported_bytes_quarantines(self):
        bundle = _bundle("g6-no-opener")
        artifact = _artifact(bundle, byte_size=42)
        wrote = store.capture_artifact_blob(artifact, types.SimpleNamespace())
        self.assertFalse(wrote)
        artifact.refresh_from_db()
        self.assertTrue(artifact.quarantined)

    def test_zero_byte_artifact_stays_silent(self):
        bundle = _bundle("g6-zero")
        artifact = _artifact(bundle, byte_size=0)  # genuinely empty → nothing to capture
        wrote = store.capture_artifact_blob(artifact, _opener_payload(b""))
        self.assertFalse(wrote)
        artifact.refresh_from_db()
        self.assertFalse(artifact.quarantined)


class RemoteFetchResilienceTests(TestCase):
    """G7 — transient remote-pull failures retry (network_resilience wired in)."""

    def test_transient_http_failure_retries_then_succeeds(self):
        from apps.migration_cloud.intake import url_intake

        calls = {"n": 0}

        def _flaky(url, dest, max_bytes):
            calls["n"] += 1
            if calls["n"] < 3:
                raise url_intake._TransientFetchError("blip")
            dest.write_bytes(b"col\nval\n")

        with mock.patch.object(url_intake, "_fetch_http", _flaky), \
             mock.patch("apps.migration_cloud.network_resilience.time.sleep", lambda *_a, **_k: None):
            path = url_intake._fetch_to_tempfile("https://x.example/file.csv", "https", 1_000_000)
        try:
            self.assertEqual(calls["n"], 3)
            self.assertEqual(path.read_bytes(), b"col\nval\n")
        finally:
            path.unlink(missing_ok=True)

    def test_cap_exceeded_is_not_retried(self):
        from apps.migration_cloud.intake import url_intake
        from apps.migration_cloud.intake.base import IntakeError

        calls = {"n": 0}

        def _too_big(url, dest, max_bytes):
            calls["n"] += 1
            raise IntakeError("Download exceeded artifact cap (8 bytes).")

        with mock.patch.object(url_intake, "_fetch_http", _too_big), \
             mock.patch("apps.migration_cloud.network_resilience.time.sleep", lambda *_a, **_k: None):
            with self.assertRaises(IntakeError):
                url_intake._fetch_to_tempfile("https://x.example/file.csv", "https", 8)
        # Permanent failure → exactly one attempt, no retry storm.
        self.assertEqual(calls["n"], 1)


def _opener_payload(data: bytes):
    """Minimal ArtifactPayload stand-in — the store only reads content_opener."""
    return types.SimpleNamespace(content_opener=lambda: io.BytesIO(data))
