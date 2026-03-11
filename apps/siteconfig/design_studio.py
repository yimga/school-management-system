"""
Phase F: Design Studio — hydrate DesignTemplate layout with context and render to PDF.
One document type (e.g. certificate) first; extend to report_card and others.
"""
import logging

from django.template import Context, Template
from django.http import HttpResponse

logger = logging.getLogger(__name__)
OPTIONAL_DESIGN_STUDIO_ERRORS = (AttributeError, OSError, RuntimeError, TypeError, ValueError)


def render_template_to_html(template, context: dict) -> str:
    """
    Hydrate a DesignTemplate's layout with context. Layout may contain
    placeholders like {{ student_name }} and optional HTML structure in layout["html"].
    """
    layout = template.layout if isinstance(template.layout, dict) else {}
    html_skeleton = layout.get("html") or "<div>{{ body }}</div>"
    body_parts = []
    for key, value in context.items():
        body_parts.append(f"<p><strong>{key}:</strong> {value}</p>")
    body = "\n".join(body_parts)
    ctx = Context({**context, "body": body})
    t = Template(html_skeleton)
    return t.render(ctx)


def render_template_to_pdf(template, context: dict, base_url: str | None = None) -> bytes | None:
    """
    Render DesignTemplate to PDF using WeasyPrint when available.
    Returns PDF bytes or None if WeasyPrint is not installed or render fails.
    """
    html = render_template_to_html(template, context)
    try:
        from weasyprint import HTML
        return HTML(string=html, base_url=base_url or "/").write_pdf()
    except (ImportError, AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
        logger.warning("Design Studio PDF render failed: %s", e)
        return None


def design_template_http_response_pdf(template, context: dict, filename: str = "document.pdf") -> HttpResponse:
    """Return an HttpResponse with PDF content for download/preview."""
    pdf_bytes = render_template_to_pdf(template, context)
    if pdf_bytes is None:
        return HttpResponse(
            "PDF generation unavailable. Install weasyprint and ensure layout is valid.",
            status=503,
            content_type="text/plain",
        )
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
