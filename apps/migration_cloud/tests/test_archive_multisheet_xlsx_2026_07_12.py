"""Multi-sheet XLSX inside a ZIP explodes too (archive parity with FILE_UPLOAD).

Wave 3 fixed multi-tab workbooks uploaded directly. A workbook zipped up with
other files still read only its first sheet. This closes that gap: an .xlsx/.xlsm
member with >=2 non-empty sheets is exploded into one TSV artifact per sheet,
with the parent-archive lineage preserved; a single-sheet member stays raw.
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase


def _xlsx_bytes(sheets: dict[str, list[list]]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet()
        ws.title = name
        for r in rows:
            ws.append(r)
        first = False
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_zip(members: dict[str, bytes]) -> Path:
    fd, tmp = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(tmp, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return Path(tmp)


def _parse_tsv(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode("utf-8")), delimiter="\t"))


def _rm(p: Path) -> None:
    # On Windows a raw member's content_opener keeps the ZipFile handle open
    # (streaming, by design), so the temp zip may still be locked. Best-effort.
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


def _adapter():
    from apps.migration_cloud.intake import get_adapter
    from apps.migration_cloud.models import IntakeMethod

    return get_adapter(IntakeMethod.ARCHIVE)


def _ctx():
    from apps.migration_cloud.intake.base import IntakeContext

    return IntakeContext(bundle_id=0, idempotency_key="ut-zip")


class ExplodeBytesTests(SimpleTestCase):
    def test_explode_workbook_accepts_bytes(self):
        from apps.migration_cloud.xlsx_explode import explode_workbook

        data = _xlsx_bytes(
            {"A": [["x"], ["1"]], "B": [["y"], ["2"]], "Empty": []}
        )
        result = explode_workbook(data)  # bytes, not a path
        self.assertEqual([name for name, _ in result], ["A", "B"])


class ArchiveMultiSheetTests(SimpleTestCase):
    def test_archived_multisheet_xlsx_explodes_per_sheet(self):
        adapter = _adapter()
        zpath = _make_zip(
            {
                "roster.xlsx": _xlsx_bytes(
                    {
                        "Students": [["admission_no", "first_name"], ["S1", "Ada"]],
                        "Staff": [["staff_no", "first_name"], ["T1", "Alan"]],
                    }
                ),
                "notes.csv": b"a,b\n1,2\n",
            }
        )
        try:
            payloads = list(adapter.iter_artifacts(zpath, _ctx()))
        finally:
            _rm(zpath)

        tsvs = [p for p in payloads if p.filename.endswith(".tsv")]
        # roster.xlsx -> Students.tsv + Staff.tsv (was: 1 raw xlsx, sheet 1 only)
        self.assertEqual(len(tsvs), 2)
        self.assertTrue(any("Students" in p.filename for p in tsvs))
        self.assertTrue(any("Staff" in p.filename for p in tsvs))
        for p in tsvs:
            # Parent-archive lineage preserved (links to the zip's parent artifact).
            self.assertEqual(p.parent_archive_path, zpath.name)
            rows = _parse_tsv(p.content_opener().read())
            self.assertGreaterEqual(len(rows), 2)  # header + >=1 data row
        # The plain CSV member still passes through untouched.
        self.assertTrue(any(p.filename == "notes.csv" for p in payloads))

    def test_archived_single_sheet_xlsx_stays_raw(self):
        adapter = _adapter()
        zpath = _make_zip(
            {"solo.xlsx": _xlsx_bytes({"OnlyTab": [["a", "b"], ["1", "2"]]})}
        )
        try:
            payloads = list(adapter.iter_artifacts(zpath, _ctx()))
        finally:
            _rm(zpath)

        self.assertEqual(len(payloads), 1)
        self.assertTrue(payloads[0].filename.endswith(".xlsx"))
        # bytes are readable via the opener (single archive pass, cached bytes).
        self.assertTrue(payloads[0].content_opener().read().startswith(b"PK"))
