"""
Super Admin views: dashboard (list schools) and Create School wizard.
Access restricted to SUPERADMIN or is_superuser via TenantSuperAdminRequiredMiddleware.
"""
import csv
import json
from datetime import timedelta
from io import StringIO

from django.contrib import messages
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods, require_POST
from django.http import JsonResponse, HttpResponse
from django.utils import timezone

from apps.registries.models import (
    CountryRegistry,
    EducationLevelRegistry,
    EducationSystemTypeRegistry,
    SubdivisionRegistry,
)
from apps.registries.services import (
    ensure_registry_baseline,
    list_country_choices,
    list_subdivision_choices,
)
from apps.siteconfig.education_profile_engine import (
    ensure_region_for_country as ensure_region_for_country_record,
    list_template_catalog,
    list_profile_options,
)
from apps.siteconfig.global_catalog import GlobalGeoCatalog
from apps.global_registries.models import EducationSystemProfile
from apps.platform_runtime.helpers import get_platform_defaults
from apps.siteconfig.tenant_config import apply_tenant_settings_overrides
from .control_plane_lifecycle import apply_school_lifecycle_action, get_lifecycle_snapshot
from .models import School, SchoolProvisioningEvent, TenantApiUsage, TenantQuotaLimit


def _safe_school_admin_change_url(school_id) -> str:
    try:
        return reverse("admin:schools_school_change", args=[school_id])
    except NoReverseMatch:
        return ""
    except Exception:
        return ""


def _safe_school_timeline_url(school_id) -> str:
    try:
        return reverse("super:api_school_timeline", args=[school_id])
    except NoReverseMatch:
        return ""
    except Exception:
        return ""


def _clamp_int(value, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _ensure_region_for_country(country_code: str, timezone_hint: str = "UTC"):
    return ensure_region_for_country_record(country_code, timezone_hint=timezone_hint)


def _canonical_country_alpha2(raw_country_code: str | None) -> str:
    normalized = GlobalGeoCatalog.normalize_country_code(raw_country_code)
    alpha2 = GlobalGeoCatalog.alpha2_for_country(normalized or raw_country_code)
    if alpha2:
        return alpha2.upper()
    raw = (raw_country_code or "").strip().upper()
    return raw if len(raw) == 2 else ""


def _resolve_subdivision(country_code: str | None, *, subdivision_id=None, province_id=None):
    alpha2 = _canonical_country_alpha2(country_code)
    if subdivision_id not in (None, ""):
        try:
            return SubdivisionRegistry.objects.filter(pk=int(subdivision_id), country_id=alpha2).first()
        except (TypeError, ValueError):
            return None
    if province_id in (None, ""):
        return None
    try:
        province_id = int(province_id)
    except (TypeError, ValueError):
        return None
    from apps.global_registries.models import Province

    province = Province.objects.select_related("region").filter(pk=province_id).first()
    if not province:
        return None
    alpha2 = _canonical_country_alpha2(province.region_id)
    if not alpha2:
        return None
    country = CountryRegistry.objects.filter(code=alpha2).first()
    if not country:
        return None
    subdivision, _created = SubdivisionRegistry.objects.get_or_create(
        country=country,
        code=str(province.code or province.name).upper()[:32],
        defaults={
            "name": province.name,
            "subdivision_type": "province",
            "metadata": {
                "legacy_province_id": province.pk,
                "legacy_region_code": province.region_id,
            },
        },
    )
    return subdivision


def _resolve_registry_codes(model, raw_codes: list[str]) -> list:
    codes = [str(code or "").strip().upper() for code in raw_codes if str(code or "").strip()]
    if not codes:
        return []
    rows = list(model.objects.filter(code__in=codes, is_active=True))
    rows_by_code = {str(row.code).upper(): row for row in rows}
    return [rows_by_code[code] for code in codes if code in rows_by_code]


def _safe_registry_url():
    """URL to Global Registry (EducationSystemProfile CRUD in admin). Phase H."""
    try:
        return reverse("admin:siteconfig_educationsystemprofile_changelist")
    except NoReverseMatch:
        return ""


def _selected_system_names(school) -> list[str]:
    """
    Return selected education-system names for a school.
    Handles RelatedManager or list-like prefetched collections.
    """
    tenant_systems = getattr(school, "tenant_systems", None)
    if hasattr(tenant_systems, "all"):
        tenant_systems = tenant_systems.all()
    if not tenant_systems:
        return []
    return [ts.system.name for ts in tenant_systems if getattr(ts, "system", None)]


def _safe_command_center_url() -> str:
    try:
        return reverse("super:command_center")
    except NoReverseMatch:
        return ""


def _safe_platform_incidents_url() -> str:
    try:
        return reverse("platform_incidents_console")
    except NoReverseMatch:
        return ""


def _brand_profile_for_school(school):
    try:
        return school.brand_profile
    except Exception:
        return None


def _education_level_label(level, country_code: str) -> str:
    labels = getattr(level, "country_labels", {}) or {}
    return str(labels.get(country_code) or getattr(level, "global_name", "") or getattr(level, "code", ""))


def _education_system_type_label(system_type, country_code: str) -> str:
    labels = getattr(system_type, "country_labels", {}) or {}
    return str(labels.get(country_code) or getattr(system_type, "name", "") or getattr(system_type, "code", ""))


def _status_tone(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"critical", "past_due", "past due", "suspended", "error", "open"}:
        return "danger"
    if normalized in {"warning", "acknowledged", "mitigated", "trialing", "pending"}:
        return "warning"
    if normalized in {"healthy", "active", "resolved", "success", "verified"}:
        return "success"
    return "neutral"


def _safe_percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 1)


def _build_command_center_data() -> dict:
    """
    Phase 3 mission-control metrics:
    - Provisioning SLA (request -> completed)
    - Churn risk indicators
    - Support backlog aging
    - Phase 4 differentiators (recovery rate, passport portability)
    """
    now = timezone.now()
    today = now.date()
    data = {
        "provisioning_sla_avg_hours": 0.0,
        "provisioning_sla_target_hours": 24,
        "provisioning_sla_breaches": 0,
        "provisioning_sla_samples": 0,
        "provisioning_breach_rows": [],
        "support_open_count": 0,
        "support_backlog_48h_count": 0,
        "support_backlog_7d_count": 0,
        "support_oldest_open_hours": 0.0,
        "support_stale_rows": [],
        "tenant_churn_risk_count": 0,
        "tenant_churn_risk_rows": [],
        "tenant_inactive_30d_count": 0,
        "trial_ending_soon_count": 0,
        "recovery_rate_pct": 0.0,
        "resolved_interventions": 0,
        "total_interventions": 0,
        "student_passport_count": 0,
        "student_passport_invite_count": 0,
    }

    open_ticket_statuses = {"OPEN", "IN_PROGRESS", "WAITING"}

    # Provisioning SLA
    try:
        from django.db.models import Min

        request_rows = (
            SchoolProvisioningEvent.objects.filter(
                event_type=SchoolProvisioningEvent.EventType.REQUEST_RECEIVED,
                created_at__gte=now - timedelta(days=60),
            )
            .values("school_id")
            .annotate(requested_at=Min("created_at"))
        )
        complete_rows = (
            SchoolProvisioningEvent.objects.filter(
                event_type=SchoolProvisioningEvent.EventType.COMPLETED,
                created_at__gte=now - timedelta(days=60),
            )
            .values("school_id")
            .annotate(completed_at=Min("created_at"))
        )
        request_map = {row["school_id"]: row["requested_at"] for row in request_rows}
        complete_map = {row["school_id"]: row["completed_at"] for row in complete_rows}
        durations = []
        breach_rows = []
        for school_id, requested_at in request_map.items():
            completed_at = complete_map.get(school_id)
            if not completed_at or completed_at < requested_at:
                continue
            hours = (completed_at - requested_at).total_seconds() / 3600.0
            durations.append(hours)
            if hours > data["provisioning_sla_target_hours"]:
                breach_rows.append({"school_id": school_id, "hours": round(hours, 1)})
        data["provisioning_sla_samples"] = len(durations)
        data["provisioning_sla_avg_hours"] = round(sum(durations) / len(durations), 1) if durations else 0.0
        data["provisioning_sla_breaches"] = len(breach_rows)
        data["provisioning_breach_rows"] = breach_rows[:20]
    except Exception:
        pass

    # Support backlog aging
    stale_urgent_school_ids: set = set()
    try:
        from apps.siteconfig.models import GlobalSupportTicket

        qs = GlobalSupportTicket.objects.filter(status__in=open_ticket_statuses).select_related("school").order_by("created_at")
        tickets = list(qs[:300])
        stale_rows = []
        oldest_open_hours = 0.0
        for ticket in tickets:
            age_hours = max(0.0, (now - ticket.created_at).total_seconds() / 3600.0)
            if age_hours > oldest_open_hours:
                oldest_open_hours = age_hours
            if age_hours >= 48:
                stale_rows.append(
                    {
                        "ticket": ticket,
                        "age_hours": round(age_hours, 1),
                    }
                )
            if ticket.priority == "URGENT" and age_hours >= 48:
                stale_urgent_school_ids.add(ticket.school_id)
        data["support_open_count"] = qs.count()
        data["support_backlog_48h_count"] = sum(1 for row in stale_rows if row["age_hours"] >= 48)
        data["support_backlog_7d_count"] = sum(1 for row in stale_rows if row["age_hours"] >= (24 * 7))
        data["support_oldest_open_hours"] = round(oldest_open_hours, 1)
        data["support_stale_rows"] = stale_rows[:25]
    except Exception:
        pass

    # Tenant churn risk heuristic
    try:
        schools = list(
            School.objects.filter(is_active=True).only(
                "id",
                "name",
                "slug",
                "last_activity",
                "billing_type",
                "trial_end_date",
            )
        )
        risk_rows = []
        inactive_count = 0
        trial_soon_count = 0
        for school in schools:
            reasons = []
            last_activity = getattr(school, "last_activity", None)
            if not last_activity or (now - last_activity) > timedelta(days=30):
                reasons.append("No activity in 30+ days")
                inactive_count += 1
            if getattr(school, "billing_type", "") == School.BillingType.FREE_TRIAL:
                trial_end = getattr(school, "trial_end_date", None)
                if trial_end and trial_end <= (today + timedelta(days=7)):
                    reasons.append("Free trial ending in <= 7 days")
                    trial_soon_count += 1
            if school.id in stale_urgent_school_ids:
                reasons.append("Urgent support ticket stale 48h+")
            if reasons:
                risk_rows.append(
                    {
                        "school": school,
                        "reasons": reasons,
                        "risk_score": len(reasons),
                    }
                )
        risk_rows.sort(key=lambda row: (-row["risk_score"], row["school"].name))
        data["tenant_churn_risk_count"] = len(risk_rows)
        data["tenant_churn_risk_rows"] = risk_rows[:25]
        data["tenant_inactive_30d_count"] = inactive_count
        data["trial_ending_soon_count"] = trial_soon_count
    except Exception:
        pass

    # Phase 4 differentiator metrics
    try:
        from apps.analytics.models import InterventionLog

        total_interventions = InterventionLog.objects.count()
        resolved = InterventionLog.objects.filter(status=InterventionLog.Status.RESOLVED).count()
        data["total_interventions"] = total_interventions
        data["resolved_interventions"] = resolved
        data["recovery_rate_pct"] = round((resolved / total_interventions) * 100, 1) if total_interventions else 0.0
    except Exception:
        pass

    try:
        from apps.people.models import StudentPassport, PassportSchoolInvite

        data["student_passport_count"] = StudentPassport.objects.count()
        data["student_passport_invite_count"] = PassportSchoolInvite.objects.count()
    except Exception:
        pass

    return data


def _parse_month_param(request) -> "date":
    """Parse ?month=YYYY-MM; return first day of that month or current month."""
    from datetime import date
    month_str = request.GET.get("month")
    if not month_str:
        return timezone.now().date().replace(day=1)
    try:
        year, month = int(month_str[:4]), int(month_str[5:7])
        if 1 <= month <= 12 and year >= 2020 and year <= 2100:
            return date(year, month, 1)
    except (ValueError, TypeError, IndexError):
        pass
    return timezone.now().date().replace(day=1)


def _month_options(last_n=12):
    """Return list of (value 'YYYY-MM', label 'Month YYYY') for last N months (current first)."""
    from datetime import date
    now = timezone.now().date()
    first = now.replace(day=1)
    options = []
    for _ in range(last_n):
        options.append((first.strftime("%Y-%m"), first.strftime("%B %Y")))
        if first.month == 1:
            first = first.replace(year=first.year - 1, month=12, day=1)
        else:
            first = first.replace(month=first.month - 1, day=1)
    return options


def _get_super_dashboard_section_order(user):
    """Return the section order for the super dashboard (per-user, from DB)."""
    from apps.runtime_blueprints.models import SuperAdminDashboardPreference, SUPER_DASHBOARD_DEFAULT_SECTION_ORDER
    if not user or not user.is_authenticated:
        return list(SUPER_DASHBOARD_DEFAULT_SECTION_ORDER)
    pref = SuperAdminDashboardPreference.objects.filter(user=user).first()
    if not pref:
        return list(SUPER_DASHBOARD_DEFAULT_SECTION_ORDER)
    return pref.get_section_order()


def super_dashboard(request):
    """List all schools with basic stats. Phase E: Financial Bento. Phase H: Registry link, selected education systems."""
    from django.db.models import Sum
    from apps.siteconfig.models import RevenueSnapshot

    # Global date filter: ?month=YYYY-MM for Financial Mission Control
    first_of_month = _parse_month_param(request)
    month_options = _month_options(12)
    current_request_month = first_of_month.strftime("%Y-%m")

    latest_event_query = SchoolProvisioningEvent.objects.filter(school_id=OuterRef("pk")).order_by("-created_at", "-id")
    schools = list(
        School.objects.all()
        .prefetch_related("tenant_systems__system")
        .order_by("name")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
        .annotate(teacher_count=Count("teacher_profiles", distinct=True))
        .annotate(latest_event_type=Subquery(latest_event_query.values("event_type")[:1]))
        .annotate(latest_event_status=Subquery(latest_event_query.values("status")[:1]))
        .annotate(latest_event_created_at=Subquery(latest_event_query.values("created_at")[:1]))
    )
    for school in schools:
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
        school.timeline_url = _safe_school_timeline_url(school.pk)
        school.sync_repair_url = reverse("super:sync_repair", args=[school.pk])
        school.selected_systems = _selected_system_names(school)

    # Phase E: Financial Mission Control / Bento (selected month); resilient if RevenueSnapshot not migrated
    total_mrr = total_waived = waiver_percentage = 0
    revenue_by_country = []
    billing_model_breakdown = []
    try:
        snapshots = RevenueSnapshot.objects.filter(snapshot_date=first_of_month)
        agg = snapshots.aggregate(total_actual=Sum("actual_revenue"), total_waived=Sum("waived_amount"))
        total_mrr = (agg["total_actual"] or 0)
        total_waived = (agg["total_waived"] or 0)
        total_all = total_mrr + total_waived
        waiver_percentage = (float(total_waived) / float(total_all) * 100) if total_all else 0
        revenue_by_country = list(
            snapshots.values("country_code")
            .annotate(actual=Sum("actual_revenue"), waived=Sum("waived_amount"))
            .order_by("-actual", "-waived")[:20]
        )
        billing_model_breakdown = list(
            snapshots.values("billing_model")
            .annotate(count=Count("id"), actual=Sum("actual_revenue"), waived=Sum("waived_amount"))
            .order_by("-actual", "-waived")
        )
    except Exception:
        pass

    # Phase H optional: approval workflow — count and list pending schools
    pending_schools = list(
        School.objects.filter(is_approved=False)
        .prefetch_related("tenant_systems__system")
        .order_by("-created_at")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
    )
    for school in pending_schools:
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
        school.timeline_url = _safe_school_timeline_url(school.pk)
        school.selected_systems = _selected_system_names(school)
    pending_approval_count = len(pending_schools)

    # Section 8.7–8.8: Health / resource hogs (PostgreSQL table sizes)
    health_top_tables = []
    health_schema_stats = []
    try:
        from .health_utils import get_top_tables_by_size, get_global_health_stats
        health_top_tables = get_top_tables_by_size(limit=10)
        health_schema_stats = get_global_health_stats()
    except Exception:
        pass

    command_center = _build_command_center_data()

    # North Star: prefer Total MRR when present, else school count
    school_count = len(schools)
    if total_mrr is not None and total_mrr > 0:
        north_star_value = total_mrr
        north_star_label = "Total MRR"
        north_star_formatted = f"${total_mrr:,.2f}"
    else:
        north_star_value = school_count
        north_star_label = "Schools"
        north_star_formatted = str(school_count)

    # Next-best-action strip (pending approvals, trials ending soon)
    next_best_actions = []
    if pending_approval_count:
        next_best_actions.append({
            "label": f"{pending_approval_count} pending approval" + ("s" if pending_approval_count != 1 else ""),
            "url": request.path + "#pending-approval",
            "count": pending_approval_count,
        })
    if command_center.get("trial_ending_soon_count", 0):
        cc_url = _safe_command_center_url()
        if cc_url:
            next_best_actions.append({
                "label": f"{command_center['trial_ending_soon_count']} trial(s) ending soon",
                "url": cc_url,
                "count": command_center["trial_ending_soon_count"],
            })
    if command_center.get("provisioning_sla_breaches", 0):
        cc_url = _safe_command_center_url()
        if cc_url:
            next_best_actions.append({
                "label": f"{command_center['provisioning_sla_breaches']} provisioning breach(es)",
                "url": cc_url,
                "count": command_center["provisioning_sla_breaches"],
            })

    return render(
        request,
        "schools/super_dashboard.html",
        {
            "schools": schools,
            "pending_schools": pending_schools,
            "pending_approval_count": pending_approval_count,
            "total_mrr": total_mrr,
            "total_waived": total_waived,
            "waiver_percentage": round(waiver_percentage, 1),
            "revenue_by_country": revenue_by_country,
            "billing_model_breakdown": billing_model_breakdown,
            "revenue_snapshot_month": first_of_month,
            "current_request_month": current_request_month,
            "month_options": month_options,
            "school_count": school_count,
            "north_star_value": north_star_value,
            "north_star_label": north_star_label,
            "north_star_formatted": north_star_formatted,
            "next_best_actions": next_best_actions,
            "registry_url": _safe_registry_url(),
            "command_center_url": _safe_command_center_url(),
            "health_top_tables": health_top_tables,
            "health_schema_stats": health_schema_stats,
            "command_center": command_center,
        },
    )


def export_schools_csv(request):
    """Export schools list as CSV (powerhouse upgrade: export)."""
    latest_event_query = SchoolProvisioningEvent.objects.filter(school_id=OuterRef("pk")).order_by("-created_at", "-id")
    schools = list(
        School.objects.all()
        .prefetch_related("tenant_systems__system")
        .order_by("name")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
        .annotate(teacher_count=Count("teacher_profiles", distinct=True))
        .annotate(latest_event_type=Subquery(latest_event_query.values("event_type")[:1]))
        .annotate(latest_event_created_at=Subquery(latest_event_query.values("created_at")[:1]))
    )
    for school in schools:
        school.selected_systems = _selected_system_names(school)

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Name", "Slug", "Subdomain", "Template/Systems", "Domain", "Domain Verified",
        "Status", "Provisioning", "Students", "Teachers", "Members", "Last activity",
    ])
    for school in schools:
        systems_str = ", ".join(school.selected_systems) if school.selected_systems else ""
        domain_verified = "Yes" if getattr(school, "custom_domain_verified", False) else "No"
        status = "Active" if school.is_active else "Inactive"
        provisioning = (school.latest_event_type or "") if school.latest_event_type else ""
        last_activity = school.updated_at.strftime("%Y-%m-%d %H:%M") if school.updated_at else ""
        w.writerow([
            school.name or "",
            school.slug or "",
            school.subdomain or "",
            systems_str,
            getattr(school, "custom_domain", "") or "",
            domain_verified,
            status,
            provisioning,
            school.student_count or 0,
            school.teacher_count or 0,
            school.member_count or 0,
            last_activity,
        ])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="schools.csv"'
    return resp


def export_super_dashboard_pdf(request):
    """Export a one-page PDF summary: North Star, financial snapshot, operational snapshot (RUNMYCAMPUS_UI_IMPROVEMENTS)."""
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    from apps.billing.models import TenantSubscription
    from apps.observability.models import PlatformIncident
    from apps.siteconfig.models import RevenueSnapshot

    first_of_month = _parse_month_param(request)
    total_mrr = total_waived = waiver_percentage = 0
    revenue_by_country = []
    try:
        snapshots = RevenueSnapshot.objects.filter(snapshot_date=first_of_month)
        agg = snapshots.aggregate(total_actual=Sum("actual_revenue"), total_waived=Sum("waived_amount"))
        total_mrr = agg["total_actual"] or 0
        total_waived = agg["total_waived"] or 0
        total_all = total_mrr + total_waived
        waiver_percentage = (float(total_waived) / float(total_all) * 100) if total_all else 0
        revenue_by_country = list(
            snapshots.values("country_code")
            .annotate(actual=Sum("actual_revenue"), waived=Sum("waived_amount"))
            .order_by("-actual", "-waived")[:10]
        )
    except Exception:
        pass

    school_count = School.objects.filter(is_active=True).count()
    pending_approval_count = School.objects.filter(is_approved=False).count()
    open_incident_count = PlatformIncident.objects.filter(
        status__in=[
            PlatformIncident.Status.OPEN,
            PlatformIncident.Status.ACKNOWLEDGED,
            PlatformIncident.Status.MITIGATED,
        ],
    ).count()
    billing_exceptions_count = TenantSubscription.objects.filter(
        status__in=[TenantSubscription.Status.PAST_DUE, TenantSubscription.Status.SUSPENDED],
    ).count()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(name="Title", parent=styles["Title"], fontSize=16, spaceAfter=12)
    heading_style = ParagraphStyle(name="Heading", parent=styles["Heading2"], fontSize=12, spaceAfter=6)
    body_style = styles["Normal"]

    flow = []
    flow.append(Paragraph("RunMyCampus Mission Control — Summary", title_style))
    flow.append(Paragraph(f"Report date: {timezone.now().strftime('%Y-%m-%d %H:%M')} | Snapshot month: {first_of_month.strftime('%B %Y')}", body_style))
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
    fin_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    flow.append(fin_table)
    if revenue_by_country:
        flow.append(Spacer(1, 0.15 * inch))
        flow.append(Paragraph("Revenue by country (top 5)", body_style))
        country_data = [["Country", "Actual", "Waived"]]
        for row in revenue_by_country[:5]:
            country_data.append([row["country_code"] or "—", f"${(row.get('actual') or 0):,.2f}", f"${(row.get('waived') or 0):,.2f}"])
        country_table = Table(country_data, colWidths=[1.5 * inch, 1.5 * inch, 1.5 * inch])
        country_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        flow.append(country_table)
    flow.append(Spacer(1, 0.25 * inch))

    flow.append(Paragraph("Operational snapshot", heading_style))
    ops_data = [
        ["Metric", "Count"],
        ["Active tenants", str(school_count)],
        ["Pending approvals", str(pending_approval_count)],
        ["Open platform incidents", str(open_incident_count)],
        ["Billing exceptions (past due / suspended)", str(billing_exceptions_count)],
    ]
    ops_table = Table(ops_data, colWidths=[3.5 * inch, 1.5 * inch])
    ops_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    flow.append(ops_table)

    doc.build(flow)
    resp = HttpResponse(buf.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="runmycampus-mission-control-summary.pdf"'
    return resp


@require_http_methods(["GET", "POST", "PUT", "PATCH"])
def api_super_dashboard_layout(request):
    """GET: return section_order for current user. POST/PUT/PATCH: save section_order (JSON body)."""
    from apps.runtime_blueprints.models import (
        SuperAdminDashboardPreference,
        SUPER_DASHBOARD_DEFAULT_SECTION_ORDER,
    )
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if request.method == "GET":
        order = _get_super_dashboard_section_order(request.user)
        return JsonResponse({"section_order": order})
    # POST/PUT/PATCH: save
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    order = body.get("section_order")
    if not isinstance(order, list):
        return JsonResponse({"error": "section_order must be a list"}, status=400)
    valid_ids = set(SUPER_DASHBOARD_DEFAULT_SECTION_ORDER)
    order = [str(s) for s in order if s in valid_ids]
    pref, _ = SuperAdminDashboardPreference.objects.get_or_create(
        user=request.user,
        defaults={"section_order": order or list(SUPER_DASHBOARD_DEFAULT_SECTION_ORDER)},
    )
    pref.section_order = order or list(SUPER_DASHBOARD_DEFAULT_SECTION_ORDER)
    pref.save(update_fields=["section_order", "updated_at"])
    return JsonResponse({"section_order": pref.get_section_order()})


def super_dashboard_v2(request):
    """Mission-control control plane for the manager host."""
    from apps.billing.models import BillingAccount, TenantSubscription
    from apps.events.legacy_bridge import legacy_webhook_sync_snapshot
    from apps.observability.models import PlatformIncident
    from apps.observability.monitoring import SystemHealthMonitor
    from apps.brand_experience.models import BrandProfile
    from apps.siteconfig.models import RevenueSnapshot

    first_of_month = _parse_month_param(request)
    month_options = _month_options(12)
    current_request_month = first_of_month.strftime("%Y-%m")

    latest_event_query = SchoolProvisioningEvent.objects.filter(school_id=OuterRef("pk")).order_by("-created_at", "-id")
    latest_subscription_query = TenantSubscription.objects.filter(school_id=OuterRef("pk")).order_by("-updated_at", "-created_at")
    country_names = {
        code: name
        for code, name in CountryRegistry.objects.filter(is_active=True).values_list("code", "name")
    }
    schools = list(
        School.objects.all()
        .select_related("subdivision", "default_region")
        .prefetch_related("tenant_systems__system", "education_levels", "education_system_types")
        .order_by("-is_active", "name")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
        .annotate(teacher_count=Count("teacher_profiles", distinct=True))
        .annotate(latest_event_type=Subquery(latest_event_query.values("event_type")[:1]))
        .annotate(latest_event_status=Subquery(latest_event_query.values("status")[:1]))
        .annotate(latest_event_created_at=Subquery(latest_event_query.values("created_at")[:1]))
        .annotate(latest_subscription_status=Subquery(latest_subscription_query.values("status")[:1]))
        .annotate(latest_subscription_amount=Subquery(latest_subscription_query.values("billed_amount")[:1]))
        .annotate(latest_subscription_period_end=Subquery(latest_subscription_query.values("current_period_end")[:1]))
    )

    total_mrr = total_waived = waiver_percentage = 0
    revenue_by_country = []
    billing_model_breakdown = []
    try:
        snapshots = RevenueSnapshot.objects.filter(snapshot_date=first_of_month)
        agg = snapshots.aggregate(total_actual=Sum("actual_revenue"), total_waived=Sum("waived_amount"))
        total_mrr = (agg["total_actual"] or 0)
        total_waived = (agg["total_waived"] or 0)
        total_all = total_mrr + total_waived
        waiver_percentage = (float(total_waived) / float(total_all) * 100) if total_all else 0
        revenue_by_country = list(
            snapshots.values("country_code")
            .annotate(actual=Sum("actual_revenue"), waived=Sum("waived_amount"))
            .order_by("-actual", "-waived")[:20]
        )
        billing_model_breakdown = list(
            snapshots.values("billing_model")
            .annotate(count=Count("id"), actual=Sum("actual_revenue"), waived=Sum("waived_amount"))
            .order_by("-actual", "-waived")
        )
    except Exception:
        pass

    pending_schools = list(
        School.objects.filter(is_approved=False)
        .prefetch_related("tenant_systems__system")
        .order_by("-created_at")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
    )
    for school in pending_schools:
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
        school.timeline_url = _safe_school_timeline_url(school.pk)
        school.selected_systems = _selected_system_names(school)
        school.country_display = country_names.get(school.canonical_country_code, school.canonical_country_code or "Unassigned")
    pending_approval_count = len(pending_schools)

    health_top_tables = []
    health_schema_stats = []
    try:
        from .health_utils import get_top_tables_by_size, get_global_health_stats

        health_top_tables = get_top_tables_by_size(limit=10)
        health_schema_stats = get_global_health_stats()
    except Exception:
        pass

    command_center = _build_command_center_data()
    platform_incidents = list(
        PlatformIncident.objects.select_related("affected_school")
        .filter(
            status__in=[
                PlatformIncident.Status.OPEN,
                PlatformIncident.Status.ACKNOWLEDGED,
                PlatformIncident.Status.MITIGATED,
            ]
        )
        .order_by("-detected_at", "-created_at")[:12]
    )
    incident_counts = {
        row["status"]: row["total"]
        for row in PlatformIncident.objects.values("status").annotate(total=Count("id"))
    }
    critical_incident_count = PlatformIncident.objects.filter(
        status__in=[
            PlatformIncident.Status.OPEN,
            PlatformIncident.Status.ACKNOWLEDGED,
            PlatformIncident.Status.MITIGATED,
        ],
        severity__in=[PlatformIncident.Severity.CRITICAL, PlatformIncident.Severity.HIGH],
    ).count()
    billing_watchlist = list(
        TenantSubscription.objects.select_related("school", "billing_account", "plan")
        .filter(status__in=[TenantSubscription.Status.PAST_DUE, TenantSubscription.Status.SUSPENDED])
        .order_by("-updated_at", "school__name")[:12]
    )
    active_subscription_count = TenantSubscription.objects.filter(
        status__in=[TenantSubscription.Status.ACTIVE, TenantSubscription.Status.TRIALING]
    ).count()
    billing_account_count = BillingAccount.objects.count()
    webhook_stack = legacy_webhook_sync_snapshot()
    try:
        platform_health = SystemHealthMonitor.get_comprehensive_health()
    except Exception:
        platform_health = {
            "overall_status": "warning",
            "cpu": {"usage_percent": 0.0, "threshold": 80.0, "status": "warning"},
            "memory": {"usage_percent": 0.0, "used_mb": 0.0, "threshold": 85.0, "status": "warning"},
            "disk": {"usage_percent": 0.0, "free_gb": 0.0, "threshold": 90.0, "status": "warning"},
            "database": {"status": "unhealthy", "response_time_ms": 0.0},
            "cache": {"status": "unhealthy", "type": "unknown"},
        }

    registry_counts = {
        "countries": CountryRegistry.objects.filter(is_active=True).count(),
        "subdivisions": SubdivisionRegistry.objects.filter(is_active=True).count(),
        "education_levels": EducationLevelRegistry.objects.filter(is_active=True).count(),
        "education_system_types": EducationSystemTypeRegistry.objects.filter(is_active=True).count(),
    }
    brand_profile_ids = set(BrandProfile.objects.values_list("school_id", flat=True))
    churn_risk_lookup = {
        str(row["school"].id): row
        for row in command_center.get("tenant_churn_risk_rows", [])
        if row.get("school") is not None
    }
    incident_school_ids = {
        incident.affected_school_id
        for incident in platform_incidents
        if getattr(incident, "affected_school_id", None)
    }
    countries_live_codes = {school.canonical_country_code for school in schools if school.canonical_country_code}
    countries_live_count = len(countries_live_codes)
    identity_complete_count = 0
    brand_profile_count = 0
    verified_domain_count = 0
    custom_domain_count = 0
    impersonation_ready_count = 0
    attention_school_count = 0
    recent_schools = sorted(schools, key=lambda school: (school.created_at, school.name), reverse=True)[:8]

    for school in schools:
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
        school.timeline_url = _safe_school_timeline_url(school.pk)
        school.sync_repair_url = reverse("super:sync_repair", args=[school.pk])
        school.selected_systems = _selected_system_names(school)
        school.country_display = country_names.get(school.canonical_country_code, school.canonical_country_code or "Unassigned")
        school.subdivision_display = school.subdivision.name if school.subdivision_id else "-"
        school.education_level_labels = [
            _education_level_label(level, school.canonical_country_code)
            for level in school.education_levels.all()
        ]
        school.education_system_type_labels = [
            _education_system_type_label(system_type, school.canonical_country_code)
            for system_type in school.education_system_types.all()
        ]
        school.has_brand_profile = school.id in brand_profile_ids or _brand_profile_for_school(school) is not None
        school.brand_status = "BrandProfile" if school.has_brand_profile else "Legacy fallback"
        school.subscription_status = (school.latest_subscription_status or "UNSEEDED").upper()
        school.subscription_tone = _status_tone(school.subscription_status)
        school.identity_status = "missing"
        if school.canonical_country_code or school.education_level_labels or school.education_system_type_labels:
            school.identity_status = "partial"
        if school.canonical_country_code and school.education_level_labels and school.education_system_type_labels:
            school.identity_status = "complete"
        school.identity_tone = _status_tone("success" if school.identity_status == "complete" else "warning")
        school.attention_reasons = []
        if not school.is_approved:
            school.attention_reasons.append("Pending approval")
        if getattr(school, "latest_event_status", "") == SchoolProvisioningEvent.Status.ERROR:
            school.attention_reasons.append("Provisioning error")
        if school.subscription_status in {TenantSubscription.Status.PAST_DUE, TenantSubscription.Status.SUSPENDED}:
            school.attention_reasons.append(f"Billing {school.subscription_status.lower().replace('_', ' ')}")
        risk_row = churn_risk_lookup.get(str(school.pk))
        if risk_row and risk_row.get("reasons"):
            school.attention_reasons.append(risk_row["reasons"][0])
        if school.pk in incident_school_ids:
            school.attention_reasons.append("Open platform incident")
        if school.identity_status != "complete":
            school.attention_reasons.append("Canonical identity incomplete")
        school.attention_reasons = school.attention_reasons[:4]
        if school.attention_reasons:
            attention_school_count += 1
        school.roster_state = "healthy"
        if not school.is_active:
            school.roster_state = "inactive"
        elif not school.is_approved:
            school.roster_state = "pending"
        elif school.attention_reasons:
            school.roster_state = "attention"
        school.roster_search = " ".join(
            filter(
                None,
                [
                    school.name,
                    school.slug,
                    school.subdomain,
                    school.country_display,
                    school.subdivision_display,
                    " ".join(school.education_level_labels),
                    " ".join(school.education_system_type_labels),
                    " ".join(school.selected_systems),
                    " ".join(school.attention_reasons),
                    school.subscription_status,
                ],
            )
        ).lower()
        if school.identity_status == "complete":
            identity_complete_count += 1
        if school.has_brand_profile:
            brand_profile_count += 1
        if school.custom_domain:
            custom_domain_count += 1
        if school.custom_domain_verified:
            verified_domain_count += 1
        if school.impersonation_consent_granted_at:
            impersonation_ready_count += 1

    schools.sort(key=lambda school: (-len(school.attention_reasons), school.name.lower()))

    country_rollup = list(
        School.objects.exclude(country_code="")
        .values("country_code")
        .annotate(school_count=Count("id"), student_count=Count("student_profiles", distinct=True))
        .order_by("-school_count", "country_code")[:12]
    )
    revenue_by_country_lookup = {
        str(row.get("country_code") or "").upper(): row
        for row in revenue_by_country
    }
    for row in country_rollup:
        country_code = str(row.get("country_code") or "").upper()
        revenue_row = revenue_by_country_lookup.get(country_code, {})
        row["country_name"] = country_names.get(country_code, country_code or "Unassigned")
        row["actual_revenue"] = revenue_row.get("actual") or 0
        row["waived_revenue"] = revenue_row.get("waived") or 0

    school_count = len(schools)
    if total_mrr is not None and total_mrr > 0:
        north_star_label = "Total MRR"
        north_star_formatted = f"${total_mrr:,.2f}"
    else:
        north_star_label = "Schools"
        north_star_formatted = str(school_count)

    next_best_actions = []
    if pending_approval_count:
        next_best_actions.append({
            "label": f"{pending_approval_count} pending approval" + ("s" if pending_approval_count != 1 else ""),
            "url": request.path + "#cp-action-queue",
            "count": pending_approval_count,
        })
    if command_center.get("trial_ending_soon_count", 0):
        cc_url = _safe_command_center_url()
        if cc_url:
            next_best_actions.append({
                "label": f"{command_center['trial_ending_soon_count']} trial(s) ending soon",
                "url": cc_url,
                "count": command_center["trial_ending_soon_count"],
            })
    if command_center.get("provisioning_sla_breaches", 0):
        cc_url = _safe_command_center_url()
        if cc_url:
            next_best_actions.append({
                "label": f"{command_center['provisioning_sla_breaches']} provisioning breach(es)",
                "url": cc_url,
                "count": command_center["provisioning_sla_breaches"],
            })
    if platform_incidents:
        next_best_actions.append({
            "label": f"{len(platform_incidents)} live incident(s)",
            "url": _safe_platform_incidents_url() or request.path,
            "count": len(platform_incidents),
        })

    overview_cards = [
        {
            "label": "Fleet tenants",
            "value": school_count,
            "meta": f"{sum(1 for school in schools if school.is_active)} active / {pending_approval_count} pending approval",
            "tone": "blue",
        },
        {
            "label": north_star_label,
            "value": north_star_formatted,
            "meta": f"${total_waived:,.2f} waived in {first_of_month.strftime('%b %Y')}",
            "tone": "emerald",
        },
        {
            "label": "Open platform incidents",
            "value": len(platform_incidents),
            "meta": f"{critical_incident_count} critical or high severity",
            "tone": "crimson" if platform_incidents else "slate",
        },
        {
            "label": "Support backlog 48h+",
            "value": command_center.get("support_backlog_48h_count", 0),
            "meta": f"{command_center.get('support_backlog_7d_count', 0)} older than 7 days",
            "tone": "amber" if command_center.get("support_backlog_48h_count", 0) else "slate",
        },
        {
            "label": "Countries live",
            "value": countries_live_count,
            "meta": f"{registry_counts['countries']} countries in registry / {registry_counts['subdivisions']} subdivisions",
            "tone": "sky",
        },
        {
            "label": "Billing exceptions",
            "value": len(billing_watchlist),
            "meta": f"{active_subscription_count} active or trialing subscriptions / {billing_account_count} billing accounts",
            "tone": "violet" if billing_watchlist else "slate",
        },
    ]
    workstream_cards = [
        {
            "title": "Mission queues",
            "metric": pending_approval_count + command_center.get("support_backlog_48h_count", 0) + len(platform_incidents),
            "meta": "Approvals, stale support, incidents, and provisioning breaches",
            "url": _safe_command_center_url(),
            "cta": "Open queues",
        },
        {
            "title": "Platform billing",
            "metric": active_subscription_count,
            "meta": f"{len(billing_watchlist)} tenants need billing attention",
            "url": reverse("super:billing_dashboard"),
            "cta": "Inspect billing",
        },
        {
            "title": "Incident console",
            "metric": len(platform_incidents),
            "meta": f"{critical_incident_count} critical/high severity incidents",
            "url": _safe_platform_incidents_url(),
            "cta": "Review incidents",
        },
        {
            "title": "Usage and quotas",
            "metric": command_center.get("tenant_churn_risk_count", 0),
            "meta": "Usage posture, risk watchlist, and adoption signals",
            "url": reverse("super:usage"),
            "cta": "View usage",
        },
        {
            "title": "Fleet health",
            "metric": str(platform_health.get("overall_status", "unknown")).upper(),
            "meta": f"Webhook drift groups: {webhook_stack.get('unsynced_legacy_groups', 0)}",
            "url": reverse("super:tenant_health"),
            "cta": "Audit tenants",
        },
        {
            "title": "Health hub",
            "metric": "—",
            "meta": "Runbooks, SLOs, incidents, tenant health",
            "url": reverse("super:control_health"),
            "cta": "Health hub",
        },
        {
            "title": "Create school",
            "metric": registry_counts["education_system_types"],
            "meta": "Registry-backed onboarding with branding and control-plane defaults",
            "url": reverse("super:create_school_wizard"),
            "cta": "Provision tenant",
        },
    ]
    readiness_cards = [
        {
            "label": "Canonical identity",
            "value": f"{identity_complete_count}/{school_count}",
            "meta": f"{school_count - identity_complete_count} tenants still partial or missing",
            "tone": "success" if identity_complete_count == school_count else "warning",
        },
        {
            "label": "BrandProfile coverage",
            "value": f"{brand_profile_count}/{school_count}",
            "meta": f"{school_count - brand_profile_count} tenants still rely on compatibility fallbacks",
            "tone": "success" if brand_profile_count == school_count else "warning",
        },
        {
            "label": "Verified domains",
            "value": f"{verified_domain_count}/{custom_domain_count or 0}",
            "meta": f"{custom_domain_count} custom domains configured",
            "tone": "success" if custom_domain_count and verified_domain_count == custom_domain_count else "neutral",
        },
        {
            "label": "Support impersonation consent",
            "value": f"{impersonation_ready_count}/{school_count}",
            "meta": "JIT consent grants available for audited support access",
            "tone": "neutral",
        },
    ]
    platform_health_cards = [
        {
            "label": "CPU",
            "value": f"{platform_health.get('cpu', {}).get('usage_percent', 0):.1f}%",
            "meta": f"threshold {platform_health.get('cpu', {}).get('threshold', 0)}%",
            "tone": _status_tone(platform_health.get("cpu", {}).get("status", "")),
        },
        {
            "label": "Memory",
            "value": f"{platform_health.get('memory', {}).get('usage_percent', 0):.1f}%",
            "meta": f"{platform_health.get('memory', {}).get('used_mb', 0):.0f} MB used",
            "tone": _status_tone(platform_health.get("memory", {}).get("status", "")),
        },
        {
            "label": "Disk",
            "value": f"{platform_health.get('disk', {}).get('usage_percent', 0):.1f}%",
            "meta": f"{platform_health.get('disk', {}).get('free_gb', 0):.1f} GB free",
            "tone": _status_tone(platform_health.get("disk", {}).get("status", "")),
        },
        {
            "label": "Database",
            "value": str(platform_health.get("database", {}).get("status", "unknown")).upper(),
            "meta": f"{platform_health.get('database', {}).get('response_time_ms', 0):.1f} ms health check",
            "tone": _status_tone(platform_health.get("database", {}).get("status", "")),
        },
    ]

    return render(
        request,
        "schools/super_dashboard.html",
        {
            "schools": schools,
            "pending_schools": pending_schools,
            "pending_approval_count": pending_approval_count,
            "total_mrr": total_mrr,
            "total_waived": total_waived,
            "waiver_percentage": round(waiver_percentage, 1),
            "revenue_by_country": revenue_by_country,
            "billing_model_breakdown": billing_model_breakdown,
            "revenue_snapshot_month": first_of_month,
            "current_request_month": current_request_month,
            "month_options": month_options,
            "school_count": school_count,
            "north_star_label": north_star_label,
            "north_star_formatted": north_star_formatted,
            "next_best_actions": next_best_actions,
            "registry_url": _safe_registry_url(),
            "command_center_url": _safe_command_center_url(),
            "health_top_tables": health_top_tables,
            "health_schema_stats": health_schema_stats,
            "command_center": command_center,
            "platform_health": platform_health,
            "platform_health_cards": platform_health_cards,
            "platform_incidents": platform_incidents,
            "platform_incidents_url": _safe_platform_incidents_url(),
            "incident_counts": incident_counts,
            "critical_incident_count": critical_incident_count,
            "billing_watchlist": billing_watchlist,
            "webhook_stack": webhook_stack,
            "registry_counts": registry_counts,
            "country_rollup": country_rollup,
            "countries_live_count": countries_live_count,
            "countries_live_pct": _safe_percentage(countries_live_count, registry_counts["countries"]),
            "overview_cards": overview_cards,
            "workstream_cards": workstream_cards,
            "readiness_cards": readiness_cards,
            "attention_school_count": attention_school_count,
            "recent_schools": recent_schools,
            "tenant_risk_rows": command_center.get("tenant_churn_risk_rows", [])[:12],
            "stale_support_rows": command_center.get("support_stale_rows", [])[:10],
            "provisioning_breach_rows": command_center.get("provisioning_breach_rows", [])[:10],
            "super_dashboard_section_order": _get_super_dashboard_section_order(request.user),
            "super_dashboard_layout_url": reverse("super:api_super_dashboard_layout"),
        },
    )


def export_revenue_csv(request):
    """Export revenue by country for selected month as CSV (powerhouse upgrade: export)."""
    from django.db.models import Sum
    from apps.siteconfig.models import RevenueSnapshot

    first_of_month = _parse_month_param(request)
    try:
        snapshots = RevenueSnapshot.objects.filter(snapshot_date=first_of_month)
        revenue_by_country = list(
            snapshots.values("country_code")
            .annotate(actual=Sum("actual_revenue"), waived=Sum("waived_amount"))
            .order_by("-actual", "-waived")
        )
    except Exception:
        revenue_by_country = []

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["Country", "Actual", "Waived", "Month"])
    month_str = first_of_month.strftime("%Y-%m")
    for row in revenue_by_country:
        w.writerow([
            row.get("country_code") or "",
            row.get("actual") or 0,
            row.get("waived") or 0,
            month_str,
        ])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="revenue-by-country-{month_str}.csv"'
    return resp


def super_usage(request):
    """Plan I: Per-tenant API usage and quota limits for super-admin billing/health."""
    from django.db.models import Sum
    schools = list(
        School.objects.filter(is_active=True)
        .annotate(student_count=Count("student_profiles", distinct=True))
        .order_by("name")
    )
    school_ids = [s.pk for s in schools]
    usage_agg = {
        (r["school_id"], r["limit_type"]): r["total"]
        for r in TenantApiUsage.objects.filter(school_id__in=school_ids)
        .values("school_id", "limit_type")
        .annotate(total=Sum("request_count"))
    }
    quotas = {}
    for q in TenantQuotaLimit.objects.filter(school_id__in=school_ids, is_active=True).values(
        "school_id", "limit_type", "limit_value", "period_days"
    ):
        quotas.setdefault(q["school_id"], []).append(q)
    for school in schools:
        school.api_usage = {k: v for (sid, k), v in usage_agg.items() if sid == school.pk}
        school.quota_limits_list = quotas.get(school.pk, [])
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
    return render(
        request,
        "schools/super_usage.html",
        {"schools": schools},
    )


def super_migration_cloud(request):
    """Migration cloud pillar: control-plane governance for profiles, runs, parity, and rollback."""
    from apps.accounts.migration_services import compute_parity
    from apps.automation.models import MigrationProfile, MigrationRun
    from apps.siteconfig.migration_services import dry_run_import

    profile_slug = (request.GET.get("profile") or "").strip()
    school_id = (request.GET.get("school_id") or "").strip()
    selected_school = None
    if school_id:
        try:
            selected_school = School.objects.filter(id=school_id).first()
        except (TypeError, ValueError):
            selected_school = None
    selected_profile = MigrationProfile.objects.filter(slug=profile_slug, is_active=True).first() if profile_slug else None

    profiles = list(MigrationProfile.objects.filter(is_active=True).order_by("sort_order", "slug"))
    recent_runs = list(
        MigrationRun.objects.select_related("school", "triggered_by")
        .order_by("-started_at")[:40]
    )
    for run in recent_runs:
        run.parity = compute_parity(run)

    rollback_candidates = [run for run in recent_runs if run.can_rollback]
    preview = None
    if selected_profile is not None:
        preview = dry_run_import(selected_profile, {"rows": [], "mapping": {}}, school=selected_school)

    summary = {
        "profiles_total": len(profiles),
        "runs_total": MigrationRun.objects.count(),
        "runs_last_30d": MigrationRun.objects.filter(started_at__gte=timezone.now() - timedelta(days=30)).count(),
        "failed_last_30d": MigrationRun.objects.filter(
            started_at__gte=timezone.now() - timedelta(days=30),
            status=MigrationRun.Status.FAILED,
        ).count(),
        "rollback_ready": MigrationRun.objects.filter(
            dry_run=False,
            rolled_back_by_run__isnull=True,
            rollback_snapshot__isnull=False,
        ).exclude(rollback_snapshot={}).count(),
    }

    return render(
        request,
        "schools/super_migration_cloud.html",
        {
            "summary": summary,
            "profiles": profiles,
            "recent_runs": recent_runs,
            "rollback_candidates": rollback_candidates[:10],
            "selected_school": selected_school,
            "selected_profile": selected_profile,
            "preview": preview,
            "dashboard_url": reverse("super:dashboard"),
            "registry_url": reverse("super:migration_profile_registry"),
        },
    )


def super_migration_profile_registry(request):
    """Migration Profile Registry: list profiles grouped by source_system and profile_category."""
    from apps.automation.models import MigrationProfile
    from itertools import groupby
    from operator import attrgetter

    profiles = list(
        MigrationProfile.objects.filter(is_active=True).order_by("source_system", "profile_category", "sort_order", "slug")
    )
    # Build groups: (source_system or "Generic", profile_category or "Uncategorized", list of profiles)
    groups = []
    for key, grp in groupby(profiles, key=lambda p: (p.source_system or "generic", p.profile_category or "uncategorized")):
        source_system, profile_category = key
        groups.append((source_system, profile_category, list(grp)))
    migration_cloud_url = reverse("super:migration_cloud")
    return render(
        request,
        "schools/super_migration_profile_registry.html",
        {
            "registry_groups": groups,
            "migration_cloud_url": migration_cloud_url,
            "dashboard_url": reverse("super:dashboard"),
            "profiles_total": len(profiles),
            "groups_count": len(groups),
        },
    )


@require_POST
def super_migration_rollback(request, run_id):
    from apps.automation.models import MigrationRun

    run = get_object_or_404(MigrationRun.objects.select_related("school"), pk=run_id)
    rollback_run, result = run.trigger_rollback(user=getattr(request, "user", None))
    if str(request.content_type or "").startswith("application/json"):
        status = 200 if result.get("success") else 400
        return JsonResponse(
            {
                "ok": bool(result.get("success")),
                "run_id": run.pk,
                "rollback_run_id": getattr(rollback_run, "pk", None),
                **result,
            },
            status=status,
        )
    if result.get("success"):
        messages.success(request, result.get("message") or "Rollback completed.")
    else:
        messages.error(request, result.get("message") or "Rollback failed.")
    return redirect("super:migration_cloud")


def super_pulse(request):
    """S13: Global Pulse Map — HTML view for super dashboard link. Same data as API v1 super/pulse."""
    from django.db.models import Sum
    from django.utils import timezone
    from apps.siteconfig.models import RevenueSnapshot

    schools = list(
        School.objects.filter(is_active=True)
        .annotate(student_count=Count("student_profiles", distinct=True))
        .values("id", "name", "slug", "subdomain", "default_region_id", "student_count", "last_activity")
    )
    first_of_month = timezone.now().date().replace(day=1)
    try:
        snapshots = RevenueSnapshot.objects.filter(snapshot_date=first_of_month).aggregate(
            total=Sum("actual_revenue"), waived=Sum("waived_amount")
        )
        total_revenue = (snapshots["total"] or 0) + (snapshots["waived"] or 0)
    except Exception:
        total_revenue = 0
    total_students = sum(s["student_count"] for s in schools)
    by_country = list(
        School.objects.filter(is_active=True)
        .values("default_region_id")
        .annotate(school_count=Count("id"), student_count=Count("student_profiles", distinct=True))
    )
    return render(
        request,
        "schools/super_pulse.html",
        {
            "tenants": schools,
            "total_students": total_students,
            "total_revenue": total_revenue,
            "by_country": by_country,
        },
    )


def super_tenant_health(request):
    """S13: Tenant Health Monitor — HTML view for super dashboard link. Same data as API v1 super/tenant-health."""
    schools = list(
        School.objects.all()
        .annotate(student_count=Count("student_profiles", distinct=True))
        .order_by("name")
    )
    for school in schools:
        school.admin_edit_url = _safe_school_admin_change_url(school.id)
        school.lifecycle = get_lifecycle_snapshot(school)
    return render(
        request,
        "schools/super_tenant_health.html",
        {"tenants": schools},
    )


def super_tenant_360(request, school_id):
    """Phase 9: Tenant 360 — identity, domain, blueprint, policy, plan, workflow/dashboard packs, runtime inspector."""
    school = get_object_or_404(School, id=school_id)
    from apps.platform_runtime.runtime_resolver import build_tenant_runtime
    from apps.tenancy.context import TenantContext

    tenant_ctx = TenantContext(
        tenant_id=str(getattr(school, "id", "") or ""),
        schema_name=getattr(school, "schema_name", None),
        school_id=getattr(school, "id", None),
        country=getattr(school, "country", None),
        timezone=getattr(school, "timezone", None),
        feature_flags={},
        policy_overrides={},
        host=request.get_host() if request else "",
    )
    try:
        runtime = build_tenant_runtime(tenant_ctx, request=None, school=school)
    except Exception:
        runtime = None

    identity = None
    blueprint_code = None
    policy_summary = {}
    trace = []
    warnings = []
    if runtime:
        identity = {
            "id": getattr(getattr(runtime, "tenant", None), "id", None),
            "slug": getattr(getattr(runtime, "tenant", None), "slug", None),
            "schema_name": getattr(getattr(runtime, "tenant", None), "schema_name", None),
        }
        bp = getattr(runtime, "blueprint", None)
        blueprint_code = getattr(bp, "code", None) or getattr(bp, "family", None)
        if getattr(runtime, "policy_typed", None):
            pt = runtime.policy_typed
            policy_summary = {"admissions": bool(getattr(pt, "admissions", None)), "finance": bool(getattr(pt, "finance", None)), "gradebook": bool(getattr(pt, "gradebook", None))}
        debug = getattr(runtime, "debug", None)
        if debug:
            trace = getattr(debug, "compilation_trace", []) or []
            warnings = getattr(debug, "warnings", []) or []

    return render(
        request,
        "schools/super_tenant_360.html",
        {
            "school": school,
            "lifecycle": get_lifecycle_snapshot(school),
            "identity": identity,
            "blueprint_code": blueprint_code,
            "policy_summary": policy_summary,
            "runtime_trace": trace,
            "runtime_warnings": warnings,
            "dashboard_url": reverse("super:dashboard"),
        },
    )


def super_control_health_dashboard(request):
    """
    Control plane health hub: single entry for runbooks, SLOs, incidents, tenant health.
    Linked from super dashboard (north-star: one place for ops health).
    """
    from django.conf import settings
    links = []
    try:
        links.append({"label": "Tenant health", "url": reverse("super:tenant_health"), "description": "Per-tenant roster and activity"})
    except Exception:
        pass
    try:
        url = reverse("platform_incidents_console")
        links.append({"label": "Incident console", "url": url, "description": "Platform incidents and status"})
    except Exception:
        pass
    try:
        url = reverse("api_operational_slo_dashboard") + "?format=html"
        links.append({"label": "SLO dashboard", "url": url, "description": "Operational SLO metrics (webhook & sync)"})
    except Exception:
        pass
    runbooks_url = getattr(settings, "CONTROL_PLANE_RUNBOOKS_URL", None) or ""
    if runbooks_url:
        links.append({"label": "Runbooks", "url": runbooks_url, "description": "Operational runbooks and playbooks"})
    return render(
        request,
        "schools/super_control_health.html",
        {"links": links, "dashboard_url": reverse("super:dashboard")},
    )


def super_workflow_packs_catalog(request):
    """Phase 4: Control-plane workflow pack catalog."""
    from apps.runtime_blueprints.models import WorkflowPack

    packs = list(WorkflowPack.objects.filter(is_active=True).order_by("family", "name").values("id", "code", "name", "family", "version"))
    try:
        admin_url = reverse("admin:siteconfig_workflowpack_changelist")
    except Exception:
        admin_url = None
    return render(
        request,
        "schools/super_workflow_packs.html",
        {"packs": packs, "admin_url": admin_url, "dashboard_url": reverse("super:dashboard")},
    )


def super_dashboard_packs_catalog(request):
    """Phase 4: Control-plane dashboard pack catalog."""
    from apps.runtime_blueprints.models import DashboardPack

    packs = list(DashboardPack.objects.filter(is_active=True).order_by("family", "name").values("id", "code", "name", "family", "version"))
    try:
        admin_url = reverse("admin:siteconfig_dashboardpack_changelist")
    except Exception:
        admin_url = None
    return render(
        request,
        "schools/super_dashboard_packs.html",
        {"packs": packs, "admin_url": admin_url, "dashboard_url": reverse("super:dashboard")},
    )


def super_blueprints_catalog(request):
    """Phase 3: Control-plane blueprint pack catalog."""
    from apps.policies.models import BlueprintPack

    try:
        from config.admin import admin_site
        admin_site_to_use = admin_site
    except Exception:
        from django.contrib.admin.sites import site as admin_site_to_use

    packs = list(BlueprintPack.objects.filter(is_active=True).order_by("category", "name").values("id", "slug", "name", "family", "category", "version"))
    for p in packs:
        try:
            p["admin_url"] = reverse(
                f"{admin_site_to_use.name}:policies_blueprintpack_change",
                args=[p["id"]],
            )
        except Exception:
            p["admin_url"] = None
    return render(
        request,
        "schools/super_blueprints_catalog.html",
        {"packs": packs, "dashboard_url": reverse("super:dashboard")},
    )


def super_policies_catalog(request):
    """Phase 3: Control-plane policy bundle catalog."""
    from apps.policies.models import PolicyBundle

    bundles = list(
        PolicyBundle.objects.filter(is_active=True)
        .order_by("country_scope", "name")
        .values("id", "code", "name", "country_scope", "version", "precedence_weight")[:200]
    )
    try:
        from config.admin import admin_site
        admin_site_to_use = admin_site
    except Exception:
        from django.contrib.admin.sites import site as admin_site_to_use
    for b in bundles:
        try:
            b["admin_url"] = reverse(f"{admin_site_to_use.name}:policies_policybundle_change", args=[b["id"]])
        except Exception:
            b["admin_url"] = None
    return render(
        request,
        "schools/super_policies_catalog.html",
        {
            "bundles": bundles,
            "dashboard_url": reverse("super:dashboard"),
            "bundles_total": len(bundles),
        },
    )


def super_registries_overview(request):
    """Phase 2: Control-plane registry governance — list registry types and counts with links to admin."""
    from django.contrib.admin.sites import site as default_admin_site
    from apps.registries.models import (
        CountryRegistry,
        SubdivisionRegistry,
        EducationLevelRegistry,
        EducationSystemTypeRegistry,
        InstitutionTypeRegistry,
        CurrencyRegistry,
        TimeZoneRegistry,
        LocaleRegistry,
        CalendarSystemRegistry,
        AcademicTerminologyRegistry,
        DocumentTypeRegistry,
        FeeCategoryRegistry,
        GradeScaleRegistry,
    )

    try:
        from config.admin import admin_site
        admin_site_to_use = admin_site
    except Exception:
        admin_site_to_use = default_admin_site

    def _count(model):
        return model.objects.count()

    def _admin_changelist_url(model, model_name):
        try:
            return reverse(
                f"{admin_site_to_use.name}:{model._meta.app_label}_{model_name}_changelist"
            )
        except Exception:
            return None

    registries = [
        ("Countries", CountryRegistry, _count(CountryRegistry)),
        ("Subdivisions", SubdivisionRegistry, _count(SubdivisionRegistry)),
        ("Education Levels", EducationLevelRegistry, _count(EducationLevelRegistry)),
        ("Education System Types", EducationSystemTypeRegistry, _count(EducationSystemTypeRegistry)),
        ("Institution Types", InstitutionTypeRegistry, _count(InstitutionTypeRegistry)),
        ("Currencies", CurrencyRegistry, _count(CurrencyRegistry)),
        ("Time Zones", TimeZoneRegistry, _count(TimeZoneRegistry)),
        ("Locales", LocaleRegistry, _count(LocaleRegistry)),
        ("Calendar Systems", CalendarSystemRegistry, _count(CalendarSystemRegistry)),
        ("Terminology Packs", AcademicTerminologyRegistry, _count(AcademicTerminologyRegistry)),
        ("Document Types", DocumentTypeRegistry, _count(DocumentTypeRegistry)),
        ("Fee Categories", FeeCategoryRegistry, _count(FeeCategoryRegistry)),
        ("Grade Scale Families", GradeScaleRegistry, _count(GradeScaleRegistry)),
    ]
    rows = []
    for label, model, count in registries:
        rows.append({
            "label": label,
            "count": count,
            "admin_url": _admin_changelist_url(model, model._meta.model_name),
        })

    return render(
        request,
        "schools/super_registries.html",
        {
            "registry_rows": rows,
            "dashboard_url": reverse("super:dashboard"),
        },
    )


def super_metadata_catalog(request):
    """Metadata catalog: entity/field search (metadata app) + platform catalog (schema, experience, runtime, registry)."""
    entities = []
    try:
        from apps.metadata.models import (
            EntityCatalogEntry,
            MetadataDependency,
        )
        q = request.GET.get("q", "").strip()
        entity_code = request.GET.get("entity", "").strip()
        qs = EntityCatalogEntry.objects.prefetch_related("fields", "fields__dependencies").order_by("code")
        if entity_code:
            qs = qs.filter(code__icontains=entity_code)
        if q:
            qs = qs.filter(
                Q(code__icontains=q) | Q(name__icontains=q) | Q(description__icontains=q)
            )
        entities = list(qs[:200])
        for ent in entities:
            ent.field_count = ent.fields.count()
            ent.sample_deps = MetadataDependency.objects.filter(field__entity=ent).count()
    except Exception:
        pass

    platform_catalog = None
    try:
        from apps.siteconfig.metadata_catalog import get_catalog
        platform_catalog = get_catalog()
    except Exception:
        pass

    return render(
        request,
        "schools/super_metadata_catalog.html",
        {
            "entities": entities,
            "query": request.GET.get("q", "").strip() or request.GET.get("entity", "").strip(),
            "platform_catalog": platform_catalog,
            "dashboard_url": reverse("super:dashboard"),
        },
    )


def super_metadata_catalog_field_impact(request, entity_code, field_name):
    """Impact view for a single field: list dependent workflows/dashboards/reports (plan todo 4)."""
    from apps.metadata.models import EntityCatalogEntry, FieldCatalogEntry, MetadataDependency

    entity = get_object_or_404(EntityCatalogEntry, code=entity_code)
    field = get_object_or_404(FieldCatalogEntry, entity=entity, field_name=field_name)
    deps = MetadataDependency.objects.filter(field=field).select_related("field").order_by("consumer_type", "consumer_code")
    return render(
        request,
        "schools/super_metadata_catalog_field_impact.html",
        {
            "entity": entity,
            "field": field,
            "dependencies": deps,
            "dashboard_url": reverse("super:dashboard"),
            "catalog_url": reverse("super:metadata_catalog"),
        },
    )


def super_command_center(request):
    """
    Phase 3 mission-control surface combining approvals, billing, support, and risk posture.
    """
    from apps.siteconfig.models import GlobalSupportTicket

    command_center = _build_command_center_data()
    pending_schools = list(
        School.objects.filter(is_approved=False)
        .order_by("-created_at")
        .annotate(student_count=Count("student_profiles", distinct=True))[:30]
    )
    trial_schools = list(
        School.objects.filter(is_active=True, billing_type=School.BillingType.FREE_TRIAL)
        .order_by("trial_end_date", "name")[:30]
    )
    stale_support = command_center.get("support_stale_rows", [])[:20]
    provisioning_breach_rows = command_center.get("provisioning_breach_rows", [])[:20]

    school_map = {
        school.id: school
        for school in School.objects.filter(id__in=[row["school_id"] for row in provisioning_breach_rows]).only("id", "name", "slug")
    }
    for row in provisioning_breach_rows:
        row["school"] = school_map.get(row["school_id"])

    return render(
        request,
        "schools/super_command_center.html",
        {
            "command_center": command_center,
            "pending_schools": pending_schools,
            "trial_schools": trial_schools,
            "stale_support": stale_support,
            "provisioning_breach_rows": provisioning_breach_rows,
            "support_dashboard_url": reverse("super:support_dashboard"),
            "billing_dashboard_url": reverse("super:billing_dashboard"),
            "usage_url": reverse("super:usage"),
            "dashboard_url": reverse("super:dashboard"),
            "open_ticket_statuses": list(GlobalSupportTicket.Status.values),
        },
    )

def super_command_center_v2(request):
    """Operational queue drill-down for the manager control plane."""
    from apps.billing.models import TenantSubscription
    from apps.events.legacy_bridge import legacy_webhook_sync_snapshot
    from apps.observability.models import PlatformIncident
    from apps.observability.monitoring import SystemHealthMonitor
    from apps.siteconfig.models import GlobalSupportTicket

    command_center = _build_command_center_data()
    pending_schools = list(
        School.objects.filter(is_approved=False)
        .order_by("-created_at")
        .annotate(student_count=Count("student_profiles", distinct=True))[:30]
    )
    trial_schools = list(
        School.objects.filter(is_active=True, billing_type=School.BillingType.FREE_TRIAL)
        .order_by("trial_end_date", "name")[:30]
    )
    stale_support = command_center.get("support_stale_rows", [])[:20]
    provisioning_breach_rows = command_center.get("provisioning_breach_rows", [])[:20]
    risk_rows = command_center.get("tenant_churn_risk_rows", [])[:20]
    platform_incidents = list(
        PlatformIncident.objects.select_related("affected_school")
        .filter(
            status__in=[
                PlatformIncident.Status.OPEN,
                PlatformIncident.Status.ACKNOWLEDGED,
                PlatformIncident.Status.MITIGATED,
            ]
        )
        .order_by("-detected_at", "-created_at")[:20]
    )
    incident_counts = {
        row["status"]: row["total"]
        for row in PlatformIncident.objects.values("status").annotate(total=Count("id"))
    }
    billing_watchlist = list(
        TenantSubscription.objects.select_related("school", "billing_account", "plan")
        .filter(status__in=[TenantSubscription.Status.PAST_DUE, TenantSubscription.Status.SUSPENDED])
        .order_by("-updated_at", "school__name")[:20]
    )
    webhook_stack = legacy_webhook_sync_snapshot()
    try:
        platform_health = SystemHealthMonitor.get_comprehensive_health()
    except Exception:
        platform_health = {"overall_status": "warning", "database": {"status": "unhealthy"}, "cache": {"status": "unhealthy"}}

    school_map = {
        school.id: school
        for school in School.objects.filter(id__in=[row["school_id"] for row in provisioning_breach_rows]).only("id", "name", "slug")
    }
    for row in provisioning_breach_rows:
        row["school"] = school_map.get(row["school_id"])
    for row in risk_rows:
        school = row.get("school")
        if school is not None:
            row["admin_edit_url"] = _safe_school_admin_change_url(school.pk)

    return render(
        request,
        "schools/super_command_center.html",
        {
            "command_center": command_center,
            "pending_schools": pending_schools,
            "trial_schools": trial_schools,
            "stale_support": stale_support,
            "provisioning_breach_rows": provisioning_breach_rows,
            "support_dashboard_url": reverse("super:support_dashboard"),
            "billing_dashboard_url": reverse("super:billing_dashboard"),
            "usage_url": reverse("super:usage"),
            "dashboard_url": reverse("super:dashboard"),
            "open_ticket_statuses": list(GlobalSupportTicket.Status.values),
            "risk_rows": risk_rows,
            "platform_incidents": platform_incidents,
            "incident_counts": incident_counts,
            "billing_watchlist": billing_watchlist,
            "webhook_stack": webhook_stack,
            "platform_health": platform_health,
            "platform_incidents_url": _safe_platform_incidents_url(),
        },
    )


def billing_dashboard(request):
    """Platform billing console: subscriptions, usage, and recent platform ledger activity."""
    from datetime import timedelta
    from django.db.models import Count, Sum
    from django.utils import timezone
    from apps.billing.models import (
        BillingAccount,
        BillingProcessorSyncEvent,
        PlatformLedgerEntry,
        RevenueSharePayout,
        TenantSubscription,
    )
    from apps.billing.services import ensure_subscription_for_school

    active_schools = list(
        School.objects.filter(is_active=True)
        .select_related("plan", "default_region")
        .annotate(student_count=Count("student_profiles", distinct=True))
        .order_by("name")
    )
    for school in active_schools:
        ensure_subscription_for_school(school)

    trial_schools = [school for school in active_schools if school.billing_type == School.BillingType.FREE_TRIAL]
    trial_schools.sort(key=lambda school: (school.trial_end_date or timezone.now().date(), school.name))
    school_ids = [s.pk for s in trial_schools]
    usage_agg = {}
    if school_ids:
        for r in TenantApiUsage.objects.filter(school_id__in=school_ids).values("school_id").annotate(total=Sum("request_count")):
            usage_agg[r["school_id"]] = r["total"]
    for school in trial_schools:
        school.api_requests = usage_agg.get(school.pk, 0)
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
        school.trial_expired = school.trial_end_date and school.trial_end_date < timezone.now().date()
    account_summary = BillingAccount.objects.values("status").annotate(total=Count("id")).order_by("status")
    subscription_summary = TenantSubscription.objects.values("status").annotate(total=Count("id")).order_by("status")
    billing_account_count = BillingAccount.objects.count()
    subscription_count = TenantSubscription.objects.count()
    active_subscriptions = list(
        TenantSubscription.objects.filter(
            status__in=[
                TenantSubscription.Status.TRIALING,
                TenantSubscription.Status.ACTIVE,
                TenantSubscription.Status.PAST_DUE,
                TenantSubscription.Status.SUSPENDED,
            ]
        )
        .select_related("school", "plan", "billing_account")
        .order_by("-updated_at", "school__name")[:30]
    )
    recent_ledger = list(
        PlatformLedgerEntry.objects.select_related("school", "billing_account")
        .order_by("-happened_at", "-created_at")[:20]
    )
    total_posted_charges = (
        PlatformLedgerEntry.objects.filter(
            status=PlatformLedgerEntry.Status.POSTED,
            entry_type=PlatformLedgerEntry.EntryType.CHARGE,
        ).aggregate(total=Sum("amount")).get("total")
        or 0
    )
    total_posted_credits = (
        PlatformLedgerEntry.objects.filter(
            status=PlatformLedgerEntry.Status.POSTED,
            entry_type__in=[
                PlatformLedgerEntry.EntryType.CREDIT,
                PlatformLedgerEntry.EntryType.WRITE_OFF,
            ],
        ).aggregate(total=Sum("amount")).get("total")
        or 0
    )
    stale_processor_accounts = BillingAccount.objects.exclude(processor_code="").filter(
        Q(last_processor_sync_at__isnull=True) | Q(last_processor_sync_at__lt=timezone.now() - timedelta(days=3))
    ).count()
    processor_event_count = BillingProcessorSyncEvent.objects.count()
    recent_processor_events = list(
        BillingProcessorSyncEvent.objects.select_related("school", "billing_account", "subscription")
        .order_by("-happened_at", "-created_at")[:12]
    )
    scheduled_payouts = list(
        RevenueSharePayout.objects.select_related("source_school")
        .filter(status__in=[RevenueSharePayout.Status.SCHEDULED, RevenueSharePayout.Status.IN_TRANSIT])
        .order_by("scheduled_for", "-created_at")[:12]
    )
    scheduled_payout_total = (
        RevenueSharePayout.objects.filter(status__in=[RevenueSharePayout.Status.SCHEDULED, RevenueSharePayout.Status.IN_TRANSIT])
        .aggregate(total=Sum("net_amount"))
        .get("total")
        or 0
    )
    return render(
        request,
        "schools/billing_dashboard.html",
        {
            "trial_schools": trial_schools,
            "account_summary": list(account_summary),
            "subscription_summary": list(subscription_summary),
            "billing_account_count": billing_account_count,
            "subscription_count": subscription_count,
            "active_subscriptions": active_subscriptions,
            "recent_ledger": recent_ledger,
            "total_posted_charges": total_posted_charges,
            "total_posted_credits": total_posted_credits,
            "stale_processor_accounts": stale_processor_accounts,
            "processor_event_count": processor_event_count,
            "recent_processor_events": recent_processor_events,
            "scheduled_payouts": scheduled_payouts,
            "scheduled_payout_total": scheduled_payout_total,
            "usage_url": reverse("super:usage"),
        },
    )


@require_http_methods(["GET", "POST"])
def create_school_wizard(request):
    """Multi-step wizard: Step 1 identity, Step 2 region, Step 3 branding. POST submits to API."""
    from apps.global_registries.models import RegionConfig, WeatherLocation
    from apps.siteconfig.models import default_header_weather_config

    if request.method == "POST":
        # Wizard form submitted via JS to api_create_school; this is fallback or redirect
        return redirect("super:api_create_school")

    ensure_registry_baseline()
    regions = RegionConfig.objects.all().order_by("name")
    defaults = default_header_weather_config()
    default_country_code = _canonical_country_alpha2(
        defaults.get("header_weather_country_code") or get_platform_defaults(use_db=False)["region_code"]
    )
    countries = list_country_choices()
    known_codes = {row["code"] for row in countries}
    if default_country_code not in known_codes and countries:
        default_country_code = countries[0]["code"]
    default_country_alpha3 = GlobalGeoCatalog.normalize_country_code(default_country_code)
    cities = GlobalGeoCatalog.search_cities(
        country_code=default_country_alpha3,
        limit=180,
    )
    default_sub_system = School.SubSystem.EN
    education_profiles = list_profile_options(
        country_code=default_country_alpha3,
        sub_system=default_sub_system,
    )
    education_levels = EducationLevelRegistry.objects.filter(is_active=True).order_by("sort_order", "global_name")
    education_system_types = EducationSystemTypeRegistry.objects.filter(is_active=True).order_by("sort_order", "name")
    # S2: One-click education templates (British/WAEC/Vocational) — same as API config/education-templates
    education_templates_standard = [
        {"code": "BRITISH_IGCSE", "name": "British / IGCSE", "description": "Michaelmas, Lent, Trinity; A*–G or 9–1."},
        {"code": "WAEC", "name": "West African (WAEC)", "description": "First, Second, Third term; A1–F9; CA 30% + Exam 70%."},
        {"code": "FRANCOPHONE_BAC", "name": "Francophone (Bac)", "description": "Trimestre 1–3; 20-point scale."},
        {"code": "VOCATIONAL", "name": "Vocational / Trade", "description": "Competency checklists; clock hours; skill badges."},
    ]
    catalog_templates = list_template_catalog(
        country_code=default_country_alpha3,
        sub_system=default_sub_system,
        limit=8,
    )
    if catalog_templates:
        education_templates_standard = catalog_templates
    if not countries or not cities:
        # Backward-compatible fallback when optional catalog dependencies are unavailable.
        WeatherLocation.ensure_seed_data()
        locations = list(
            WeatherLocation.objects.select_related("region")
            .filter(is_active=True)
            .order_by("region__name", "sort_order", "city")
        )
        countries = []
        seen = set()
        for loc in locations:
            if loc.region_id in seen:
                continue
            seen.add(loc.region_id)
            countries.append(
                {
                    "code": _canonical_country_alpha2(loc.region_id) or loc.region_id,
                    "code_alpha2": _canonical_country_alpha2(loc.region_id) or "",
                    "code_alpha3": loc.region_id,
                    "name": loc.region.name,
                    "timezone": loc.region.timezone,
                }
            )
        cities = [
            {
                "id": str(loc.pk),
                "country_code": _canonical_country_alpha2(loc.region_id) or loc.region_id,
                "country_code_alpha3": loc.region_id,
                "city": loc.city,
                "label": loc.display_label,
                "timezone": loc.timezone or loc.region.timezone or "UTC",
                "latitude": float(loc.latitude),
                "longitude": float(loc.longitude),
            }
            for loc in locations
            if not default_country_alpha3 or loc.region_id == default_country_alpha3
        ]
    return render(
        request,
        "schools/super_create_school_wizard.html",
        {
            "regions": regions,
            "countries": countries,
            "cities": cities,
            "default_country_code": default_country_code or defaults.get("header_weather_country_code") or get_platform_defaults(use_db=False)["region_code"],
            "default_sub_system": default_sub_system,
            "education_profiles": education_profiles,
            "education_levels": education_levels,
            "education_system_types": education_system_types,
            "education_templates_standard": education_templates_standard,
            "school_admin_edit_template": _safe_school_admin_change_url("00000000-0000-0000-0000-000000000000"),
            "geo_city_search_min_chars": 1,
        },
    )


@require_http_methods(["GET"])
def api_geo_cities(request):
    country_code = GlobalGeoCatalog.normalize_country_code(request.GET.get("country_code"))
    query = (request.GET.get("q") or "").strip()
    limit = _clamp_int(request.GET.get("limit"), 120, minimum=10, maximum=500)
    cities = GlobalGeoCatalog.search_cities(country_code=country_code, query=query, limit=limit)
    return JsonResponse({"country_code": country_code, "query": query, "cities": cities})


@require_http_methods(["GET"])
def api_geo_timezones(request):
    country_code = GlobalGeoCatalog.normalize_country_code(request.GET.get("country_code"))
    query = (request.GET.get("q") or "").strip()
    limit = _clamp_int(request.GET.get("limit"), 500, minimum=10, maximum=2000)
    timezones = GlobalGeoCatalog.list_timezones(country_code=country_code, query=query, limit=limit)
    return JsonResponse({"country_code": country_code, "query": query, "timezones": timezones})


@require_http_methods(["GET"])
def api_provinces(request):
    """List canonical subdivisions for a country; keeps `provinces` key for compatibility."""
    ensure_registry_baseline()
    country_code = (request.GET.get("country_code") or "").strip()
    subdivisions = list_subdivision_choices(country_code)
    alpha2 = _canonical_country_alpha2(country_code)
    return JsonResponse(
        {
            "country_code": alpha2,
            "provinces": subdivisions,
            "subdivisions": subdivisions,
        }
    )


@require_http_methods(["GET"])
def api_education_profiles(request):
    country_code = GlobalGeoCatalog.normalize_country_code(request.GET.get("country_code"))
    sub_system = (request.GET.get("sub_system") or School.SubSystem.EN).strip().upper()
    valid_subsystems = {School.SubSystem.EN, School.SubSystem.FR, School.SubSystem.INT}
    if sub_system not in valid_subsystems:
        sub_system = School.SubSystem.EN
    province_id = request.GET.get("province_id")
    subdivision_id = request.GET.get("subdivision_id")
    if subdivision_id not in (None, ""):
        try:
            subdivision = SubdivisionRegistry.objects.filter(pk=int(subdivision_id)).first()
        except (TypeError, ValueError):
            subdivision = None
        if subdivision:
            province_id = (subdivision.metadata or {}).get("legacy_province_id")
    if province_id is not None and province_id != "":
        try:
            province_id = int(province_id)
        except (TypeError, ValueError):
            province_id = None
    else:
        province_id = None

    profiles = list_profile_options(
        country_code=country_code,
        sub_system=sub_system,
        province_id=province_id,
    )
    return JsonResponse(
        {
            "country_code": country_code,
            "sub_system": sub_system,
            "province_id": province_id,
            "profiles": profiles,
            "auto_option": {
                "code": "",
                "name": "Auto by Country and Sub-system",
                "description": "Recommended. Provisioning resolves the best profile automatically.",
            },
        }
    )


@require_http_methods(["GET"])
def api_system_blueprint(request):
    """
    Phase Global: Environment Discovery — get merged blueprint for region + flavor.
    GET ?region_id=CMR&flavor=EN returns primary_language, grading_scale, term_labels, etc.
    """
    from apps.siteconfig.education_profile_engine import get_system_blueprint
    region_id = (request.GET.get("region_id") or "").strip() or None
    flavor = (request.GET.get("flavor") or "").strip() or None
    blueprint = get_system_blueprint(region_id=region_id, flavor=flavor)
    return JsonResponse(blueprint)


@require_http_methods(["GET"])
def api_plans_configurator(request):
    """
    Plan Configurator API (Phase E): GET plans, addons, country_multiplier.
    Same contract for onboarding billing step and PlanConfigurator component.
    Version: 1.
    """
    from apps.plans_entitlements.models import CountryMultiplier, Plan, PlanAddon
    from decimal import Decimal

    country_code = GlobalGeoCatalog.normalize_country_code((request.GET.get("country_code") or "").strip())
    plans = []
    for p in Plan.objects.filter(is_active=True).order_by("name"):
        plans.append({
            "id": p.pk,
            "name": p.name,
            "slug": p.slug,
            "billing_model": p.billing_model or "FLAT",
            "base_price": float(p.base_price) if p.base_price is not None else None,
            "price_per_student": float(p.price_per_student) if p.price_per_student is not None else None,
            "tier_rules": p.tier_rules if isinstance(p.tier_rules, list) else [],
            "max_students": p.max_students,
            "max_staff": p.max_staff,
            "included_features": p.included_features or [],
        })
    addons = []
    for a in PlanAddon.objects.filter(is_active=True).order_by("name"):
        addons.append({
            "code": a.code,
            "name": a.name,
            "price": float(a.price),
        })
    multiplier = Decimal("1")
    if country_code:
        row = CountryMultiplier.objects.filter(country_code=country_code, is_active=True).first()
        if row:
            multiplier = row.multiplier
    return JsonResponse({
        "version": 1,
        "country_code": country_code or "",
        "country_multiplier": float(multiplier),
        "plans": plans,
        "addons": addons,
    })


@require_http_methods(["GET"])
def api_school_timeline(request, school_id):
    school = get_object_or_404(School, id=school_id)
    limit = _clamp_int(request.GET.get("limit"), 80, minimum=1, maximum=500)
    events = list(
        SchoolProvisioningEvent.objects.filter(school=school)
        .order_by("-created_at", "-id")
        .values("event_type", "status", "message", "payload", "created_at")[:limit]
    )
    for event in events:
        created_at = event.get("created_at")
        event["created_at"] = created_at.isoformat() if created_at else ""
    return JsonResponse(
        {
            "school_id": str(school.id),
            "school_name": school.name,
            "events": events,
        }
    )


@require_http_methods(["POST"])
def api_approve_school(request, school_id):
    """Phase H optional: Set school is_approved=True. Super Admin only."""
    from apps.schools.control_plane import log_control_plane_action
    from apps.compliance.models_audit import AuditLog

    school = get_object_or_404(School, id=school_id)
    outcome = apply_school_lifecycle_action(school, action="approve")
    log_control_plane_action(
        request,
        AuditLog.Action.APPROVE,
        "School",
        str(school.id),
        object_repr=getattr(school, "name", "") or str(school.id),
        reason="School approved",
        sensitivity=AuditLog.Sensitivity.HIGH,
        old_values=outcome["old_values"],
        new_values=outcome["new_values"],
        changed_fields=outcome["changed_fields"],
    )
    return JsonResponse({"ok": True, "school_id": str(school.id), "message": outcome["message"]})


@require_http_methods(["POST"])
def school_lifecycle_action(request, school_id):
    import json

    from apps.compliance.models_audit import AuditLog
    from apps.schools.control_plane import log_control_plane_action

    school = get_object_or_404(School, id=school_id)
    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}

    action = str(payload.get("action") or request.POST.get("action") or "").strip()
    reason = str(payload.get("reason") or request.POST.get("reason") or "").strip()
    trial_end_date = payload.get("trial_end_date") or request.POST.get("trial_end_date")
    next_url = str(request.POST.get("next") or reverse("super:tenant_360", args=[school.id])).strip()
    expects_json = str(request.content_type or "").startswith("application/json")

    try:
        outcome = apply_school_lifecycle_action(
            school,
            action=action,
            reason=reason,
            trial_end_date=trial_end_date,
        )
    except ValueError as exc:
        if expects_json:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        messages.error(request, str(exc))
        return redirect(next_url)

    audit_action = AuditLog.Action.APPROVE if str(action).strip().lower() == "approve" else AuditLog.Action.UPDATE
    log_control_plane_action(
        request,
        audit_action,
        "School",
        str(school.id),
        object_repr=getattr(school, "name", "") or str(school.id),
        reason=f"School lifecycle action: {action}",
        sensitivity=AuditLog.Sensitivity.HIGH,
        old_values=outcome["old_values"],
        new_values=outcome["new_values"],
        changed_fields=outcome["changed_fields"],
    )
    if expects_json:
        return JsonResponse({"ok": True, "school_id": str(school.id), **outcome})

    messages.success(request, outcome["message"])
    return redirect(next_url)


@require_http_methods(["GET"])
def api_school_policy_bundles(request, school_id):
    """List policy bundles for a school (for pack versioning rollback UI)."""
    from apps.policies.rollback import list_policy_bundles_for_school

    school = get_object_or_404(School, id=school_id)
    bundles = list_policy_bundles_for_school(school)
    from apps.policies.models import TenantBlueprint
    tb = TenantBlueprint.objects.filter(school=school).select_related("active_bundle").first()
    active_id = tb.active_bundle_id if tb else None
    items = [
        {
            "id": b.id,
            "version": b.version,
            "applied_pack_version": getattr(b, "applied_pack_version", "") or "",
            "code": getattr(b, "code", "") or "",
            "name": getattr(b, "name", "") or "",
            "created_at": b.created_at.isoformat() if hasattr(b.created_at, "isoformat") else str(b.created_at),
            "is_active": b.id == active_id,
        }
        for b in bundles[:50]
    ]
    return JsonResponse({"school_id": str(school.id), "active_bundle_id": active_id, "bundles": items})


@require_http_methods(["POST"])
def api_school_policy_bundle_activate(request, school_id, bundle_id):
    """Set the active policy bundle for a school (rollback to previous version)."""
    from apps.policies.rollback import set_active_policy_bundle
    from apps.policies.models import PolicyBundle

    school = get_object_or_404(School, id=school_id)
    bundle = get_object_or_404(PolicyBundle, id=bundle_id, school=school)
    ok = set_active_policy_bundle(school, bundle)
    if not ok:
        return JsonResponse({"ok": False, "error": "Could not set active bundle"}, status=400)
    return JsonResponse({"ok": True, "school_id": str(school.id), "active_bundle_id": bundle.id, "message": "Active policy bundle updated."})


def _slug_from_name(name: str) -> str:
    """W1-1: Derive URL-safe slug from school name for minimal create path."""
    import re
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:120] if s else "school"


@require_POST
def api_create_school(request):
    """
    Validate payload, create School row (is_active=False), enqueue provisioning task.
    Returns 202 + job_id or 400 with errors.
    W1-1: Minimal path: name, contact_email, country_code (optional); slug/subdomain derived from name when omitted.
    """
    import json

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    ensure_registry_baseline()
    name = (data.get("name") or "").strip()
    slug = (data.get("slug") or "").strip().lower().replace(" ", "-")
    if not slug and name:
        slug = _slug_from_name(name)
    subdomain = (data.get("subdomain") or slug or "").strip().lower()
    contact_email = (data.get("contact_email") or "").strip()
    region_code = GlobalGeoCatalog.normalize_country_code((data.get("region_code") or "").strip())
    raw_country_code = (data.get("country_code") or region_code or "").strip()
    country_code = GlobalGeoCatalog.normalize_country_code(raw_country_code)
    canonical_country_code = _canonical_country_alpha2(raw_country_code or country_code)
    city_id = (data.get("city_id") or "").strip()
    sub_system = (data.get("sub_system") or School.SubSystem.EN).strip().upper()
    valid_subsystems = {School.SubSystem.EN, School.SubSystem.FR, School.SubSystem.INT}
    if sub_system not in valid_subsystems:
        sub_system = School.SubSystem.EN
    education_profile_code = (data.get("education_profile_code") or "").strip()
    education_system_ids = data.get("education_system_ids")  # Phase B: list of profile codes (multi-select)
    if not isinstance(education_system_ids, list):
        education_system_ids = []
    education_system_ids = [str(x).strip() for x in education_system_ids if x]
    education_level_codes = data.get("education_level_codes")
    if not isinstance(education_level_codes, list):
        education_level_codes = []
    education_level_codes = [str(x).strip().upper() for x in education_level_codes if x]
    education_system_type_codes = data.get("education_system_type_codes")
    if not isinstance(education_system_type_codes, list):
        education_system_type_codes = []
    education_system_type_codes = [str(x).strip().upper() for x in education_system_type_codes if x]
    subdivision_id = data.get("subdivision_id")
    province_id = data.get("province_id")  # Phase B: optional province for geo filtering
    if province_id is not None and province_id != "":
        try:
            province_id = int(province_id)
        except (TypeError, ValueError):
            province_id = None
    primary_color = (data.get("primary_color") or "#0d6efd").strip()
    accent_color = (data.get("accent_color") or "#198754").strip()
    theme_choice = (data.get("theme_choice") or "UNFOLD").strip().upper()
    if theme_choice not in {"UNFOLD", "JAZZMIN", "SNEAT"}:
        theme_choice = "UNFOLD"
    custom_domain = (data.get("custom_domain") or "").strip()
    plan_id = data.get("plan_id")
    if plan_id is not None and plan_id != "":
        try:
            plan_id = int(plan_id)
        except (TypeError, ValueError):
            plan_id = None
    addons = data.get("addons")
    if not isinstance(addons, list):
        addons = []

    if not subdomain and slug:
        subdomain = slug
    errors = []
    if not name:
        errors.append("name is required")
    # W1-1: slug optional; derived from name when omitted.
    if not slug and name:
        slug = _slug_from_name(name)
    if not slug:
        errors.append("slug could not be derived from name; provide slug or name")
    # W1-3: Contact email required for provisioning and welcome email.
    if not contact_email:
        errors.append("contact_email is required")

    if errors:
        return JsonResponse({"errors": errors}, status=400)

    if School.objects.filter(slug=slug).exists():
        return JsonResponse({"errors": ["slug already exists"]}, status=400)
    if subdomain and School.objects.filter(subdomain=subdomain).exists():
        return JsonResponse({"errors": ["subdomain already exists"]}, status=400)

    # S2: Allow standard one-click template codes (API config/education-templates) without requiring DB record
    STANDARD_TEMPLATE_CODES = {
        row["code"]
        for row in list_template_catalog(country_code=country_code, sub_system=sub_system)
    }
    explicit_profile = None
    if education_profile_code:
        explicit_profile = EducationSystemProfile.objects.filter(
            code=education_profile_code,
            is_active=True,
            approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
        ).first()
        if explicit_profile is None and education_profile_code not in STANDARD_TEMPLATE_CODES:
            errors.append("education_profile_code is invalid")
        elif explicit_profile is not None and explicit_profile.sub_system not in {
            EducationSystemProfile.SubSystem.ANY,
            sub_system,
        }:
            errors.append("education_profile_code does not match selected sub-system")
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    from apps.global_registries.models import RegionConfig, WeatherLocation
    default_region = None
    selected_city = GlobalGeoCatalog.get_city(city_id, country_code=country_code)
    selected_location = None
    if city_id and selected_city is None:
        try:
            selected_location = (
                WeatherLocation.objects.select_related("region")
                .filter(pk=int(city_id), is_active=True)
                .first()
            )
        except (TypeError, ValueError):
            selected_location = None
    if selected_location and country_code and selected_location.region_id != country_code:
        selected_location = None
    if selected_city:
        country_code = selected_city["country_code"]
        canonical_country_code = _canonical_country_alpha2(selected_city.get("country_code_alpha2") or country_code)
        default_region = _ensure_region_for_country(country_code, selected_city.get("timezone") or "UTC")
    elif selected_location:
        default_region = selected_location.region
        country_code = selected_location.region_id
        canonical_country_code = _canonical_country_alpha2(country_code)
    if default_region is None and country_code:
        default_region = RegionConfig.objects.filter(code=country_code).first() or _ensure_region_for_country(country_code)
    if default_region is None and region_code:
        default_region = RegionConfig.objects.filter(code=region_code).first() or _ensure_region_for_country(region_code)
    if default_region is None and explicit_profile and explicit_profile.region_id:
        default_region = explicit_profile.region
        country_code = explicit_profile.region_id
        canonical_country_code = _canonical_country_alpha2(country_code)
    if default_region is not None and not canonical_country_code:
        canonical_country_code = _canonical_country_alpha2(default_region.code)
    resolved_timezone = (
        (selected_city.get("timezone") if selected_city else "")
        or (selected_location.timezone if selected_location else "")
        or (explicit_profile.default_timezone if explicit_profile else "")
        or (default_region.timezone if default_region else "")
        or "UTC"
    )
    resolved_subdivision = _resolve_subdivision(
        canonical_country_code or country_code,
        subdivision_id=subdivision_id,
        province_id=province_id,
    )
    selected_levels = _resolve_registry_codes(EducationLevelRegistry, education_level_codes)
    selected_system_types = _resolve_registry_codes(EducationSystemTypeRegistry, education_system_type_codes)
    if education_level_codes and len({row.code for row in selected_levels}) != len(set(education_level_codes)):
        errors.append("education_level_codes contains unknown values")
    if education_system_type_codes and len({row.code for row in selected_system_types}) != len(set(education_system_type_codes)):
        errors.append("education_system_type_codes contains unknown values")
    if subdivision_id not in (None, "") and resolved_subdivision is None:
        errors.append("subdivision_id is invalid")
    if errors:
        return JsonResponse({"errors": errors}, status=400)
    location_payload = {
        "country_code": country_code or (default_region.code if default_region else ""),
        "country_code_alpha2": canonical_country_code or "",
        "subdivision_code": resolved_subdivision.code if resolved_subdivision else "",
        "subdivision_name": resolved_subdivision.name if resolved_subdivision else "",
        "city": "",
        "label": "",
        "timezone": resolved_timezone,
        "city_id": city_id or "",
    }
    if selected_city:
        location_payload.update(
            {
                "city": selected_city.get("city", ""),
                "label": selected_city.get("label", ""),
                "latitude": selected_city.get("latitude"),
                "longitude": selected_city.get("longitude"),
            }
        )
    elif selected_location:
        location_payload.update(
            {
                "city": selected_location.city,
                "label": selected_location.display_label,
                "latitude": float(selected_location.latitude),
                "longitude": float(selected_location.longitude),
            }
        )

    school_settings_overrides = {
        "contact_email": contact_email,
        "provisioning": {
            "logo_uploaded": False,
            "education_profile_mode": "explicit" if explicit_profile else "auto",
            "education_system_ids": education_system_ids,
            "education_level_codes": [row.code for row in selected_levels],
            "education_system_type_codes": [row.code for row in selected_system_types],
            "province_id": province_id,
            "subdivision_id": resolved_subdivision.id if resolved_subdivision else None,
        },
        "education_profile_code": (explicit_profile.code if explicit_profile else education_profile_code or ""),
        "location": location_payload,
        "custom_domain": {
            "hostname": custom_domain or "",
            "status": "pending_verification" if custom_domain else "not_configured",
            "verified": False,
        },
    }

    create_kw = dict(
        name=name,
        slug=slug,
        subdomain=subdomain or slug,
        sub_system=sub_system,
        default_region=default_region,
        country_code=canonical_country_code or "",
        subdivision=resolved_subdivision,
        timezone=resolved_timezone,
        primary_color=primary_color,
        accent_color=accent_color,
        custom_domain=custom_domain or "",
        is_active=False,
        is_approved=not (__import__("os").getenv("ENABLE_SCHOOL_APPROVAL_WORKFLOW", "").strip().lower() in ("1", "true", "yes")),
        settings={},
    )
    if hasattr(School, "theme_choice"):
        create_kw["theme_choice"] = theme_choice
    if plan_id and hasattr(School, "plan_id"):
        from apps.plans_entitlements.models import Plan
        if Plan.objects.filter(pk=plan_id, is_active=True).exists():
            create_kw["plan_id"] = plan_id
    if addons and hasattr(School, "addons"):
        addons = [str(x).strip() for x in addons if x]
        create_kw["addons"] = addons
    school = School.objects.create(**create_kw)
    if selected_levels:
        school.education_levels.set(selected_levels)
    if selected_system_types:
        school.education_system_types.set(selected_system_types)
    try:
        from apps.schools.control_plane import log_control_plane_action
        from apps.compliance.models_audit import AuditLog
        log_control_plane_action(
            request,
            AuditLog.Action.CREATE,
            "School",
            str(school.id),
            object_repr=school.name or str(school.id),
            reason="School created via super create-school API",
            sensitivity=AuditLog.Sensitivity.HIGH,
            new_values={"name": school.name, "slug": school.slug, "subdomain": school.subdomain},
        )
    except Exception:
        pass
    try:
        from apps.billing.services import ensure_subscription_for_school

        ensure_subscription_for_school(school)
    except Exception:
        pass
    apply_tenant_settings_overrides(
        school=school,
        overrides=school_settings_overrides,
        actor_is_superadmin=bool(getattr(request.user, "is_superuser", False)),
        force_override=False,
        persist=True,
    )
    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.REQUEST_RECEIVED,
        status=SchoolProvisioningEvent.Status.INFO,
        message="Provisioning request accepted.",
        payload={
            "country_code": country_code or (default_region.code if default_region else ""),
            "sub_system": sub_system,
            "education_profile_code": (explicit_profile.code if explicit_profile else education_profile_code or ""),
            "custom_domain": custom_domain or "",
        },
        created_by=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
    )
    if custom_domain:
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.DOMAIN_PENDING,
            status=SchoolProvisioningEvent.Status.INFO,
            message=f"Custom domain {custom_domain} pending DNS verification.",
            payload={"hostname": custom_domain},
            created_by=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        )

    # Enqueue provisioning task (Celery or sync for now)
    try:
        from apps.schools.tasks import provision_school_task
        result = provision_school_task.delay(str(school.id), contact_email=contact_email)
        job_id = getattr(result, "id", None)
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.QUEUED,
            status=SchoolProvisioningEvent.Status.INFO,
            message="Provisioning queued.",
            payload={"job_id": job_id or ""},
            created_by=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        )
    except Exception:
        # Run synchronously if Celery not available
        from apps.schools.tasks import provision_school_sync
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.QUEUED,
            status=SchoolProvisioningEvent.Status.WARNING,
            message="Celery unavailable; provisioning started in synchronous fallback mode.",
            payload={},
            created_by=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        )
        provision_school_sync(str(school.id), contact_email=contact_email)
        job_id = None

    return JsonResponse(
        {
            "school_id": str(school.id),
            "job_id": job_id,
            "message": "School created; provisioning started.",
            "timeline_url": _safe_school_timeline_url(school.id),
        },
        status=202,
    )


# ---------- Phase G: Emergency Sync Repair (Super Admin) ----------

def _sync_repair_force_overwrite_conflict(conflict, resolved_by):
    """Apply client_data to entity and mark conflict RESOLVED_CLIENT. Call inside transaction.atomic()."""
    from django.utils import timezone
    from apps.api.sync_services import _get_entity_config
    conflict.resolved_by = resolved_by
    conflict.resolved_at = timezone.now()
    conflict.status = "RESOLVED_CLIENT"
    config = _get_entity_config()
    if conflict.entity_type in config:
        model, allowed = config[conflict.entity_type]
        updates = {k: v for k, v in (conflict.client_data or {}).items() if k in allowed}
        if updates:
            try:
                instance = model.objects.get(pk=conflict.entity_id)
                for key, value in updates.items():
                    setattr(instance, key, value)
                update_fields = list(updates.keys())
                if hasattr(instance, "updated_at"):
                    update_fields.append("updated_at")
                instance.save(update_fields=update_fields)
            except model.DoesNotExist:
                pass
    conflict.save(update_fields=["status", "resolved_at", "resolved_by"])


@require_http_methods(["GET", "POST"])
def sync_repair(request, school_id):
    """
    Phase G: Super Admin Emergency Sync Repair. List SyncConflict for a school;
    side-by-side client vs server; Force Overwrite applies client_data with transaction.atomic().
    """
    from django.db import transaction
    from django.shortcuts import redirect
    from django.contrib import messages
    from apps.siteconfig.models import SyncConflict

    school = get_object_or_404(School, pk=school_id)
    if not (getattr(request.user, "is_superuser", False)):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Superuser required for Sync Repair.")

    if request.method == "POST":
        conflict_id = request.POST.get("conflict_id")
        if conflict_id:
            try:
                conflict = SyncConflict.objects.get(pk=int(conflict_id), school_id=school_id, status=SyncConflict.Status.PENDING)
            except (ValueError, SyncConflict.DoesNotExist):
                messages.error(request, "Conflict not found or already resolved.")
            else:
                with transaction.atomic():
                    _sync_repair_force_overwrite_conflict(conflict, request.user)
                try:
                    from apps.schools.control_plane import log_control_plane_action
                    from apps.compliance.models_audit import AuditLog
                    log_control_plane_action(
                        request,
                        AuditLog.Action.UPDATE,
                        "SyncConflict",
                        str(conflict.pk),
                        object_repr=f"SyncConflict #{conflict.pk} ({conflict.entity_type})",
                        reason="Sync repair force overwrite (client applied)",
                        sensitivity=AuditLog.Sensitivity.HIGH,
                        new_values={"status": "RESOLVED_CLIENT", "school_id": str(school_id)},
                    )
                except Exception:
                    pass
                messages.success(request, f"Conflict #{conflict_id} resolved (client version applied).")
            return redirect("super:sync_repair", school_id=school_id)

    conflicts = list(
        SyncConflict.objects.filter(school_id=school_id)
        .select_related("reported_by")
        .order_by("-created_at")[:100]
    )
    return render(
        request,
        "schools/super_sync_repair.html",
        {"school": school, "conflicts": conflicts, "dashboard_url": reverse("super:dashboard")},
    )


def super_policy_diff(request):
    """Phase 9: Policy diff viewer — compare platform default, country/region, blueprint, tenant override."""
    school_id = request.GET.get("school_id")
    school = None
    layers = []
    if school_id:
        try:
            school = School.objects.get(id=school_id)
            from apps.policies.policy_registry import get_effective_policy
            policy = get_effective_policy(school, user=getattr(request, "user", None))
            import json
            layers = [
                {"label": "Effective (tenant)", "data": json.dumps(policy or {}, indent=2), "source": "tenant + blueprint + country"},
            ]
        except School.DoesNotExist:
            pass
    return render(
        request,
        "schools/super_policy_diff.html",
        {"school": school, "layers": layers, "dashboard_url": reverse("super:dashboard")},
    )


def super_compliance_overview(request):
    """Phase 13: Control-plane compliance governance — policy pack, audit review, export risk."""
    return render(
        request,
        "schools/super_compliance_overview.html",
        {"dashboard_url": reverse("super:dashboard")},
    )


def super_analytics_overview(request):
    """Phase 13: Analytics and observability — tenant health, adoption, feature usage, workflow success."""
    return render(
        request,
        "schools/super_analytics_overview.html",
        {"dashboard_url": reverse("super:dashboard")},
    )


def super_support_dashboard(request):
    """Global support ticket command center: list tickets with filters; HTMX refreshes queue."""
    from apps.siteconfig.models import GlobalSupportTicket

    status_filter = request.GET.get("status", "").strip()
    priority_filter = request.GET.get("priority", "").strip()
    qs = GlobalSupportTicket.objects.select_related("school", "user", "assigned_to").order_by("-created_at")[:100]
    if status_filter:
        qs = qs.filter(status=status_filter)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    tickets = list(qs)
    tickets = _annotate_tickets_sla(tickets)
    open_count = GlobalSupportTicket.objects.filter(status=GlobalSupportTicket.Status.OPEN).count()
    in_progress_count = GlobalSupportTicket.objects.filter(status=GlobalSupportTicket.Status.IN_PROGRESS).count()
    now = timezone.now()
    backlog_48h = sum(1 for t in tickets if t.age_hours >= 48)
    backlog_7d = sum(1 for t in tickets if t.age_hours >= (24 * 7))
    oldest_hours = max((t.age_hours for t in tickets), default=0.0)
    sla_breach_response = sum(1 for t in tickets if getattr(t, "sla_response_breach", False))
    sla_breach_resolution = sum(1 for t in tickets if getattr(t, "sla_resolution_breach", False))
    from apps.siteconfig.support_sla import SUPPORT_SLA_RESPONSE_HOURS, SUPPORT_SLA_RESOLUTION_HOURS
    return render(
        request,
        "schools/super_support_dashboard.html",
        {
            "tickets": tickets,
            "request_user_id": getattr(request.user, "id", None),
            "open_count": open_count,
            "in_progress_count": in_progress_count,
            "backlog_48h": backlog_48h,
            "backlog_7d": backlog_7d,
            "oldest_hours": round(oldest_hours, 1),
            "sla_breach_response": sla_breach_response,
            "sla_breach_resolution": sla_breach_resolution,
            "sla_response_hours": SUPPORT_SLA_RESPONSE_HOURS,
            "sla_resolution_hours": SUPPORT_SLA_RESOLUTION_HOURS,
            "status_filter": status_filter,
            "priority_filter": priority_filter,
        },
    )


def _annotate_tickets_sla(tickets):
    """Annotate ticket list with age_hours and SLA breach flags (integrated with siteconfig.support_sla)."""
    from apps.siteconfig.support_sla import ticket_response_breach, ticket_resolution_breach

    now = timezone.now()
    for ticket in tickets:
        ticket.age_hours = round(max(0.0, (now - ticket.created_at).total_seconds() / 3600.0), 1)
        ticket.sla_response_breach = ticket_response_breach(ticket)
        ticket.sla_resolution_breach = ticket_resolution_breach(ticket)
    return tickets


def support_queue_fragment(request):
    """HTMX fragment: ticket queue table (refresh every 60s). SLA breach from apps.siteconfig.support_sla."""
    from apps.siteconfig.models import GlobalSupportTicket
    from apps.siteconfig.support_sla import SUPPORT_SLA_RESPONSE_HOURS, SUPPORT_SLA_RESOLUTION_HOURS

    status_filter = request.GET.get("status", "").strip()
    priority_filter = request.GET.get("priority", "").strip()
    qs = GlobalSupportTicket.objects.select_related("school", "user", "assigned_to").order_by("-created_at")[:50]
    if status_filter:
        qs = qs.filter(status=status_filter)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    tickets = _annotate_tickets_sla(list(qs))
    return render(
        request,
        "schools/super_support_queue_fragment.html",
        {
            "tickets": tickets,
            "request_user_id": getattr(request.user, "id", None),
            "sla_response_hours": SUPPORT_SLA_RESPONSE_HOURS,
            "sla_resolution_hours": SUPPORT_SLA_RESOLUTION_HOURS,
        },
    )


def support_assign_ticket(request):
    """POST: assign ticket to current user or unassign. Redirects to support dashboard or returns fragment for HTMX."""
    from django.shortcuts import redirect
    from apps.siteconfig.models import GlobalSupportTicket

    if request.method != "POST":
        return redirect("super:support_dashboard")
    ticket_id = request.POST.get("ticket_id", "").strip()
    action = request.POST.get("action", "").strip().lower()
    if not ticket_id or action not in ("assign_me", "unassign"):
        return redirect("super:support_dashboard")
    try:
        ticket = GlobalSupportTicket.objects.get(pk=ticket_id)
    except GlobalSupportTicket.DoesNotExist:
        return redirect("super:support_dashboard")
    if action == "assign_me":
        ticket.assigned_to_id = getattr(request.user, "id", None)
        if ticket.first_response_at is None:
            ticket.first_response_at = timezone.now()
            ticket.save(update_fields=["assigned_to_id", "first_response_at"])
        else:
            ticket.save(update_fields=["assigned_to_id"])
    else:
        ticket.assigned_to = None
        ticket.save(update_fields=["assigned_to_id"])
    if request.headers.get("HX-Request"):
        from apps.siteconfig.support_sla import SUPPORT_SLA_RESPONSE_HOURS, SUPPORT_SLA_RESOLUTION_HOURS
        status_filter = request.GET.get("status", "").strip()
        priority_filter = request.GET.get("priority", "").strip()
        qs = GlobalSupportTicket.objects.select_related("school", "user", "assigned_to").order_by("-created_at")[:50]
        if status_filter:
            qs = qs.filter(status=status_filter)
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        tickets = _annotate_tickets_sla(list(qs))
        return render(
            request,
            "schools/super_support_queue_fragment.html",
            {
                "tickets": tickets,
                "request_user_id": getattr(request.user, "id", None),
                "sla_response_hours": SUPPORT_SLA_RESPONSE_HOURS,
                "sla_resolution_hours": SUPPORT_SLA_RESOLUTION_HOURS,
            },
        )
    return redirect("super:support_dashboard")


# -----------------------------------------------------------------------------
# Sovereign AI: Model Hub and Global Upgrade (Super Admin)
# -----------------------------------------------------------------------------

def ai_model_hub(request):
    """
    Super Admin: list regions with default_model, fallback_model, last_health_check_at, status.
    Single source: RegionalAIConfig + health from cache (ai:health:{cluster}).
    """
    from django.core.cache import cache
    from apps.siteconfig.models import RegionalAIConfig
    from apps.siteconfig.tasks import AI_HEALTH_CACHE_PREFIX, AI_HEALTH_CACHE_TTL

    configs = list(RegionalAIConfig.objects.filter(is_active=True).order_by("regional_cluster"))
    for c in configs:
        health = cache.get(f"{AI_HEALTH_CACHE_PREFIX}{c.regional_cluster}") or {}
        c.health_status = health.get("status", "unknown")
        c.last_health_check_at = health.get("last_check_at", "")

    return render(
        request,
        "schools/super_ai_model_hub.html",
        {
            "configs": configs,
            "dashboard_url": reverse("super:dashboard"),
            "global_ai_version_url": reverse("super:global_ai_version"),
        },
    )


@require_http_methods(["GET", "POST"])
def global_ai_version(request):
    """
    Super Admin: form with target model_id and "Upgrade all regions" button.
    POST enqueues global_ai_upgrade_run and redirects to progress (run_id in session); poll for regions_done/regions_total.
    """
    from django.core.cache import cache
    from apps.siteconfig.models import RegionalAIConfig
    from apps.siteconfig.tasks import global_ai_upgrade_run, AI_UPGRADE_PROGRESS_PREFIX
    import uuid

    if request.method == "POST":
        model_id = (request.POST.get("model_id") or "").strip()
        if not model_id:
            from django.contrib import messages
            messages.warning(request, "Model ID is required.")
            return redirect("super:global_ai_version")
        run_id = str(uuid.uuid4())
        global_ai_upgrade_run.delay(run_id, model_id)
        request.session["ai_upgrade_run_id"] = run_id
        return redirect("super:global_ai_version_progress", run_id=run_id)

    clusters = list(
        RegionalAIConfig.objects.filter(is_active=True).values_list("regional_cluster", flat=True).distinct()
    )
    return render(
        request,
        "schools/super_global_ai_version.html",
        {
            "clusters": clusters,
            "dashboard_url": reverse("super:dashboard"),
            "ai_model_hub_url": reverse("super:ai_model_hub"),
        },
    )


def global_ai_version_progress(request, run_id):
    """Poll endpoint or page showing regions_done/regions_total for the run."""
    from django.core.cache import cache
    from django.http import JsonResponse
    from apps.siteconfig.tasks import AI_UPGRADE_PROGRESS_PREFIX

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.GET.get("json"):
        data = cache.get(f"{AI_UPGRADE_PROGRESS_PREFIX}{run_id}") or {}
        return JsonResponse(data)
    return render(
        request,
        "schools/super_global_ai_version_progress.html",
        {"run_id": run_id, "dashboard_url": reverse("super:dashboard")},
    )


# -----------------------------------------------------------------------------
# Secure impersonation (view as tenant)
# -----------------------------------------------------------------------------

def _can_impersonate(request):
    """True if request.user is allowed to impersonate (SUPERADMIN or is_superuser)."""
    if not getattr(request.user, "is_authenticated", False):
        return False
    if getattr(request.user, "is_superuser", False):
        return True
    role = (getattr(request.user, "role", "") or "").upper()
    return role == "SUPERADMIN"


@require_POST
def switch_to_tenant(request):
    """
    Super-admin only. Accepts school_id (POST), creates a short-lived signed token,
    logs ImpersonationLog.SWITCH, redirects to the tenant's impersonation entry URL.
    """
    if not _can_impersonate(request):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Super Admin access required.")
    from django.core.signing import TimestampSigner
    from django.conf import settings
    from apps.siteconfig.models import ImpersonationLog
    from .tenant_url import build_tenant_backend_url
    import json
    import base64

    school_id = request.POST.get("school_id", "").strip()
    if not school_id:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("school_id required.")
    school = get_object_or_404(School, id=school_id, is_active=True)
    # JIT: principal consent required before impersonation (195-country governance; configurable).
    if getattr(settings, "JIT_IMPERSONATION_REQUIRE_CONSENT", True):
        from django.utils import timezone
        from datetime import timedelta
        consent_at = getattr(school, "impersonation_consent_granted_at", None)
        if not consent_at:
            from django.contrib import messages
            messages.error(
                request,
                "Impersonation requires principal consent for this school. Ask the school admin to grant consent in their Backend settings.",
            )
            return redirect("super:dashboard")
        # Optional: consent expires after N days (e.g. 30)
        consent_days = getattr(settings, "JIT_IMPERSONATION_CONSENT_DAYS", 30)
        if consent_days and timezone.now() - consent_at > timedelta(days=consent_days):
            from django.contrib import messages
            messages.warning(request, "Impersonation consent for this school has expired. Principal must re-grant.")
            return redirect("super:dashboard")
    payload = {
        "school_id": str(school.id),
        "user_id": request.user.id,
    }
    payload_b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    signer = TimestampSigner(key=getattr(settings, "SECRET_KEY", "fallback"))
    token = signer.sign(payload_b64)
    # Audit
    ImpersonationLog.objects.create(
        actor=request.user,
        school=school,
        action=ImpersonationLog.Action.SWITCH,
        ip_address=_get_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
    )
    try:
        from apps.schools.control_plane import log_control_plane_action
        from apps.compliance.models_audit import AuditLog
        log_control_plane_action(
            request,
            AuditLog.Action.VIEW,
            "School",
            str(school.id),
            object_repr=school.name or str(school.id),
            reason="Impersonation switch (control plane)",
            sensitivity=AuditLog.Sensitivity.CRITICAL,
        )
    except Exception:
        pass
    entry_path = "/authentication/impersonate/"
    next_url = request.POST.get("next", "/").strip() or "/"
    url = build_tenant_backend_url(request, school, path=entry_path)
    sep = "&" if "?" in url else "?"
    redirect_to = f"{url}{sep}impersonate={token}&next={next_url}"
    return redirect(redirect_to)


def super_runtime_inspector(request):
    """Control plane: inspect tenant_runtime for a selected school (effective blueprint, packs, overrides)."""
    from apps.platform_runtime.runtime_inspector import get_runtime_inspection_for_school

    school_id = (request.GET.get("school_id") or "").strip()
    school = None
    inspection = None
    schools_sample = list(School.objects.filter(is_active=True).order_by("-last_activity", "-created_at")[:20].values("id", "name", "slug"))
    if school_id:
        try:
            school = School.objects.get(id=school_id)
            inspection = get_runtime_inspection_for_school(school)
        except (School.DoesNotExist, ValueError):
            pass
    return render(
        request,
        "schools/super_runtime_inspector.html",
        {
            "school": school,
            "inspection": inspection,
            "schools_sample": schools_sample,
            "dashboard_url": reverse("super:dashboard"),
        },
    )


def super_workflow_simulator(request):
    """Control plane: simulate workflow/pack resolution for a selected school and role."""
    school_id = (request.GET.get("school_id") or "").strip()
    role = (request.GET.get("role") or "ADMIN").strip().upper()
    school = None
    workflow_summary = None
    if school_id:
        try:
            school = School.objects.get(id=school_id)
            from apps.platform_runtime.runtime_resolver import build_tenant_runtime_for_tenant
            rt = build_tenant_runtime_for_tenant(school, user=getattr(request, "user", None))
            if rt and hasattr(rt, "workflow_for"):
                wf = rt.workflow_for(role)
                workflow_summary = {"role": role, "workflow_id": getattr(wf, "id", None), "workflow_slug": getattr(wf, "slug", None)}
            elif rt and hasattr(rt, "policy"):
                workflow_summary = {"role": role, "workflow_id": None, "workflow_slug": None, "note": "workflow_for not available"}
        except (School.DoesNotExist, ValueError):
            pass
    return render(
        request,
        "schools/super_workflow_simulator.html",
        {"school": school, "workflow_summary": workflow_summary, "dashboard_url": reverse("super:dashboard")},
    )


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
