"""
Document generation utilities for KB and report exports.

Supports:
- HTML -> ODT/DOCX via Pandoc
- Markdown -> ODT/DOCX via Pandoc or LibreOffice fallback
"""

import os
import re
import shutil
import subprocess
import tempfile

from apps.platform_runtime.structured_logging import log_exception_with_context
from .document_conversion import (
    convert_html_to_docx,
    convert_html_to_odt,
    find_soffice,
)

try:
    import markdown

    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False


def _run_pandoc_convert(
    source_path: str,
    output_path: str,
    *,
    source_format: str,
    output_format: str,
    title: str,
    reference_doc: str | None = None,
    toc: bool = False,
) -> None:
    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise RuntimeError(
            "Pandoc not found. Install from https://pandoc.org/ "
            "(e.g. apt-get install pandoc)."
        )

    cmd = [
        pandoc,
        source_path,
        "-o",
        output_path,
        "--from",
        source_format,
        "--to",
        output_format,
        "--metadata",
        f"title={title}",
    ]
    if toc:
        cmd.append("--toc")
    if reference_doc and os.path.isfile(reference_doc):
        cmd.extend(["--reference-doc", reference_doc])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if result.returncode != 0:
        raise RuntimeError(
            f"Pandoc conversion failed: {result.stderr or result.stdout or 'unknown error'}"
        )
    if not os.path.isfile(output_path):
        raise RuntimeError("Pandoc did not produce output.")


def _simple_markdown_to_html(content: str) -> str:
    html = content

    html = re.sub(r"^# (.+)$", r"<h1>\\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$", r"<h3>\\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^#### (.+)$", r"<h4>\\1</h4>", html, flags=re.MULTILINE)

    html = re.sub(r"\\*\\*(.+?)\\*\\*", r"<strong>\\1</strong>", html)
    html = re.sub(r"\\*(.+?)\\*", r"<em>\\1</em>", html)
    html = re.sub(
        r"```(\\w+)?\\n(.*?)```",
        r"<pre><code class=\"language-\\1\">\\2</code></pre>",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(r"`(.+?)`", r"<code>\\1</code>", html)
    html = re.sub(r"\\[(.+?)\\]\\((.+?)\\)", r"<a href=\"\\2\">\\1</a>", html)

    lines = html.split("\n")
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("<"):
            out.append(f"<p>{stripped}</p>")
        else:
            out.append(line)
    return "\n".join(out)


# §2.4: Typed exceptions for markdown conversion fallback (broad_exception_audit)
_MARKDOWN_CONVERT_ERRORS = (
    TypeError,
    ValueError,
    KeyError,
    AttributeError,
    LookupError,
)


def markdown_to_html(content: str) -> str:
    if MARKDOWN_AVAILABLE:
        try:
            md = markdown.Markdown(
                extensions=["fenced_code", "tables", "nl2br", "sane_lists"]
            )
            return md.convert(content)
        except _MARKDOWN_CONVERT_ERRORS:
            log_exception_with_context(
                "portal.document_generation: markdown convert failed, using simple fallback",
                extra={
                    "module": "document_generation",
                    "fallback": "_simple_markdown_to_html",
                },
            )
    return _simple_markdown_to_html(content)


def html_to_odt(
    html_content: str,
    title: str = "Document",
    reference_doc: str | None = None,
) -> bytes:
    """
    Convert HTML to ODT using Pandoc.
    """
    with tempfile.TemporaryDirectory(prefix="portal_odt_") as tmp:
        html_path = os.path.join(tmp, "input.html")
        odt_path = os.path.join(tmp, "output.odt")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        _run_pandoc_convert(
            html_path,
            odt_path,
            source_format="html",
            output_format="odt",
            title=title,
            reference_doc=reference_doc,
            toc=False,
        )

        with open(odt_path, "rb") as f:
            return f.read()


def html_to_docx(
    html_content: str,
    title: str = "Document",
    reference_doc: str | None = None,
) -> bytes:
    """
    Convert HTML to DOCX using Pandoc.
    """
    with tempfile.TemporaryDirectory(prefix="portal_docx_") as tmp:
        html_path = os.path.join(tmp, "input.html")
        docx_path = os.path.join(tmp, "output.docx")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        _run_pandoc_convert(
            html_path,
            docx_path,
            source_format="html",
            output_format="docx",
            title=title,
            reference_doc=reference_doc,
            toc=False,
        )

        with open(docx_path, "rb") as f:
            return f.read()


def markdown_to_document(
    markdown_content: str,
    *,
    output_format: str,
    title: str = "Document",
    reference_doc: str | None = None,
    engine: str = "auto",
    toc: bool = False,
) -> bytes:
    """
    Convert Markdown to ODT or DOCX.

    engine:
    - auto: prefer Pandoc; fallback to LibreOffice HTML conversion
    - pandoc: direct markdown conversion with Pandoc
    - libreoffice: markdown -> html -> LibreOffice conversion
    """
    fmt = (output_format or "").lower().strip()
    if fmt not in {"odt", "docx"}:
        raise ValueError(f"Unsupported output format: {output_format}")

    requested_engine = (engine or "auto").lower().strip()
    if requested_engine not in {"auto", "pandoc", "libreoffice"}:
        raise ValueError(f"Unsupported engine: {engine}")

    pandoc_available = shutil.which("pandoc") is not None
    libreoffice_available = find_soffice() is not None

    if requested_engine == "auto":
        selected_engine = "pandoc" if pandoc_available else "libreoffice"
    else:
        selected_engine = requested_engine

    if selected_engine == "pandoc" and not pandoc_available:
        raise RuntimeError("Pandoc not found for markdown conversion.")
    if selected_engine == "libreoffice" and not libreoffice_available:
        raise RuntimeError("LibreOffice not found for markdown conversion.")

    if selected_engine == "pandoc":
        with tempfile.TemporaryDirectory(prefix="portal_md_convert_") as tmp:
            md_path = os.path.join(tmp, "input.md")
            out_path = os.path.join(tmp, f"output.{fmt}")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            _run_pandoc_convert(
                md_path,
                out_path,
                source_format="markdown",
                output_format=fmt,
                title=title,
                reference_doc=reference_doc,
                toc=toc,
            )
            with open(out_path, "rb") as f:
                return f.read()

    html = markdown_to_html(markdown_content)
    if fmt == "odt":
        return convert_html_to_odt(html, title=title)
    return convert_html_to_docx(html, title=title)
