"""Shared PDF text extraction + tabularisation for Migration Cloud.

Single source of truth used by BOTH entry points that turn a PDF into rows:

  * :mod:`apps.migration_cloud.intake.pdf_intake` — the ``IntakeMethod.PDF``
    path (an operator hands the platform a stack of transcripts).
  * :mod:`apps.migration_cloud.profiler` + :mod:`apps.migration_cloud.orchestrator`
    — the *connectionless* ``FILE_UPLOAD`` path, where a tenant simply drops a
    PDF, the profiler magic-sniffs ``%PDF-`` and routes it through the exact
    same extraction so it profiles + lands like any other tabular artifact.

Keeping the extraction here (rather than duplicated in each caller) means the
heuristics that turn free-form transcript text into columns never drift apart.

Extraction resolution order — digital text first, OCR last:

  1. ``pdfplumber`` — digitally-generated PDFs (pure-Python, manylinux wheels,
     no system binaries). The common case: an exported transcript / fee
     statement / roster saved as PDF.
  2. ``pypdf`` / ``PyPDF2`` — lighter text-layer fallback.
  3. ``pytesseract`` over ``pdf2image`` — scanned / image-only PDFs. Requires
     the Tesseract + Poppler *system* binaries, which are absent on stock
     deploys, so this degrades to ``""`` and the caller surfaces an honest
     "this PDF needs OCR" hint rather than hard-failing.

Every extractor degrades to ``""`` when its library is unavailable, so the
platform never 500s on a PDF — it yields zero rows and explains why.
"""

from __future__ import annotations

import io
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import IO, Any

logger = logging.getLogger(__name__)

PdfSource = Any  # Path | str | bytes | bytearray | IO[bytes]


def pdf_text_available() -> bool:
    """True when a *digital* text extractor (no system binaries) is importable.

    Lets callers distinguish "we could not read this PDF because the extractor
    isn't installed" from "this PDF has no text layer (scanned — needs OCR)".
    """
    for mod in ("pdfplumber", "pypdf", "PyPDF2"):
        try:
            __import__(mod)
            return True
        except Exception:  # noqa: BLE001 — any import failure means unavailable
            continue
    return False


# --- Source normalisation -------------------------------------------------

def _as_bytes(source: PdfSource) -> bytes:
    """Coerce any accepted source to raw bytes (empty bytes on failure)."""
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    if isinstance(source, (str, Path)):
        try:
            return Path(source).read_bytes()
        except Exception:  # noqa: BLE001
            return b""
    # File-like — read whatever it yields.
    read = getattr(source, "read", None)
    if callable(read):
        try:
            data = read()
        except Exception:  # noqa: BLE001
            return b""
        return data if isinstance(data, (bytes, bytearray)) else b""
    return b""


# --- Text extraction ------------------------------------------------------

def extract_pdf_text(source: PdfSource, *, force_ocr: bool = False) -> str:
    """Return the PDF's text, falling through extractors as available.

    ``source`` may be a path, raw bytes, or a binary file-like object.
    Returns ``""`` when no extractor can read it (missing libs / scanned PDF
    with no OCR binaries) — callers treat empty as "zero rows + explain".
    """
    data = _as_bytes(source)
    if not data:
        return ""
    if not force_ocr:
        text = _try_pdfplumber(data)
        if text.strip():
            return text
        text = _try_pypdf(data)
        if text.strip():
            return text
    return _try_ocr(data)


def _try_pdfplumber(data: bytes) -> str:
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return ""
    out: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text:
                    out.append(page_text)
    except Exception:  # noqa: BLE001
        return ""
    return "\n".join(out)


def _try_pypdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        try:
            from PyPDF2 import PdfReader  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001
            return ""
    out: list[str] = []
    try:
        reader = PdfReader(io.BytesIO(data))
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


def _ocr_paths() -> tuple[str | None, str | None, str | None]:
    """Resolve ``(tesseract_cmd, poppler_path, tessdata_prefix)`` for OCR.

    Explicit env vars win (``RMC_OCR_TESSERACT_CMD`` / ``RMC_OCR_POPPLER_PATH`` /
    ``TESSDATA_PREFIX``); otherwise auto-discover the ``.ocr-env`` prefix that
    ``build.sh`` vendors at the repo root on Render's native runtime. Any piece
    left unresolved is ``None`` — the caller then relies on the binary being on
    ``PATH`` (or degrades to "").
    """
    tess = os.environ.get("RMC_OCR_TESSERACT_CMD") or None
    poppler = os.environ.get("RMC_OCR_POPPLER_PATH") or None
    tessdata = os.environ.get("TESSDATA_PREFIX") or None
    try:
        # apps/migration_cloud/pdf_extract.py → parents[2] == repo root.
        env_root = Path(__file__).resolve().parents[2] / ".ocr-env"
        env_bin = env_root / "bin"
        if tess is None and (env_bin / "tesseract").exists():
            tess = str(env_bin / "tesseract")
        if poppler is None and (env_bin / "pdftoppm").exists():
            poppler = str(env_bin)
        if tessdata is None and (env_root / "share" / "tessdata").exists():
            tessdata = str(env_root / "share" / "tessdata")
    except Exception:  # noqa: BLE001
        pass
    return tess, poppler, tessdata


def _try_ocr(data: bytes) -> str:
    """OCR fallback — needs Tesseract + Poppler system binaries.

    Disabled unless ``RMC_OCR_ENABLED=1``, so stock deploys behave exactly as
    before (scanned PDFs degrade to ""). When enabled, the binaries are located
    via :func:`_ocr_paths` (explicit env vars or the ``.ocr-env`` prefix that
    ``build.sh`` vendors). ``pdf2image`` renders pages from a *path*, so the
    bytes are spilled to a short-lived temp file. Absent binaries / libs → ``""``
    (graceful — never a 500).
    """
    if os.environ.get("RMC_OCR_ENABLED", "0") != "1":
        return ""
    try:
        import pytesseract  # type: ignore[import-not-found]
        from pdf2image import convert_from_path  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return ""
    tess_cmd, poppler_path, tessdata_prefix = _ocr_paths()
    if tess_cmd:
        try:
            pytesseract.pytesseract.tesseract_cmd = tess_cmd
        except Exception:  # noqa: BLE001
            pass
    if tessdata_prefix:
        os.environ.setdefault("TESSDATA_PREFIX", tessdata_prefix)
    fd, tmp_name = tempfile.mkstemp(prefix="mc_pdf_ocr_", suffix=".pdf")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_bytes(data)
        convert_kwargs: dict[str, Any] = {"dpi": 200}
        if poppler_path:
            convert_kwargs["poppler_path"] = poppler_path
        try:
            pages = convert_from_path(str(tmp), **convert_kwargs)
        except Exception:  # noqa: BLE001
            return ""
        out: list[str] = []
        for img in pages:
            try:
                out.append(pytesseract.image_to_string(img))
            except Exception:  # noqa: BLE001
                continue
        return "\n".join(out)
    finally:
        tmp.unlink(missing_ok=True)


# --- Tabularisation -------------------------------------------------------

_KV_LINE = re.compile(r"^\s*([^:]{1,80}?)\s*[:|]\s*(.+?)\s*$")
_GRADE_LINE = re.compile(
    r"^\s*([A-Z]{2,8}\d{2,4})\s+(.{4,80}?)\s+([A-F][+-]?|\d{1,3}(?:\.\d{1,2})?)\s*$"
)


def tabularise(raw_text: str) -> str:
    """Heuristically convert free-form transcript text into TSV.

    Two patterns observed in real transcripts:

    1. **Grade table** — ``ENG101  English Literature  A-`` rows. Emitted as
       ``course_code<TAB>course_name<TAB>score``. Preferred when present.
    2. **Key/value header block** — ``Name: Jane Doe``, ``DOB: 2008-04-12``.
       Emitted as ``field<TAB>value``.
    3. **No structured pattern** — a single-column ``raw_line`` TSV so the
       operator still sees every byte and the mapper can quarantine into
       ``custom_fields``.

    Downstream the profiler + mapper handle the TSV like any other tabular
    artifact.
    """
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    if not lines:
        return "raw_line\n"

    kv_rows: list[tuple[str, str]] = []
    grade_rows: list[tuple[str, str, str]] = []
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


def extract_pdf_tsv(source: PdfSource, *, force_ocr: bool = False) -> str:
    """Convenience: extract text then tabularise. ``""`` when no text found."""
    text = extract_pdf_text(source, force_ocr=force_ocr)
    if not text.strip():
        return ""
    return tabularise(text)
