"""
LibreOffice headless conversion: ODT/DOCX/ODS/HTML to PDF or DOCX/ODT.

Requires LibreOffice installed (e.g. apt-get install libreoffice-writer,
or full LibreOffice). Run from server or Celery worker.
Callers must pass source_path under a controlled directory when path is user-derived.

Usage:
    from apps.portal.document_conversion import convert_to_pdf, convert_to_docx
    pdf_bytes = convert_to_pdf("/path/to/file.odt")
    docx_bytes = convert_to_docx("/path/to/file.odt")
"""
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _find_soffice() -> str | None:
    """Locate LibreOffice/soffice binary across common install paths."""
    env_path = os.getenv("SOFFICE_PATH") or os.getenv("LIBREOFFICE_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    for candidate in (shutil.which("soffice"), shutil.which("libreoffice")):
        if candidate and os.path.isfile(candidate):
            return candidate

    # Common Windows locations
    if os.name == "nt":
        win_candidates = [
            r"C:\Program Files\LibreOffice\program\soffice.com",
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.com",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]
        for path in win_candidates:
            if os.path.isfile(path):
                return path

    # macOS
    if sys.platform == "darwin":
        mac_candidate = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        if os.path.isfile(mac_candidate):
            return mac_candidate

    # Linux common locations
    linux_candidates = [
        "/usr/bin/soffice",
        "/usr/local/bin/soffice",
        "/snap/bin/libreoffice",
        "/usr/lib/libreoffice/program/soffice",
    ]
    for path in linux_candidates:
        if os.path.isfile(path):
            return path

    return None


def find_soffice() -> str | None:
    """Public helper for other modules (e.g., management commands)."""
    return _find_soffice()


def _convert_with_libreoffice(source_path: str, target_ext: str) -> bytes:
    """
    Convert a document to the requested format using LibreOffice headless.
    """
    source_path = os.path.abspath(source_path)
    if not os.path.isfile(source_path):
        raise RuntimeError(f"Source file not found: {source_path}")

    soffice = _find_soffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice not found. Install it (e.g. apt-get install libreoffice-writer) "
            "to use document conversion."
        )

    out_dir = tempfile.mkdtemp(prefix="portal_convert_")
    try:
        # --headless --convert-to <ext> --outdir <dir> <file>
        result = subprocess.run(
            [soffice, "--headless", "--convert-to", target_ext, "--outdir", out_dir, source_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            err = result.stderr or result.stdout or "unknown error"
            logger.warning("LibreOffice conversion failed: returncode=%s stderr=%s", result.returncode, err[:300])
            raise RuntimeError(f"LibreOffice conversion failed: {err}")

        base = Path(source_path).stem
        out_path = Path(out_dir) / f"{base}.{target_ext.split(':')[0]}"
        if not out_path.exists():
            raise RuntimeError("LibreOffice did not produce output file.")

        return out_path.read_bytes()
    finally:
        try:
            for f in Path(out_dir).iterdir():
                f.unlink(missing_ok=True)
            os.rmdir(out_dir)
        except OSError:
            pass


def convert_to_pdf(source_path: str) -> bytes:
    """
    Convert a document (ODT, DOCX, ODS, etc.) to PDF using LibreOffice headless.
    """
    return _convert_with_libreoffice(source_path, "pdf")


def convert_to_docx(source_path: str) -> bytes:
    """
    Convert a document (ODT, HTML, etc.) to DOCX using LibreOffice headless.
    """
    return _convert_with_libreoffice(source_path, "docx")


def convert_to_odt(source_path: str) -> bytes:
    """
    Convert a document (HTML, DOCX, etc.) to ODT using LibreOffice headless.
    """
    return _convert_with_libreoffice(source_path, "odt")


def convert_html_to_odt(html_content: str, title: str = "Document") -> bytes:
    """
    Convert HTML content directly to ODT using LibreOffice headless.
    """
    with tempfile.TemporaryDirectory(prefix="portal_convert_html_") as tmp_dir:
        html_path = Path(tmp_dir) / "input.html"
        html_path.write_text(
            f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title></head><body>{html_content}</body></html>",
            encoding="utf-8",
        )
        return convert_to_odt(str(html_path))


def convert_html_to_docx(html_content: str, title: str = "Document") -> bytes:
    """
    Convert HTML content to DOCX.

    LibreOffice reliably converts HTML -> ODT, but some Windows builds fail on
    direct HTML -> DOCX export filters. Use an ODT intermediate so KB exports
    remain reproducible in release gates.
    """
    with tempfile.TemporaryDirectory(prefix="portal_convert_html_") as tmp_dir:
        html_path = Path(tmp_dir) / "input.html"
        html_path.write_text(
            f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title></head><body>{html_content}</body></html>",
            encoding="utf-8",
        )
        odt_bytes = convert_to_odt(str(html_path))
        odt_path = Path(tmp_dir) / "input.odt"
        odt_path.write_bytes(odt_bytes)
        return convert_to_docx(str(odt_path))
