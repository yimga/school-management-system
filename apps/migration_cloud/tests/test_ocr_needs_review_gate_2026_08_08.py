"""OCR always-on: confidence gate + needs-review lane (2026-08-08).

The OCR engine (Tesseract/Poppler via pdf2image, gated on RMC_OCR_ENABLED +
vendored binaries) already auto-runs on a scanned PDF whose text layer is empty.
What was missing: a scanned page that OCR'd to too few / low-confidence
characters silently landed as garbage rows. This wires the already-built
`tier3.ocr_confidence_warning` into the extraction path — `extract_pdf_text_with_meta`
reports whether OCR ran + its char count + mean word confidence, and the PDF
intake adapter routes a low-confidence result to the needs-review lane (refuse +
explain) instead of landing it.

Each test fails against the pre-wave code (no meta / confidence, so a
low-confidence OCR result landed as an artifact).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from django.test import TestCase

from apps.migration_cloud.intake.base import IntakeContext, IntakeError
from apps.migration_cloud.intake.pdf_intake import PdfIntakeAdapter
from apps.migration_cloud import pdf_extract


def _ctx() -> IntakeContext:
    return IntakeContext(bundle_id=1, idempotency_key="ocr-gate-test")


def _run(handle):
    return list(PdfIntakeAdapter().iter_artifacts(handle, _ctx()))


class ExtractMetaUnitTests(TestCase):
    def test_digital_extraction_reports_no_ocr(self):
        with mock.patch.object(pdf_extract, "_try_pdfplumber", return_value="Digital transcript text"):
            text, meta = pdf_extract.extract_pdf_text_with_meta(b"%PDF-1.4 fake")
        self.assertEqual(text, "Digital transcript text")
        self.assertFalse(meta["used_ocr"])
        self.assertIsNone(meta["ocr_confidence"])
        self.assertEqual(meta["char_count"], len("Digital transcript text"))

    def test_ocr_disabled_degrades_gracefully(self):
        # With OCR disabled and no digital text, the fall-through reports
        # used_ocr=True but empty text + no confidence — never a crash.
        env = dict(os.environ)
        env.pop("RMC_OCR_ENABLED", None)
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(pdf_extract, "_try_pdfplumber", return_value=""), \
             mock.patch.object(pdf_extract, "_try_pypdf", return_value=""):
            text, meta = pdf_extract.extract_pdf_text_with_meta(b"%PDF-1.4 scanned")
            self.assertEqual(text, "")
            self.assertTrue(meta["used_ocr"])
            self.assertIsNone(meta["ocr_confidence"])
            self.assertIsNone(pdf_extract._ocr_render_pages(b"x"))
            self.assertEqual(pdf_extract._try_ocr(b"x"), "")
            self.assertEqual(pdf_extract._try_ocr_with_confidence(b"x"), ("", None))


class NeedsReviewGateTests(TestCase):
    HANDLE = Path("transcript.pdf")

    def _meta(self, **over):
        m = {"used_ocr": True, "char_count": 500, "ocr_confidence": 0.9}
        m.update(over)
        return m

    def test_low_char_ocr_routes_to_needs_review(self):
        # Below migration_cloud.ocr.min_chars_for_decision (40) → refuse.
        with mock.patch(
            "apps.migration_cloud.intake.pdf_intake.extract_pdf_text_with_meta",
            return_value=("hi", self._meta(char_count=2)),
        ):
            with self.assertRaises(IntakeError) as cm:
                _run(self.HANDLE)
        self.assertIn("needs manual review", str(cm.exception))

    def test_low_confidence_ocr_routes_to_needs_review(self):
        # Below migration_cloud.ocr.low_confidence_threshold (0.5) → refuse.
        with mock.patch(
            "apps.migration_cloud.intake.pdf_intake.extract_pdf_text_with_meta",
            return_value=("ENG101 English A\n" * 40, self._meta(ocr_confidence=0.2)),
        ):
            with self.assertRaises(IntakeError) as cm:
                _run(self.HANDLE)
        self.assertIn("needs manual review", str(cm.exception))

    def test_high_confidence_ocr_yields_artifact(self):
        with mock.patch(
            "apps.migration_cloud.intake.pdf_intake.extract_pdf_text_with_meta",
            return_value=("ENG101 English Literature A\n" * 30, self._meta()),
        ):
            out = _run(self.HANDLE)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].filename.endswith(".tsv"))

    def test_digital_pdf_skips_the_ocr_gate(self):
        # used_ocr=False → the confidence gate never applies, even with a low
        # char count, because digital extraction is trustworthy.
        with mock.patch(
            "apps.migration_cloud.intake.pdf_intake.extract_pdf_text_with_meta",
            return_value=("Name: Jane Doe", {"used_ocr": False, "char_count": 14, "ocr_confidence": None}),
        ):
            out = _run(self.HANDLE)
        self.assertEqual(len(out), 1)

    def test_empty_extraction_still_raises_install_hint(self):
        with mock.patch(
            "apps.migration_cloud.intake.pdf_intake.extract_pdf_text_with_meta",
            return_value=("", self._meta(char_count=0)),
        ):
            with self.assertRaises(IntakeError) as cm:
                _run(self.HANDLE)
        self.assertIn("no extractable text", str(cm.exception))
