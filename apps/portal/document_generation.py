"""
Optional document generation: HTML to ODT for letters, report cards, bulk export.

Requires Pandoc (https://pandoc.org/). Use for:
- Report card "Download as ODT" (render term report HTML, then pass to html_to_odt).
- Bulk letters / mail merge: render a letter template per recipient, then html_to_odt each;
  or merge placeholders in a single ODT template (future enhancement).

Usage:
    from django.template.loader import render_to_string
    from apps.portal.document_generation import html_to_odt

    html = render_to_string("reports/term_report.html", context)
    odt_bytes = html_to_odt(html, title=f"Report {student.student_code}")
    # Serve or save odt_bytes
"""
import os
import shutil
import subprocess
import tempfile


def html_to_odt(
    html_content: str,
    title: str = "Document",
    reference_doc: str | None = None,
) -> bytes:
    """
    Convert HTML to LibreOffice ODT using Pandoc.

    Args:
        html_content: Full HTML string (e.g. from render_to_string).
        title: Document title (Pandoc metadata).
        reference_doc: Optional path to reference.odt for styling.

    Returns:
        ODT file content as bytes.

    Raises:
        RuntimeError: If Pandoc is not found or conversion fails.
    """
    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise RuntimeError(
            "Pandoc not found. Install from https://pandoc.org/ "
            "(e.g. apt-get install pandoc) to use HTML to ODT conversion."
        )

    with tempfile.TemporaryDirectory(prefix="portal_odt_") as tmp:
        html_path = os.path.join(tmp, "input.html")
        odt_path = os.path.join(tmp, "output.odt")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        cmd = [
            pandoc,
            html_path,
            "-o",
            odt_path,
            "--from=html",
            "--to=odt",
            "--metadata",
            f"title={title}",
        ]
        if reference_doc and os.path.isfile(reference_doc):
            cmd.extend(["--reference-doc", reference_doc])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(
                f"Pandoc conversion failed: {result.stderr or result.stdout or 'unknown error'}"
            )
        if not os.path.isfile(odt_path):
            raise RuntimeError("Pandoc did not produce ODT output.")

        with open(odt_path, "rb") as f:
            return f.read()
