"""Modern HTML -> PDF rendering using WeasyPrint.

We keep this separate from ReportLab so you can choose either:
- ReportLab: good for programmatic PDFs
- WeasyPrint: best for branded, CSS-based report cards

Usage (example):
    from apps.reports.weasy import render_pdf
    return render_pdf(request, "reports/term_report.html", context, filename="report.pdf")
"""

from __future__ import annotations

from django.http import HttpResponse
from django.template.loader import get_template
from django.conf import settings

def _load_weasyprint_html():
    try:
        from weasyprint import HTML
    except Exception as exc:
        raise RuntimeError(
            "WeasyPrint dependencies are missing. Install system libraries first."
        ) from exc
    return HTML


def render_pdf_bytes(request, template_name: str, context: dict) -> bytes:
    html_string = get_template(template_name).render(context, request=request)

    # Base URL lets WeasyPrint resolve /static/ and media URLs.
    base_url = getattr(settings, "WEASYPRINT_BASEURL", None) or request.build_absolute_uri("/")

    HTML = _load_weasyprint_html()
    return HTML(string=html_string, base_url=base_url).write_pdf()


def render_pdf(request, template_name: str, context: dict, filename: str = "document.pdf") -> HttpResponse:
    pdf_bytes = render_pdf_bytes(request, template_name, context)

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp
