from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.shortcuts import redirect, render, get_object_or_404
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
from apps.academics.services_year_setup import clone_academic_year
from apps.portal.services import link_guardian_via_invite
from apps.accounts.decorators import permission_required
from apps.siteconfig.templatetags.admin_health import admin_section_stats
from apps.siteconfig.templatetags.admin_kpis import admin_kpis
from apps.siteconfig.models_dashboard import get_dashboard_widget_metadata, DashboardWidget
from apps.siteconfig.dashboard_views import effective_chart_types
from apps.accounts.utils import get_dashboard_context

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


def _teacher_org_tree(user):
    """Build org tree for teacher: department, reports_to, assignments (year -> classrooms -> subjects)."""
    try:
        from apps.people.models import TeacherProfile
        from apps.evals.models import TeacherAssignment
        from apps.academics.services import get_active_year_and_term
    except ImportError:
        return None
    teacher = TeacherProfile.objects.filter(user=user).select_related("department", "reports_to").first()
    if not teacher:
        return None
    year, _ = get_active_year_and_term()
    assignments = []
    if year:
        qs = TeacherAssignment.objects.filter(
            teacher=teacher,
            is_active=True,
            subject_assignment__academic_year=year,
        ).select_related(
            "subject_assignment__classroom",
            "subject_assignment__subject",
            "subject_assignment__academic_year",
        )
        # Group by classroom then subject
        by_class = {}
        for ta in qs:
            sa = ta.subject_assignment
            if not sa:
                continue
            cname = sa.classroom.name if sa.classroom else "—"
            if cname not in by_class:
                by_class[cname] = []
            by_class[cname].append(sa.subject.name if sa.subject else "—")
        assignments = [{"classroom": c, "subjects": list(set(subs))} for c, subs in sorted(by_class.items())]
    return {
        "teacher": teacher,
        "department": teacher.department,
        "reports_to": teacher.reports_to,
        "position_title": teacher.position_title or "—",
        "assignments": assignments,
        "academic_year": year,
    }


def _parent_children_tree(user):
    """Build tree of children linked to this parent (guardian)."""
    links = StudentGuardian.objects.filter(guardian_user=user).select_related(
        "student",
        "student__classroom",
        "student__classroom__academic_year",
    )
    children = []
    for link in links:
        s = link.student
        classroom = getattr(s, "classroom", None)
        class_name = classroom.name if classroom else "—"
        year_name = getattr(getattr(classroom, "academic_year", None), "name", "") or "—"
        children.append({
            "student": s,
            "relationship": link.get_relationship_display(),
            "classroom": class_name,
            "academic_year": year_name,
        })
    return {"children": children} if children else None


def _admin_context(user):
    """Build admin context for staff: Site Settings, Backend, Admin, RBAC URLs and permissions summary."""
    if not (user.is_staff or user.is_superuser):
        role = getattr(user, "role", None)
        if role not in ("ADMIN", "IT_ADMIN", "LEADERSHIP"):
            return None
    site_settings_url = None
    if getattr(user, "has_feature_permission", lambda _: False)("settings.manage"):
        try:
            site = SiteSettings.get_solo()
            site_settings_url = reverse("admin:siteconfig_sitesettings_change", args=[site.pk])
        except Exception:
            try:
                site_settings_url = reverse("admin:siteconfig_sitesettings_changelist")
            except NoReverseMatch:
                pass
    try:
        backend_url = reverse("accounts:backend_dashboard")
    except NoReverseMatch:
        backend_url = None
    try:
        admin_url = reverse("admin:index")
    except NoReverseMatch:
        admin_url = None
    try:
        rbac_url = reverse("accounts:rbac")
    except NoReverseMatch:
        rbac_url = None
    permissions_summary = []
    if hasattr(user, "feature_permissions"):
        for p in user.feature_permissions.all().values_list("code", flat=True):
            permissions_summary.append(p)
    if hasattr(user, "roles"):
        for role in user.roles.all().prefetch_related("permissions"):
            for p in role.permissions.all().values_list("code", flat=True):
                permissions_summary.append(p)
    permissions_summary = sorted(set(permissions_summary))[:20]  # cap for display
    return {
        "site_settings_url": site_settings_url,
        "backend_url": backend_url,
        "admin_url": admin_url,
        "rbac_url": rbac_url,
        "permissions_summary": permissions_summary,
    }


@login_required
def user_profile(request):
    """Profile landing: account overview, org tree (teacher), children tree (parent), change password & edit profile."""
    context = {}
    role = getattr(request.user, "role", None)
    if role == "TEACHER":
        context["teacher_org_tree"] = _teacher_org_tree(request.user)
    if role == "PARENT":
        context["parent_children_tree"] = _parent_children_tree(request.user)
    admin_ctx = _admin_context(request.user)
    if admin_ctx:
        context["admin_context"] = admin_ctx
    # MFA status (only when django_otp is available)
    try:
        from django_otp import user_has_device
        context["mfa_enabled"] = user_has_device(request.user)
    except Exception:
        pass
    # Optional teacher_pay_leave when payroll exposes data (e.g. next pay date, leave balance)
    # Parent upcoming fees summary when finance exposes it
    try:
        from apps.finance.services import get_parent_fees_summary
        parent_fees = get_parent_fees_summary(request.user)
        if parent_fees:
            context["parent_fees_summary"] = parent_fees
    except Exception:
        pass
    # Profile completion: photo + email + first_name + last_name (25% each)
    filled = []
    missing = []
    if request.user.profile_photo:
        filled.append("profile photo")
    else:
        missing.append("profile photo")
    if request.user.email and request.user.email.strip():
        filled.append("email")
    else:
        missing.append("email")
    if request.user.first_name and request.user.first_name.strip():
        filled.append("first name")
    else:
        missing.append("first name")
    if request.user.last_name and request.user.last_name.strip():
        filled.append("last name")
    else:
        missing.append("last name")
    percent = (len(filled) * 100) // 4
    context["profile_completion"] = {"percent": percent, "filled": filled, "missing": missing}
    # Active sessions count (for Security line)
    try:
        from django.contrib.sessions.models import Session
        from django.utils import timezone as tz

        now = tz.now()
        count = 0
        for session in Session.objects.filter(expire_date__gte=now)[:500]:
            data = session.get_decoded()
            if str(request.user.pk) == data.get("_auth_user_id"):
                count += 1
        context["active_sessions_count"] = count
    except Exception:
        context["active_sessions_count"] = None
    return render(request, "accounts/profile.html", context)


@login_required
def profile_edit(request):
    """Edit own profile: first name, last name, email, profile photo."""
    user = request.user
    from .forms import UserProfileEditForm

    if request.method == "POST":
        form = UserProfileEditForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:user_profile")
    else:
        form = UserProfileEditForm(instance=user)
    return render(request, "accounts/profile_edit.html", {"form": form})


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

    # One query: unread counts per sender (senders who messaged me and I haven't read)
    unread_by_sender = dict(
        Message.objects.filter(
            recipient=user, is_read=False, is_archived=False
        ).values("sender").annotate(cnt=Count("id")).values_list("sender", "cnt")
    )

    from apps.communication.models import DirectConversation

    # For parents: only show conversations with staff/teacher that are not closed
    is_parent = getattr(user, "role", None) == User.Role.PARENT

    seen_other_ids = set()
    conversations = []
    for msg in qs:
        other = msg.recipient if msg.sender_id == user.id else msg.sender
        if other.id in seen_other_ids:
            continue
        if is_parent:
            if getattr(other, "role", None) == User.Role.PARENT:
                continue
            if DirectConversation.is_closed(user, other):
                continue
        seen_other_ids.add(other.id)
        unread_count = unread_by_sender.get(other.id, 0)
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
    """Messages hub: Direct and Groups. Parents redirected to Contact School (RBAC)."""
    if getattr(request.user, "role", None) == User.Role.PARENT:
        return redirect(reverse("portal:parent_contact_school"))
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


def _is_staff_or_teacher(user):
    if getattr(user, "role", None) == User.Role.PARENT:
        return False
    return user.is_staff or user.is_superuser or getattr(user, "role", None) in (
        User.Role.ADMIN, User.Role.TEACHER, User.Role.LEADERSHIP,
        User.Role.PRINCIPAL, User.Role.VICE_PRINCIPAL, User.Role.DEPT_LEAD,
        User.Role.HOD, User.Role.SECRETARY, User.Role.BURSAR,
    )


@login_required
def direct_thread(request, user_id):
    """View 1-on-1 thread. Parents can only open threads with staff/teacher (to reply); staff can close the loop."""
    from apps.communication.models import Message, DirectConversation
    from django.utils import timezone

    User = request.user.__class__
    if user_id == request.user.pk:
        return redirect("accounts:user_messages")
    other = get_object_or_404(User.objects.filter(is_active=True), pk=user_id)

    other_is_parent = getattr(other, "role", None) == User.Role.PARENT
    i_am_parent = getattr(request.user, "role", None) == User.Role.PARENT

    # Parent can only chat with staff/teacher (reply to school); not with another parent
    if i_am_parent and other_is_parent:
        return redirect(reverse("portal:parent_contact_school"))

    # Staff–parent conversation record (only when one is parent, one is staff/teacher)
    conv = None
    if (i_am_parent and _is_staff_or_teacher(other)) or (other_is_parent and _is_staff_or_teacher(request.user)):
        conv = DirectConversation.get_or_create_for(request.user, other)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "close" and _is_staff_or_teacher(request.user) and other_is_parent and conv:
            conv.closed_at = timezone.now()
            conv.save(update_fields=["closed_at"])
            messages.success(request, "Conversation closed. Parent can no longer reply.")
            return redirect("accounts:user_messages")
        body = (request.POST.get("body") or "").strip()
        subject = (request.POST.get("subject") or "").strip() or "Direct message"
        if body:
            if conv and conv.closed_at:
                messages.error(request, "This conversation is closed.")
            else:
                msg = Message.objects.create(
                    sender=request.user,
                    recipient=other,
                    subject=subject,
                    body=body,
                )
                _notify_new_direct_message(request.user, other, msg)
                Message.objects.filter(sender=other, recipient=request.user, is_read=False).update(is_read=True)
            return redirect("accounts:direct_thread", user_id=other.pk)

    messages_qs = Message.objects.filter(
        Q(sender=request.user, recipient=other) | Q(sender=other, recipient=request.user)
    ).filter(is_archived=False).select_related("sender", "recipient").order_by("created_at")

    Message.objects.filter(sender=other, recipient=request.user, is_read=False).update(is_read=True)

    conversation_closed = conv.closed_at if conv else False
    can_close = _is_staff_or_teacher(request.user) and other_is_parent and conv and not conv.closed_at
    can_reply = not conversation_closed

    context = {
        "other_user": other,
        "messages": list(messages_qs),
        "conversation_closed": conversation_closed,
        "can_close": can_close,
        "can_reply": can_reply,
    }
    return render(request, "accounts/direct_thread.html", context)


@login_required
def direct_compose(request):
    """Start a new direct message; staff/teacher only; parents use Contact School (RBAC)."""
    if getattr(request.user, "role", None) == User.Role.PARENT:
        return redirect(reverse("portal:parent_contact_school"))
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
        from apps.communication.models import DirectConversation
        if getattr(recipient, "role", None) == User.Role.PARENT and _is_staff_or_teacher(request.user):
            DirectConversation.get_or_create_for(request.user, recipient)
        msg = Message.objects.create(sender=request.user, recipient=recipient, subject=subject, body=body)
        _notify_new_direct_message(request.user, recipient, msg)
        return redirect("accounts:direct_thread", user_id=recipient.pk)

    # GET: list active users (exclude self) for recipient dropdown; limit for large schools
    recipients = (
        User.objects.filter(is_active=True)
        .exclude(pk=request.user.pk)
        .order_by("first_name", "last_name")
        .values("id", "first_name", "last_name", "username")[:500]
    )
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
    prevents hard-coded URLs from drifting. Respects "Dashboard view" preference
    (Overview, Workflow Center, Finance, etc.) for backend, teacher, and parent.
    Preserves GET params (e.g. preview_section for config preview) on the target URL.
    """
    user = request.user
    if not user.is_authenticated:
        return redirect(reverse("accounts:login"))

    def _redirect_with_params(name_or_url, *args, **kwargs):
        target = reverse(name_or_url, args=args, kwargs=kwargs)
        if request.GET:
            target += "?" if "?" not in target else "&"
            target += request.GET.urlencode()
        return redirect(target)

    # Respect the user's "Dashboard view" preference (Portal Preferences) when possible.
    dash_view = None
    try:
        from apps.siteconfig.models import UserPreference as PortalUserPreference

        pref = PortalUserPreference.objects.filter(user=user).only("dashboard_view").first()
        dash_view = getattr(pref, "dashboard_view", None)
    except Exception:
        dash_view = None

    role = getattr(user, "role", None)

    # Staff/backend: Dashboard or Workflow Center as default view
    if user.has_feature_permission("settings.manage"):
        if dash_view == "WORKFLOW":
            return _redirect_with_params("accounts:workflow_center")
        return _redirect_with_params("accounts:backend_dashboard")

    if role == "TEACHER":
        if dash_view == "WORKFLOW":
            return _redirect_with_params("portal:teacher_workflow")
        return _redirect_with_params("evals:teacher_dashboard")
    if role == "PARENT":
        if dash_view == "WORKFLOW":
            return _redirect_with_params("portal:parent_workflow")
        if dash_view == "FINANCE":
            return _redirect_with_params("portal:parent_finance")
        if dash_view == "ACADEMICS":
            return _redirect_with_params("portal:parent_performance")
        if dash_view == "ATTENDANCE":
            return _redirect_with_params("portal:parent_dashboard")
        return _redirect_with_params("portal:parent_dashboard")

    # Default: admin
    return _redirect_with_params("admin:index")


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
    dashboard_context = get_dashboard_context(request.user, "backend")
    allow_custom_layout = dashboard_context.get("allow_custom_layout", False)
    dashboard_settings = dashboard_context.get("dashboard_settings", {})
    dashboard_layout_url = dashboard_context.get("dashboard_layout_url", "")
    widget_meta_json = dashboard_context.get("widget_meta_json", "")
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
        _item("bulk_letters", "Bulk Letters", "siteconfig:bulk_letters", icon="bi-envelope-paper", allow=bool(action_perms.get("people"))),
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

    # Chart JSON for dashboard visualizations
    chart_finance_status_json = ""
    chart_finance_trend_json = ""
    chart_attendance_donut_json = ""
    chart_rbac_roles_json = ""
    if compliance_profile and finance_status_counts:
        status_labels = dict(Invoice.Status.choices)
        chart_finance_status_json = json.dumps({
            "type": "doughnut",
            "data": {
                "labels": [status_labels.get(sc["status"], sc["status"]) for sc in finance_status_counts],
                "datasets": [{
                    "data": [sc["count"] for sc in finance_status_counts],
                    "backgroundColor": ["#6c757d", "#0d6efd", "#ffc107", "#198754", "#dc3545", "#adb5bd"][: len(finance_status_counts)],
                }],
            },
        })
    if finance_trend:
        chart_finance_trend_json = json.dumps({
            "type": "line",
            "data": {
                "labels": [t["label"] for t in finance_trend],
                "datasets": [{
                    "label": "Invoice total",
                    "data": [float(t.get("total", 0)) for t in finance_trend],
                    "fill": True,
                    "borderColor": "#0d6efd",
                    "backgroundColor": "rgba(13, 110, 253, 0.15)",
                    "tension": 0.3,
                }],
            },
        })
    if attendance_counts:
        labels = list(attendance_counts.keys())
        counts = list(attendance_counts.values())
        chart_attendance_donut_json = json.dumps({
            "type": "doughnut",
            "data": {
                "labels": labels,
                "datasets": [{
                    "data": counts,
                    "backgroundColor": ["#198754", "#ffc107", "#dc3545", "#6c757d", "#0d6efd"][: len(labels)],
                }],
            },
        })
    roles_qs = AccessRole.objects.prefetch_related("permissions", "users").order_by("code")
    role_user_counts = {r.code: r.users.count() for r in roles_qs}
    if role_user_counts:
        chart_rbac_roles_json = json.dumps({
            "type": "bar",
            "data": {
                "labels": list(role_user_counts.keys()),
                "datasets": [{
                    "label": "Users",
                    "data": list(role_user_counts.values()),
                    "backgroundColor": "rgba(13, 110, 253, 0.8)",
                    "borderColor": "#0d6efd",
                    "borderWidth": 1,
                }],
            },
            "options": {"indexAxis": "y"},
        })

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
        "dashboard_stats_cards": [],  # Suppress portal_base stats block; backend has its own
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
        "widget_meta_json": widget_meta_json,
        "widget_chart_types_json": mark_safe(
            json.dumps(effective_chart_types(request.user, "backend"))
        ),
        "finance_requests_count": finance_requests_qs.count(),
        "finance_request_notifications": finance_requests_qs[:5],
        "finance_request_link": finance_request_link,
        "finance_access_banner": finance_access_banner,
        "certification_stats": certification_stats,
        "gce_enabled": year and getattr(year, "enable_gce_registration", False) if year else False,
        "chart_finance_status_json": chart_finance_status_json,
        "chart_finance_trend_json": chart_finance_trend_json,
        "chart_attendance_donut_json": chart_attendance_donut_json,
        "chart_rbac_roles_json": chart_rbac_roles_json,
        "quick_student_create_url": _safe_reverse("accounts:backend_student_create") if _safe_reverse("accounts:backend_student_create") != "#" else _safe_reverse("admin:people_studentprofile_add"),
        "quick_teacher_create_url": _safe_reverse("accounts:backend_teacher_create") if _safe_reverse("accounts:backend_teacher_create") != "#" else _safe_reverse("admin:people_teacherprofile_add"),
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


def _workflow_link(label, url_name, primary=False, args=None, kwargs=None):
    """Build a workflow step link; return None if URL resolution fails so the button is skipped."""
    try:
        url = reverse(url_name, args=args or (), kwargs=kwargs or {})
        return {"label": label, "url": url, "primary": primary} if primary else {"label": label, "url": url}
    except NoReverseMatch:
        return None


def _can_access_approval_hub(user):
    """Staff roles that can access approval workflows."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    role = (getattr(user, "role", "") or "").upper()
    return role in {
        "ADMIN", "LEADERSHIP", "IT_ADMIN", "PRINCIPAL", "VICE_PRINCIPAL",
        "DEAN", "BURSAR", "FINANCE_STAFF", "ACADEMICS_STAFF", "COMMS_STAFF",
    }


@login_required
@user_passes_test(_can_access_approval_hub)
def approval_workflow_hub(request):
    """Hub linking to Grade Approvals, Access Requests, Contact Requests."""
    return render(request, "accounts/approval_workflow_hub.html", {
        "BREADCRUMBS": [
            {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
            {"label": "Approval Hub", "url": "", "active": True},
        ],
    })


@login_required
@user_passes_test(_is_admin_user)
def automation_hub(request):
    """Single place for automation: execution log, approval queue, and links to configure schedules (Site Settings)."""
    execution_log_url = approval_queue_url = site_settings_url = None
    try:
        execution_log_url = reverse("admin:automation_automationexecutionlog_changelist")
    except NoReverseMatch:
        pass
    try:
        approval_queue_url = reverse("admin:automation_automationapprovalqueue_changelist")
    except NoReverseMatch:
        pass
    try:
        site = SiteSettings.get_solo()
        site_settings_url = reverse("admin:siteconfig_sitesettings_change", args=[site.pk])
    except Exception:
        pass
    return render(request, "accounts/automation_hub.html", {
        "BREADCRUMBS": [
            {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
            {"label": "Workflow Center", "url": reverse("accounts:workflow_center")},
            {"label": "Automation", "url": "", "active": True},
        ],
        "execution_log_url": execution_log_url,
        "approval_queue_url": approval_queue_url,
        "site_settings_url": site_settings_url,
    })


@login_required
@user_passes_test(_is_admin_user)
def import_hub(request):
    """Hub linking to Entity Import, Grade Import, templates."""
    return render(request, "accounts/import_hub.html", {
        "BREADCRUMBS": [
            {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
            {"label": "Import Hub", "url": "", "active": True},
        ],
    })


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def workflow_center(request):
    """
    Operator-friendly entry point to the end-to-end school workflow.
    Keeps admins out of scattered menus and makes the Cameroon-first lifecycle discoverable.
    Every link is resolved defensively so one broken URL does not 500 the page.
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

    # Build links defensively: only include links that resolve
    year_setup_links = [
        _workflow_link("Clone previous year", "accounts:clone_year_setup"),
        _workflow_link("Promotion mapping (next class)", "admin:academics_classroompromotionmapping_changelist"),
        _workflow_link("Academic years", "admin:academics_academicyear_changelist"),
        _workflow_link("Terms", "admin:academics_term_changelist"),
        _workflow_link("Classrooms", "admin:academics_classroom_changelist"),
        _workflow_link("Departments", "admin:academics_department_changelist"),
        _workflow_link("Specialties", "admin:academics_specialty_changelist"),
        _workflow_link("Subjects", "admin:academics_subject_changelist"),
    ]
    onboarding_links = [
        {"label": "Add student", "url": student_create_url, "primary": True},
        {"label": "Add teacher", "url": teacher_create_url, "primary": True},
        {"label": "Student list", "url": student_list_url},
        _workflow_link("Onboard student (wizard)", "portal:student_onboarding"),
        _workflow_link("Onboard teacher (wizard)", "portal:teacher_onboarding"),
        _workflow_link("Guardian invites", "admin:portal_pendingguardianinvite_changelist"),
        _workflow_link("Student profiles (admin)", "admin:people_studentprofile_changelist"),
    ]
    marks_links = [
        _workflow_link("Teacher marks entry", "evals:teacher_marks_entry"),
        _workflow_link("Marks history", "evals:teacher_marks_list"),
        _workflow_link("Approval requests", "admin:evals_gradeapprovalrequest_changelist"),
    ]
    reports_links = [
        _workflow_link("Publish term results", "reports:publish_term_results"),
        _workflow_link("Year-end rollover", "accounts:rollover_year"),
        _workflow_link("Statistical return", "reports:statistical_return"),
        _workflow_link("Promotion preview (borderline)", "reports:promotion_preview"),
        _workflow_link("Resource return checklist", "admin:people_studentresourcereturn_changelist"),
        _workflow_link("Report card builder", "siteconfig:reportcard_builder"),
        _workflow_link("Report library", "siteconfig:report_library"),
    ]
    communication_links = [
        _workflow_link("Message groups", "communication:group_list"),
        _workflow_link("Create announcement", "communication:announcement_create"),
        _workflow_link("Parent contact requests", "portal:staff_contact_request_list"),
        _workflow_link("Absence alert (Site settings)", "admin:siteconfig_sitesettings_change", args=(site.pk,)),
    ]
    documents_links = [
        _workflow_link("Document library", "portal:document_library_manage"),
        _workflow_link("Signature requests", "portal:signature_requests_manage"),
        _workflow_link("Public documents", "portal:portal_feature", kwargs={"feature": "documents"}),
    ]
    certification_links = (
        [
            _workflow_link("Certification Center", "accounts:certification_home"),
            _workflow_link("Exam sessions", "admin:academics_certificationexamsession_changelist"),
            _workflow_link("Candidates", "admin:academics_certificationcandidate_changelist"),
            _workflow_link("Presets & Templates", "admin:academics_certificationexampreset_changelist"),
            _workflow_link("Audit logs", "admin:academics_certificationauditlog_changelist"),
        ]
        if (year and getattr(year, "enable_gce_registration", False))
        else [_workflow_link("Enable in Academic Year", "admin:academics_academicyear_changelist")]
    )
    settings_links = [
        _workflow_link("Academic rules", "accounts:academic_rules"),
        _workflow_link("Site settings (admin)", "admin:siteconfig_sitesettings_change", args=(site.pk,)),
        _workflow_link("Preferences (operator UI)", "siteconfig:user_preferences"),
        _workflow_link("RBAC & access control", "accounts:rbac"),
    ]

    # Filter out any None links and ensure each step has at least an empty list
    def _filter_links(links):
        return [lnk for lnk in links if lnk is not None and lnk.get("url")]

    gce_enabled = year and getattr(year, "enable_gce_registration", False) if year else False

    steps = [
        {
            "title": "1) Year setup",
            "subtitle": "Academic year, terms, classrooms, departments, specialties.",
            "step_key": "year_setup",
            "icon": "bi-calendar3",
            "progress_label": f"{progress.get('classrooms', 0)} classrooms" if year else "Set active year",
            "tip": "Set the active academic year first; other steps use it for enrollment and reports.",
            "links": _filter_links(year_setup_links),
        },
        {
            "title": "2) Onboarding",
            "subtitle": "Enroll students/teachers and link parents.",
            "step_key": "onboarding",
            "icon": "bi-people",
            "progress_label": f"{progress.get('students', 0)} students, {progress.get('teachers', 0)} teachers",
            "tip": "Use the wizards for guided onboarding; invite guardians so parents can see reports.",
            "links": _filter_links(onboarding_links),
        },
        {
            "title": "3) Marks entry + OCR",
            "subtitle": "Enter marks, upload marksheets, review OCR, submit for approval.",
            "step_key": "marks",
            "icon": "bi-pencil-square",
            "progress_label": None,
            "tip": "Teachers enter marks; use approval requests for controlled release.",
            "links": _filter_links(marks_links),
        },
        {
            "title": "4) Publish reports",
            "subtitle": "Generate report cards and publish to parents safely.",
            "step_key": "reports",
            "icon": "bi-file-earmark-text",
            "progress_label": None,
            "tip": "Publish term results when marks are approved; parents see them in the portal.",
            "links": _filter_links(reports_links),
        },
        {
            "title": "5) Communication",
            "subtitle": "Groups, department chats, announcements, and parent contact requests.",
            "step_key": "communication",
            "icon": "bi-chat-dots",
            "progress_label": None,
            "tip": None,
            "links": _filter_links(communication_links),
        },
        {
            "title": "5b) Documents & forms",
            "subtitle": "Document library, upload forms, and electronic signature requests.",
            "step_key": "documents",
            "icon": "bi-folder2-open",
            "progress_label": None,
            "tip": None,
            "links": _filter_links(documents_links),
        },
        {
            "title": "6) Certification & exams (optional)",
            "subtitle": "General & technical: GCE, BAC, BEPC, CAP, etc. Enable per year; manage candidates, deadlines, exports.",
            "step_key": "certification",
            "icon": "bi-award",
            "progress_label": "Enabled" if gce_enabled else "Enable in Academic Year",
            "tip": "Designed for Cameroon general and technical education; adapt sessions to your subsystem (GCE, BAC, BEPC, CAP).",
            "links": _filter_links(certification_links),
        },
        {
            "title": "7) Settings & theme",
            "subtitle": "Site settings, preferences, preview/sandbox, and role access.",
            "step_key": "settings",
            "icon": "bi-gear",
            "progress_label": None,
            "tip": "RBAC controls who sees which dashboards; set theme and branding here.",
            "links": _filter_links(settings_links),
        },
        {
            "title": "8) Automation",
            "subtitle": "Execution log, approval queue, and schedule configuration (reminders, invoices, receipts).",
            "step_key": "automation",
            "icon": "bi-robot",
            "progress_label": None,
            "tip": "Use dry-run on tasks to preview; high-impact automations can require approval.",
            "links": _filter_links([
                _workflow_link("Automation hub", "accounts:automation_hub", primary=True),
            ]),
        },
    ]
    total_steps = len(steps)
    for i, s in enumerate(steps, start=1):
        s["step_index"] = i
        s["total_steps"] = total_steps

    return render(
        request,
        "accounts/workflow_center.html",
        {"site": site, "active_year": year, "active_term": term, "steps": steps, "workflow_progress": progress},
    )


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def clone_year_setup(request):
    """
    Clone structure from a previous academic year to a target year (terms, classrooms, subject assignments, promotion rules).
    Target year must already exist; create it in admin first if needed.
    """
    from apps.academics.models import AcademicYear

    years = list(AcademicYear.objects.all().order_by("-start_date"))
    if request.method == "POST":
        from django.views.decorators.http import require_http_methods

        source_id = request.POST.get("source_year")
        target_id = request.POST.get("target_year")
        if not source_id or not target_id:
            messages.error(request, "Please select both source and target year.")
            return render(request, "accounts/clone_year_setup.html", {"years": years})

        if source_id == target_id:
            messages.error(request, "Source and target year must be different.")
            return render(request, "accounts/clone_year_setup.html", {"years": years})

        source_year = get_object_or_404(AcademicYear, id=source_id)
        target_year = get_object_or_404(AcademicYear, id=target_id)
        try:
            stats = clone_academic_year(source_year, target_year)
            messages.success(
                request,
                f"Cloned {source_year.name} → {target_year.name}: "
                f"{stats['terms_created']} terms, {stats['classrooms_created']} classrooms, "
                f"{stats['subject_assignments_created']} subject assignments, {stats['promotion_rules_created']} promotion rules.",
            )
            return redirect("accounts:workflow_center")
        except Exception as e:
            messages.error(request, f"Clone failed: {e}")
            return render(request, "accounts/clone_year_setup.html", {"years": years})

    return render(request, "accounts/clone_year_setup.html", {"years": years})


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def rollover_year(request):
    """
    Year-end rollover: move students from source year to target year and assign next classroom.
    Uses promotion status to suggest next class; operator can override per student.
    Optionally lock the source year after rollover.
    """
    from apps.academics.models import AcademicYear, Classroom
    from apps.reports.services import (
        get_promotion_status,
        _annual_average_for_student,
        terms_for_student,
    )
    from apps.academics.models import Term

    years = list(AcademicYear.objects.all().order_by("-start_date"))
    if request.method == "POST":
        source_id = request.POST.get("source_year")
        target_id = request.POST.get("target_year")
        lock_source = request.POST.get("lock_source") == "on"
        notify_parents = request.POST.get("notify_parents") == "on"
        allow_outstanding_returns = request.POST.get("allow_outstanding_returns") == "on"
        if not source_id or not target_id:
            messages.error(request, "Please select both source and target year.")
            return render(request, "accounts/rollover_year.html", {"years": years})

        source_year = get_object_or_404(AcademicYear, id=source_id)
        target_year = get_object_or_404(AcademicYear, id=target_id)
        if getattr(source_year, "is_locked", False):
            messages.error(request, f"{source_year.name} is locked; rollover from this year is not allowed.")
            return render(request, "accounts/rollover_year.html", {"years": years})

        target_classrooms = list(Classroom.objects.filter(academic_year=target_year).order_by("name"))
        target_classrooms_by_id = {c.id: c for c in target_classrooms}

        students = list(StudentProfile.objects.filter(
            academic_year=source_year, is_active=True
        ).select_related("classroom"))
        site = SiteSettings.get_solo()
        flags = getattr(site, "backend_feature_flags", None) or {}
        block_if_outstanding = flags.get("block_promotion_if_outstanding_returns", False)
        from django.db.models import Count
        from apps.people.models import StudentResourceReturn
        outstanding_by_student = dict(
            StudentResourceReturn.objects.filter(
                academic_year=source_year,
                returned_at__isnull=True,
            )
            .values("student_id")
            .annotate(count=Count("id"))
            .values_list("student_id", "count")
        )
        updated = 0
        graduated = 0
        skipped_outstanding = 0
        rolled_students = []  # (student, new_classroom) for notifications
        GRADUATE_VALUE = "__graduate__"
        for s in students:
            key = f"classroom_{s.id}"
            classroom_id = request.POST.get(key)
            if not classroom_id:
                continue
            outstanding = outstanding_by_student.get(s.id, 0)
            if block_if_outstanding and not allow_outstanding_returns and outstanding > 0:
                skipped_outstanding += 1
                continue
            if classroom_id == GRADUATE_VALUE:
                s.academic_year = target_year
                s.classroom = None
                s.status = StudentProfile.Status.ALUMNI
                s.is_active = False
                s.save(update_fields=["academic_year", "classroom", "status", "is_active"])
                graduated += 1
                continue
            try:
                new_class = target_classrooms_by_id.get(int(classroom_id))
            except (ValueError, TypeError):
                continue
            if not new_class:
                continue
            s.academic_year = target_year
            s.classroom = new_class
            s.save(update_fields=["academic_year", "classroom"])
            updated += 1
            rolled_students.append((s, new_class))
        if notify_parents and rolled_students:
            from apps.people.models import StudentGuardian
            from apps.finance.models import Notification as FinanceNotification
            notifier = None
            try:
                from apps.evals.notifications import NotificationService
                notifier = NotificationService()
            except Exception:
                pass
            for student, new_classroom in rolled_students:
                msg = f"Your child {student.get_full_name() or student.last_name} has been assigned to {new_classroom.name} for {target_year.name}."
                for link in StudentGuardian.objects.filter(student=student).select_related("guardian_user"):
                    if link.guardian_user_id:
                        FinanceNotification.objects.create(
                            title="Class assignment",
                            message=msg,
                            severity=FinanceNotification.Severity.INFO,
                            recipient_id=link.guardian_user_id,
                            created_by=request.user,
                        )
                    if notifier and getattr(link, "phone", None) and link.phone and getattr(link, "receives_sms", False):
                        try:
                            notifier.send_sms(link.phone, msg)
                        except Exception:
                            pass
        if lock_source:
            source_year.is_locked = True
            source_year.save(update_fields=["is_locked"])
            messages.success(request, f"Rolled over {updated} students to {target_year.name} and locked {source_year.name}.")
        else:
            messages.success(request, f"Rolled over {updated} students to {target_year.name}.")
        if graduated:
            messages.success(request, f"Marked {graduated} student(s) as Alumni.")
        if skipped_outstanding:
            messages.warning(
                request,
                f"Skipped {skipped_outstanding} student(s) due to outstanding resource returns. "
                "Enable 'Allow rollover despite outstanding returns' to include them, or mark items returned in Resource return checklist.",
            )
        return redirect("accounts:rollover_year")

    # GET: show form and optionally student list when source/target selected
    source_id = request.GET.get("source_year")
    target_id = request.GET.get("target_year")
    context = {"years": years, "rows": [], "source_year": None, "target_year": None, "target_classrooms": [], "checklist": [], "block_promotion_if_outstanding_returns": False}
    if source_id and target_id:
        source_year = AcademicYear.objects.filter(id=source_id).first()
        target_year = AcademicYear.objects.filter(id=target_id).first()
        if source_year and target_year:
            context["source_year"] = source_year
            context["target_year"] = target_year
            target_classrooms_list = list(
                Classroom.objects.filter(academic_year=target_year).order_by("name")
            )
            context["target_classrooms"] = target_classrooms_list
            # Pre-rollover checklist (informational)
            source_locked = getattr(source_year, "is_locked", False)
            context["checklist"] = [
                {"label": "Source year is not locked", "ok": not source_locked},
                {"label": "Target year has classrooms", "ok": len(target_classrooms_list) > 0},
                {"label": "Final grades entered and reports finalized (manual check)", "ok": None},
            ]
            # Promotion mapping for suggested next class (if model exists)
            promotion_map = {}
            try:
                from apps.academics.models import ClassroomPromotionMapping
                for m in ClassroomPromotionMapping.objects.filter(
                    source_year=source_year, target_year=target_year
                ).select_related("source_classroom", "target_classroom"):
                    if m.source_classroom_id:
                        promotion_map[m.source_classroom_id] = m.target_classroom
            except Exception:
                pass
            terms = list(Term.objects.filter(academic_year=source_year).order_by("position", "start_date"))
            students = StudentProfile.objects.filter(
                academic_year=source_year, is_active=True
            ).select_related("classroom")
            from django.db.models import Count
            from apps.people.models import StudentResourceReturn
            outstanding_counts = dict(
                StudentResourceReturn.objects.filter(
                    academic_year=source_year,
                    returned_at__isnull=True,
                )
                .values("student_id")
                .annotate(count=Count("id"))
                .values_list("student_id", "count")
            )
            site = SiteSettings.get_solo()
            context["block_promotion_if_outstanding_returns"] = (
                (getattr(site, "backend_feature_flags", None) or {}).get("block_promotion_if_outstanding_returns", False)
            )
            for s in students:
                annual_avg = _annual_average_for_student(s, terms) if terms else None
                promo = get_promotion_status(s, source_year, annual_avg) if annual_avg is not None else "NO_DATA"
                # Suggest: promotion mapping first, then same-name classroom in target year
                suggested = None
                if s.classroom_id and promotion_map:
                    suggested = promotion_map.get(s.classroom_id)
                if not suggested and s.classroom:
                    suggested = Classroom.objects.filter(
                        academic_year=target_year, name=s.classroom.name
                    ).first()
                if not suggested and context["target_classrooms"]:
                    suggested = context["target_classrooms"][0]
                context["rows"].append({
                    "student": s,
                    "annual_average": round(annual_avg, 2) if annual_avg is not None else None,
                    "promotion_status": promo,
                    "suggested_classroom": suggested,
                    "outstanding_returns": outstanding_counts.get(s.id, 0),
                })
    return render(request, "accounts/rollover_year.html", context)


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def academic_rules(request):
    """
    Single page showing promotion thresholds, grading scale, and who can edit grades (academic rules summary).
    """
    from apps.reports.models import PromotionRule

    site = SiteSettings.get_solo()
    year, _ = get_active_year_and_term()
    rules = []
    if year:
        rules = list(
            PromotionRule.objects.filter(academic_year=year)
            .select_related("classroom")
            .order_by("classroom__name")[:50]
        )
    return render(
        request,
        "accounts/academic_rules.html",
        {
            "site": site,
            "active_year": year,
            "rules": rules,
            "pass_mark": getattr(site, "pass_mark", None),
            "use_promotion_rule_for_pass": getattr(site, "use_promotion_rule_for_pass", False),
        },
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
