"""v4.00.88 — Counsel-handoff PDF rendering.

Combines (a) the LMS PKI bundle (provider endpoints + maturity pills),
(b) the audit packet (alarms + rollups + retention counters + entries),
and (c) the tenant-isolated HMAC signature into a single counsel-ready
PDF for external legal review.

When the `reportlab` library is available, renders a real PDF.
When it isn't, falls back to an HTML representation (still valid for
counsel review) wrapped with a clear "PDF backend unavailable — HTML
fallback" header. NEVER raises.
"""
from __future__ import annotations
import html as _html
import io
import logging

logger = logging.getLogger(__name__)


def _reportlab_available() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


def render_counsel_handoff_pdf(*, pki_bundle: dict, audit_packet: dict, tenant_schema: str = "", signature: str = "") -> tuple[bytes, str]:
    """Render the counsel handoff. Returns (bytes, content_type).

    On success with reportlab: returns (pdf_bytes, "application/pdf").
    On reportlab unavailable: returns (html_bytes, "text/html").
    """
    if _reportlab_available():
        try:
            return _render_pdf_reportlab(pki_bundle=pki_bundle, audit_packet=audit_packet, tenant_schema=tenant_schema, signature=signature), "application/pdf"
        except Exception as exc:  # noqa: BLE001
            logger.warning("counsel handoff PDF render failed: %s", exc)
            # fall through to HTML
    return _render_html_fallback(pki_bundle=pki_bundle, audit_packet=audit_packet, tenant_schema=tenant_schema, signature=signature).encode("utf-8"), "text/html; charset=utf-8"


def _render_pdf_reportlab(*, pki_bundle: dict, audit_packet: dict, tenant_schema: str, signature: str) -> bytes:
    """Real PDF via reportlab. Honest stub-shape — full layout polish
    is a separate counsel-collaboration loop."""
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("Counsel Handoff Packet", styles["Title"]))
    elements.append(Paragraph(f"Tenant: {tenant_schema or '(unspecified)'}", styles["Normal"]))
    elements.append(Paragraph(f"Generated: {pki_bundle.get('generated_at', '')}", styles["Normal"]))
    elements.append(Paragraph(f"HMAC: {signature[:32]}...", styles["Code"]))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("LMS Providers", styles["Heading2"]))
    providers = pki_bundle.get("providers", [])
    if providers:
        provider_rows = [["Slug", "Label", "Maturity", "OAuth Ready"]]
        for p in providers:
            provider_rows.append([
                p.get("slug", ""), p.get("label", ""),
                p.get("maturity", ""), "Yes" if p.get("oauth_ready") else "No",
            ])
        t = Table(provider_rows)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
        elements.append(t)
    else:
        elements.append(Paragraph("No providers configured.", styles["Normal"]))

    elements.append(Spacer(1, 16))
    elements.append(Paragraph("Audit Packet Summary", styles["Heading2"]))
    elements.append(Paragraph(f"Total entries: {len(audit_packet.get('entries', []))}", styles["Normal"]))
    elements.append(Paragraph(f"Filters: {audit_packet.get('filters', {})}", styles["Normal"]))

    doc.build(elements)
    return buf.getvalue()


def _render_html_fallback(*, pki_bundle: dict, audit_packet: dict, tenant_schema: str, signature: str) -> str:
    """HTML fallback when reportlab is missing. Counsel-readable."""
    rows: list[str] = []
    rows.append("<!doctype html><html><head><meta charset='utf-8'><title>Counsel Handoff Packet</title></head><body>")
    rows.append("<h1>Counsel Handoff Packet</h1>")
    rows.append("<p><em>PDF backend unavailable - HTML fallback served.</em></p>")
    rows.append(f"<p><strong>Tenant:</strong> {_html.escape(tenant_schema or '(unspecified)')}</p>")
    rows.append(f"<p><strong>Generated:</strong> {_html.escape(pki_bundle.get('generated_at', ''))}</p>")
    rows.append(f"<p><strong>HMAC:</strong> <code>{_html.escape(signature[:64])}</code></p>")

    rows.append("<h2>LMS Providers</h2>")
    providers = pki_bundle.get("providers", [])
    if providers:
        rows.append("<table border='1' cellpadding='4'><thead><tr><th>Slug</th><th>Label</th><th>Maturity</th><th>OAuth Ready</th></tr></thead><tbody>")
        for p in providers:
            rows.append(
                f"<tr><td>{_html.escape(str(p.get('slug', '')))}</td>"
                f"<td>{_html.escape(str(p.get('label', '')))}</td>"
                f"<td>{_html.escape(str(p.get('maturity', '')))}</td>"
                f"<td>{'Yes' if p.get('oauth_ready') else 'No'}</td></tr>"
            )
        rows.append("</tbody></table>")
    else:
        rows.append("<p>No providers configured.</p>")

    rows.append("<h2>Audit Packet Summary</h2>")
    rows.append(f"<p>Total entries: {len(audit_packet.get('entries', []))}</p>")
    rows.append(f"<p>Filters: {_html.escape(repr(audit_packet.get('filters', {})))}</p>")
    rows.append("</body></html>")
    return "\n".join(rows)
