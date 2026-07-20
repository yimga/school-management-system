"""Render achievement certificates via CertificateLocalizer + template.

Metric 21: RTL locales (ar/he/fa/ur) must emit ``dir="rtl"`` and the matching
language pack — proved by ``test_certificate_rtl_render`` and the Playwright
fixture suite under ``tests/e2e/certificate-rtl.spec.js``.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from apps.reports.localization import CertificateLocalizer, get_certificate_localizer

CERTIFICATE_TEMPLATE = "reports/certificate_document.html"
RTL_CERTIFICATE_LOCALES = ("ar", "he", "fa", "ur")


def render_certificate_html(
    *,
    language: str,
    student_data: dict[str, Any] | None = None,
    region_code: str | None = None,
) -> str:
    """Return a full HTML certificate document for ``language``."""
    localizer = get_certificate_localizer(language=language, region_code=region_code)
    data = {
        "student": "Amina Hassan",
        "academic_year": "2025-2026",
        "average": 88.0,
        "rank": 3,
        "promotion_status": "PROMOTED",
        "date_issued": "2026-07-18",
        "school_name": "RunMyCampus Demo School",
    }
    if student_data:
        data.update(student_data)
    context = localizer.get_certificate_context(data)
    return render_to_string(CERTIFICATE_TEMPLATE, context)


def write_rtl_e2e_fixtures(destination_dir) -> list[str]:
    """Materialize ar/he/fa/ur certificate HTML fixtures for Playwright (serverless)."""
    from pathlib import Path

    dest = Path(destination_dir)
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for lang in RTL_CERTIFICATE_LOCALES:
        html = render_certificate_html(language=lang)
        path = dest / f"certificate-rtl-{lang}.html"
        path.write_text(html, encoding="utf-8")
        written.append(str(path))
    return written


__all__ = [
    "CERTIFICATE_TEMPLATE",
    "RTL_CERTIFICATE_LOCALES",
    "CertificateLocalizer",
    "render_certificate_html",
    "write_rtl_e2e_fixtures",
]
