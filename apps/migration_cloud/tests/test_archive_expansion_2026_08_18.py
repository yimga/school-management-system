"""An uploaded .zip must be expanded, not quarantined.

A live tenant uploaded ``archive.zip`` through the ordinary file-upload page and
got bundle status FAILED with ``profiler_error`` and the message "No workable
artifacts after profiling". Zipping your exports is the most natural way a school
sends its data, and it could never succeed.

The mechanism: ``_sniff_format`` correctly identifies the file and returns
``ARCHIVE``, with the comment "handled by archive_intake" -- but archive_intake
only runs on the dedicated ``IntakeMethod.ARCHIVE`` adapter. On the file-upload
path nothing expanded it, no reader matched ARCHIVE, so it quarantined; and
``has_workable`` EXCLUDES archive artifacts, so the bundle then failed for having
no workable files. ``expand_archive_artifacts`` closes that for every intake
method by expanding before the profiling loop.

The safety tests are not decoration. Members are operator-supplied bytes and
member NAMES are attacker-controlled strings, so traversal names must never be
registered and the expansion must stay bounded.
"""

from __future__ import annotations

import io
import zipfile

from django.test import SimpleTestCase, TestCase

from apps.migration_cloud.models import (
    ArtifactFormat,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.profiler import (
    _is_safe_archive_member,
    _iter_archive_members,
    expand_archive_artifacts,
)
from apps.schools.models import School


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in members.items():
            zf.writestr(name, payload)
    return buf.getvalue()


class ArchiveMemberSafetyTests(SimpleTestCase):
    def test_traversal_names_are_rejected(self):
        for bad in ("../escape.csv", "a/../../escape.csv", "/etc/passwd", "..\\win.csv"):
            self.assertFalse(_is_safe_archive_member(bad), bad)

    def test_directory_entries_are_rejected(self):
        self.assertFalse(_is_safe_archive_member("folder/"))
        self.assertFalse(_is_safe_archive_member(""))

    def test_ordinary_names_are_accepted(self):
        for good in ("students.csv", "exports/students.csv", "2026/term1/grades.xlsx"):
            self.assertTrue(_is_safe_archive_member(good), good)

    def test_zip_members_are_yielded(self):
        data = _zip_bytes({"students.csv": b"a,b\n1,2\n", "subjects.csv": b"x\n1\n"})
        got = dict(_iter_archive_members(io.BytesIO(data), "archive.zip"))
        self.assertEqual(set(got), {"students.csv", "subjects.csv"})
        self.assertEqual(got["students.csv"], b"a,b\n1,2\n")

    def test_traversal_member_is_not_yielded(self):
        data = _zip_bytes({"ok.csv": b"a\n1\n", "../evil.csv": b"x\n"})
        self.assertEqual(list(dict(_iter_archive_members(io.BytesIO(data), "a.zip"))), ["ok.csv"])

    def test_unsupported_archive_type_raises_a_usable_message(self):
        with self.assertRaises(ValueError) as ctx:
            list(_iter_archive_members(io.BytesIO(b"not an archive at all"), "mystery.7z"))
        self.assertIn("upload the CSV/Excel files directly", str(ctx.exception))


class ArchiveExpansionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Zip School",
            slug="zip-school",
            subdomain="zip-school",
            is_active=True,
        )
        self.bundle = MigrationBundle.objects.create(school=self.school)

    def _archive_artifact(self, payload: bytes, filename="archive.zip"):
        from apps.migration_cloud.artifact_blob_store import capture_artifact_blob
        from apps.migration_cloud.profiler import _ArchiveMemberPayload

        art = MigrationArtifact.objects.create(
            bundle=self.bundle,
            path_within_bundle=filename,
            filename=filename,
            byte_size=len(payload),
            sha256="z" * 64,
            locale_hints={},
            profile={},
        )
        capture_artifact_blob(art, _ArchiveMemberPayload(payload))
        return art

    def test_uploaded_zip_becomes_child_artifacts(self):
        art = self._archive_artifact(
            _zip_bytes({"students.csv": b"first_name,last_name\nAda,N\n"})
        )
        created = expand_archive_artifacts(self.bundle)
        self.assertEqual(created, 1, "the zip was not expanded — this is the bundle-82 bug")
        child = MigrationArtifact.objects.get(parent_archive=art)
        self.assertEqual(child.filename, "students.csv")
        art.refresh_from_db()
        self.assertEqual(art.detected_format, ArtifactFormat.ARCHIVE)
        self.assertFalse(art.quarantined, "the container itself must not be quarantined")

    def test_expansion_is_idempotent(self):
        self._archive_artifact(_zip_bytes({"students.csv": b"a\n1\n"}))
        expand_archive_artifacts(self.bundle)
        again = expand_archive_artifacts(self.bundle)
        self.assertEqual(again, 0, "re-running duplicated the archive members")
        self.assertEqual(MigrationArtifact.objects.filter(bundle=self.bundle).count(), 2)

    def test_corrupt_archive_quarantines_with_a_real_reason(self):
        art = self._archive_artifact(b"PK\x03\x04 truncated garbage", filename="broken.zip")
        expand_archive_artifacts(self.bundle)
        art.refresh_from_db()
        self.assertTrue(art.quarantined)
        self.assertIn("profiler_error", art.quarantine_reason)
        self.assertNotEqual(
            art.quarantine_reason.strip(),
            "profiler_error",
            "the reason must carry a cause, not just the category",
        )

    def test_non_archive_artifact_is_untouched(self):
        art = self._archive_artifact(b"first_name,last_name\nAda,N\n", filename="students.csv")
        self.assertEqual(expand_archive_artifacts(self.bundle), 0)
        art.refresh_from_db()
        self.assertFalse(art.quarantined)
