"""Parse-safety seals from the 2026-08-09 re-audit.

1. archive_intake XLSX-member branch read the whole decompressed member with a
   plain stream.read(), gated only by the DECLARED member size -- so a workbook
   member that under-declares (zip central-directory lie) but inflates to GiB
   (a deflate bomb) OOM'd the worker. It now caps the in-memory read like the
   raw-member path.
2. tier3 CSV export wrote tenant values (names, descriptions) with no formula
   neutralization, so a value like ``=cmd|'/c calc'!A1`` executed when the
   "no lock-in" export CSV was opened in Excel / Sheets.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud import tier3
from apps.migration_cloud.intake import archive_intake
from apps.migration_cloud.intake.base import IntakeError


class _ChunkStream:
    """A minimal read()-able that yields the given chunks then EOF."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read(self, n=-1):
        return self._chunks.pop(0) if self._chunks else b""


class ArchiveMemberCapTests(SimpleTestCase):
    def test_oversize_member_refused_mid_read(self):
        # 120 bytes streamed under a 100-byte cap -> bomb guard fires.
        stream = _ChunkStream([b"A" * 60, b"B" * 60])
        with self.assertRaises(IntakeError) as cm:
            archive_intake._read_member_capped(stream, 100, "bomb.xlsx")
        self.assertIn("decompression bomb", str(cm.exception))

    def test_small_member_reads_fully(self):
        stream = _ChunkStream([b"hello", b"world"])
        data = archive_intake._read_member_capped(stream, 100, "ok.xlsx")
        self.assertEqual(data, b"helloworld")


class CsvFormulaInjectionTests(SimpleTestCase):
    def test_formula_triggers_neutralized(self):
        for raw in ("=cmd|'/c calc'!A1", "@SUM(1)", "\tTAB", "\rCR"):
            self.assertEqual(tier3._csv_safe(raw), "'" + raw)

    def test_leading_minus_or_plus_text_neutralized(self):
        self.assertEqual(tier3._csv_safe("-cmd"), "'-cmd")
        self.assertEqual(tier3._csv_safe("+cmd"), "'+cmd")

    def test_numbers_and_dates_round_trip(self):
        # Negative amounts, signed values, decimals, thousands, ISO dates: unchanged.
        for raw in ("-50", "-1,234.56", "+42", "2025-08-15", "3.14"):
            self.assertEqual(tier3._csv_safe(raw), raw)

    def test_plain_text_and_empty_unchanged(self):
        self.assertEqual(tier3._csv_safe("Grace Hopper"), "Grace Hopper")
        self.assertEqual(tier3._csv_safe(""), "")
        self.assertEqual(tier3._csv_safe(None), "")

    def test_csv_dump_rows_neutralizes_malicious_cell(self):
        out = tier3._csv_dump_rows(
            [{"name": "=HYPERLINK(0)", "amount": "-99.50"}],
            ["name", "amount"],
        )
        lines = out.strip().splitlines()
        # Header + one data row; the formula cell is quoted, the amount is not.
        self.assertIn("'=HYPERLINK(0)", lines[1])
        self.assertIn("-99.50", lines[1])
        self.assertNotIn("'-99.50", lines[1])
