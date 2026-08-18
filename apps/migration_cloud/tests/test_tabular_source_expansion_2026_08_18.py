"""Formats the engine claims to detect must actually be readable.

``ArtifactFormat`` declares fourteen formats and ``_sniff_format`` detects all of
them, but ``_read_sample`` only dispatches CSV/TSV/JSON/JSONL/XLSX/XLS/PDF. XML,
SQL, SQLITE and PARQUET fell through to ``return [], [], encoding`` -- no rows, no
headers, and NO ERROR. The artifact profiled as empty, the classifier saw nothing,
and the school was told its file was fine while it contributed exactly nothing.
Silence is worse than failure here: a quarantine reason at least tells you to act.

Two of those are ordinary school exports rather than exotica:

  * **XML** is what older on-premise SIS packages emit.
  * **SQLite** (``.db`` / ``.sqlite3``) is what a desktop system hands you when
    the school asks IT for "the database" -- and ``DatabaseIntakeAdapter`` has
    always been able to export its tables to CSV, but only via the DATABASE
    intake method. Upload the same file through the web form and nothing ran it,
    exactly the shape of the archive.zip defect.

Whatever stays unreadable must SAY so, in words that name the next step.
"""

from __future__ import annotations

import io
import sqlite3
import tempfile
from pathlib import Path

from django.test import TestCase

from apps.migration_cloud.models import (
    ArtifactFormat,
    MigrationArtifact,
    MigrationBundle,
)
from apps.schools.models import School

XML_EXPORT = b"""<?xml version="1.0" encoding="UTF-8"?>
<students>
  <student><full_name>ANDONGMAD FAVOUR</full_name><date_of_birth>2012-01-25</date_of_birth></student>
  <student><full_name>AWA BERTRAND</full_name><date_of_birth>2011-06-03</date_of_birth></student>
</students>
"""

# The billion-laughs bomb. An uploaded file is operator-supplied bytes, so the
# parser must refuse it rather than expand it in memory.
XML_BOMB = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<lolz>&lol3;</lolz>
"""


def _sqlite_bytes() -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "school.db"
        conn = sqlite3.connect(path)
        try:
            conn.execute("CREATE TABLE students (full_name TEXT, date_of_birth TEXT)")
            conn.executemany(
                "INSERT INTO students VALUES (?, ?)",
                [("ANDONGMAD FAVOUR", "2012-01-25"), ("AWA BERTRAND", "2011-06-03")],
            )
            conn.execute("CREATE TABLE subjects (name TEXT)")
            conn.execute("INSERT INTO subjects VALUES ('Mathematics')")
            conn.commit()
        finally:
            conn.close()
        return path.read_bytes()


class _Payload:
    """Minimal payload shim: ``capture_artifact_blob`` wants a content_opener."""

    def __init__(self, data: bytes):
        self._data = data

    def content_opener(self):
        return io.BytesIO(self._data)


class TabularSourceBase(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Format School",
            slug="format-school",
            subdomain="format-school",
            is_active=True,
        )
        self.bundle = MigrationBundle.objects.create(school=self.school)

    def _artifact(self, payload: bytes, filename: str):
        from apps.migration_cloud.artifact_blob_store import capture_artifact_blob

        art = MigrationArtifact.objects.create(
            bundle=self.bundle,
            path_within_bundle=filename,
            filename=filename,
            byte_size=len(payload),
            sha256=f"{abs(hash(filename)):064x}"[:64],
            locale_hints={},
            profile={},
        )
        capture_artifact_blob(art, _Payload(payload))
        return art


class XmlReadingTests(TabularSourceBase):
    def test_an_xml_export_yields_rows_and_headers(self):
        from apps.migration_cloud.profiler import _read_sample

        art = self._artifact(XML_EXPORT, "students.xml")
        art.detected_format = ArtifactFormat.XML
        art.save(update_fields=["detected_format"])
        rows, headers, _enc = _read_sample(art)
        self.assertEqual(
            [h.lower() for h in headers],
            ["full_name", "date_of_birth"],
            "an XML export profiled as having no columns at all",
        )
        self.assertEqual(len(rows), 2)
        self.assertIn("ANDONGMAD FAVOUR", [str(c) for c in rows[0]])

    def test_an_xml_bomb_is_refused_rather_than_expanded(self):
        from apps.migration_cloud.profiler import _read_sample

        art = self._artifact(XML_BOMB, "bomb.xml")
        art.detected_format = ArtifactFormat.XML
        art.save(update_fields=["detected_format"])
        rows, headers, _enc = _read_sample(art)
        self.assertEqual(rows, [])
        self.assertEqual(headers, [])


class SqliteExpansionTests(TabularSourceBase):
    def test_an_uploaded_sqlite_file_becomes_one_artifact_per_table(self):
        from apps.migration_cloud.profiler import expand_tabular_source_artifacts

        art = self._artifact(_sqlite_bytes(), "school.db")
        created = expand_tabular_source_artifacts(self.bundle)
        self.assertEqual(
            created, 2, "the uploaded database contributed no tables at all"
        )
        children = MigrationArtifact.objects.filter(parent_archive=art)
        self.assertEqual(
            {c.filename for c in children}, {"students.csv", "subjects.csv"}
        )
        students = children.get(filename="students.csv")
        from apps.migration_cloud.profiler import _read_sample

        students.detected_format = ArtifactFormat.CSV
        rows, headers, _enc = _read_sample(students)
        self.assertEqual([h.lower() for h in headers], ["full_name", "date_of_birth"])
        self.assertEqual(len(rows), 2)

    def test_expansion_is_idempotent(self):
        from apps.migration_cloud.profiler import expand_tabular_source_artifacts

        self._artifact(_sqlite_bytes(), "school.db")
        expand_tabular_source_artifacts(self.bundle)
        again = expand_tabular_source_artifacts(self.bundle)
        self.assertEqual(again, 0, "re-running duplicated every table")

    def test_a_corrupt_database_quarantines_with_a_real_reason(self):
        from apps.migration_cloud.profiler import expand_tabular_source_artifacts

        art = self._artifact(b"SQLite format 3\x00 truncated garbage", "broken.db")
        expand_tabular_source_artifacts(self.bundle)
        art.refresh_from_db()
        self.assertTrue(art.quarantined)
        self.assertIn("profiler_error", art.quarantine_reason)


class UnreadableFormatsSpeakUpTests(TabularSourceBase):
    """Whatever cannot be parsed must say what to do instead."""

    def test_a_parquet_upload_is_not_silently_empty(self):
        from apps.migration_cloud.profiler import unreadable_format_reason

        reason = unreadable_format_reason(ArtifactFormat.PARQUET, "data.parquet")
        self.assertTrue(reason, "parquet profiled empty with no explanation")
        self.assertIn("CSV", reason, "the message must name a format that works")

    def test_a_readable_format_has_no_complaint(self):
        self._assert_silent(ArtifactFormat.CSV)
        self._assert_silent(ArtifactFormat.XLSX)
        self._assert_silent(ArtifactFormat.XML)

    def _assert_silent(self, fmt):
        from apps.migration_cloud.profiler import unreadable_format_reason

        self.assertEqual(unreadable_format_reason(fmt, "f"), "", fmt)

    def test_legacy_xls_without_its_reader_says_what_to_do(self):
        """xlrd is not installed here, and .xls is a very common school export."""
        from apps.migration_cloud.profiler import _read_xls

        rows, headers, _enc = _read_xls(io.BytesIO(b"\xd0\xcf\x11\xe0"), "utf-8")
        self.assertEqual((rows, headers), ([], []))
        from apps.migration_cloud.profiler import unreadable_format_reason

        try:
            import xlrd  # noqa: F401
        except Exception:
            self.assertIn(
                "Save it as",
                unreadable_format_reason(ArtifactFormat.XLS, "roster.xls"),
                "a legacy .xls silently profiled as empty",
            )
