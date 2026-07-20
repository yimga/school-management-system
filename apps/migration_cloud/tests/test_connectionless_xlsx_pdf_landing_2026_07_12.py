"""Connectionless XLSX + PDF ingest: classify AND land (regression).

Before this wave, the connectionless ``FILE_UPLOAD`` path let a tenant drop an
Excel workbook or a PDF, the profiler classified it — and then the apply step
(``_iter_canonical_rows``) landed **zero rows**, because it only handled
csv/tsv/json/jsonl and returned ``iter(())`` for everything else. The two
formats a school is most likely to hand us ("excel or pdf") dead-ended silently.

These tests pin the fix:

  * an XLSX blob now yields real rows through ``_iter_canonical_rows`` (openpyxl
    is a core dep, so this always runs);
  * a text PDF yields rows too (needs pdfplumber + reportlab — skipped when the
    optional test stack is absent, but exercised in CI/prod where requirements
    installs pdfplumber);
  * an unreadable / scanned-without-OCR PDF degrades to zero rows *without
    raising* — apply must never 500 on a bad PDF;
  * the profiler routes a bare (UNKNOWN) XLSX upload to the XLSX reader (real
    columns, not a CSV-misread of the binary);
  * the review surface's zero-row hint explains PDF/XLSX dead-ends in plain
    language.
"""

from __future__ import annotations

import io
import types
from unittest import skipUnless

from django.test import TestCase

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)


def _payload(data: bytes):
    return types.SimpleNamespace(content_opener=lambda: io.BytesIO(data))


def _xlsx_bytes(headers: list[str], rows: list[list]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pdf_bytes(lines: list[str]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 720
    for ln in lines:
        c.drawString(72, y, ln)
        y -= 18
    c.showPage()
    c.save()
    return buf.getvalue()


def _pdf_stack_available() -> bool:
    """True when both the extractor (pdfplumber/pypdf) and a PDF *writer* exist."""
    try:
        import reportlab  # noqa: F401

        from apps.migration_cloud.pdf_extract import pdf_text_available

        return pdf_text_available()
    except Exception:  # noqa: BLE001
        return False


class _Fixtures(TestCase):
    def _bundle(self, key: str, **kwargs) -> MigrationBundle:
        return MigrationBundle.objects.create(
            label=kwargs.pop("label", "connectionless bundle"),
            intake_method=kwargs.pop("intake_method", IntakeMethod.FILE_UPLOAD),
            idempotency_key=key,
            status=kwargs.pop("status", BundleStatus.INGESTING),
            **kwargs,
        )

    def _artifact(
        self,
        bundle: MigrationBundle,
        *,
        filename: str,
        path: str | None = None,
        fmt: str = ArtifactFormat.CSV,
    ) -> MigrationArtifact:
        return MigrationArtifact.objects.create(
            bundle=bundle,
            path_within_bundle=path or filename,
            filename=filename,
            detected_format=fmt,
            byte_size=0,
            sha256="0" * 64,
        )


class XlsxLandingTests(_Fixtures):
    def test_xlsx_lands_rows_via_canonical_iter(self):
        from apps.migration_cloud.orchestrator import _ArtifactJob, _iter_canonical_rows

        data = _xlsx_bytes(["name", "age"], [["Ada", 36], ["Grace", 45]])
        bundle = self._bundle("xlsx-land")
        art = self._artifact(
            bundle, filename="roster.xlsx", path="roster.xlsx", fmt=ArtifactFormat.XLSX
        )
        self.assertTrue(store.capture_artifact_blob(art, _payload(data)))

        job = _ArtifactJob(
            artifact=art,
            domain="students",
            mappings=[
                {"source_column": "name", "canonical_field": "full_name"},
                {"source_column": "age", "canonical_field": "years"},
            ],
        )
        rows = list(_iter_canonical_rows(job))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["full_name"], "Ada")
        # Integer cells stringify to "36" (matching a CSV export), not "36.0".
        self.assertEqual(rows[0]["years"], "36")
        self.assertEqual(rows[1]["full_name"], "Grace")

    def test_profiler_routes_bare_xlsx_upload_to_xlsx_reader(self):
        """A FILE_UPLOAD xlsx arrives UNKNOWN — the profiler must magic-sniff it
        to XLSX and read real columns, not CSV-misread the binary."""
        from apps.migration_cloud import profiler

        data = _xlsx_bytes(["first_name", "last_name"], [["Ada", "Lovelace"]])
        bundle = self._bundle("xlsx-profile")
        art = self._artifact(
            bundle, filename="staff.xlsx", path="staff.xlsx", fmt=ArtifactFormat.UNKNOWN
        )
        self.assertTrue(store.capture_artifact_blob(art, _payload(data)))

        profiler._profile_one(art)
        art.refresh_from_db()
        self.assertEqual(art.detected_format, ArtifactFormat.XLSX)
        self.assertEqual(art.column_count, 2)
        self.assertGreaterEqual(art.row_count, 1)
        names = [c.get("name") for c in (art.profile or {}).get("columns", [])]
        self.assertIn("first_name", names)


class PdfLandingTests(_Fixtures):
    @skipUnless(_pdf_stack_available(), "pdfplumber + reportlab required")
    def test_pdf_lands_rows_via_canonical_iter(self):
        from apps.migration_cloud.orchestrator import _ArtifactJob, _iter_canonical_rows

        data = _pdf_bytes(
            ["ENG101 English Literature A-", "MTH201 Calculus B+", "SCI110 Biology 88"]
        )
        bundle = self._bundle("pdf-land")
        art = self._artifact(
            bundle, filename="transcript.pdf", path="transcript.pdf", fmt=ArtifactFormat.PDF
        )
        self.assertTrue(store.capture_artifact_blob(art, _payload(data)))

        job = _ArtifactJob(
            artifact=art,
            domain="grades",
            mappings=[
                {"source_column": "course_code", "canonical_field": "course_code"},
                {"source_column": "score", "canonical_field": "score"},
            ],
        )
        rows = list(_iter_canonical_rows(job))
        self.assertGreaterEqual(len(rows), 2)
        codes = {r.get("course_code") for r in rows}
        self.assertIn("ENG101", codes)

    def test_unreadable_pdf_yields_no_rows_not_error(self):
        """A scanned-without-OCR / corrupt PDF must degrade to zero rows, never
        raise — apply cannot 500 on a bad PDF."""
        from apps.migration_cloud.orchestrator import _ArtifactJob, _iter_canonical_rows

        data = b"%PDF-1.4\nnot actually a parseable pdf body\n%%EOF"
        bundle = self._bundle("pdf-unreadable")
        art = self._artifact(
            bundle, filename="scan.pdf", path="scan.pdf", fmt=ArtifactFormat.PDF
        )
        self.assertTrue(store.capture_artifact_blob(art, _payload(data)))

        job = _ArtifactJob(artifact=art, domain="custom_fields", mappings=[])
        rows = list(_iter_canonical_rows(job))
        self.assertEqual(rows, [])


class ReviewHintTests(TestCase):
    def test_row_hint_explains_empty_pdf_and_xlsx(self):
        from apps.migration_cloud.views_tenant_upload import _row_hint

        empty_pdf = types.SimpleNamespace(
            quarantined=False, row_count=0, detected_format="pdf"
        )
        self.assertIn("OCR", _row_hint(empty_pdf))

        empty_xlsx = types.SimpleNamespace(
            quarantined=False, row_count=0, detected_format="xlsx"
        )
        self.assertIn("worksheet", _row_hint(empty_xlsx))

        # A PDF that DID land rows gets no hint.
        good_pdf = types.SimpleNamespace(
            quarantined=False, row_count=12, detected_format="pdf"
        )
        self.assertEqual(_row_hint(good_pdf), "")

        # Zero-row CSV/TSV/JSON get an actionable empty-file hint.
        empty_csv = types.SimpleNamespace(
            quarantined=False, row_count=0, detected_format="csv"
        )
        self.assertIn("data rows", _row_hint(empty_csv))
