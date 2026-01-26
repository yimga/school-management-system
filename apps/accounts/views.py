from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.http import HttpResponseForbidden
from django.urls import reverse
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from config.admin import admin_site
from apps.finance.models import Invoice, ReferralReward, PaymentReminder
from apps.finance.services import finance_dashboard_data
from apps.portal.models import PendingGuardianInvite
from apps.people.models import StudentGuardian, StudentProfile, TeacherAttendance
from apps.reports.models import TermPublishStatus
from apps.siteconfig.models import SiteSettings
from apps.academics.services import get_active_year_and_term
from apps.portal.services import link_guardian_via_invite
from apps.accounts.decorators import permission_required
from apps.siteconfig.templatetags.admin_health import admin_section_stats
from apps.siteconfig.templatetags.admin_kpis import admin_kpis

from .forms import ClaimInviteAccountForm, PermissionForm, RoleForm, UserPermissionForm, UserRoleForm
from .models import AccessRole, Permission, User


@permission_required("settings.manage")
@user_passes_test(lambda u: u.is_authenticated and (u.is_staff or u.is_superuser or getattr(u, "role", None) == User.Role.ADMIN))
def backend_entity_import(request):
    """Admin-only page to stage CSV imports (students/guardians) against new APIs."""
    site = SiteSettings.get_solo()
    flags = getattr(site, "backend_feature_flags", {}) or {}
    allowed_roles = [r.upper() for r in flags.get("allowed_roles_entity_import", [])]
    if not flags.get("enable_entity_import", True):
        return HttpResponseForbidden("Entity import is disabled by admin.")
    if allowed_roles:
        role = (getattr(request.user, "role", "") or "").upper()
        if role not in allowed_roles and not (request.user.is_staff or request.user.is_superuser):
            return HttpResponseForbidden("You are not allowed to access Entity Import.")
    return render(request, "accounts/entity_import.html", {})


@permission_required("settings.manage")
@user_passes_test(lambda u: u.is_authenticated and (u.is_staff or u.is_superuser or getattr(u, "role", None) == User.Role.ADMIN))
def backend_entity_console(request):
    """Admin-only page for EntityForm/Table beta UI."""
    site = SiteSettings.get_solo()
    flags = getattr(site, "backend_feature_flags", {}) or {}
    allowed_roles = [r.upper() for r in flags.get("allowed_roles_entity_console", [])]
    if not flags.get("enable_entity_console", True):
        return HttpResponseForbidden("Entity console is disabled by admin.")
    if allowed_roles:
        role = (getattr(request.user, "role", "") or "").upper()
        if role not in allowed_roles and not (request.user.is_staff or request.user.is_superuser):
            return HttpResponseForbidden("You are not allowed to access Entity Console.")
    return render(request, "accounts/entity_console.html", {})


def redirect_view(request):
    """Central post-login redirect based on role.

    Keeping this logic in one place makes LOGIN_REDIRECT_URL reliable and
    prevents hard-coded URLs from drifting.
    """
    user = request.user
    if not user.is_authenticated:
        return redirect(reverse("accounts:login"))

    if user.has_feature_permission("settings.manage"):
        return redirect("accounts:backend_dashboard")

    if getattr(user, "role", None) == "TEACHER":
        return redirect("evals:teacher_dashboard")
    if getattr(user, "role", None) == "PARENT":
        return redirect("portal:parent_dashboard")

    # Default: admin
    return redirect("admin:index")


def _is_admin_user(user):
    return user.is_authenticated and (
        user.is_superuser or user.is_staff or user.role == User.Role.ADMIN
    )


def _resolve_admin_portal_stats(section_stats, config):
    if not isinstance(config, dict):
        config = {}

    def _to_int(value, fallback):
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    sections = config.get("sections") or list(section_stats.keys())
    max_sections = _to_int(config.get("max_sections"), 3)
    max_items = _to_int(config.get("max_items"), 3)
    items = config.get("items") if isinstance(config.get("items"), dict) else {}

    selected = {}
    for section in sections:
        if max_sections and len(selected) >= max_sections:
            break
        stats = section_stats.get(section)
        if not isinstance(stats, dict):
            continue
        preferred_items = items.get(section)
        if isinstance(preferred_items, list) and preferred_items:
            filtered = {label: stats[label] for label in preferred_items if label in stats}
        else:
            filtered = dict(stats)
            if max_items and max_items > 0:
                filtered = dict(list(filtered.items())[:max_items])
        if filtered:
            selected[section] = filtered

    if selected:
        return selected

    if not section_stats:
        return {}

    fallback = {}
    for section, stats in section_stats.items():
        if max_sections and len(fallback) >= max_sections:
            break
        if not isinstance(stats, dict):
            continue
        filtered = dict(stats)
        if max_items and max_items > 0:
            filtered = dict(list(filtered.items())[:max_items])
        fallback[section] = filtered
    return fallback


@login_required
@user_passes_test(_is_admin_user)
def rbac_dashboard(request):
    role_form = RoleForm(prefix="role")
    permission_form = PermissionForm(prefix="permission")
    user_role_form = UserRoleForm(prefix="user_role")
    user_permission_form = UserPermissionForm(prefix="user_permission")

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "role":
            role_form = RoleForm(request.POST, prefix="role")
            if role_form.is_valid():
                role_form.save()
                messages.success(request, "Role created successfully.")
                return redirect("accounts:rbac")
        elif form_type == "permission":
            permission_form = PermissionForm(request.POST, prefix="permission")
            if permission_form.is_valid():
                permission_form.save()
                messages.success(request, "Permission created successfully.")
                return redirect("accounts:rbac")
        elif form_type == "user_roles":
            user_role_form = UserRoleForm(request.POST, prefix="user_role")
            if user_role_form.is_valid():
                user = user_role_form.cleaned_data["user"]
                roles = user_role_form.cleaned_data["roles"]
                user.roles.set(roles)
                messages.success(request, f"Roles updated for {user.username}.")
                return redirect("accounts:rbac")
        elif form_type == "user_permissions":
            user_permission_form = UserPermissionForm(request.POST, prefix="user_permission")
            if user_permission_form.is_valid():
                user = user_permission_form.cleaned_data["user"]
                permissions = user_permission_form.cleaned_data["permissions"]
                user.feature_permissions.set(permissions)
                messages.success(request, f"Permissions updated for {user.username}.")
                return redirect("accounts:rbac")

    today = timezone.localdate()
    week_start = today - timedelta(days=6)
    window = TeacherAttendance.objects.filter(date__range=(week_start, today))
    present_map = {
        entry["date"]: entry["count"]
        for entry in window.filter(status=TeacherAttendance.Status.PRESENT)
        .values("date")
        .annotate(count=Count("id"))
    }
    attendance_trend = [
        {"date": week_start + timedelta(days=offset), "present": present_map.get(week_start + timedelta(days=offset), 0)}
        for offset in range(7)
    ]
    attendance_trend_total = sum(item["present"] for item in attendance_trend)
    attendance_trend_progress = min(attendance_trend_total, 100)

    context = {
        "roles": AccessRole.objects.prefetch_related("permissions").order_by("code"),
        "permissions": Permission.objects.order_by("code"),
        "role_form": role_form,
        "permission_form": permission_form,
        "user_role_form": user_role_form,
        "user_permission_form": user_permission_form,
        "attendance_trend_total": attendance_trend_total,
        "attendance_trend_progress": attendance_trend_progress,

    }
    return render(request, "accounts/rbac_dashboard.html", context)


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def backend_dashboard(request):
    from .activity_helper import get_recent_activity
    
    site = SiteSettings.get_solo()
    year, term = get_active_year_and_term()
    stats = {
        "students": StudentProfile.objects.filter(is_active=True).count(),
        "guardians": StudentGuardian.objects.count(),
        "pending_invites": PendingGuardianInvite.objects.filter(guardian_user__isnull=True).count(),
        "pending_referrals": ReferralReward.objects.filter(status=ReferralReward.Status.PENDING).count(),
        "overdue_invoices": Invoice.objects.filter(status=Invoice.Status.OVERDUE).count(),
        "published_terms": TermPublishStatus.objects.filter(is_published=True).count(),
    }
    
    # Get recent activity
    recent_activities = get_recent_activity(limit=10)
    
    finance_overview = {}
    finance_summary = {}
    finance_trend = []
    finance_status_counts = []
    compliance_profile = site.compliance_profile
    if compliance_profile:
        finance_overview = finance_dashboard_data(compliance_profile)
        finance_summary = finance_overview.get("summary", {})
        finance_trend = finance_overview.get("trend", [])
        finance_status_counts = finance_overview.get("status_counts", [])

    today = timezone.localdate()
    attendance_today = TeacherAttendance.objects.filter(date=today)
    status_labels = {choice.value: choice.label for choice in TeacherAttendance.Status}
    attendance_counts = {label: 0 for label in status_labels.values()}
    for row in attendance_today.values("status").annotate(count=Count("id")):
        label = status_labels.get(row["status"], row["status"])
        attendance_counts[label] = row["count"]

    week_start = today - timedelta(days=6)
    window = TeacherAttendance.objects.filter(date__range=(week_start, today))
    present_map = {
        entry["date"]: entry["count"]
        for entry in window.filter(status=TeacherAttendance.Status.PRESENT)
        .values("date")
        .annotate(count=Count("id"))
    }
    attendance_trend = [
        {"date": week_start + timedelta(days=offset), "present": present_map.get(week_start + timedelta(days=offset), 0)}
        for offset in range(7)
    ]
    attendance_trend_total = sum(item["present"] for item in attendance_trend)
    attendance_trend_progress = min(attendance_trend_total, 100)
    avg_weekly_present = attendance_trend_total / 7 if attendance_trend else 0
    ai_insight = f"Average daily presence last week: {avg_weekly_present:.0f} students."

    reminders_qs = (
        PaymentReminder.objects.select_related("invoice__student")
        .filter(is_active=True)
        .order_by("next_send_at")
    )[:4]
    reminders = list(reminders_qs)
    reminder_alerts = bool(reminders)
    section_stats = {
        section: dict(stats)
        for section, stats in admin_section_stats().items()
    }
    admin_portal_stats = _resolve_admin_portal_stats(
        section_stats,
        getattr(site, "admin_portal_stats_config", {}) or {},
    )
    can_manage_settings = request.user.has_feature_permission("settings.manage")

    app_context = admin_site.each_context(request)
    modules = sum(len(app.get("models") or []) for app in app_context.get("available_apps", []))
    kpi_data = admin_kpis()
    hero_stats = [
        {"label": "Students", "value": kpi_data["students"], "meta": "Active profiles"},
        {"label": "Subjects", "value": kpi_data["subjects"], "meta": "Catalog size"},
        {"label": "Report cards", "value": kpi_data["report_cards"], "meta": "Generated"},
        {"label": "Modules", "value": modules, "meta": "Registered apps"},
    ]
    hero_actions = [
        {"label": "Open parent portal", "url": reverse("portal:parent_dashboard")},
        {"label": "Backend config", "url": reverse("accounts:backend_dashboard")},
        {"label": "Frontend admin", "url": reverse("admin:index")},
    ]
    if can_manage_settings:
        hero_actions.append({"label": "Open Full Site Settings", "url": reverse("siteconfig:user_preferences")})

    hero = {
        "tagline": "Admin hub",
        "title": "Gilead School System Management",
        "subtitle": "Configure school apps, monitor health, and keep reports, finance, and portals aligned from one warm, modern dashboard.",
        "icon": "bi bi-pie-chart",
        "stats": hero_stats,
        "actions": hero_actions,
        "insight": ai_insight,
        "status_pills": [
            {"label": "Today’s reminders", "value": len(reminders), "meta": "queued alerts"},
            {"label": "Published terms", "value": stats["published_terms"], "meta": "published"},
        ],
    }
    context = {
        "site": site,
        "stats": stats,
        "roles": AccessRole.objects.prefetch_related("permissions").order_by("code"),
        "permissions": Permission.objects.order_by("code"),
        "pending_invites": stats["pending_invites"],
        "grade_import_upload_url": reverse("evals:grade_import_upload"),
        "grade_import_template_url": reverse("evals:grade_import_template"),
        "active_year": year,
        "active_term": term,
        "recent_activities": recent_activities,
        "finance_summary": finance_summary,
        "finance_trend": finance_trend,
        "finance_status_counts": finance_status_counts,
        "attendance_counts": attendance_counts,
        "attendance_trend": attendance_trend,
        "attendance_trend_total": attendance_trend_total,
        "attendance_trend_progress": attendance_trend_progress,
        "attended_today": attendance_today.count(),
        "reminders": reminders,
        "reminder_alerts": reminder_alerts,
        "compliance_profile": compliance_profile,
        "section_stats": section_stats,
        "admin_portal_stats": admin_portal_stats,
        "can_manage_settings": can_manage_settings,
        "ai_insight": ai_insight,
        "social_links": site.active_social_links,
        "avg_weekly_present": avg_weekly_present,
        "hero": hero,
        "app_list": app_context.get("available_apps", []),
    }
    return render(request, "accounts/backend_dashboard.html", context)


@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def login_view(request):
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username"),
            password=request.POST.get("password"),
        )
        if user:
            login(request,user)
            return redirect(reverse("accounts:redirect"))

        messages.error(request, "Invalid username or password.")
    return render(request,"auth/login.html")

def logout_view(request):
    logout(request)
    return redirect(reverse("accounts:login"))


def claim_invite(request):
    if request.user.is_authenticated:
        return redirect(reverse("accounts:redirect"))

    form = ClaimInviteAccountForm(request.POST or None)
    if form.is_valid():
        invite = form.invite
        user = form.save_user()
        link_guardian_via_invite(invite, user, awarded_by=user)
        login(request, user)
        messages.success(
            request,
            f"Welcome! You are now linked to {invite.student} and can view reports/finance."
        )
        return redirect("portal:parent_dashboard")

    return render(request, "accounts/claim_invite.html", {"form": form})
