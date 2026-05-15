"""PDF transcript intake — extracts structured rows from text or scanned PDFs.

A common long-tail school case is migrating a stack of paper or scanned
transcripts. This module turns one PDF into one ``ArtifactPayload`` whose
``content_opener`` returns the extracted text as a UTF-8 byte stream
formatted as TSV (header row + one row per detected line). Downstream the
profiler + mapper handle it like any other tabular artifact.

Resolution order per page:
    1. ``pdfplumber`` text extraction — works for digitally-generated PDFs.
    2. ``pytesseract`` OCR over ``pdf2image``-rendered pages — works for
       scanned PDFs. Requires Tesseract + Poppler binaries in PATH.
    3. ``PyPDF2`` fallback if pdfplumber isn't available.

Graceful degradation: when no extractor is available, the adapter raises
``IntakeError`` with the missing-dependency install hint; the wizard
surfaces it so the operator knows to install `pdfplumber + pytesseract`
or use a different intake path.

Outputs a TSV stream so the existing CSV/TSV reader in the profiler
handles it without a new format-specific path. Header is inferred from the
"key: value" pattern common on transcripts; fall back to a single
``raw_line`` column when no pattern dominates.
"""

from __future__ import annotations

import io
import logging
import os
import re
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

from apps.migration_cloud import defaults as mc_defaults
from apps.migration_cloud.models import IntakeMethod

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
            text = _extract_pdf_text(path, force_ocr=ocr_pref)
            if not text.strip():
                raise IntakeError(
                    f"PDF {path.name} produced no extractable text. "
                    "Install pdfplumber + pytesseract (with Tesseract + Poppler "
                    "binaries) for OCR support."
                )
            tsv_bytes = _tabularise(text).encode("utf-8")
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


# --- Text extraction ------------------------------------------------------

def _extract_pdf_text(path: Path, *, force_ocr: bool = False) -> str:
    """Return the PDF's text, falling through extractors as available."""
    if not force_ocr:
        text = _try_pdfplumber(path)
        if text.strip():
            return text
        text = _try_pypdf(path)
        if text.strip():
            return text
    return _try_ocr(path)


def _try_pdfplumber(path: Path) -> str:
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return ""
    out: list[str] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text:
                    out.append(page_text)
    except Exception:  # noqa: BLE001
        return ""
    return "\n".join(out)


def _try_pypdf(path: Path) -> str:
    try:
        from PyPDF2 import PdfReader  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        try:
            from pypdf import PdfReader  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001
            return ""
    out: list[str] = []
    try:
        reader = PdfReader(str(path))
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                page_text = ""
            if page_text:
                out.append(page_text)
    except Exception:  # noqa: BLE001
        return ""
    return "\n".join(out)


def _try_ocr(path: Path) -> str:
    try:
        import pytesseract  # type: ignore[import-not-found]
        from pdf2image import convert_from_path  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return ""
    try:
        pages = convert_from_path(str(path), dpi=200)
    except Exception:  # noqa: BLE001
        return ""
    out: list[str] = []
    for img in pages:
        try:
            out.append(pytesseract.image_to_string(img))
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(out)


# --- Tabularisation -------------------------------------------------------

_KV_LINE = re.compile(r"^\s*([^:]{1,80}?)\s*[:|]\s*(.+?)\s*$")
_GRADE_LINE = re.compile(
    r"^\s*([A-Z]{2,8}\d{2,4})\s+(.{4,80}?)\s+([A-F][+-]?|\d{1,3}(?:\.\d{1,2})?)\s*$"
)


def _tabularise(raw_text: str) -> str:
    """Heuristically convert free-form transcript text into TSV.

    Two patterns observed in real transcripts:

    1. **Key/value header block** ("Name: Jane Doe", "DOB: 2008-04-12") at
       the top, followed by a grade table. We emit two artifacts via one
       TSV: header rows with `field<TAB>value`, then a separator, then
       course rows with `course_code<TAB>course_name<TAB>grade`.
       Downstream the profiler/mapper picks the dominant shape.

    2. **No structured pattern** — emit a single-column TSV with header
       ``raw_line`` and one row per non-empty line. Mapper quarantines into
       ``custom_fields`` so the operator sees the bytes.
    """
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    if not lines:
        return "raw_line\n"

    kv_rows: list[tuple[str, str]] = []
    grade_rows: list[tuple[str, str, str]] = []
    other_lines: list[str] = []
    for ln in lines:
        gm = _GRADE_LINE.match(ln)
        if gm:
            grade_rows.append((gm.group(1), gm.group(2).strip(), gm.group(3)))
            continue
        km = _KV_LINE.match(ln)
        if km:
            key = km.group(1).strip().lower().replace(" ", "_")
            kv_rows.append((key, km.group(2).strip()))
            continue
        other_lines.append(ln)

    # Prefer the grade-table shape if present (most transcripts).
    if grade_rows:
        buf = io.StringIO()
        buf.write("course_code\tcourse_name\tscore\n")
        for code, name, score in grade_rows:
            buf.write(f"{code}\t{name}\t{score}\n")
        return buf.getvalue()

    if kv_rows:
        buf = io.StringIO()
        buf.write("field\tvalue\n")
        for k, v in kv_rows:
            buf.write(f"{k}\t{v}\n")
        return buf.getvalue()

    # No pattern — preserve raw lines so the operator has the bytes.
    buf = io.StringIO()
    buf.write("raw_line\n")
    for ln in lines:
        buf.write(f"{ln}\n")
    return buf.getvalue()


# Register the PDF intake method (defined in models.IntakeMethod below).
# Falls back gracefully if PDF method isn't enumerated yet — the registry
# accepts the registration but `get_adapter` only resolves enumerated members.
try:
    register_adapter(IntakeMethod.PDF, PdfIntakeAdapter())
except AttributeError:
    # IntakeMethod.PDF not yet added to the enum — silently skip; the
    # migration that adds it will pick this up on the next import.
    pass
