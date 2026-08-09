"""PDF transcript intake — extracts structured rows from text or scanned PDFs.

A common long-tail school case is migrating a stack of paper or scanned
transcripts. This module turns one PDF into one ``ArtifactPayload`` whose
``content_opener`` returns the extracted text as a UTF-8 byte stream
formatted as TSV (header row + one row per detected line). Downstream the
profiler + mapper handle it like any other tabular artifact.

The actual text extraction + tabularisation lives in
:mod:`apps.migration_cloud.pdf_extract` (the single source of truth shared
with the connectionless ``FILE_UPLOAD`` path, so the heuristics never drift).
This adapter is the thin path-oriented ``IntakeMethod.PDF`` wrapper around it.

Graceful degradation: when no extractor is available (or the PDF is scanned
and no OCR binaries are installed), extraction returns empty and the adapter
raises ``IntakeError`` with the missing-dependency install hint; the wizard
surfaces it so the operator knows to install ``pdfplumber`` (digital text) or
``pytesseract`` + Tesseract + Poppler (scanned) — or use a different intake.
"""

from __future__ import annotations

import logging
import os
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

from apps.migration_cloud import defaults as mc_defaults
from apps.migration_cloud.models import IntakeMethod
from apps.migration_cloud.pdf_extract import extract_pdf_text_with_meta, tabularise

from .base import (
    ArtifactPayload,
    IntakeAdapter,
    IntakeContext,
    IntakeError,
    register_adapter,
)

logger = logging.getLogger(__name__)


class PdfIntakeAdapter(IntakeAdapter):
    """Adapter for the ``PDF`` intake method.

    Handle accepted as either:
        * a single path/Path to a PDF
        * a list of paths
        * a dict ``{"path": ..., "ocr": True/False}`` — explicit OCR opt-in
    """

    def validate_handle(self, handle: Any, ctx: IntakeContext) -> None:
        for path, _ in _iter_handle(handle):
            if not path.exists() or not path.is_file():
                raise IntakeError(f"PDF not found at intake: {path}")
            if path.suffix.lower() != ".pdf":
                raise IntakeError(f"Expected .pdf extension; got {path.suffix!r}.")

    def iter_artifacts(
        self, handle: Any, ctx: IntakeContext
    ) -> Iterator[ArtifactPayload]:
        max_bytes = int(mc_defaults.get("migration_cloud.intake.max_artifact_bytes"))
        for path, opts in _iter_handle(handle):
            ocr_pref = bool(opts.get("ocr"))
            text, meta = extract_pdf_text_with_meta(path, force_ocr=ocr_pref)
            if not text.strip():
                raise IntakeError(
                    f"PDF {path.name} produced no extractable text. "
                    "Install pdfplumber (digital PDFs) or pytesseract + "
                    "Tesseract + Poppler binaries (scanned PDFs) for OCR support."
                )
            # OCR always-on: a scanned PDF that OCR'd to too few / low-confidence
            # characters must NOT silently land as garbage rows. Route it to the
            # needs-review lane (refuse + explain via the existing confidence
            # thresholds) so the operator corrects / re-scans it or imports the
            # data another way. Digitally-extracted PDFs skip this gate entirely.
            if meta.get("used_ocr"):
                from apps.migration_cloud.tier3 import ocr_confidence_warning

                warning = ocr_confidence_warning(
                    ocr_chars=int(meta.get("char_count") or 0),
                    vendor_confidence=meta.get("ocr_confidence"),
                )
                if warning:
                    raise IntakeError(
                        f"{warning} This scanned PDF ({path.name}) was OCR'd but "
                        "needs manual review before import — correct or re-scan it, "
                        "or import the data another way."
                    )
            tsv_bytes = tabularise(text).encode("utf-8")
            if len(tsv_bytes) > max_bytes:
                raise IntakeError(
                    f"Extracted text from {path.name} exceeds artifact cap."
                )

            # Persist the extracted TSV to a temp file so the profiler can
            # stream it the same way it streams every other artifact.
            fd, tmp_name = tempfile.mkstemp(prefix="mc_pdf_", suffix=".tsv")
            os.close(fd)
            tmp = Path(tmp_name)
            tmp.write_bytes(tsv_bytes)
            digest = sha256(tsv_bytes).hexdigest()

            def opener(p=tmp):
                return p.open("rb")

            yield ArtifactPayload(
                path_within_bundle=path.stem + ".tsv",
                filename=path.stem + ".tsv",
                byte_size=len(tsv_bytes),
                sha256=digest,
                mime_type="text/tab-separated-values",
                content_opener=opener,
            )


# --- Handle normalisation -------------------------------------------------

def _iter_handle(handle: Any) -> Iterator[tuple[Path, dict[str, Any]]]:
    if isinstance(handle, (str, Path)):
        yield Path(handle), {}
        return
    if isinstance(handle, dict) and "path" in handle:
        yield Path(handle["path"]), {k: v for k, v in handle.items() if k != "path"}
        return
    try:
        iterator = iter(handle)
    except TypeError as exc:
        raise IntakeError(
            f"PdfIntakeAdapter does not accept handle of type {type(handle).__name__}"
        ) from exc
    for item in iterator:
        if isinstance(item, (str, Path)):
            yield Path(item), {}
        elif isinstance(item, dict) and "path" in item:
            yield Path(item["path"]), {k: v for k, v in item.items() if k != "path"}
        else:
            raise IntakeError(f"PdfIntakeAdapter cannot normalise item: {item!r}")


# Register the PDF intake method (defined in models.IntakeMethod below).
# Falls back gracefully if PDF method isn't enumerated yet — the registry
# accepts the registration but `get_adapter` only resolves enumerated members.
try:
    register_adapter(IntakeMethod.PDF, PdfIntakeAdapter())
except AttributeError:
    # IntakeMethod.PDF not yet added to the enum — silently skip; the
    # migration that adds it will pick this up on the next import.
    pass
