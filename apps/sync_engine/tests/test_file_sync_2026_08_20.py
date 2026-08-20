"""G3: files never crossed the boundary at all, and nothing said so.

``_derive_sync_fields`` drops every ``FileField`` — correctly, because a delta bundle
carries column VALUES and a synced path would point the far side at a file it does not
have, so the apply would report a clean 200 over a broken reference. The consequence was
absolute: student photos, scanned report cards and payment proofs simply did not exist
across the boundary, and every sync status read green while they did not.

The acceptance criterion from the brief is the one worth proving: a large attachment
survives repeated connection drops and lands with a matching hash, while the data rail is
never delayed by it. So the tests below are mostly about the two properties that make
that true on a bad link — RESUME (bytes already transferred are never re-sent) and
VERIFY (nothing is committed to storage until the whole file hashes correctly) — plus the
authorisation boundary, because a path parameter used to read a file is a traversal hole
unless something constrains it.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from apps.accounts.models import User
from apps.api.sync_files_api import (
    FILE_OFFSET_HEADER,
    FILE_PATH_HEADER,
    FILE_SHA256_HEADER,
    FILE_SIZE_HEADER,
    SyncFileChunkView,
    SyncFileManifestView,
)
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.edge_outbox import mint_edge_credential
from apps.sync_engine.file_manifest import build_manifest, file_stat, servable_paths
from apps.sync_engine.models import SyncFileTransfer


class _FileFixture(TestCase):
    """A real student with a real stored photo, in a throwaway MEDIA_ROOT."""

    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="rmc-filesync-")
        self._override = override_settings(MEDIA_ROOT=self.media)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(shutil.rmtree, self.media, True)

        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"File {uid}", slug=f"file-{uid}", subdomain=f"file{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"file_{uid}", password="Test1234", email=f"fi{uid}@t.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.token, _obj = mint_edge_credential(
            self.school, self.user, device_id="file-box", days=30
        )
        self.rf = APIRequestFactory()

        self.payload = b"photo-bytes-" * 5000  # ~60 KB, several chunks at a small size
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="N", student_code=f"S-{uid}"
        )
        self.student.profile_photo.save(f"ada-{uid}.jpg", ContentFile(self.payload), save=True)
        self.path = self.student.profile_photo.name


class ManifestTests(_FileFixture):
    def test_the_manifest_lists_the_file_with_its_hash_and_size(self):
        entries = {e["path"]: e for e in build_manifest(self.school)}
        self.assertIn(self.path, entries)
        self.assertEqual(entries[self.path]["sha256"], self.sha)
        self.assertEqual(entries[self.path]["size"], len(self.payload))

    def test_a_row_that_references_a_missing_file_is_not_offered(self):
        """Shipping a manifest entry the far side can never fetch produces a transfer that
        retries forever and a queue that never drains."""
        default_storage.delete(self.path)
        self.assertNotIn(self.path, {e["path"] for e in build_manifest(self.school)})

    def test_another_school_s_files_are_not_servable(self):
        other = School.objects.create(name="Oth", slug="oth-fs", subdomain="othfs")
        self.assertNotIn(self.path, servable_paths(other))

    def test_the_endpoint_returns_the_manifest(self):
        request = self.rf.get(
            "/api/v1/sync/files/manifest/", HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        resp = SyncFileManifestView.as_view()(request)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["ok"])
        self.assertIn(self.path, {f["path"] for f in resp.data["files"]})


class ChunkDownloadTests(_FileFixture):
    def _chunk(self, offset, length):
        request = self.rf.get(
            f"/api/v1/sync/files/chunk/?path={self.path}&offset={offset}&length={length}",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        return SyncFileChunkView.as_view()(request)

    def test_a_range_is_served_with_the_whole_file_hash(self):
        resp = self._chunk(0, 1000)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, self.payload[:1000])
        self.assertEqual(resp[FILE_SHA256_HEADER], self.sha)
        self.assertEqual(resp[FILE_SIZE_HEADER], str(len(self.payload)))

    def test_reassembling_every_range_reproduces_the_file_exactly(self):
        got, offset = b"", 0
        while offset < len(self.payload):
            resp = self._chunk(offset, 4096)
            got += resp.content
            offset += len(resp.content)
            if not resp.content:
                break
        self.assertEqual(hashlib.sha256(got).hexdigest(), self.sha)

    def test_a_path_that_is_not_this_school_s_is_refused(self):
        """The authorisation boundary. A path parameter used to read a file is a traversal
        hole unless something constrains it, and the constraint is membership of THIS
        school's own file set — which cannot be argued into ../../secrets."""
        request = self.rf.get(
            "/api/v1/sync/files/chunk/?path=../../etc/passwd",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        resp = SyncFileChunkView.as_view()(request)
        self.assertEqual(resp.status_code, 404)

    def test_not_yours_and_does_not_exist_answer_identically(self):
        """Distinguishing them turns the endpoint into a probe for other tenants' filenames."""
        missing = self.rf.get(
            "/api/v1/sync/files/chunk/?path=nope/nothing.jpg",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        traversal = self.rf.get(
            "/api/v1/sync/files/chunk/?path=../../etc/passwd",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        a = SyncFileChunkView.as_view()(missing)
        b = SyncFileChunkView.as_view()(traversal)
        self.assertEqual((a.status_code, a.data), (b.status_code, b.data))


class ChunkUploadTests(_FileFixture):
    def _send(self, offset, body, *, sha=None, size=None, path=None):
        request = self.rf.post(
            "/api/v1/sync/files/chunk/",
            data=body,
            content_type="application/octet-stream",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            **{
                "HTTP_" + FILE_PATH_HEADER.upper().replace("-", "_"): path or self.path,
                "HTTP_" + FILE_OFFSET_HEADER.upper().replace("-", "_"): str(offset),
                "HTTP_" + FILE_SHA256_HEADER.upper().replace("-", "_"): sha if sha is not None else self.sha,
                "HTTP_" + FILE_SIZE_HEADER.upper().replace("-", "_"): str(
                    size if size is not None else len(self.payload)
                ),
            },
        )
        return SyncFileChunkView.as_view()(request)

    def test_a_file_uploaded_in_pieces_lands_intact(self):
        step = 8192
        for offset in range(0, len(self.payload), step):
            resp = self._send(offset, self.payload[offset:offset + step])
            self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data["complete"])
        self.assertEqual(file_stat(self.path)[1], self.sha)

    def test_an_interrupted_upload_resumes_where_it_stopped(self):
        """The property that makes an intermittent link converge at all: a transfer that
        restarts from zero on every drop never finishes."""
        half = len(self.payload) // 2
        first = self._send(0, self.payload[:half])
        self.assertFalse(first.data["complete"])
        self.assertEqual(first.data["bytes_received"], half)

        second = self._send(half, self.payload[half:])
        self.assertTrue(second.data["complete"])
        self.assertEqual(second.data["sha256"], self.sha)

    def test_a_wrong_offset_is_answered_with_the_right_one(self):
        """Writing at a wrong offset would leave a hole, the hash would fail at the end,
        and the whole transfer would restart — on a bad link, forever."""
        self._send(0, self.payload[:100])
        resp = self._send(9999, self.payload[100:200])
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["expected_offset"], 100)

    def test_a_corrupted_transfer_is_refused_and_never_committed(self):
        """A truncated file that reached storage is indistinguishable from a good one
        afterwards — and would be served to a parent as their child's report card."""
        before = file_stat(self.path)[1]
        corrupt = bytearray(self.payload)
        corrupt[0] ^= 0xFF
        resp = self._send(0, bytes(corrupt))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["error"], "hash_mismatch")
        self.assertEqual(file_stat(self.path)[1], before, "the bad bytes were committed")

    def test_an_upload_to_an_unknown_path_is_refused(self):
        resp = self._send(0, b"x", path="somewhere/else.jpg")
        self.assertEqual(resp.status_code, 404)

    @override_settings(RMC_SYNC_FILE_MAX_BYTES=10)
    def test_an_absurd_declared_size_is_refused_outright(self):
        resp = self._send(0, b"x", size=10_000_000)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["error"], "file_too_large")


class QueueTests(_FileFixture):
    def test_a_file_the_box_already_has_byte_for_byte_is_not_queued(self):
        from apps.sync_engine.file_sync import enqueue_from_manifest

        out = enqueue_from_manifest(
            self.school, [{"path": self.path, "sha256": self.sha, "size": len(self.payload)}]
        )
        self.assertEqual(out, {"queued": 0, "already_current": 1})

    def test_a_file_whose_CONTENT_differs_is_re_queued(self):
        """Comparing by presence rather than content would leave a half-written or stale
        copy in place forever while reporting a clean sync."""
        from apps.sync_engine.file_sync import enqueue_from_manifest

        out = enqueue_from_manifest(
            self.school, [{"path": self.path, "sha256": "0" * 64, "size": 123}]
        )
        self.assertEqual(out["queued"], 1)
        row = SyncFileTransfer.objects.get(school=self.school, relative_path=self.path)
        self.assertEqual(row.direction, SyncFileTransfer.PULL)
        self.assertEqual(row.state, SyncFileTransfer.State.PENDING)

    def test_a_local_file_the_cloud_does_not_have_is_queued_for_upload(self):
        from apps.sync_engine.file_sync import enqueue_local_only

        out = enqueue_local_only(self.school, [])
        self.assertGreaterEqual(out["queued"], 1)
        self.assertTrue(
            SyncFileTransfer.objects.filter(
                school=self.school, direction=SyncFileTransfer.PUSH, relative_path=self.path
            ).exists()
        )

    def test_the_queue_is_scoped_to_one_school(self):
        from apps.sync_engine.file_sync import enqueue_from_manifest

        other = School.objects.create(name="Oth", slug="oth-q", subdomain="othq")
        enqueue_from_manifest(other, [{"path": self.path, "sha256": "0" * 64, "size": 1}])
        self.assertEqual(
            SyncFileTransfer.objects.filter(school=self.school).count(), 0
        )

    def test_a_pass_with_an_unreachable_cloud_reports_instead_of_raising(self):
        """Files are a background concern. A failure here must surface as a report, not as
        an exception that takes down whatever scheduled it."""
        from apps.sync_engine.file_sync import run_file_sync_pass

        result = run_file_sync_pass(
            self.school,
            manifest_endpoint="http://127.0.0.1:1/manifest/",
            chunk_endpoint="http://127.0.0.1:1/chunk/",
            token="x",
        )
        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])

    @override_settings(RMC_SYNC_FILE_TRANSFER_ENABLED=False)
    def test_the_kill_switch_stops_the_pass_cleanly(self):
        from apps.sync_engine.file_sync import run_file_sync_pass

        result = run_file_sync_pass(
            self.school, manifest_endpoint="x", chunk_endpoint="y", token="z"
        )
        self.assertFalse(result["ok"])
        self.assertIn("disabled", result["message"])


class StagingTests(_FileFixture):
    def test_the_staging_path_is_deterministic(self):
        """A random temp name would silently restart every resume at zero, which on an
        intermittent link means the file never arrives."""
        from apps.api.sync_files_api import staging_path

        a = staging_path(self.school.pk, self.path)
        b = staging_path(self.school.pk, self.path)
        self.assertEqual(a, b)
        self.assertTrue(os.path.isdir(os.path.dirname(a)))

    def test_two_schools_never_share_a_staging_file(self):
        from apps.api.sync_files_api import staging_path

        self.assertNotEqual(
            staging_path("school-a", self.path), staging_path("school-b", self.path)
        )


class DownloadVerificationTests(_FileFixture):
    """A download is only real once it hashes. Anything less must not reach storage."""

    def _transfer(self, sha):
        return SyncFileTransfer.objects.create(
            school=self.school,
            direction=SyncFileTransfer.PULL,
            relative_path=self.path,
            sha256=sha,
            size_bytes=len(self.payload),
        )

    def test_an_unverifiable_download_is_parked_not_committed(self):
        """No declared hash means nothing to verify against. Committing anyway would let
        a truncated or empty transfer overwrite a real file with no way to tell after."""
        from unittest import mock

        from apps.sync_engine import file_sync

        before = file_stat(self.path)[1]
        transfer = self._transfer("")
        with mock.patch.object(
            file_sync, "fetch_chunk",
            return_value=(200, b"short", {"size": 5, "sha256": "", "complete": True}),
        ):
            ok, reason = file_sync.download_one(transfer, "http://x/chunk/", "tok")

        self.assertFalse(ok)
        self.assertEqual(reason, "unverifiable")
        self.assertEqual(file_stat(self.path)[1], before, "unverified bytes reached storage")

    def test_a_hash_mismatch_discards_the_staging_copy(self):
        """Resuming on top of corrupted bytes would never converge."""
        from unittest import mock

        from apps.sync_engine import file_sync

        before = file_stat(self.path)[1]
        transfer = self._transfer("0" * 64)
        with mock.patch.object(
            file_sync, "fetch_chunk",
            return_value=(200, b"wrong", {"size": 5, "sha256": "0" * 64, "complete": True}),
        ):
            ok, reason = file_sync.download_one(transfer, "http://x/chunk/", "tok")

        self.assertFalse(ok)
        self.assertEqual(reason, "hash_mismatch")
        transfer.refresh_from_db()
        self.assertEqual(transfer.bytes_done, 0, "a corrupted transfer must restart clean")
        self.assertEqual(file_stat(self.path)[1], before)

    def test_a_verified_download_replaces_the_file(self):
        from unittest import mock

        from apps.sync_engine import file_sync

        new_payload = b"replacement-bytes" * 100
        new_sha = hashlib.sha256(new_payload).hexdigest()
        transfer = self._transfer(new_sha)
        with mock.patch.object(
            file_sync, "fetch_chunk",
            return_value=(200, new_payload, {"size": len(new_payload), "sha256": new_sha,
                                             "complete": True}),
        ):
            ok, reason = file_sync.download_one(transfer, "http://x/chunk/", "tok")

        self.assertTrue(ok, reason)
        self.assertEqual(file_stat(self.path)[1], new_sha)
        transfer.refresh_from_db()
        self.assertEqual(transfer.state, SyncFileTransfer.State.DONE)
