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
import uuid
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

CONVERSION_TIMEOUT_SECONDS = int(os.getenv("LIBREOFFICE_CONVERSION_TIMEOUT_SECONDS", "120"))
REPO_ROOT = Path(__file__).resolve().parents[2]


def portal_temp_root() -> Path:
    raw = (os.getenv("PORTAL_TEMP_ROOT") or "").strip()
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else (REPO_ROOT / path)
    return REPO_ROOT / "var" / "tmp"


@contextmanager
def portal_tempdir(prefix: str):
    root = portal_temp_root()
    root.mkdir(parents=True, exist_ok=True)
    tmp_dir = root / f"{prefix}{uuid.uuid4().hex}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield tmp_dir
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _is_safe_source_path(source_path: str) -> bool:
    """Allow conversion only from media/tmp/workspace roots."""
    ap = os.path.abspath(source_path)
    roots = [
        os.path.abspath(os.getenv("MEDIA_ROOT", "media")),
        os.path.abspath(os.getenv("TMPDIR", tempfile.gettempdir())),
        os.path.abspath("."),
    ]
    try:
        return any(ap.startswith(root) for root in roots)
    except Exception:
        return False


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
    if not _is_safe_source_path(source_path):
        raise RuntimeError("Unsafe source path for conversion; path must be under approved roots.")

    soffice = _find_soffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice not found. Install it (e.g. apt-get install libreoffice-writer) "
            "to use document conversion."
        )

    with portal_tempdir("portal_convert_") as out_dir, portal_tempdir(
        "portal_soffice_profile_"
    ) as profile_dir:
        env = os.environ.copy()
        temp_root = str(portal_temp_root())
        env["TMP"] = temp_root
        env["TEMP"] = temp_root
        env["TMPDIR"] = temp_root
        # --headless --convert-to <ext> --outdir <dir> <file>
        result = subprocess.run(
            [
                soffice,
                f"-env:UserInstallation={profile_dir.as_uri()}",
                "--headless",
                "--nologo",
                "--nodefault",
                "--nolockcheck",
                "--norestore",
                "--convert-to",
                target_ext,
                "--outdir",
                str(out_dir),
                source_path,
            ],
            cwd=str(out_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=CONVERSION_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            err = result.stderr or result.stdout or "unknown error"
            logger.warning(
                "LibreOffice conversion failed: returncode=%s stderr=%s",
                result.returncode,
                err[:300],
            )
            raise RuntimeError(f"LibreOffice conversion failed: {err}")

        base = Path(source_path).stem
        out_path = out_dir / f"{base}.{target_ext.split(':')[0]}"
        if not out_path.exists():
            raise RuntimeError("LibreOffice did not produce output file.")

        return out_path.read_bytes()


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
    with portal_tempdir("portal_convert_html_") as tmp_dir:
        html_path = tmp_dir / "input.html"
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
    with portal_tempdir("portal_convert_html_") as tmp_dir:
        html_path = tmp_dir / "input.html"
        html_path.write_text(
            f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title></head><body>{html_content}</body></html>",
            encoding="utf-8",
        )
        odt_bytes = convert_to_odt(str(html_path))
        odt_path = tmp_dir / "input.odt"
        odt_path.write_bytes(odt_bytes)
        return convert_to_docx(str(odt_path))


# Calc conversions
def convert_calc_to_pdf(source_path: str) -> bytes:
    """Convert spreadsheet sources (ODS/XLS/XLSX/CSV) to PDF."""
    return _convert_with_libreoffice(source_path, "pdf")


def convert_calc_to_xlsx(source_path: str) -> bytes:
    """Convert spreadsheet sources to XLSX."""
    return _convert_with_libreoffice(source_path, "xlsx")


def convert_calc_to_ods(source_path: str) -> bytes:
    """Convert spreadsheet sources to ODS."""
    return _convert_with_libreoffice(source_path, "ods")


# Impress conversions
def convert_impress_to_pdf(source_path: str) -> bytes:
    """Convert presentation sources (ODP/PPT/PPTX) to PDF."""
    return _convert_with_libreoffice(source_path, "pdf")


def convert_impress_to_pptx(source_path: str) -> bytes:
    """Convert presentation sources to PPTX."""
    return _convert_with_libreoffice(source_path, "pptx")


def convert_impress_to_odp(source_path: str) -> bytes:
    """Convert presentation sources to ODP."""
    return _convert_with_libreoffice(source_path, "odp")


def convert_odt_to_html(source_path: str) -> str:
    """Convert Writer-family documents to HTML via LibreOffice headless."""
    raw = _convert_with_libreoffice(source_path, "html")
    return raw.decode("utf-8", errors="replace")
