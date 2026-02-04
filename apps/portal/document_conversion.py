"""
LibreOffice headless conversion: ODT/DOCX/ODS to PDF.

Requires LibreOffice installed (e.g. apt-get install libreoffice-writer,
or full LibreOffice). Run from server or Celery worker.

Usage:
    from apps.portal.document_conversion import convert_to_pdf
    pdf_bytes = convert_to_pdf("/path/to/file.odt")
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def convert_to_pdf(source_path: str) -> bytes:
    """
    Convert a document (ODT, DOCX, ODS, etc.) to PDF using LibreOffice headless.

    Args:
        source_path: Absolute path to the source file on disk.

    Returns:
        PDF file content as bytes.

    Raises:
        RuntimeError: If LibreOffice is not found or conversion fails.
    """
    source_path = os.path.abspath(source_path)
    if not os.path.isfile(source_path):
        raise RuntimeError(f"Source file not found: {source_path}")

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError(
            "LibreOffice not found. Install it (e.g. apt-get install libreoffice-writer) "
            "to use ODT/DOCX to PDF conversion."
        )

    out_dir = tempfile.mkdtemp(prefix="portal_convert_")
    try:
        # --headless --convert-to pdf --outdir <dir> <file>
        result = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir, source_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"LibreOffice conversion failed: {result.stderr or result.stdout or 'unknown error'}"
            )

        base = Path(source_path).stem
        pdf_path = Path(out_dir) / f"{base}.pdf"
        if not pdf_path.exists():
            raise RuntimeError("LibreOffice did not produce a PDF file.")

        return pdf_path.read_bytes()
    finally:
        try:
            for f in Path(out_dir).iterdir():
                f.unlink(missing_ok=True)
            os.rmdir(out_dir)
        except OSError:
            pass
