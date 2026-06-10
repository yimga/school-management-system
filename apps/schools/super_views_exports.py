"""
Super admin CSV/PDF exports (BR-12 split from super_views).
"""

from __future__ import annotations

import csv
from io import StringIO

from django.db import DatabaseError
from django.db.models import Count, OuterRef, Subquery, Sum
from django.http import HttpResponse
from django.utils import timezone

from .models import School, SchoolProvisioningEvent
from .super_views_dashboard_helpers import parse_month_param, selected_system_names
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_AUDIT_EXPORT,
    require_platform_scope,
)

@require_platform_scope(PLATFORM_SCOPE_AUDIT_EXPORT)
def export_schools_csv(request):
    """Export schools list as CSV with unified fleet status columns."""
    from apps.schools.control_plane_lifecycle import batch_current_subscriptions
    from apps.schools.fleet_status import build_fleet_queryset, resolve_school_fleet_status

    latest_event_query = SchoolProvisioningEvent.objects.filter(
        school_id=OuterRef("pk")
    ).order_by("-created_at", "-id")
    schools = list(
        build_fleet_queryset()
        .prefetch_related("tenant_systems__system")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
        .annotate(teacher_count=Count("teacher_profiles", distinct=True))
        .annotate(
            latest_event_created_at=Subquery(
                latest_event_query.values("created_at")[:1]
            )
        )
    )
    subs = batch_current_subscriptions(schools)
    for school in schools:
        school.selected_systems = selected_system_names(school)
        school.fleet_status = resolve_school_fleet_status(
            school, cached_subscription=subs.get(school.pk)
        )

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "Name",
            "Slug",
            "Subdomain",
            "Template/Systems",
            "Domain",
            "Domain Verified",
            "Fleet Status",
            "Heatmap Tier",
            "Operational State",
            "Active",
            "Approved",
            "Frozen",
            "Provisioning",
            "Students",
            "Teachers",
            "Members",
            "Last activity",
        ]
    )
    for school in schools:
        systems_str = (
            ", ".join(school.selected_systems) if school.selected_systems else ""
        )
        domain_verified = (
            "Yes" if getattr(school, "custom_domain_verified", False) else "No"
        )
        fs = school.fleet_status or {}
        provisioning = (
            (school.latest_event_type or "") if school.latest_event_type else ""
        )
        last_activity = (
            school.updated_at.strftime("%Y-%m-%d %H:%M") if school.updated_at else ""
        )
        w.writerow(
            [
                school.name or "",
                school.slug or "",
                school.subdomain or "",
                systems_str,
                getattr(school, "custom_domain", "") or "",
                domain_verified,
                fs.get("fleet_state_label") or "",
                fs.get("heatmap_tier") or "",
                fs.get("lifecycle_state") or "",
                "Yes" if school.is_active else "No",
                "Yes" if school.is_approved else "No",
                "Yes" if getattr(school, "is_frozen", False) else "No",
                provisioning,
                school.student_count or 0,
                school.teacher_count or 0,
                school.member_count or 0,
                last_activity,
            ]
        )
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="schools-fleet-status.csv"'
    return resp
@require_platform_scope(PLATFORM_SCOPE_AUDIT_EXPORT)
def export_super_dashboard_pdf(request):
    """Export a one-page PDF summary: North Star, financial snapshot, operational snapshot (RUNMYCAMPUS_UI_IMPROVEMENTS)."""
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    from apps.billing.models import TenantSubscription
    from apps.observability.models import PlatformIncident
    from apps.siteconfig.models import RevenueSnapshot

    first_of_month = parse_month_param(request)
    total_mrr = total_waived = waiver_percentage = 0
    revenue_by_country = []
    try:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        snapshots = RevenueSnapshot.objects.filter(snapshot_date=first_of_month)
        agg = snapshots.aggregate(
            total_actual=Sum("actual_revenue"), total_waived=Sum("waived_amount")
        )
        total_mrr = agg["total_actual"] or 0
        total_waived = agg["total_waived"] or 0
        total_all = total_mrr + total_waived
        waiver_percentage = (
            (float(total_waived) / float(total_all) * 100) if total_all else 0
        )
        revenue_by_country = list(
            snapshots.values("country_code")
            .annotate(actual=Sum("actual_revenue"), waived=Sum("waived_amount"))
            .order_by("-actual", "-waived")[:10]
        )
    except DatabaseError:
        pass

    school_count = School.objects.filter(is_active=True).count()
    pending_approval_count = School.objects.filter(is_approved=False).count()
    from apps.schools.fleet_status import resolve_fleet_summary

    fleet_summary = resolve_fleet_summary()
    open_incident_count = PlatformIncident.objects.filter(
        status__in=[
            PlatformIncident.Status.OPEN,
            PlatformIncident.Status.ACKNOWLEDGED,
            PlatformIncident.Status.MITIGATED,
        ],
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    ).count()
    billing_exceptions_count = TenantSubscription.objects.filter(
        status__in=[
            TenantSubscription.Status.PAST_DUE,
            TenantSubscription.Status.SUSPENDED,
        ],
    ).count()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="Title", parent=styles["Title"], fontSize=16, spaceAfter=12
    )
    heading_style = ParagraphStyle(
        name="Heading", parent=styles["Heading2"], fontSize=12, spaceAfter=6
    )
    body_style = styles["Normal"]

    flow = []
    flow.append(Paragraph("RunMyCampus Mission Control — Summary", title_style))
    flow.append(
        Paragraph(
            f"Report date: {timezone.now().strftime('%Y-%m-%d %H:%M')} | Snapshot month: {first_of_month.strftime('%B %Y')}",
            body_style,
        )
    )
    flow.append(Spacer(1, 0.25 * inch))

    flow.append(Paragraph("North Star", heading_style))
    north_star_label = "Total MRR"
    north_star_value = f"${total_mrr:,.2f}"
    flow.append(Paragraph(f"<b>{north_star_label}:</b> {north_star_value}", body_style))
    flow.append(Spacer(1, 0.2 * inch))

    flow.append(Paragraph("Financial snapshot", heading_style))
    fin_data = [
        ["Metric", "Value"],
        ["MRR (actual)", f"${total_mrr:,.2f}"],
        ["Waived", f"${total_waived:,.2f}"],
        ["Waiver %", f"{waiver_percentage:.1f}%"],
    ]
    fin_table = Table(fin_data, colWidths=[2.5 * inch, 2 * inch])
    fin_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    flow.append(fin_table)
    if revenue_by_country:
        flow.append(Spacer(1, 0.15 * inch))
        flow.append(Paragraph("Revenue by country (top 5)", body_style))
        country_data = [["Country", "Actual", "Waived"]]
        for row in revenue_by_country[:5]:
            country_data.append(
                [
                    row["country_code"] or "—",
                    f"${(row.get('actual') or 0):,.2f}",
                    f"${(row.get('waived') or 0):,.2f}",
                ]
            )
        country_table = Table(
            country_data, colWidths=[1.5 * inch, 1.5 * inch, 1.5 * inch]
        )
        country_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        flow.append(country_table)
    flow.append(Spacer(1, 0.25 * inch))

    flow.append(Paragraph("Operational snapshot", heading_style))
    ops_data = [
        ["Metric", "Count"],
        ["Total fleet", str(fleet_summary.get("total") or 0)],
        ["Live (healthy + trial)", str(fleet_summary.get("live") or 0)],
        ["Watch (provisioning / pending)", str(fleet_summary.get("watch") or 0)],
        ["Critical (suspended / billing / errors)", str(fleet_summary.get("critical") or 0)],
        ["Inactive / idle", str(fleet_summary.get("idle") or 0)],
        ["Active tenants", str(school_count)],
        ["Pending approvals", str(pending_approval_count)],
        ["Open platform incidents", str(open_incident_count)],
        ["Billing exceptions (past due / suspended)", str(billing_exceptions_count)],
    ]
    ops_table = Table(ops_data, colWidths=[3.5 * inch, 1.5 * inch])
    ops_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    flow.append(ops_table)

    doc.build(flow)
    resp = HttpResponse(buf.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = (
        'attachment; filename="runmycampus-mission-control-summary.pdf"'
    )
    return resp


@require_platform_scope(PLATFORM_SCOPE_AUDIT_EXPORT)
def export_fleet_status_odt(request):
    """Export full fleet status report as ODT (LibreOffice / Pandoc / built-in fallback)."""
    from apps.portal.document_conversion import find_soffice
    from apps.portal.document_generation import markdown_to_document
    from apps.schools.fleet_report_markdown import build_fleet_status_markdown

    markdown = build_fleet_status_markdown()
    engine = "libreoffice" if find_soffice() is not None else "auto"
    try:
        content = markdown_to_document(
            markdown,
            output_format="odt",
            title="RunMyCampus Fleet Status",
            engine=engine,
        )
    except (RuntimeError, ValueError):
        content = markdown_to_document(
            markdown,
            output_format="odt",
            title="RunMyCampus Fleet Status",
            engine="auto",
        )

    stamp = timezone.now().strftime("%Y%m%d-%H%M")
    resp = HttpResponse(content, content_type="application/vnd.oasis.opendocument.text")
    resp["Content-Disposition"] = f'attachment; filename="fleet-status-{stamp}.odt"'
    return resp


@require_platform_scope(PLATFORM_SCOPE_AUDIT_EXPORT)
def export_revenue_csv(request):
    """Export revenue by country for selected month as CSV (powerhouse upgrade: export)."""
    from django.db.models import Sum
    from apps.siteconfig.models import RevenueSnapshot

    first_of_month = parse_month_param(request)
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    try:
        snapshots = RevenueSnapshot.objects.filter(snapshot_date=first_of_month)
        revenue_by_country = list(
            snapshots.values("country_code")
            .annotate(actual=Sum("actual_revenue"), waived=Sum("waived_amount"))
            .order_by("-actual", "-waived")
        )
    except DatabaseError:
        revenue_by_country = []

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["Country", "Actual", "Waived", "Month"])
    month_str = first_of_month.strftime("%Y-%m")
    for row in revenue_by_country:
        w.writerow(
            [
                row.get("country_code") or "",
                row.get("actual") or 0,
                row.get("waived") or 0,
                month_str,
            ]
        )
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = (
        f'attachment; filename="revenue-by-country-{month_str}.csv"'
    )
    return resp
