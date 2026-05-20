"""
North-star weekly report: CSV + optional PDF attachment (batch 1356).
"""

from __future__ import annotations

import csv
import io
from typing import Any

from django.template.loader import render_to_string
from django.utils import timezone

from apps.portal.help_north_star import build_north_star_bundle


def north_star_csv_bytes(*, days: int = 7) -> bytes:
    bundle = build_north_star_bundle(days=days)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["metric", "value"])
    writer.writerow(["days", bundle.get("days", "")])
    writer.writerow(["generated_at", bundle.get("generated_at", "")])
    defl = bundle.get("deflection") or {}
    for key in (
        "deflection_rate_pct",
        "suggested",
        "dismissed",
        "opened",
        "submitted",
        "total_events",
    ):
        writer.writerow([f"deflection.{key}", defl.get(key, "")])
    csat = bundle.get("csat") or {}
    for key in ("ratings_count", "thumbs_up", "thumbs_down", "avg_stars"):
        writer.writerow([f"csat.{key}", csat.get(key, "")])
    for key in (
        "searches",
        "deflection_events",
        "ai_reviews_pending",
        "ai_csat_count",
        "ai_csat_positive_pct",
    ):
        if key in bundle:
            writer.writerow([key, bundle.get(key, "")])
    return buf.getvalue().encode("utf-8")


def north_star_pdf_bytes(*, days: int = 7, base_url: str = "/") -> bytes | None:
    bundle = build_north_star_bundle(days=days)
    html = render_to_string(
        "portal/email/help_north_star_report.html",
        {"bundle": bundle, "generated_at": timezone.now()},
    )
    try:
        from django.conf import settings

        from apps.reports.weasy import _load_weasyprint_html

        resolved_base = getattr(settings, "WEASYPRINT_BASEURL", None) or base_url
        HTML = _load_weasyprint_html()
        return HTML(string=html, base_url=resolved_base).write_pdf()
    except Exception:
        return None


def send_north_star_weekly_email(*, days: int = 7) -> dict[str, Any]:
    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives

    recipients_raw = (
        getattr(settings, "HELP_NORTH_STAR_WEEKLY_EMAIL", None)
        or getattr(settings, "OPERATOR_ALERT_EMAIL", None)
        or getattr(settings, "MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL", None)
        or ""
    )
    recipients = [e.strip() for e in str(recipients_raw).split(",") if e.strip()]
    if not recipients:
        return {"ok": False, "reason": "no_recipients"}

    csv_body = north_star_csv_bytes(days=days)
    subject = f"RunMyCampus Help North Star ({days}d)"
    text = (
        "Weekly help center north-star metrics are attached as CSV. "
        "Open manager Help analytics for interactive drill-down."
    )
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=recipients,
    )
    stamp = timezone.now().strftime("%Y%m%d")
    msg.attach(f"help-north-star-{stamp}.csv", csv_body, "text/csv")
    pdf = north_star_pdf_bytes(days=days)
    if pdf:
        msg.attach(f"help-north-star-{stamp}.pdf", pdf, "application/pdf")
    msg.send(fail_silently=False)
    return {"ok": True, "recipients": recipients, "pdf_attached": bool(pdf)}
