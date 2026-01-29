from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.http import HttpResponseForbidden
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from django.utils.safestring import mark_safe
import json
from django_ratelimit.decorators import ratelimit
from config.admin import admin_site
from apps.finance.models import Invoice, ReferralReward, PaymentReminder, Notification as FinanceNotification
from apps.finance.services import finance_dashboard_data
from apps.portal.models import PendingGuardianInvite
from apps.people.models import StudentGuardian, StudentProfile, TeacherAttendance, TeacherProfile
from apps.academics.models import AcademicYear, Classroom
from apps.reports.models import TermPublishStatus
from apps.siteconfig.models import SiteSettings
from apps.academics.services import get_active_year_and_term
from apps.portal.services import link_guardian_via_invite
from apps.accounts.decorators import permission_required
from apps.siteconfig.templatetags.admin_health import admin_section_stats
from apps.siteconfig.templatetags.admin_kpis import admin_kpis
from apps.siteconfig.models_dashboard import get_dashboard_widget_metadata
from apps.siteconfig.dashboard_views import load_dashboard_layout_settings

from .forms import ClaimInviteAccountForm, PermissionForm, RoleForm, UserPermissionForm, UserRoleForm
from .models import AccessRole, Permission, User


def _notify_new_direct_message(sender, recipient, message):
    """Create an in-app notification for the recipient of a direct message."""
    try:
        msg_preview = (message.body or message.subject or "")[:200]
        if len((message.body or "") or (message.subject or "")) > 200:
            msg_preview += "..."
        link = reverse("accounts:direct_thread", args=[sender.pk])
        FinanceNotification.objects.create(
            recipient=recipient,
            created_by=sender,
            title=f"New message from {sender.get_full_name() or sender.username}",
            message=msg_preview,
            link=link,
        )
    except Exception:
        pass


@login_required
def user_profile(request):
    """Lightweight profile landing page for any authenticated user (RBAC-safe)."""
    return render(request, "accounts/profile.html", {})


@login_required
def user_notifications(request):
    """User notifications landing page (RBAC-safe)."""
    from apps.finance.models import Notification
    from django.db.models import Q

    base_qs = Notification.objects.filter(
        Q(recipient=request.user) | Q(created_by=request.user)
    ).order_by("-created_at")

    # Stats from full queryset before slicing
    total_count = base_qs.count()
    unread_count = base_qs.filter(is_read=False).count()
    read_count = base_qs.filter(is_read=True).count()

    # Filter by status if requested, then slice for display
    status_filter = request.GET.get("status")
    if status_filter == "unread":
        notifications = base_qs.filter(is_read=False)[:50]
    elif status_filter == "read":
        notifications = base_qs.filter(is_read=True)[:50]
    else:
        notifications = base_qs[:50]

    context = {
        "notifications": notifications,
        "total_count": total_count,
        "unread_count": unread_count,
        "read_count": read_count,
        "status_filter": status_filter,
    }

    return render(request, "accounts/notifications.html", context)


def _direct_conversations(user, limit=50):
    """Build list of 1-on-1 conversations for the Messages hub (Direct tab)."""
    from apps.communication.models import Message

    # All messages where user is sender or recipient (exclude archived for listing)
    qs = Message.objects.filter(
        Q(sender=user) | Q(recipient=user)
    ).filter(is_archived=False).select_related("sender", "recipient").order_by("-created_at")

    # Collect distinct other users and latest message per conversation
    seen_other_ids = set()
    conversations = []
    for msg in qs:
        other = msg.recipient if msg.sender_id == user.id else msg.sender
        if other.id in seen_other_ids:
            continue
        seen_other_ids.add(other.id)
        # Unread count: messages from other to me that I haven't read
        unread_count = Message.objects.filter(
            sender=other, recipient=user, is_read=False, is_archived=False
        ).count()
        conversations.append({
            "other_user": other,
            "last_message": msg,
            "last_message_at": msg.created_at,
            "unread_count": unread_count,
            "snippet": (msg.body or msg.subject or "")[:120],
        })
        if len(conversations) >= limit:
            break
    return conversations


@login_required
def user_messages(request):
    """Messages hub: Direct (1-on-1) and Groups tabs (RBAC-safe)."""
    from apps.portal.services import threads_for_user

    active_tab = request.GET.get("tab", "groups")
    threads = threads_for_user(request.user, limit=12)
    direct_list = _direct_conversations(request.user)

    context = {
        "threads": threads,
        "direct_conversations": direct_list,
        "active_tab": active_tab,
    }
    return render(request, "accounts/messages.html", context)


@login_required
def direct_thread(request, user_id):
    """View 1-on-1 thread with another user; GET: show messages, POST: send reply. Mark received as read."""
    from apps.communication.models import Message

    User = request.user.__class__
    other = User.objects.filter(pk=user_id).select_related().first()
    if not other or other.pk == request.user.pk:
        return redirect("accounts:user_messages")

    # All messages between me and other (either direction), ordered by created_at
    messages_qs = Message.objects.filter(
        Q(sender=request.user, recipient=other) | Q(sender=other, recipient=request.user)
    ).filter(is_archived=False).select_related("sender", "recipient").order_by("created_at")

    if request.method == "POST":
        body = (request.POST.get("body") or "").strip()
        subject = (request.POST.get("subject") or "").strip() or "Direct message"
        if body:
            msg = Message.objects.create(
                sender=request.user,
                recipient=other,
                subject=subject,
                body=body,
            )
            _notify_new_direct_message(request.user, other, msg)
            # Mark messages from other to me as read when I reply
            Message.objects.filter(sender=other, recipient=request.user, is_read=False).update(is_read=True)
            return redirect("accounts:direct_thread", user_id=other.pk)

    # Mark received messages as read when opening thread
    Message.objects.filter(sender=other, recipient=request.user, is_read=False).update(is_read=True)

    context = {
        "other_user": other,
        "messages": list(messages_qs),
    }
    return render(request, "accounts/direct_thread.html", context)


@login_required
def direct_compose(request):
    """Start a new direct message: pick recipient and send (GET: form, POST: create and redirect to thread)."""
    from apps.communication.models import Message
    from django.contrib.auth import get_user_model

    User = get_user_model()
    if request.method == "POST":
        recipient_id = request.POST.get("recipient")
        body = (request.POST.get("body") or "").strip()
        subject = (request.POST.get("subject") or "").strip() or "Direct message"
        if not body or not recipient_id:
            return redirect("accounts:direct_compose")
        recipient = User.objects.filter(pk=recipient_id, is_active=True).exclude(pk=request.user.pk).first()
        if not recipient:
            return redirect("accounts:direct_compose")
        Message.objects.create(sender=request.user, recipient=recipient, subject=subject, body=body)
        return redirect("accounts:direct_thread", user_id=recipient.pk)

    # GET: list active users (exclude self) for recipient dropdown
    recipients = User.objects.filter(is_active=True).exclude(pk=request.user.pk).order_by("first_name", "last_name").values("id", "first_name", "last_name", "username")
    context = {"recipients": list(recipients)}
    return render(request, "accounts/direct_compose.html", context)


@login_required
def user_documentation(request):
    """Shortcut to role-appropriate documentation/help (RBAC-safe)."""
    return render(request, "accounts/documentation.html", {})


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

    # Respect the user's "Dashboard view" preference (Portal Preferences) when possible.
    dash_view = None
    try:
        from apps.siteconfig.models import UserPreference as PortalUserPreference

        pref = PortalUserPreference.objects.filter(user=user).only("dashboard_view").first()
        dash_view = getattr(pref, "dashboard_view", None)
    except Exception:
        dash_view = None

    role = getattr(user, "role", None)
    if role == "TEACHER":
        # Teacher dashboard is the primary hub; we don't route away, but the preference can
        # be used for in-page emphasis later.
        return redirect("evals:teacher_dashboard")
    if role == "PARENT":
        if dash_view == "FINANCE":
            return redirect("portal:parent_finance")
        if dash_view == "ACADEMICS":
            return redirect("portal:parent_performance")
        if dash_view == "ATTENDANCE":
            return redirect("portal:parent_dashboard")  # attendance is a section on the dashboard
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
    
    # Certification/GCE stats (if enabled for active year)
    certification_stats = {}
    if year and getattr(year, "enable_gce_registration", False):
        from apps.academics.models import CertificationExamSession, CertificationCandidate
        active_sessions = CertificationExamSession.objects.filter(academic_year=year, is_active=True)
        total_candidates = CertificationCandidate.objects.filter(session__academic_year=year).count()
        draft_candidates = CertificationCandidate.objects.filter(session__academic_year=year, status="DRAFT").count()
        verified_candidates = CertificationCandidate.objects.filter(session__academic_year=year, status="VERIFIED").count()
        certification_stats = {
            "active_sessions": active_sessions.count(),
            "total_candidates": total_candidates,
            "draft_candidates": draft_candidates,
            "verified_candidates": verified_candidates,
            "sessions": active_sessions[:3],  # Recent sessions for quick access
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

    finance_access_banner = {
        "text": "Finance dashboards highlight overdue invoices and fee reminders.",
        "summary": f"{stats['overdue_invoices']} overdue invoices tracked.",
        "level": "info",
        "request_url": None,
        "cta": None,
    }

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
    role_upper = (getattr(request.user, "role", "") or "").upper()
    admin_like = bool(request.user.is_superuser or role_upper in {User.Role.ADMIN, User.Role.SUPERADMIN})
    can_manage_settings = admin_like and request.user.has_feature_permission("settings.manage")

    # Simple role-based action flags for UI gating (defensive guard in template too)
    action_perms = {
        "people": bool(role_upper in {User.Role.ADMIN, User.Role.LEADERSHIP, User.Role.IT_ADMIN, User.Role.SUPERADMIN} or request.user.is_superuser),
        "finance": bool(role_upper in {
            User.Role.ADMIN,
            User.Role.LEADERSHIP,
            User.Role.IT_ADMIN,
            User.Role.BURSAR,
            User.Role.SUPERADMIN,
        } or request.user.is_superuser),
        "site_settings": bool(can_manage_settings),
        "admin_panel": bool(request.user.is_staff or request.user.is_superuser or role_upper in {User.Role.ADMIN, User.Role.IT_ADMIN}),
    }

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
    allow_custom_layout = bool(
        request.user.is_authenticated
        and (
            request.user.is_staff
            or request.user.is_superuser
            or role_upper in {"ADMIN", "LEADERSHIP", "IT_ADMIN", "TEACHER", "PARENT"}
        )
    )
    dashboard_settings = load_dashboard_layout_settings(request.user, "backend")
    def _safe_reverse(name, default="#", kwargs=None):
        try:
            return reverse(name, kwargs=kwargs)
        except Exception:
            return default
    
    portal_cfg = getattr(site, "portal_features", {}) or {}
    has_docs = bool(portal_cfg.get("documents"))

    def _item(item_id, label, url_name=None, *, url=None, icon="bi-circle", allow=True, kwargs=None):
        """Build a sidebar/shortcut item, dropping unresolved links."""
        if not allow:
            return None
        final_url = url if url is not None else _safe_reverse(url_name, kwargs=kwargs)
        if not final_url or final_url == "#":
            return None
        return {"id": item_id, "label": label, "url": final_url, "icon": icon}

    available_sidebar_items = [
        _item("backend", "Backend Console", "accounts:backend_dashboard", icon="bi-speedometer2"),
        _item("workflow", "Workflow Center", "accounts:workflow_center", icon="bi-diagram-3", allow=bool(action_perms.get("site_settings"))),
        _item("messages", "Messages", "accounts:user_messages", icon="bi-chat-dots"),
        _item(
            "notifications",
            "Notifications",
            "accounts:user_notifications",
            icon="bi-bell",
        ),
        _item(
            "groups",
            "Message Groups",
            "communication:group_list",
            icon="bi-people",
            allow=bool(role_upper in {User.Role.TEACHER, User.Role.ADMIN, User.Role.LEADERSHIP, User.Role.IT_ADMIN, User.Role.SUPERADMIN} or request.user.is_staff or request.user.is_superuser),
        ),
        _item(
            "announcements",
            "Announcements",
            "communication:announcement_create",
            icon="bi-megaphone",
            allow=bool(role_upper in {User.Role.ADMIN, User.Role.LEADERSHIP, User.Role.IT_ADMIN, User.Role.SUPERADMIN} or request.user.is_staff or request.user.is_superuser),
        ),
        _item("reports", "Publish Results", "reports:publish_term_results", icon="bi-award", allow=bool(action_perms.get("people"))),
        _item("report_builder", "Report Card Builder", "siteconfig:reportcard_builder", icon="bi-file-earmark-richtext", allow=bool(action_perms.get("people"))),
        _item("report_library", "Report Library", "siteconfig:report_library", icon="bi-journal-text", allow=bool(action_perms.get("people"))),
        _item("certification", "Certification & Exams", "accounts:certification_home", icon="bi-award", allow=bool(year and getattr(year, "enable_gce_registration", False) if year else False)),
        _item("finance", "Finance Dashboard", "finance:dashboard", icon="bi-cash-stack", allow=bool(action_perms.get("finance"))),
        _item("documents", "Document Library", "portal:document_library_manage", icon="bi-file-earmark-text", allow=bool(action_perms.get("site_settings") or admin_like)),
        _item("signatures", "Signature Requests", "portal:signature_requests_manage", icon="bi-pen", allow=bool(action_perms.get("site_settings") or admin_like)),
        _item("documents_portal", "Public Documents", "portal:portal_feature", kwargs={"feature": "documents"}, icon="bi-folder-open", allow=has_docs),
        _item("customizer", "Customizer", "siteconfig:customizer", icon="bi-palette", allow=bool(action_perms.get("site_settings") or admin_like)),
        _item("portal", "Parent Portal", "portal:parent_dashboard", icon="bi-people"),
        _item("preferences", "Preferences", "siteconfig:user_preferences", icon="bi-sliders"),
        _item("kb", "Help Center", "kb:kb_home", icon="bi-life-preserver"),
        _item("admin", "Admin Panel", "admin:index", icon="bi-grid", allow=bool(action_perms.get("admin_panel"))),
    ]
    available_sidebar_items = [item for item in available_sidebar_items if item]
    from .sidebar_organizer import organize_sidebar_items, get_sidebar_category_labels
    organized_sidebar = organize_sidebar_items(available_sidebar_items, request.user)
    sidebar_categories = get_sidebar_category_labels()
    dashboard_layout_url = reverse("api:dashboard-layout", kwargs={"page": "backend"})
    finance_requests_qs = FinanceNotification.objects.filter(
        recipient=request.user,
        title__icontains="finance access request",
        is_read=False,
    ).order_by("-created_at")
    try:
        finance_request_link = reverse("requests:dashboard")
    except NoReverseMatch:
        finance_request_link = f"{reverse('accounts:user_messages')}?subject=finance+access+request"

    try:
        from apps.people.views_backend import backend_student_create  # noqa: F401
        use_backend_people_ui = True
    except ImportError:
        use_backend_people_ui = False

    # Workflow progress and recommended next steps for dashboard
    workflow_progress = _workflow_progress(year)
    recommended_next_steps = []
    try:
        if not year:
            recommended_next_steps.append({"label": "Set up academic year", "url": reverse("admin:academics_academicyear_changelist"), "icon": "bi-calendar-event"})
        else:
            if workflow_progress.get("classrooms", 0) == 0:
                recommended_next_steps.append({"label": "Create classrooms", "url": reverse("admin:academics_classroom_changelist"), "icon": "bi-door-open"})
            if workflow_progress.get("students", 0) == 0:
                try:
                    recommended_next_steps.append({"label": "Add student", "url": reverse("accounts:backend_student_create"), "icon": "bi-person-plus"})
                except Exception:
                    recommended_next_steps.append({"label": "Add student", "url": reverse("admin:people_studentprofile_add"), "icon": "bi-person-plus"})
            if workflow_progress.get("teachers", 0) == 0:
                try:
                    recommended_next_steps.append({"label": "Add teacher", "url": reverse("accounts:backend_teacher_create"), "icon": "bi-person-badge"})
                except Exception:
                    recommended_next_steps.append({"label": "Add teacher", "url": reverse("admin:people_teacherprofile_add"), "icon": "bi-person-badge"})
        if not recommended_next_steps:
            recommended_next_steps.append({"label": "Workflow Center", "url": reverse("accounts:workflow_center"), "icon": "bi-diagram-3"})
            recommended_next_steps.append({"label": "Publish results", "url": reverse("reports:publish_term_results"), "icon": "bi-award"})
    except Exception:
        recommended_next_steps = [{"label": "Workflow Center", "url": reverse("accounts:workflow_center"), "icon": "bi-diagram-3"}]
    context = {
        "site": site,
        "stats": stats,
        "workflow_progress": workflow_progress,
        "recommended_next_steps": recommended_next_steps,
        "use_backend_people_ui": use_backend_people_ui,
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
        "action_perms": action_perms,
        "show_request_settings_access": not action_perms["site_settings"],
        "ai_insight": ai_insight,
        "social_links": site.active_social_links,
        "avg_weekly_present": avg_weekly_present,
        "hero": hero,
        "app_list": app_context.get("available_apps", []),
        "allow_custom_layout": allow_custom_layout,
        "dashboard_settings": dashboard_settings,
        "dashboard_layout_url": dashboard_layout_url,
        "available_sidebar_items": available_sidebar_items,
        "organized_sidebar": organized_sidebar,
        "sidebar_categories": sidebar_categories,
        "widget_meta_json": mark_safe(json.dumps(get_dashboard_widget_metadata())),
        "finance_requests_count": finance_requests_qs.count(),
        "finance_request_notifications": finance_requests_qs[:5],
        "finance_request_link": finance_request_link,
        "finance_access_banner": finance_access_banner,
        "certification_stats": certification_stats,
        "gce_enabled": year and getattr(year, "enable_gce_registration", False) if year else False,
        "breadcrumbs": [{"title": "Backend", "url": reverse("accounts:backend_dashboard"), "icon": "bi-speedometer2"}],
        "BREADCRUMBS": [
            {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
            {"label": "Dashboard", "url": "", "active": True},
        ],
    }
    return render(request, "accounts/backend_dashboard.html", context)


def _workflow_progress(year):
    """Compute workflow progress stats for the active year (counts for progress indicators)."""
    if not year:
        return {}
    try:
        classrooms = Classroom.objects.filter(academic_year=year, is_active=True).count()
        students = StudentProfile.objects.filter(academic_year=year, is_active=True).count()
        teachers = TeacherProfile.objects.filter(is_active=True).count()
        return {
            "classrooms": classrooms,
            "students": students,
            "teachers": teachers,
            "has_year_setup": bool(year),
            "has_classrooms": classrooms > 0,
            "has_students": students > 0,
            "has_teachers": teachers > 0,
        }
    except Exception:
        return {}


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def workflow_center(request):
    """
    Operator-friendly entry point to the end-to-end school workflow.
    Keeps admins out of scattered menus and makes the Cameroon-first lifecycle discoverable.
    """
    site = SiteSettings.get_solo()
    year, term = get_active_year_and_term()
    progress = _workflow_progress(year)

    # Prefer backend UI links where available (user-friendly), fallback to admin
    try:
        student_list_url = reverse("accounts:backend_student_list")
        student_create_url = reverse("accounts:backend_student_create")
        teacher_list_url = reverse("accounts:backend_teacher_list")
        teacher_create_url = reverse("accounts:backend_teacher_create")
    except Exception:
        student_list_url = reverse("admin:people_studentprofile_changelist")
        student_create_url = reverse("admin:people_studentprofile_add")
        teacher_list_url = reverse("admin:people_teacherprofile_changelist")
        teacher_create_url = reverse("admin:people_teacherprofile_add")

    steps = [
        {
            "title": "1) Year setup",
            "subtitle": "Academic year, terms, classrooms, departments, specialties.",
            "step_key": "year_setup",
            "progress_label": f"{progress.get('classrooms', 0)} classrooms" if year else "Set active year",
            "links": [
                {"label": "Academic years", "url": reverse("admin:academics_academicyear_changelist")},
                {"label": "Terms", "url": reverse("admin:academics_term_changelist")},
                {"label": "Classrooms", "url": reverse("admin:academics_classroom_changelist")},
                {"label": "Departments", "url": reverse("admin:academics_department_changelist")},
                {"label": "Specialties", "url": reverse("admin:academics_specialty_changelist")},
                {"label": "Subjects", "url": reverse("admin:academics_subject_changelist")},
            ],
        },
        {
            "title": "2) Onboarding",
            "subtitle": "Enroll students/teachers and link parents.",
            "step_key": "onboarding",
            "progress_label": f"{progress.get('students', 0)} students, {progress.get('teachers', 0)} teachers",
            "links": [
                {"label": "Add student", "url": student_create_url, "primary": True},
                {"label": "Add teacher", "url": teacher_create_url, "primary": True},
                {"label": "Student list", "url": student_list_url},
                {"label": "Onboard student (wizard)", "url": reverse("portal:student_onboarding")},
                {"label": "Onboard teacher (wizard)", "url": reverse("portal:teacher_onboarding")},
                {"label": "Guardian invites", "url": reverse("admin:portal_pendingguardianinvite_changelist")},
                {"label": "Student profiles (admin)", "url": reverse("admin:people_studentprofile_changelist")},
            ],
        },
        {
            "title": "3) Marks entry + OCR",
            "subtitle": "Enter marks, upload marksheets, review OCR, submit for approval.",
            "step_key": "marks",
            "progress_label": None,
            "links": [
                {"label": "Teacher marks entry", "url": reverse("evals:teacher_marks_entry")},
                {"label": "Marks history", "url": reverse("evals:teacher_marks_list")},
                {"label": "Approval requests", "url": reverse("admin:evals_gradeapprovalrequest_changelist")},
            ],
        },
        {
            "title": "4) Publish reports",
            "subtitle": "Generate report cards and publish to parents safely.",
            "step_key": "reports",
            "progress_label": None,
            "links": [
                {"label": "Publish term results", "url": reverse("reports:publish_term_results")},
                {"label": "Report card builder", "url": reverse("siteconfig:reportcard_builder")},
                {"label": "Report library", "url": reverse("siteconfig:report_library")},
            ],
        },
        {
            "title": "5) Communication",
            "subtitle": "Groups, department chats, announcements, and parent contact requests.",
            "step_key": "communication",
            "progress_label": None,
            "links": [
                {"label": "Message groups", "url": reverse("communication:group_list")},
                {"label": "Create announcement", "url": reverse("communication:announcement_create")},
                {"label": "Parent contact requests", "url": reverse("portal:staff_contact_request_list")},
            ],
        },
        {
            "title": "5b) Documents & forms",
            "subtitle": "Document library, upload forms, and electronic signature requests.",
            "step_key": "documents",
            "progress_label": None,
            "links": [
                {"label": "Document library", "url": reverse("portal:document_library_manage")},
                {"label": "Signature requests", "url": reverse("portal:signature_requests_manage")},
                {"label": "Public documents", "url": reverse("portal:portal_feature", kwargs={"feature": "documents"})},
            ],
        },
        {
            "title": "6) Certification & GCE (optional)",
            "subtitle": "Enable per academic year. Manage candidates, deadlines, exports, and audit trail.",
            "step_key": "certification",
            "progress_label": None,
            "links": (
                [
                    {"label": "Certification Center", "url": reverse("accounts:certification_home")},
                    {"label": "Exam sessions", "url": reverse("admin:academics_certificationexamsession_changelist")},
                    {"label": "Candidates", "url": reverse("admin:academics_certificationcandidate_changelist")},
                    {"label": "Presets & Templates", "url": reverse("admin:academics_certificationexampreset_changelist")},
                    {"label": "Audit logs", "url": reverse("admin:academics_certificationauditlog_changelist")},
                ]
                if (year and getattr(year, "enable_gce_registration", False))
                else [
                    {"label": "Enable in Academic Year", "url": reverse("admin:academics_academicyear_changelist")},
                ]
            ),
        },
        {
            "title": "7) Settings & theme",
            "subtitle": "Site settings, preferences, preview/sandbox, and role access.",
            "step_key": "settings",
            "progress_label": None,
            "links": [
                {"label": "Site settings (admin)", "url": reverse("admin:siteconfig_sitesettings_change", args=(site.pk,))},
                {"label": "Preferences (operator UI)", "url": reverse("siteconfig:user_preferences")},
                {"label": "RBAC & access control", "url": reverse("accounts:rbac")},
            ],
        },
    ]

    return render(
        request,
        "accounts/workflow_center.html",
        {"site": site, "active_year": year, "active_term": term, "steps": steps, "workflow_progress": progress},
    )


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
