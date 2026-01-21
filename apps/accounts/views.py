from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.contrib import admin as django_admin
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

    attendance_trend_total = sum(item['present'] for item in attendance_trend)
    attendance_trend_progress = min(attendance_trend_total, 100)
    context = {
        "roles": AccessRole.objects.prefetch_related("permissions").order_by("code"),
        "permissions": Permission.objects.order_by("code"),
        "role_form": role_form,
        "permission_form": permission_form,
        "user_role_form": user_role_form,
        "user_permission_form": user_permission_form,
    }
    return render(request, "accounts/rbac_dashboard.html", context)


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def backend_dashboard(request):
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

    reminders_qs = (
        PaymentReminder.objects.select_related("invoice__student")
        .filter(is_active=True)
        .order_by("next_send_at")
    )[:4]
    reminders = list(reminders_qs)
    reminder_alerts = bool(reminders)
    section_stats = admin_section_stats()
    can_manage_settings = request.user.has_feature_permission("settings.manage")

    app_context = django_admin.site.each_context(request)
    modules = sum(len(app.get("models") or []) for app in app_context.get("available_apps", []))
    kpi_data = admin_kpis()
    hero_stats = [
        {"label": "Students", "value": kpi_data["students"], "meta": "Active profiles"},
        {"label": "Subjects", "value": kpi_data["subjects"], "meta": "Catalog size"},
        {"label": "Report cards", "value": kpi_data["report_cards"], "meta": "Generated"},
        {"label": "Modules", "value": modules, "meta": "Registered apps"},
    ]
    hero = {
        "tagline": "Admin hub",
        "title": "Gilead School System Management",
        "subtitle": "Configure school apps, monitor health, and keep reports, finance, and portals aligned from one warm, modern dashboard.",
        "icon": "bi bi-pie-chart",
        "stats": hero_stats,
        "actions": [
            {"label": "Open parent portal", "url": reverse("portal:parent_dashboard")},
            {"label": "Backend config", "url": reverse("accounts:backend_dashboard")},
            {"label": "Frontend admin", "url": reverse("admin:index")},
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
        "finance_summary": finance_summary,
        "finance_trend": finance_trend,
        "finance_status_counts": finance_status_counts,
        "attendance_counts": attendance_counts,
        "attendance_trend": attendance_trend,
        "attended_today": attendance_today.count(),
        "reminders": reminders,
        "reminder_alerts": reminder_alerts,
        "compliance_profile": compliance_profile,
        "section_stats": section_stats,
        "can_manage_settings": can_manage_settings,
        "hero": hero,
        "app_list": app_context.get("available_apps", []),
    }
    return render(request, "accounts/backend_dashboard.html", context)


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
