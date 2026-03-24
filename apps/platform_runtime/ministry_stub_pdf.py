"""
Ministry / statutory stub PDF generation (ReportLab) — shared by tenant API and manager preview.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def build_ministry_stub_pdf_bytes(
    stub: str,
    label: str,
    *,
    school_name: str | None = None,
    country_code: str | None = None,
) -> bytes:
    """Return PDF bytes for a ministry stub shell (jurisdiction-aware when country_code is set)."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    from apps.platform_runtime.learning_institution_catalog import (
        STATUTORY_JURISDICTION_HINTS,
    )

    cc = (country_code or "").strip().upper()[:2]
    hint = STATUTORY_JURISDICTION_HINTS.get(cc) if cc else None
    if cc and len(cc) == 2 and cc.isalpha() and not hint:
        hint = {
            "label": f"Jurisdiction ({cc})",
            "framework": "Configure region pack and statutory connectors — this PDF is a shell only.",
        }

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle(f"Ministry report — {label}")
    y = 750
    c.drawString(72, y, "RunMyCampus — Ministry / statutory export (generated shell)")
    y -= 24
    c.drawString(72, y, f"Report: {label}")
    y -= 24
    c.drawString(72, y, f"Stub key: {stub}")
    y -= 24
    if cc:
        c.drawString(72, y, f"Jurisdiction code: {cc} — {hint['label'] if hint else ''}")
        y -= 24
        if hint:
            c.drawString(72, y, f"Framework note: {hint['framework'][:90]}")
            y -= 20
            if len(hint["framework"]) > 90:
                c.drawString(72, y, f"  {hint['framework'][90:180]}")
                y -= 20
    if school_name:
        c.drawString(72, y, f"Tenant: {school_name}")
    else:
        c.drawString(72, y, "Tenant: (not resolved in session)")
    y -= 36
    c.drawString(
        72,
        y,
        "This document is a structured shell for RFP / accreditation / statutory workflows.",
    )
    y -= 20
    c.drawString(
        72,
        y,
        "Replace with live aggregates when ministry connectors and region packs are fully wired.",
    )
    c.showPage()
    c.save()
    return buf.getvalue()
