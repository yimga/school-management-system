"""
Document generation utilities for KB and report exports.

Supports:
- HTML -> ODT/DOCX via Pandoc with built-in serializer fallback
- Markdown -> ODT/DOCX via Pandoc, built-in serializer, or explicit LibreOffice
"""

import io
import logging
import os
import re
import shutil
import subprocess
import zipfile
from contextlib import contextmanager
from html.parser import HTMLParser
from xml.sax.saxutils import escape

from apps.platform_runtime.structured_logging import log_exception_with_context
from .document_conversion import (
    convert_html_to_docx,
    convert_html_to_odt,
    find_soffice,
    portal_tempdir,
)

try:
    import markdown

    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False

try:
    from odf.opendocument import OpenDocumentText
    from odf.text import H as ODFHeading
    from odf.text import P as ODFParagraph

    ODF_AVAILABLE = True
except ImportError:
    ODF_AVAILABLE = False


@contextmanager
def _suppress_markdown_debug_logs():
    logger = logging.getLogger("MARKDOWN")
    original_level = logger.level
    if original_level in {logging.NOTSET, logging.DEBUG}:
        logger.setLevel(logging.INFO)
    try:
        yield
    finally:
        logger.setLevel(original_level)


class _HTMLBlockParser(HTMLParser):
    _HEADING_LEVELS = {f"h{level}": level for level in range(1, 7)}
    _PARAGRAPH_TAGS = {"p", "div", "section", "article", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict[str, object]] = []
        self._buffer: list[str] = []
        self._kind: str | None = None
        self._level = 0
        self._list_stack: list[dict[str, int | bool]] = []

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in self._HEADING_LEVELS:
            self._flush()
            self._kind = "heading"
            self._level = self._HEADING_LEVELS[tag]
            return
        if tag in self._PARAGRAPH_TAGS:
            self._flush()
            self._kind = "paragraph"
            self._level = 0
            return
        if tag == "pre":
            self._flush()
            self._kind = "preformatted"
            self._level = 0
            return
        if tag in {"ul", "ol"}:
            self._flush()
            self._list_stack.append({"ordered": tag == "ol", "index": 1})
            return
        if tag == "li":
            self._flush()
            self._kind = "paragraph"
            self._level = 0
            marker = "* "
            if self._list_stack and bool(self._list_stack[-1]["ordered"]):
                marker = f"{int(self._list_stack[-1]['index'])}. "
                self._list_stack[-1]["index"] = int(self._list_stack[-1]["index"]) + 1
            self._buffer.append(marker)
            return
        if tag == "tr":
            self._flush()
            self._kind = "paragraph"
            self._level = 0
            return
        if tag in {"td", "th"}:
            if self._buffer:
                self._buffer.append(" | ")
            return
        if tag == "br":
            self._buffer.append("\n")
            return
        if tag == "hr":
            self._flush()
            self.blocks.append({"kind": "paragraph", "level": 0, "text": "---"})

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in self._HEADING_LEVELS or tag in self._PARAGRAPH_TAGS or tag in {
            "li",
            "pre",
            "tr",
        }:
            self._flush()
            return
        if tag in {"ul", "ol"}:
            self._flush()
            if self._list_stack:
                self._list_stack.pop()
            return
        if tag in {"td", "th"} and self._buffer:
            self._buffer.append(" | ")

    def handle_data(self, data: str):
        if not data:
            return
        if self._kind is None:
            self._kind = "paragraph"
            self._level = 0
        self._buffer.append(data)

    def close(self):
        super().close()
        self._flush()

    def _flush(self):
        if self._kind is None:
            self._buffer.clear()
            return
        raw_text = "".join(self._buffer)
        self._buffer = []
        kind = self._kind
        level = self._level
        self._kind = None
        self._level = 0
        if kind == "preformatted":
            text = raw_text.replace("\r\n", "\n").strip("\n")
        else:
            text = re.sub(r"[ \t\f\v]+", " ", raw_text)
            text = re.sub(r" *\n *", "\n", text)
            text = re.sub(r"(?:\s*\|\s*)+$", "", text)
            text = text.strip()
        if text:
            self.blocks.append({"kind": kind, "level": level, "text": text})


def _html_to_blocks(html_content: str) -> list[dict[str, object]]:
    parser = _HTMLBlockParser()
    parser.feed(html_content or "")
    parser.close()
    return parser.blocks


def _serialize_html_to_odt(html_content: str, *, title: str) -> bytes:
    if not ODF_AVAILABLE:
        raise RuntimeError("odfpy is required for built-in ODT generation.")
    document = OpenDocumentText()
    blocks = _html_to_blocks(html_content)
    if not blocks:
        blocks = [{"kind": "heading", "level": 1, "text": title}]
    for block in blocks:
        block_text = str(block["text"])
        if block["kind"] == "heading":
            document.text.addElement(
                ODFHeading(outlinelevel=min(max(int(block["level"]), 1), 6), text=block_text)
            )
            continue
        for line in block_text.split("\n") or [""]:
            text = line if line else " "
            document.text.addElement(ODFParagraph(text=text))
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _docx_run_xml(text: str, *, bold: bool = False, size: int | None = None) -> str:
    escaped = escape(text if text else " ")
    properties: list[str] = []
    if bold:
        properties.append("<w:b/>")
    if size:
        properties.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    run_props = f"<w:rPr>{''.join(properties)}</w:rPr>" if properties else ""
    return f"<w:r>{run_props}<w:t xml:space=\"preserve\">{escaped}</w:t></w:r>"


def _docx_paragraph_xml(block: dict[str, object]) -> str:
    kind = str(block["kind"])
    text = str(block["text"])
    size_map = {1: 32, 2: 28, 3: 26, 4: 24, 5: 22, 6: 20}
    lines = text.split("\n") or [text]
    parts = ["<w:p>"]
    if kind == "heading":
        size = size_map.get(int(block["level"]), 24)
        for index, line in enumerate(lines):
            parts.append(_docx_run_xml(line, bold=True, size=size))
            if index < len(lines) - 1:
                parts.append("<w:r><w:br/></w:r>")
    else:
        for index, line in enumerate(lines):
            parts.append(_docx_run_xml(line))
            if index < len(lines) - 1:
                parts.append("<w:r><w:br/></w:r>")
    parts.append("</w:p>")
    return "".join(parts)


def _serialize_html_to_docx(html_content: str, *, title: str) -> bytes:
    blocks = _html_to_blocks(html_content)
    if not blocks:
        blocks = [{"kind": "heading", "level": 1, "text": title}]
    body_xml = "".join(_docx_paragraph_xml(block) for block in blocks)
    document_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        "<w:body>"
        f"{body_xml}"
        "<w:sectPr>"
        "<w:pgSz w:w=\"12240\" w:h=\"15840\"/>"
        "<w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" "
        "w:header=\"720\" w:footer=\"720\" w:gutter=\"0\"/>"
        "</w:sectPr>"
        "</w:body>"
        "</w:document>"
    )
    content_types_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" "
        "ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/word/document.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
        "</Types>"
    )
    relationships_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" "
        "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" "
        "Target=\"word/document.xml\"/>"
        "</Relationships>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", relationships_xml)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


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
            with _suppress_markdown_debug_logs():
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
    Convert HTML to ODT using Pandoc when available, otherwise a built-in serializer.
    """
    if shutil.which("pandoc"):
        with portal_tempdir("portal_odt_") as tmp:
            html_path = tmp / "input.html"
            odt_path = tmp / "output.odt"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            try:
                _run_pandoc_convert(
                    str(html_path),
                    str(odt_path),
                    source_format="html",
                    output_format="odt",
                    title=title,
                    reference_doc=reference_doc,
                    toc=False,
                )
            except RuntimeError:
                log_exception_with_context(
                    "portal.document_generation: pandoc html->odt failed, using built-in serializer",
                    extra={"module": "document_generation", "fallback": "internal_odt"},
                )
            else:
                with open(odt_path, "rb") as f:
                    return f.read()
    return _serialize_html_to_odt(html_content, title=title)


def html_to_docx(
    html_content: str,
    title: str = "Document",
    reference_doc: str | None = None,
) -> bytes:
    """
    Convert HTML to DOCX using Pandoc when available, otherwise a built-in serializer.
    """
    if shutil.which("pandoc"):
        with portal_tempdir("portal_docx_") as tmp:
            html_path = tmp / "input.html"
            docx_path = tmp / "output.docx"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            try:
                _run_pandoc_convert(
                    str(html_path),
                    str(docx_path),
                    source_format="html",
                    output_format="docx",
                    title=title,
                    reference_doc=reference_doc,
                    toc=False,
                )
            except RuntimeError:
                log_exception_with_context(
                    "portal.document_generation: pandoc html->docx failed, using built-in serializer",
                    extra={"module": "document_generation", "fallback": "internal_docx"},
                )
            else:
                with open(docx_path, "rb") as f:
                    return f.read()
    return _serialize_html_to_docx(html_content, title=title)


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
    - auto: prefer Pandoc; fallback to built-in HTML serialization
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
    if requested_engine == "auto":
        selected_engine = "pandoc" if pandoc_available else "internal"
    else:
        selected_engine = requested_engine

    if selected_engine == "pandoc" and not pandoc_available:
        raise RuntimeError("Pandoc not found for markdown conversion.")
    if selected_engine == "libreoffice" and find_soffice() is None:
        raise RuntimeError("LibreOffice not found for markdown conversion.")

    if selected_engine == "pandoc":
        with portal_tempdir("portal_md_convert_") as tmp:
            md_path = tmp / "input.md"
            out_path = tmp / f"output.{fmt}"
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            try:
                _run_pandoc_convert(
                    str(md_path),
                    str(out_path),
                    source_format="markdown",
                    output_format=fmt,
                    title=title,
                    reference_doc=reference_doc,
                    toc=toc,
                )
            except RuntimeError:
                if requested_engine != "auto":
                    raise
                log_exception_with_context(
                    "portal.document_generation: pandoc markdown convert failed, using built-in serializer",
                    extra={"module": "document_generation", "fallback": "internal_markdown"},
                )
            else:
                with open(out_path, "rb") as f:
                    return f.read()

    html = markdown_to_html(markdown_content)
    if selected_engine == "libreoffice":
        if fmt == "odt":
            return convert_html_to_odt(html, title=title)
        return convert_html_to_docx(html, title=title)
    if fmt == "odt":
        return html_to_odt(html, title=title, reference_doc=reference_doc)
    return html_to_docx(html, title=title, reference_doc=reference_doc)
