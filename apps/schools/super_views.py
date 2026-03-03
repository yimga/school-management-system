"""
Super Admin views: dashboard (list schools) and Create School wizard.
Access restricted to SUPERADMIN or is_superuser via TenantSuperAdminRequiredMiddleware.
"""
import csv
from datetime import timedelta
from io import StringIO

from django.db.models import Count
from django.db.models import OuterRef, Subquery
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods, require_POST
from django.http import JsonResponse, HttpResponse
from django.utils import timezone

from apps.siteconfig.education_profile_engine import (
    ensure_region_for_country as ensure_region_for_country_record,
    list_profile_options,
)
from apps.siteconfig.global_catalog import GlobalGeoCatalog
from apps.siteconfig.models import EducationSystemProfile
from apps.siteconfig.tenant_config import apply_tenant_settings_overrides
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
        school.quota_limits = quotas.get(school.pk, [])
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
    return render(
        request,
        "schools/super_usage.html",
        {"schools": schools},
    )


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
        .values("id", "name", "slug", "is_active", "is_approved", "last_activity", "student_count")
    )
    for s in schools:
        s["admin_edit_url"] = _safe_school_admin_change_url(s["id"])
    return render(
        request,
        "schools/super_tenant_health.html",
        {"tenants": schools},
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


def billing_dashboard(request):
    """Plan X: Billing dashboard — trial schools, trial_end_date, usage; Stripe integration via webhooks (see docs)."""
    from django.db.models import Sum
    from django.utils import timezone
    trial_schools = list(
        School.objects.filter(is_active=True, billing_type=School.BillingType.FREE_TRIAL)
        .annotate(student_count=Count("student_profiles", distinct=True))
        .order_by("trial_end_date", "name")
    )
    school_ids = [s.pk for s in trial_schools]
    usage_agg = {}
    if school_ids:
        for r in TenantApiUsage.objects.filter(school_id__in=school_ids).values("school_id").annotate(total=Sum("request_count")):
            usage_agg[r["school_id"]] = r["total"]
    for school in trial_schools:
        school.api_requests = usage_agg.get(school.pk, 0)
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
        school.trial_expired = school.trial_end_date and school.trial_end_date < timezone.now().date()
    return render(
        request,
        "schools/billing_dashboard.html",
        {
            "trial_schools": trial_schools,
            "usage_url": reverse("super:usage"),
        },
    )


@require_http_methods(["GET", "POST"])
def create_school_wizard(request):
    """Multi-step wizard: Step 1 identity, Step 2 region, Step 3 branding. POST submits to API."""
    from apps.siteconfig.models import (
        RegionConfig,
        WeatherLocation,
        default_header_weather_config,
    )

    if request.method == "POST":
        # Wizard form submitted via JS to api_create_school; this is fallback or redirect
        return redirect("super:api_create_school")

    regions = RegionConfig.objects.all().order_by("name")
    defaults = default_header_weather_config()
    default_country_code = GlobalGeoCatalog.normalize_country_code(
        defaults.get("header_weather_country_code", "CMR")
    )
    countries = GlobalGeoCatalog.list_countries()
    known_codes = {row["code"] for row in countries}
    if default_country_code not in known_codes and countries:
        default_country_code = countries[0]["code"]
    cities = GlobalGeoCatalog.search_cities(
        country_code=default_country_code,
        limit=180,
    )
    default_sub_system = School.SubSystem.EN
    education_profiles = list_profile_options(
        country_code=default_country_code,
        sub_system=default_sub_system,
    )
    # S2: One-click education templates (British/WAEC/Vocational) — same as API config/education-templates
    education_templates_standard = [
        {"code": "BRITISH_IGCSE", "name": "British / IGCSE", "description": "Michaelmas, Lent, Trinity; A*–G or 9–1."},
        {"code": "WAEC", "name": "West African (WAEC)", "description": "First, Second, Third term; A1–F9; CA 30% + Exam 70%."},
        {"code": "FRANCOPHONE_BAC", "name": "Francophone (Bac)", "description": "Trimestre 1–3; 20-point scale."},
        {"code": "VOCATIONAL", "name": "Vocational / Trade", "description": "Competency checklists; clock hours; skill badges."},
    ]
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
            countries.append({"code": loc.region_id, "name": loc.region.name, "timezone": loc.region.timezone})
        cities = [
            {
                "id": str(loc.pk),
                "country_code": loc.region_id,
                "city": loc.city,
                "label": loc.display_label,
                "timezone": loc.timezone or loc.region.timezone or "UTC",
                "latitude": float(loc.latitude),
                "longitude": float(loc.longitude),
            }
            for loc in locations
            if not default_country_code or loc.region_id == default_country_code
        ]
    return render(
        request,
        "schools/super_create_school_wizard.html",
        {
            "regions": regions,
            "countries": countries,
            "cities": cities,
            "default_country_code": default_country_code or defaults.get("header_weather_country_code", "CMR"),
            "default_sub_system": default_sub_system,
            "education_profiles": education_profiles,
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
    """Phase B: List provinces/states for a country (for wizard and systems filter)."""
    country_code = GlobalGeoCatalog.normalize_country_code(request.GET.get("country_code") or "")
    if not country_code:
        return JsonResponse({"country_code": "", "provinces": []})
    from apps.siteconfig.models import RegionConfig, Province
    region = RegionConfig.objects.filter(code=country_code).first()
    if not region:
        return JsonResponse({"country_code": country_code, "provinces": []})
    provinces = list(
        Province.objects.filter(region=region)
        .order_by("name")
        .values("id", "code", "name")
    )
    return JsonResponse({"country_code": country_code, "provinces": provinces})


@require_http_methods(["GET"])
def api_education_profiles(request):
    country_code = GlobalGeoCatalog.normalize_country_code(request.GET.get("country_code"))
    sub_system = (request.GET.get("sub_system") or School.SubSystem.EN).strip().upper()
    valid_subsystems = {School.SubSystem.EN, School.SubSystem.FR, School.SubSystem.INT}
    if sub_system not in valid_subsystems:
        sub_system = School.SubSystem.EN
    province_id = request.GET.get("province_id")
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
    from apps.siteconfig.models import Plan, PlanAddon, CountryMultiplier
    from decimal import Decimal

    country_code = (request.GET.get("country_code") or "").strip().upper()[:3]
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
    school = get_object_or_404(School, id=school_id)
    school.is_approved = True
    school.save(update_fields=["is_approved", "updated_at"])
    return JsonResponse({"ok": True, "school_id": str(school.id), "message": "School approved."})


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

    name = (data.get("name") or "").strip()
    slug = (data.get("slug") or "").strip().lower().replace(" ", "-")
    if not slug and name:
        slug = _slug_from_name(name)
    subdomain = (data.get("subdomain") or slug or "").strip().lower()
    contact_email = (data.get("contact_email") or "").strip()
    region_code = GlobalGeoCatalog.normalize_country_code((data.get("region_code") or "").strip())
    country_code = GlobalGeoCatalog.normalize_country_code(
        (data.get("country_code") or region_code or "").strip()
    )
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
    STANDARD_TEMPLATE_CODES = {"BRITISH_IGCSE", "WAEC", "FRANCOPHONE_BAC", "VOCATIONAL"}
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

    from apps.siteconfig.models import RegionConfig, WeatherLocation
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
        default_region = _ensure_region_for_country(country_code, selected_city.get("timezone") or "UTC")
    elif selected_location:
        default_region = selected_location.region
        country_code = selected_location.region_id
    if default_region is None and country_code:
        default_region = RegionConfig.objects.filter(code=country_code).first() or _ensure_region_for_country(country_code)
    if default_region is None and region_code:
        default_region = RegionConfig.objects.filter(code=region_code).first() or _ensure_region_for_country(region_code)
    if default_region is None and explicit_profile and explicit_profile.region_id:
        default_region = explicit_profile.region
        country_code = explicit_profile.region_id
    resolved_timezone = (
        (selected_city.get("timezone") if selected_city else "")
        or (selected_location.timezone if selected_location else "")
        or (explicit_profile.default_timezone if explicit_profile else "")
        or (default_region.timezone if default_region else "")
        or "UTC"
    )
    location_payload = {
        "country_code": country_code or (default_region.code if default_region else ""),
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
            "province_id": province_id,
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
        from apps.siteconfig.models import Plan
        if Plan.objects.filter(pk=plan_id, is_active=True).exists():
            create_kw["plan_id"] = plan_id
    if addons and hasattr(School, "addons"):
        addons = [str(x).strip() for x in addons if x]
        create_kw["addons"] = addons
    school = School.objects.create(**create_kw)
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


def super_support_dashboard(request):
    """Global support ticket command center: list tickets with filters; HTMX refreshes queue."""
    from apps.siteconfig.models import GlobalSupportTicket

    status_filter = request.GET.get("status", "").strip()
    priority_filter = request.GET.get("priority", "").strip()
    qs = GlobalSupportTicket.objects.select_related("school", "user").order_by("-created_at")[:100]
    if status_filter:
        qs = qs.filter(status=status_filter)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    tickets = list(qs)
    open_count = GlobalSupportTicket.objects.filter(status=GlobalSupportTicket.Status.OPEN).count()
    in_progress_count = GlobalSupportTicket.objects.filter(status=GlobalSupportTicket.Status.IN_PROGRESS).count()
    now = timezone.now()
    backlog_48h = 0
    backlog_7d = 0
    oldest_hours = 0.0
    for ticket in tickets:
        age_hours = max(0.0, (now - ticket.created_at).total_seconds() / 3600.0)
        ticket.age_hours = round(age_hours, 1)
        if age_hours >= 48:
            backlog_48h += 1
        if age_hours >= (24 * 7):
            backlog_7d += 1
        if age_hours > oldest_hours:
            oldest_hours = age_hours
    return render(
        request,
        "schools/super_support_dashboard.html",
        {
            "tickets": tickets,
            "open_count": open_count,
            "in_progress_count": in_progress_count,
            "backlog_48h": backlog_48h,
            "backlog_7d": backlog_7d,
            "oldest_hours": round(oldest_hours, 1),
            "status_filter": status_filter,
            "priority_filter": priority_filter,
        },
    )


def support_queue_fragment(request):
    """HTMX fragment: ticket queue table (refresh every 60s)."""
    from apps.siteconfig.models import GlobalSupportTicket

    status_filter = request.GET.get("status", "").strip()
    qs = GlobalSupportTicket.objects.select_related("school", "user").order_by("-created_at")[:50]
    if status_filter:
        qs = qs.filter(status=status_filter)
    tickets = list(qs)
    now = timezone.now()
    for ticket in tickets:
        ticket.age_hours = round(max(0.0, (now - ticket.created_at).total_seconds() / 3600.0), 1)
    return render(
        request,
        "schools/super_support_queue_fragment.html",
        {"tickets": tickets},
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
    entry_path = "/authentication/impersonate/"
    next_url = request.POST.get("next", "/").strip() or "/"
    url = build_tenant_backend_url(request, school, path=entry_path)
    sep = "&" if "?" in url else "?"
    redirect_to = f"{url}{sep}impersonate={token}&next={next_url}"
    return redirect(redirect_to)


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
