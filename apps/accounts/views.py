from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import PasswordChangeView as DjangoPasswordChangeView
from django.db import DatabaseError, OperationalError, ProgrammingError
from django.db.models import Avg, Count, Q
from django.conf import settings
from django.shortcuts import redirect, render, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import reverse, reverse_lazy, NoReverseMatch
from django.views.decorators.http import require_http_methods, require_POST
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils import translation
from django.utils.translation import gettext as _
import json
from django_ratelimit.decorators import ratelimit
from config.admin import admin_site
from apps.finance.models import (
    Invoice,
    ReferralReward,
    PaymentReminder,
    Notification as FinanceNotification,
)
from apps.finance.services import finance_dashboard_data
from apps.integrations_marketplace.models import ServiceIntegration
from apps.people.models import (
    StudentGuardian,
    StudentProfile,
    TeacherAttendance,
    TeacherProfile,
    Badge,
    BadgeType,
)
from apps.reports.models import TermPublishStatus
from apps.academics.services import get_active_year_and_term
from apps.accounts.decorators import permission_required
from apps.schools.mixins import require_school
from apps.observability.tracing import trace_view
from apps.dashboard.context import build_dashboard_extras
from apps.dashboard.recommendation_service import get_recommended_next_steps
from apps.siteconfig.templatetags.admin_health import admin_section_stats
from apps.siteconfig.templatetags.admin_kpis import admin_kpis
from apps.siteconfig.dashboard_views import effective_chart_types
from apps.accounts.utils import get_dashboard_context
from apps.siteconfig.config_service import (
    get_effective_flags,
    get_effective_site_settings,
)

from .forms import (
    ClaimInviteAccountForm,
    EditRoleForm,
    PermissionForm,
    RoleForm,
    TemporaryRoleGrantForm,
    UserPermissionForm,
    UserRoleForm,
)
from .iam_pdp_guards import rbac_dashboard_pdp
from .models import AccessRole, Permission, User, TemporaryRoleGrant

ACCOUNTS_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    NoReverseMatch,
    OperationalError,
    ProgrammingError,
    RuntimeError,
    TypeError,
    ValueError,
)


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
    except (DatabaseError, NoReverseMatch):
        pass


def get_org_chain_to_staff(teacher_profile):
    """Return ordered list of TeacherProfile from org root down to this staff (walk reports_to up, then reverse)."""
    if not teacher_profile:
        return []
    visited = set()
    chain = []
    current = teacher_profile
    while current and current.id not in visited:
        visited.add(current.id)
        chain.append(current)
        current = getattr(current, "reports_to", None)
    chain.reverse()
    return chain


def _get_teacher_approved_syllabi(teacher_profile):
    """Return approved CourseSyllabus entries for this teacher (by class/specialty/subject)."""
    if not teacher_profile:
        return []
    try:
        from apps.academics.models import CourseSyllabus
    except ImportError:
        return []
    qs = CourseSyllabus.objects.filter(
        status=CourseSyllabus.Status.APPROVED,
        subject_assignment__teacher_assignments__teacher=teacher_profile,
    ).select_related(
        "subject_assignment__classroom",
        "subject_assignment__subject",
        "subject_assignment__specialty",
    )
    return list(qs)


def _teacher_org_tree(user):
    """Build org tree for teacher: hierarchy diagram + assignments (year -> classrooms -> subjects)."""
    try:
        from apps.people.models import TeacherProfile
        from apps.evals.models import TeacherAssignment
        from apps.academics.services import get_active_year_and_term
    except ImportError:
        return None
    teacher = (
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        TeacherProfile.objects.filter(user=user)
        .select_related("department", "reports_to")
        .first()
    )
    if not teacher:
        return None
    year, _ = get_active_year_and_term()
    assignments = []
    if year:
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        qs = TeacherAssignment.objects.filter(
            teacher=teacher,
            is_active=True,
            subject_assignment__academic_year=year,
        ).select_related(
            "subject_assignment__classroom",
            "subject_assignment__subject",
            "subject_assignment__academic_year",
        )
        by_class = {}
        for ta in qs:
            sa = ta.subject_assignment
            if not sa:
                continue
            cname = sa.classroom.name if sa.classroom else "-"
            if cname not in by_class:
                by_class[cname] = []
            by_class[cname].append(sa.subject.name if sa.subject else "-")
        assignments = [
            {"classroom": c, "subjects": list(set(subs))}
            for c, subs in sorted(by_class.items())
        ]

    def _node_payload(profile, relation):
        if not profile:
            return None
        target_user = getattr(profile, "user", None)
        display_name = (
            (
                target_user.get_full_name()
                if target_user and hasattr(target_user, "get_full_name")
                else ""
            )
            or (target_user.username if target_user else "")
            or "Staff"
        )
        initials_parts = display_name.strip().split()
        initials = "".join(part[:1].upper() for part in initials_parts[:2]) or "S"
        photo_url = ""
        profile_photo = getattr(profile, "profile_photo", None)
        user_photo = (
            getattr(target_user, "profile_photo", None) if target_user else None
        )
        try:
            if profile_photo and getattr(profile_photo, "url", ""):
                photo_url = profile_photo.url
            elif user_photo and getattr(user_photo, "url", ""):
                photo_url = user_photo.url
        except (OSError, ValueError):
            photo_url = ""
        return {
            "id": profile.pk,
            "name": display_name,
            "title": getattr(profile, "position_title", "") or "Staff member",
            "department": getattr(getattr(profile, "department", None), "name", "")
            or "",
            "photo_url": photo_url,
            "initials": initials,
            "is_self": bool(
                target_user and target_user.pk == getattr(user, "pk", None)
            ),
            "relation": relation,
        }

    chain_profiles = get_org_chain_to_staff(teacher)
    chain_nodes = [_node_payload(profile, "chain") for profile in chain_profiles]
    chain_nodes = [node for node in chain_nodes if node]
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    direct_reports = list(
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        TeacherProfile.objects.filter(
            reports_to=teacher,
            is_active=True,
        )
        .select_related("user", "department")
        .order_by("position_title", "user__first_name", "user__last_name")[:8]
    )
    direct_report_nodes = [
        _node_payload(profile, "direct_report") for profile in direct_reports
    ]
    direct_report_nodes = [node for node in direct_report_nodes if node]

    diagram_levels = [[node] for node in chain_nodes]
    if direct_report_nodes:
        diagram_levels.append(direct_report_nodes)

    return {
        "teacher": teacher,
        "department": teacher.department,
        "reports_to": teacher.reports_to,
        "position_title": teacher.position_title or "-",
        "assignments": assignments,
        "academic_year": year,
        "diagram_levels": diagram_levels,
        "direct_reports_count": len(direct_report_nodes),
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
        class_name = classroom.name if classroom else "-"
        year_name = (
            getattr(getattr(classroom, "academic_year", None), "name", "") or "-"
        )
        children.append(
            {
                "student": s,
                "relationship": link.get_relationship_display(),
                "classroom": class_name,
                "academic_year": year_name,
            }
        )
    return {"children": children} if children else None


def _admin_context(user, request=None):
    """Build admin context for staff: Site Settings, Backend, Admin, RBAC URLs and permissions summary."""
    if not (user.is_staff or user.is_superuser):
        role = getattr(user, "role", None)
        if role not in ("ADMIN", "IT_ADMIN", "LEADERSHIP"):
            return None
    site_settings_url = None
    if getattr(user, "has_feature_permission", lambda _: False)("settings.manage"):
        try:
            from apps.siteconfig.staff_navigation import site_settings_change_url

            site = (
                get_effective_site_settings(request=request)
                if request is not None
                else get_effective_site_settings()
            )
            site_settings_url = site_settings_change_url(request, site.pk)
        except (AttributeError, NoReverseMatch, TypeError, ValueError):
            try:
                from apps.siteconfig.staff_navigation import site_settings_list_url

                site_settings_url = site_settings_list_url(request)
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
    from apps.siteconfig.user_identity import ensure_user_identity

    identity = ensure_user_identity(request.user, request=request)
    context = {
        "preferences_url": reverse("siteconfig:user_preferences"),
        "profile_edit_url": reverse("accounts:profile_edit"),
    }
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    role = getattr(request.user, "role", None)
    teacher_profile = identity.get("people_profile")
    if teacher_profile is None:
        try:
            teacher_profile = (
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                TeacherProfile.objects.filter(user=request.user)
                .select_related("department", "reports_to")
                .first()
            )
        except (ProgrammingError, DatabaseError, OperationalError):
            teacher_profile = None
    if teacher_profile:
        context["org_chain"] = get_org_chain_to_staff(teacher_profile)
    if role == User.Role.TEACHER and teacher_profile:
        context["teacher_org_tree"] = _teacher_org_tree(request.user)
        context["staff_id"] = getattr(teacher_profile, "staff_id", None) or (
            f"Staff #{request.user.pk}" if teacher_profile else None
        )
        context["approved_syllabi"] = _get_teacher_approved_syllabi(teacher_profile)
        try:
            context["digital_id_url"] = reverse("portal:my_digital_id")
        except NoReverseMatch:
            context["digital_id_url"] = None
        # Phase 1: Staff badges (non-expired, STAFF audience only)
        from django.utils import timezone as tz

        context["staff_badges"] = list(
            Badge.objects.filter(
                user=request.user,
                badge_type__audience=BadgeType.Audience.STAFF,
            )
            .filter(Q(expiry_at__isnull=True) | Q(expiry_at__gt=tz.now()))
            .select_related("badge_type")
            .order_by("-issued_at")[:20]
        )
    if role == User.Role.PARENT:
        try:
            context["parent_children_tree"] = _parent_children_tree(request.user)
        except (ProgrammingError, DatabaseError, OperationalError):
            context["parent_children_tree"] = None
    admin_ctx = _admin_context(request.user, request)
    if admin_ctx:
        context["admin_context"] = admin_ctx
    # MFA status (only when django_otp is available)
    try:
        from django_otp import user_has_device

        context["mfa_enabled"] = user_has_device(request.user)
    except (AttributeError, ImportError):
        pass
    # Optional teacher_pay_leave when payroll exposes data (e.g. next pay date, leave balance)
    # Parent upcoming fees summary when finance exposes it
    try:
        from apps.finance.services import get_parent_fees_summary

        parent_fees = get_parent_fees_summary(request.user)
        if parent_fees:
            context["parent_fees_summary"] = parent_fees
    except (AttributeError, DatabaseError, ImportError):
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
    context["profile_completion"] = {
        "percent": percent,
        "filled": filled,
        "missing": missing,
    }
    # Active sessions count (for Security line) — computed before security evaluation
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
    except (
        AttributeError,
        DatabaseError,
        ImportError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        context["active_sessions_count"] = None

    try:
        from apps.accounts.profile_security_evaluation import evaluate_user_profile_security

        context["profile_security"] = evaluate_user_profile_security(
            request.user,
            school=getattr(request, "school", None),
            active_sessions_count=context.get("active_sessions_count"),
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        context["profile_security"] = None

    # PII masking (plan 3.21): full address/DOB masked until re-auth.
    try:
        from apps.accounts.pii_masking import can_show_pii, mask_date

        context["can_show_pii"] = can_show_pii(request)
        dob = None
        if teacher_profile and getattr(teacher_profile, "date_of_birth", None):
            dob = teacher_profile.date_of_birth
        if not context["can_show_pii"] and dob is not None:
            context["pii_masked_dob"] = mask_date(dob)
        else:
            context["pii_masked_dob"] = None
    except (AttributeError, ImportError, TypeError, ValueError):
        context["can_show_pii"] = True
        context["pii_masked_dob"] = None

    from apps.accounts.mfa_setup_flow import build_mfa_setup_context, handle_mfa_setup_post

    profile_next = reverse("accounts:user_profile")
    if request.method == "POST" and request.POST.get("mfa_inline") == "1":
        outcome, mfa_ctx = handle_mfa_setup_post(request, next_url=profile_next)
        if outcome == "redirect_profile":
            return redirect(profile_next + "#profile-mfa-wizard")
        if outcome == "redirect_mfa_setup":
            return redirect("accounts:mfa_setup")
        if outcome == "render" and mfa_ctx:
            context.update(mfa_ctx)
    else:
        context.update(build_mfa_setup_context(request, next_url=profile_next))
    context["show_mfa_inline_wizard"] = True

    from apps.accounts.operator_account_render import render_account_page

    return render_account_page(
        request,
        portal_template="accounts/profile.html",
        body_template="accounts/partials/operator_profile_body.html",
        context=context,
        page_title=_("My profile"),
    )


@login_required
def profile_edit(request):
    """Edit own profile: first name, last name, email, profile photo."""
    user = request.user
    from .forms import UserProfileEditForm

    if request.method == "POST":
        form = UserProfileEditForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile updated."))
            return redirect("accounts:user_profile")
    else:
        form = UserProfileEditForm(instance=user)
    from apps.accounts.operator_account_render import render_account_page

    return render_account_page(
        request,
        portal_template="accounts/profile_edit.html",
        body_template="accounts/partials/operator_profile_edit_body.html",
        context={"form": form},
        page_title=_("Edit profile"),
    )


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

    from apps.accounts.operator_account_render import render_account_page

    return render_account_page(
        request,
        portal_template="accounts/notifications.html",
        body_template="accounts/partials/notifications_body.html",
        context=context,
        page_title=_("Inbox"),
    )


@login_required
def notification_preferences(request):
    """User-facing notification channel preferences.

    Wave 8 (v2.83). Lets every authenticated user pick which channels
    (Email / SMS / App / WhatsApp) deliver their notifications, plus opt
    in/out of the weekly digest. Backed by `siteconfig.UserPreference`
    (existing model, no migration). Apple Settings-app style.
    """
    from apps.siteconfig.models_tooling import UserPreference

    pref, _created = UserPreference.objects.get_or_create(user=request.user)
    available_channels = [c.value for c in UserPreference.NotificationChannel]

    if request.method == "POST":
        selected = request.POST.getlist("notification_channels")
        # Filter to only allowed values (defensive against client tampering).
        cleaned = [c for c in selected if c in available_channels]
        pref.notification_channels = cleaned
        pref.receive_weekly_summary = bool(request.POST.get("receive_weekly_summary"))
        pref.save(update_fields=["notification_channels", "receive_weekly_summary"])
        messages.success(request, _("Notification preferences updated."))
        return redirect("accounts:notification_preferences")

    enabled_channels = set(pref.notification_channels or [])
    ctx = {
        "preference": pref,
        "channel_choices": [
            (c.value, c.label, c.value in enabled_channels)
            for c in UserPreference.NotificationChannel
        ],
    }
    from apps.accounts.operator_account_render import render_account_page

    return render_account_page(
        request,
        portal_template="accounts/notification_preferences.html",
        body_template="accounts/partials/operator_notification_preferences_body.html",
        context=ctx,
        page_title=_("Notification preferences"),
    )


@login_required
@require_POST
def mark_all_notifications_read(request):
    """SSR action: mark all of the caller's unread notifications read, then redirect back.

    Mirrors `apps.api.notification_api.NotificationViewSet.mark_all_read` but
    server-rendered (no fetch/JS), so it works inside the Apple Mail-style inbox
    without requiring page-data wiring.
    """
    from apps.finance.models import Notification

    count = (
        Notification.objects.filter(recipient=request.user, is_read=False)
        .update(is_read=True)
    )
    if count:
        messages.success(
            request,
            _("Marked %(count)d notification as read.") % {"count": count}
            if count == 1
            else _("Marked %(count)d notifications as read.") % {"count": count},
        )
    else:
        messages.info(request, _("Nothing to mark — your inbox is already clear."))

    target = request.META.get("HTTP_REFERER") or reverse("accounts:user_notifications")
    return redirect(target)


def _direct_conversations(user, limit=50):
    """Build list of 1-on-1 conversations for the Messages hub (Direct tab)."""
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    from apps.communication.models import Message

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    # All messages where user is sender or recipient (exclude archived for listing)
    qs = (
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        Message.objects.filter(Q(sender=user) | Q(recipient=user))
        .filter(is_archived=False)
        .select_related("sender", "recipient")
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        .order_by("-created_at")
    )
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    # One query: unread counts per sender (senders who messaged me and I haven't read)
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    unread_by_sender = dict(
        Message.objects.filter(recipient=user, is_read=False, is_archived=False)
        .values("sender")
        .annotate(cnt=Count("id"))
        .values_list("sender", "cnt")
    )

    from apps.communication.models import DirectConversation

    # For parents: only show conversations with staff/teacher that are not closed
    # For students: only show conversations with staff/teacher
    is_parent = getattr(user, "role", None) == User.Role.PARENT
    is_student = getattr(user, "role", None) == User.Role.STUDENT

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
        if is_student:
            if not _is_staff_or_teacher(other):
                continue
        seen_other_ids.add(other.id)
        unread_count = unread_by_sender.get(other.id, 0)
        conversations.append(
            {
                "other_user": other,
                "last_message": msg,
                "last_message_at": msg.created_at,
                "unread_count": unread_count,
                "snippet": (msg.body or msg.subject or "")[:120],
            }
        )
        if len(conversations) >= limit:
            break
    return conversations


@login_required
def user_messages(request):
    """Messages hub: Direct and Groups. Parents use Contact School only (redirected). Students see Direct only. Staff/teachers see both."""
    role = getattr(request.user, "role", None)
    if role == User.Role.PARENT:
        return redirect(reverse("portal:parent_contact_school"))
    from apps.portal.services import threads_for_user

    # Students: show only Direct tab (conversations with staff); staff/teachers see both
    direct_only = role == User.Role.STUDENT
    if direct_only:
        _active_tab = "direct"
        threads = []
    else:
        _active_tab = request.GET.get("tab", "groups")
        try:
            threads = threads_for_user(request.user, limit=12)
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
            threads = []

    try:
        direct_list = _direct_conversations(request.user)
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
        direct_list = []

    context = {
        "threads": threads,
        "direct_conversations": direct_list,
        "active_tab": request.GET.get("tab") if not direct_only else "direct",
        "direct_only": direct_only,
        "is_student": role == User.Role.STUDENT,
    }
    return render(request, "accounts/messages.html", context)


def _is_staff_or_teacher(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = getattr(user, "role", None)
    if role in (User.Role.PARENT, User.Role.STUDENT):
        return False
    return (
        user.is_staff
        or user.is_superuser
        or role
        in (
            User.Role.ADMIN,
            User.Role.TEACHER,
            User.Role.LEADERSHIP,
            User.Role.PRINCIPAL,
            User.Role.VICE_PRINCIPAL,
            User.Role.DEPT_LEAD,
            User.Role.HOD,
            User.Role.SECRETARY,
            User.Role.BURSAR,
            User.Role.IT_ADMIN,
            User.Role.PROPRIETOR,
            User.Role.COMMS_STAFF,
            User.Role.EXECUTIVE_ASSISTANT,
            User.Role.VIRTUAL_ASSISTANT,
            User.Role.ACADEMICS_STAFF,
            User.Role.FINANCE_STAFF,
            User.Role.ACCOUNTANT,
        )
    )


def _can_access_direct_messages(user) -> bool:
    """Roles allowed to use direct messaging compose/thread endpoints."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = getattr(user, "role", None)
    if role in (User.Role.PARENT, User.Role.STUDENT):
        return False
    return _is_staff_or_teacher(user)


@login_required
def direct_thread(request, user_id):
    """View 1-on-1 thread. Parents and students can only open threads with staff/teacher (view/reply). Staff can close the loop."""
    from apps.communication.models import Message, DirectConversation
    from django.utils import timezone

    User = request.user.__class__
    if user_id == request.user.pk:
        return redirect("accounts:user_messages")
    other = get_object_or_404(User.objects.filter(is_active=True), pk=user_id)

    other_is_parent = getattr(other, "role", None) == User.Role.PARENT
    i_am_parent = getattr(request.user, "role", None) == User.Role.PARENT
    i_am_student = getattr(request.user, "role", None) == User.Role.STUDENT
    other_is_staff = _is_staff_or_teacher(other)

    # Parents do not use direct messaging; they use Contact School only.
    if i_am_parent:
        return redirect(reverse("portal:parent_contact_school"))
    if i_am_student and not other_is_staff:
        return HttpResponseForbidden("You can only message staff or teachers.")
    if (
        not i_am_parent
        and not i_am_student
        and not _can_access_direct_messages(request.user)
    ):
        return HttpResponseForbidden(
            "You don't have permission to send direct messages."
        )

    # Staff–parent conversation record (only when one is parent, one is staff/teacher)
    conv = None
    if (i_am_parent and _is_staff_or_teacher(other)) or (
        other_is_parent and _is_staff_or_teacher(request.user)
    ):
        conv = DirectConversation.get_or_create_for(request.user, other)

    if request.method == "POST":
        action = request.POST.get("action")
        if (
            action == "close"
            and _is_staff_or_teacher(request.user)
            and other_is_parent
            and conv
        ):
            conv.closed_at = timezone.now()
            conv.save(update_fields=["closed_at"])
            messages.success(
                request, _("Conversation closed. Parent can no longer reply.")
            )
            return redirect("accounts:user_messages")
        body = (request.POST.get("body") or "").strip()
        subject = (request.POST.get("subject") or "").strip() or "Direct message"
        if body:
            if conv and conv.closed_at:
                messages.error(request, _("This conversation is closed."))
            else:
                from apps.communication.comms_locale import locale_target_for_user

                msg = Message.objects.create(
                    sender=request.user,
                    recipient=other,
                    subject=subject,
                    body=body,
                    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                    locale_target=locale_target_for_user(other),
                )
                _notify_new_direct_message(request.user, other, msg)
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                Message.objects.filter(
                    sender=other, recipient=request.user, is_read=False
                ).update(is_read=True)
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            return redirect("accounts:direct_thread", user_id=other.pk)

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    messages_qs = (
        Message.objects.filter(
            Q(sender=request.user, recipient=other)
            | Q(sender=other, recipient=request.user)
        )
        .filter(is_archived=False)
        .select_related("sender", "recipient")
        .order_by("created_at")
    )

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    Message.objects.filter(sender=other, recipient=request.user, is_read=False).update(
        is_read=True
    )

    conversation_closed = conv.closed_at if conv else False
    can_close = (
        _is_staff_or_teacher(request.user)
        and other_is_parent
        and conv
        and not conv.closed_at
    )
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
    if not _can_access_direct_messages(request.user):
        return HttpResponseForbidden(
            "You don't have permission to compose direct messages."
        )
    from apps.communication.models import Message

    if request.method == "POST":
        recipient_id = request.POST.get("recipient")
        body = (request.POST.get("body") or "").strip()
        subject = (request.POST.get("subject") or "").strip() or "Direct message"
        if not body or not recipient_id:
            messages.error(request, _("Select a recipient and enter a message."))
            return redirect("accounts:direct_compose")
        recipient = (
            User.objects.filter(pk=recipient_id, is_active=True)
            .exclude(pk=request.user.pk)
            .first()
        )
        if not recipient:
            messages.error(request, _("Selected recipient is not available."))
            return redirect("accounts:direct_compose")
        from apps.communication.models import DirectConversation

        if getattr(
            recipient, "role", None
        ) == User.Role.PARENT and _is_staff_or_teacher(request.user):
            DirectConversation.get_or_create_for(request.user, recipient)
        from apps.communication.comms_locale import locale_target_for_user

        msg = Message.objects.create(
            sender=request.user,
            recipient=recipient,
            subject=subject,
            body=body,
            locale_target=locale_target_for_user(recipient),
        )
        _notify_new_direct_message(request.user, recipient, msg)
        return redirect("accounts:direct_thread", user_id=recipient.pk)

    # GET: list active users (exclude self) for recipient dropdown; limit for large schools
    recipients = (
        User.objects.filter(is_active=True)
        .exclude(pk=request.user.pk)
        .order_by("first_name", "last_name")
        .values("id", "first_name", "last_name", "username")[:500]
    )
    # Pass 13.D: surface AI draft entitlement to the template so the inline
    # partial only renders for tenants who own the AI_TEACHER_COMMS capability.
    school = getattr(request, "school", None)
    ai_teacher_comms_enabled = False
    if school is not None:
        try:
            from apps.billing.entitlements import can as _entitlement_can
            ai_teacher_comms_enabled = bool(
                _entitlement_can(school, "AI_TEACHER_COMMS")
            )
        except Exception:  # noqa: BLE001 - fail closed
            ai_teacher_comms_enabled = False
    context = {
        "recipients": list(recipients),
        "ai_teacher_comms_enabled": ai_teacher_comms_enabled,
        "ai_teacher_comms_endpoint": reverse("portal:ai_draft_parent_message"),
        "ai_teacher_comms_intent": "parent_message",
    }
    return render(request, "accounts/direct_compose.html", context)


@login_required
def user_documentation(request):
    """Shortcut to role-appropriate documentation/help (RBAC-safe)."""
    from apps.accounts.operator_account_render import render_account_page

    return render_account_page(
        request,
        portal_template="accounts/documentation.html",
        body_template="accounts/partials/operator_documentation_body.html",
        context={},
        page_title=_("Documentation"),
    )


@permission_required("settings.manage")
@user_passes_test(
    lambda u: (
        u.is_authenticated
        and (
            u.is_staff or u.is_superuser or getattr(u, "role", None) == User.Role.ADMIN
        )
    )
)
def backend_entity_import(request):
    """Admin-only page to stage CSV imports (students/guardians) against new APIs."""
    _site = get_effective_site_settings(request=request)
    flags = get_effective_flags(request)
    allowed_roles = [r.upper() for r in flags.get("allowed_roles_entity_import", [])]
    if not flags.get("enable_entity_import", True):
        return HttpResponseForbidden("Entity import is disabled by admin.")
    if allowed_roles:
        role = (getattr(request.user, "role", "") or "").upper()
        if role not in allowed_roles and not (
            request.user.is_staff or request.user.is_superuser
        ):
            return HttpResponseForbidden("You are not allowed to access Entity Import.")
    return render(
        request,
        "accounts/entity_import.html",
        {
            "BREADCRUMBS": [
                {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
                {"label": "Import & bulk", "url": reverse("studio_os:import_hub")},
                {"label": "Entity import", "url": "", "active": True},
            ],
        },
    )


@permission_required("settings.manage")
@user_passes_test(
    lambda u: (
        u.is_authenticated
        and (
            u.is_staff or u.is_superuser or getattr(u, "role", None) == User.Role.ADMIN
        )
    )
)
def backend_entity_console(request):
    """Admin-only page for EntityForm/Table beta UI."""
    _site = get_effective_site_settings(request=request)
    flags = get_effective_flags(request)
    allowed_roles = [r.upper() for r in flags.get("allowed_roles_entity_console", [])]
    if not flags.get("enable_entity_console", True):
        return HttpResponseForbidden("Entity console is disabled by admin.")
    if allowed_roles:
        role = (getattr(request.user, "role", "") or "").upper()
        if role not in allowed_roles and not (
            request.user.is_staff or request.user.is_superuser
        ):
            return HttpResponseForbidden(
                "You are not allowed to access Entity Console."
            )
    return render(request, "accounts/entity_console.html", {})


def redirect_view(request):
    """Central post-login redirect based on role.

    Keeping this logic in one place makes LOGIN_REDIRECT_URL reliable and
    prevents hard-coded URLs from drifting. Respects "Dashboard view" preference
    (Overview, Workflow Center, Finance, etc.) for backend, teacher, and parent.
    Preserves GET params (e.g. preview_section for config preview) on the target URL.
    When on base domain and user has a school membership, redirect to tenant subdomain (Backend is subdomain-only).
    Respects login_intent_role (Student / Staff / Parent) from login page when set.
    """
    user = request.user
    if not user.is_authenticated:
        return redirect(reverse("accounts:login"))

    # Manager host is dedicated to super-admin operations.
    try:
        from apps.schools.host_routing import public_host_kind

        host = (request.get_host() or "").split(":")[0].lower()
        if public_host_kind(host) == "manager":
            return redirect("super:dashboard")
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

    from apps.schools.tenant_url import get_tenant_prefix

    def _redirect_with_params(name_or_url, *args, **kwargs):
        target = reverse(name_or_url, args=args, kwargs=kwargs)
        prefix = get_tenant_prefix(request)
        if prefix:
            target = prefix.rstrip("/") + target
        if request.GET:
            target += "?" if "?" not in target else "&"
            target += request.GET.urlencode()
        return redirect(target)

    # Login intent (role selector on login page): send to the chosen portal when no next URL.
    intent = request.session.pop(LOGIN_INTENT_ROLE_KEY, None)
    if intent and not request.GET.get("next"):
        from apps.accounts.portal_roles import (
            ACTIVE_PORTAL_ROLE_KEY,
            has_teacher_hat,
            has_parent_hat,
        )

        if intent == "student":
            if (getattr(user, "role", "") or "").upper() == User.Role.STUDENT:
                return _redirect_with_params("portal:student_portal_grades")
        elif intent == "parent":
            if has_parent_hat(user):
                request.session[ACTIVE_PORTAL_ROLE_KEY] = "PARENT"
                return _redirect_with_params("portal:parent_dashboard")
        elif intent == "staff":
            if has_teacher_hat(user):
                request.session[ACTIVE_PORTAL_ROLE_KEY] = "TEACHER"
                return _redirect_with_params("evals:teacher_dashboard")
            if user.has_feature_permission("settings.manage"):
                return _redirect_with_params("accounts:backend_dashboard")
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    # Base domain: send users with a school membership to tenant URL (subdomain or /t/<slug>/)
    if not getattr(request, "school", None):
        try:
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            from apps.schools.models import SchoolMembership
            from apps.schools.tenant_url import is_base_domain, build_tenant_backend_url
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

            if is_base_domain(request):
                m = (
                    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                    SchoolMembership.objects.filter(user=user)
                    .select_related("school")
                    .order_by("-is_primary")
                    .first()
                )
                if m and m.school:
                    target = build_tenant_backend_url(request, m.school)
                    return redirect(target)
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
            pass

    # Respect the user's "Dashboard view" preference (Portal Preferences) when possible.
    dash_view = None
    try:
        from apps.siteconfig.models import UserPreference as PortalUserPreference

        pref = (
            PortalUserPreference.objects.filter(user=user)
            .only("dashboard_view")
            .first()
        )
        dash_view = getattr(pref, "dashboard_view", None)
    except (DatabaseError, ImportError, AttributeError):
        dash_view = None

    from apps.accounts.portal_roles import get_effective_portal_role

    role = get_effective_portal_role(request) or getattr(user, "role", None)

    # Staff/backend: Dashboard or Workflow Center as default view
    if user.has_feature_permission("settings.manage"):
        if dash_view == "WORKFLOW":
            return _redirect_with_params("studio_os:workflow_center")
        return _redirect_with_params("accounts:backend_dashboard")

    if role == User.Role.TEACHER:
        if dash_view == "WORKFLOW":
            return _redirect_with_params("portal:teacher_workflow")
        return _redirect_with_params("evals:teacher_dashboard")
    if role == User.Role.PARENT:
        if dash_view == "WORKFLOW":
            return _redirect_with_params("portal:parent_workflow")
        if dash_view == "FINANCE":
            return _redirect_with_params("portal:parent_finance")
        if dash_view == "ACADEMICS":
            return _redirect_with_params("portal:parent_performance")
        if dash_view == "ATTENDANCE":
            return _redirect_with_params("portal:parent_dashboard")
        return _redirect_with_params("portal:parent_dashboard")
    if role == User.Role.STUDENT:
        if dash_view == "WORKFLOW":
            return _redirect_with_params("portal:student_workflow")
        return _redirect_with_params("portal:student_portal_grades")

    # Default: admin
    return _redirect_with_params("admin:index")


@login_required
def switch_portal_role(request):
    """
    Set the active portal role (Teacher or Parent) for dual-hat users and redirect to the appropriate dashboard.
    GET or POST with ?role=TEACHER or ?role=PARENT. Only allowed when the user has that hat.
    """
    from apps.accounts.portal_roles import (
        ACTIVE_PORTAL_ROLE_KEY,
        ALLOWED_PORTAL_ROLES,
        has_teacher_hat,
        has_parent_hat,
    )

    role = (request.GET.get("role") or request.POST.get("role") or "").strip().upper()
    if role not in ALLOWED_PORTAL_ROLES:
        return redirect(reverse("accounts:redirect"))
    if role == User.Role.TEACHER and not has_teacher_hat(request.user):
        return redirect(reverse("accounts:redirect"))
    if role == User.Role.PARENT and not has_parent_hat(request.user):
        return redirect(reverse("accounts:redirect"))
    request.session[ACTIVE_PORTAL_ROLE_KEY] = role
    try:
        from django.db import IntegrityError
        from django.core.exceptions import ValidationError
        from apps.siteconfig.models import UserPreference

        pref, _ = UserPreference.objects.get_or_create(user=request.user, defaults={})
        pref.last_portal_role = role
        pref.save(update_fields=["last_portal_role", "updated_at"])
    except (IntegrityError, ValidationError, OSError):
        pass
    return redirect(reverse("accounts:redirect"))


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
            filtered = {
                label: stats[label] for label in preferred_items if label in stats
            }
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


def _rbac_roles_by_category(roles_qs):
    """Group roles by category for RBAC UI (additive; uses ROLE_CATEGORIES)."""
    from apps.accounts.permissions import ROLE_CATEGORIES

    role_by_code = {r.code: r for r in roles_qs}
    result = []
    for category_label, codes in ROLE_CATEGORIES.items():
        roles_in_cat = [role_by_code[c] for c in codes if c in role_by_code]
        if roles_in_cat:
            result.append((category_label, roles_in_cat))
    return result


def _rbac_permissions_by_group(permissions_qs):
    """Group permissions by module for RBAC UI (additive; uses PERMISSION_GROUPS)."""
    from apps.accounts.permissions import PERMISSION_GROUPS

    perm_by_code = {p.code: p for p in permissions_qs}
    result = []
    for group_label, codes in PERMISSION_GROUPS.items():
        perms_in_group = [perm_by_code[c] for c in codes if c in perm_by_code]
        if perms_in_group:
            result.append((group_label, perms_in_group))
    # Append any permission not in any group (additive)
    seen_ids = {p.id for _, perms in result for p in perms}
    other = [p for p in permissions_qs if p.id not in seen_ids]
    if other:
        result.append(("Other", other))
    return result


@rbac_dashboard_pdp
@login_required
@require_school
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def rbac_dashboard(request):
    from apps.accounts.tenant_identity import user_has_school_membership

    school = request.school

    from apps.accounts.access_roles import roles_queryset_for_school, role_applies_to_school

    roles_qs = roles_queryset_for_school(school).prefetch_related("permissions")
    permissions_qs = Permission.objects.order_by("code")
    initial_user_roles = {}
    if request.method == "GET" and request.GET.get("user"):
        try:
            u = User.objects.get(pk=request.GET.get("user"))
            if user_has_school_membership(u, school):
                initial_user_roles = {
                    "user": u,
                    "roles": [
                        r
                        for r in u.roles.all()
                        if role_applies_to_school(r, school)
                    ],
                }
        except (User.DoesNotExist, ValueError):
            pass

    edit_role_id = None
    edit_role_form = None
    if request.method == "GET" and request.GET.get("edit_role"):
        try:
            edit_role = roles_queryset_for_school(school).prefetch_related(
                "permissions"
            ).get(pk=request.GET.get("edit_role"))
            edit_role_form = EditRoleForm(role=edit_role)
            edit_role_id = edit_role.pk
        except (AccessRole.DoesNotExist, ValueError):
            pass

    role_form = RoleForm(prefix="role")
    permission_form = PermissionForm(prefix="permission")
    user_role_form = UserRoleForm(
        prefix="user_role", initial=initial_user_roles or None, school=school
    )
    user_permission_form = UserPermissionForm(prefix="user_permission", school=school)
    temporary_grant_form = TemporaryRoleGrantForm(prefix="temp_grant", school=school)

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "role":
            role_form = RoleForm(request.POST, prefix="role")
            if role_form.is_valid():
                role = role_form.save(commit=False)
                role.school = school
                role.save()
                role_form.save_m2m()
                messages.success(request, _("Role created successfully."))
                return redirect("accounts:rbac")
        elif form_type == "permission":
            permission_form = PermissionForm(request.POST, prefix="permission")
            if permission_form.is_valid():
                permission_form.save()
                messages.success(request, _("Permission created successfully."))
                return redirect("accounts:rbac")
        elif form_type == "user_roles":
            user_role_form = UserRoleForm(request.POST, prefix="user_role", school=school)
            if user_role_form.is_valid():
                user = user_role_form.cleaned_data["user"]
                if not user_has_school_membership(user, school):
                    messages.error(request, _("User is not a member of this school."))
                    return redirect("accounts:rbac")
                roles = user_role_form.cleaned_data["roles"]
                for role in roles:
                    if not role_applies_to_school(role, school):
                        messages.error(
                            request,
                            _("Role %(code)s is not valid for this school.")
                            % {"code": role.code},
                        )
                        return redirect("accounts:rbac")
                user.roles.set(roles)
                messages.success(request, f"Roles updated for {user.username}.")
                return redirect("accounts:rbac")
            else:
                try:
                    role_ids = [int(pk) for pk in request.POST.getlist("user_role-roles")]
                    initial_user_roles = {
                        "roles": list(
                            roles_queryset_for_school(school).filter(pk__in=role_ids)
                        )
                    }
                except (ValueError, AccessRole.DoesNotExist):
                    initial_user_roles = {}
        elif form_type == "user_permissions":
            user_permission_form = UserPermissionForm(
                request.POST, prefix="user_permission", school=school
            )
            if user_permission_form.is_valid():
                user = user_permission_form.cleaned_data["user"]
                if not user_has_school_membership(user, school):
                    messages.error(request, _("User is not a member of this school."))
                    return redirect("accounts:rbac")
                permissions = user_permission_form.cleaned_data["permissions"]
                user.feature_permissions.set(permissions)
                messages.success(request, f"Permissions updated for {user.username}.")
                return redirect("accounts:rbac")
        elif form_type == "edit_role":
            edit_role_form = EditRoleForm(request.POST)
            if edit_role_form.is_valid():
                role = get_object_or_404(
                    roles_queryset_for_school(school),
                    pk=edit_role_form.cleaned_data["role_id"],
                )
                role.description = edit_role_form.cleaned_data["description"] or ""
                role.permissions.set(edit_role_form.cleaned_data["permissions"])
                role.save()
                messages.success(request, f"Role '{role.name}' updated.")
                return redirect("accounts:rbac")
            edit_role_id = edit_role_form.cleaned_data.get(
                "role_id"
            ) or request.POST.get("role_id")
        elif form_type == "temporary_grant":
            temporary_grant_form = TemporaryRoleGrantForm(
                request.POST, prefix="temp_grant", school=school
            )
            if temporary_grant_form.is_valid():
                from datetime import datetime, time

                user = temporary_grant_form.cleaned_data["user"]
                if not user_has_school_membership(user, school):
                    messages.error(request, _("User is not a member of this school."))
                    return redirect("accounts:rbac")
                role = temporary_grant_form.cleaned_data["role"]
                if not role_applies_to_school(role, school):
                    messages.error(
                        request,
                        _("Role %(code)s is not valid for this school.")
                        % {"code": role.code},
                    )
                    return redirect("accounts:rbac")
                expires_date = temporary_grant_form.cleaned_data["expires_at"]
                valid_from_date = temporary_grant_form.cleaned_data.get("valid_from")
                notes = (temporary_grant_form.cleaned_data.get("notes") or "").strip()[
                    :255
                ]
                expires_at = timezone.make_aware(
                    datetime.combine(expires_date, time(23, 59, 59)),
                    timezone.get_current_timezone(),
                )
                valid_from = None
                if valid_from_date:
                    valid_from = timezone.make_aware(
                        datetime.combine(valid_from_date, time(0, 0, 0)),
                        timezone.get_current_timezone(),
                    )
                TemporaryRoleGrant.objects.create(
                    user=user,
                    role=role,
                    expires_at=expires_at,
                    valid_from=valid_from,
                    created_by=request.user,
                    notes=notes,
                )
                messages.success(
                    request,
                    f"Temporary role '{role.name}' granted to {user.username} until {expires_date}.",
                )
                return redirect("accounts:rbac")

    today = timezone.localdate()
    from apps.platform_runtime.localization import (
        calendar_week_bounds,
        week_start_day_for_school,
    )

    school = getattr(request, "school", None)
    if school:
        week_start, week_end = calendar_week_bounds(
            today, week_start_day=week_start_day_for_school(school)
        )
    else:
        week_start = today - timedelta(days=6)
        week_end = today
    window = TeacherAttendance.objects.filter(date__range=(week_start, week_end))
    present_map = {
        entry["date"]: entry["count"]
        for entry in window.filter(status=TeacherAttendance.Status.PRESENT)
        .values("date")
        .annotate(count=Count("id"))
    }
    day_count = (week_end - week_start).days + 1
    attendance_trend = [
        {
            "date": week_start + timedelta(days=offset),
            "present": present_map.get(week_start + timedelta(days=offset), 0),
        }
        for offset in range(day_count)
    ]
    attendance_trend_total = sum(item["present"] for item in attendance_trend)
    attendance_trend_progress = min(attendance_trend_total, 100)

    selected_role_ids = set()
    if initial_user_roles and "roles" in initial_user_roles:
        selected_role_ids = {r.pk for r in initial_user_roles["roles"]}
    elif request.method == "POST" and request.POST.get("form_type") == "user_roles":
        for pk in request.POST.getlist("user_role-roles"):
            try:
                selected_role_ids.add(int(pk))
            except ValueError:
                pass

    from apps.accounts.tenant_identity import users_queryset_for_school

    now = timezone.now()
    school_user_ids = users_queryset_for_school(school).values_list("pk", flat=True)
    active_temporary_grants = (
        TemporaryRoleGrant.objects.filter(
            user_id__in=school_user_ids,
            expires_at__gt=now,
        )
        .filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=now),
        )
        .filter(Q(role__school__isnull=True) | Q(role__school_id=school.pk))
        .select_related("user", "role", "created_by")
        .order_by("expires_at")[:50]
    )

    context = {
        "roles": roles_qs,
        "permissions": permissions_qs,
        "roles_by_category": _rbac_roles_by_category(roles_qs),
        "permissions_by_group": _rbac_permissions_by_group(permissions_qs),
        "role_form": role_form,
        "permission_form": permission_form,
        "user_role_form": user_role_form,
        "user_permission_form": user_permission_form,
        "temporary_grant_form": temporary_grant_form,
        "active_temporary_grants": active_temporary_grants,
        "edit_role_form": edit_role_form,
        "edit_role_id": edit_role_id,
        "selected_role_ids": selected_role_ids,
        "attendance_trend_total": attendance_trend_total,
        "attendance_trend_progress": attendance_trend_progress,
    }
    return render(request, "accounts/rbac_dashboard.html", context)


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def backend_dashboard(request):
    # Manager host: school backend is tenant-primary; operators use impersonation on the tenant host.
    if (getattr(request, "public_host_kind", None) or "").lower() == "manager":
        messages.warning(
            request,
            _(
                "The school backend runs on the tenant host. "
                "Use “Open as school” from the super dashboard to impersonate that school."
            ),
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        )
        return redirect(reverse("super:dashboard"))
    # Tenant Backend is subdomain-only: on base domain redirect to tenant subdomain
    if not getattr(request, "school", None):
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        try:
            from apps.schools.models import SchoolMembership
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            from apps.schools.tenant_url import is_base_domain, build_tenant_backend_url

            if is_base_domain(request):
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                m = (
                    SchoolMembership.objects.filter(user=request.user)
                    .select_related("school")
                    .order_by("-is_primary")
                    .first()
                )
                if m and m.school:
                    return redirect(build_tenant_backend_url(request, m.school))
        except ACCOUNTS_SOFT_FAILURES:
            pass

    from .activity_helper import get_recent_activity

    site = get_effective_site_settings(request=request)
    year, term = get_active_year_and_term()

    backend_flags = get_effective_flags(request)

    def _clamp_backend_int(value, default, minimum=3, maximum=12):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = int(default)
        return max(minimum, min(maximum, parsed))

    backend_layout_max_items_per_list = _clamp_backend_int(
        backend_flags.get("backend_layout_max_items_per_list"),
        5,
    )
    backend_max_items_slice = f":{backend_layout_max_items_per_list}"

    backend_module_visibility = {
        "overview": bool(backend_flags.get("backend_module_overview", True)),
        "admin_portal": bool(backend_flags.get("backend_module_admin_portal", True)),
        "welcome": bool(backend_flags.get("backend_module_welcome", True)),
        "enrollment_trends": bool(
            backend_flags.get("backend_module_enrollment_trends", True)
        ),
        "at_risk_students": bool(
            backend_flags.get("backend_module_at_risk_students", True)
        ),
        "outstanding_fees": bool(
            backend_flags.get("backend_module_outstanding_fees", True)
        ),
        "recent_admissions": bool(
            backend_flags.get("backend_module_recent_admissions", True)
        ),
        "recent_activity": bool(
            backend_flags.get("backend_module_recent_activity", True)
        ),
        "top_performing": bool(
            backend_flags.get("backend_module_top_performing", True)
        ),
        "attendance_today": bool(
            backend_flags.get("backend_module_attendance_today", True)
        ),
        "ops_watch": bool(backend_flags.get("backend_module_ops_watch", True)),
        "quick_links": bool(backend_flags.get("backend_module_quick_links", True)),
        "planner": bool(backend_flags.get("backend_module_planner", True)),
    }
    backend_visual_settings = {
        "show_trend_ribbons": bool(
            backend_flags.get("backend_viz_show_trend_ribbons", True)
        ),
        "show_progress_rings": bool(
            backend_flags.get("backend_viz_show_progress_rings", True)
        ),
        "show_rank_sparklines": bool(
            backend_flags.get("backend_viz_show_rank_sparklines", True)
        ),
    }
    backend_theme_settings = {
        "warm_palette": bool(backend_flags.get("backend_warm_palette", True)),
        "reduce_card_flatness": bool(
            backend_flags.get("backend_reduce_card_flatness", True)
        ),
        "high_depth_surfaces": bool(
            backend_flags.get("backend_high_depth_surfaces", True)
        ),
        "balanced_motion": bool(backend_flags.get("backend_balanced_motion", True)),
        "layout_equal_heights": bool(
            backend_flags.get("backend_layout_equal_heights", True)
        ),
    }
    from apps.portal.models import PendingGuardianInvite
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    stats = {
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        "students": StudentProfile.objects.filter(is_active=True).count(),
        "guardians": StudentGuardian.objects.count(),
        "pending_invites": PendingGuardianInvite.objects.filter(
            guardian_user__isnull=True
        ).count(),
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        "pending_referrals": ReferralReward.objects.filter(
            status=ReferralReward.Status.PENDING
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        ).count(),
        "overdue_invoices": Invoice.objects.filter(
            status=Invoice.Status.OVERDUE
        ).count(),
        "published_terms": TermPublishStatus.objects.filter(is_published=True).count(),
    }

    # Certification/GCE stats (if enabled for active year)
    certification_stats = {}
    if year and getattr(year, "enable_gce_registration", False):
        from apps.academics.models import (
            CertificationExamSession,
            CertificationCandidate,
        )

        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        active_sessions = CertificationExamSession.objects.filter(
            academic_year=year, is_active=True
        )
        total_candidates = CertificationCandidate.objects.filter(
            session__academic_year=year
        ).count()
        draft_candidates = CertificationCandidate.objects.filter(
            session__academic_year=year, status="DRAFT"
        ).count()
        verified_candidates = CertificationCandidate.objects.filter(
            session__academic_year=year, status="VERIFIED"
        ).count()
        certification_stats = {
            "active_sessions": active_sessions.count(),
            "total_candidates": total_candidates,
            "draft_candidates": draft_candidates,
            "verified_candidates": verified_candidates,
            "sessions": active_sessions[:3],  # Recent sessions for quick access
        }

    # Get recent activity
    recent_activities = get_recent_activity(
        limit=max(backend_layout_max_items_per_list, 5)
    )

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

    from apps.platform_runtime.localization import (
        calendar_week_bounds,
        week_start_day_for_school,
    )

    school = getattr(request, "school", None)
    if school:
        week_start, week_end = calendar_week_bounds(
            today, week_start_day=week_start_day_for_school(school)
        )
    else:
        week_start = today - timedelta(days=6)
        week_end = today
    window = TeacherAttendance.objects.filter(date__range=(week_start, week_end))
    present_map = {
        entry["date"]: entry["count"]
        for entry in window.filter(status=TeacherAttendance.Status.PRESENT)
        .values("date")
        .annotate(count=Count("id"))
    }
    day_count = (week_end - week_start).days + 1
    attendance_trend = [
        {
            "date": week_start + timedelta(days=offset),
            "present": present_map.get(week_start + timedelta(days=offset), 0),
        }
        for offset in range(day_count)
    ]
    attendance_trend_total = sum(item["present"] for item in attendance_trend)
    attendance_trend_progress = min(attendance_trend_total, 100)
    avg_weekly_present = attendance_trend_total / day_count if attendance_trend else 0
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
        for section, stats in admin_section_stats({"request": request}).items()
    }
    admin_portal_stats = _resolve_admin_portal_stats(
        section_stats,
        getattr(site, "admin_portal_stats_config", {}) or {},
    )
    role_upper = (getattr(request.user, "role", "") or "").upper()
    admin_like = bool(
        request.user.is_superuser
        or role_upper in {User.Role.ADMIN, User.Role.SUPERADMIN}
    )
    can_manage_settings = admin_like and request.user.has_feature_permission(
        "settings.manage"
    )

    # Simple role-based action flags for UI gating (defensive guard in template too)
    action_perms = {
        "people": bool(
            role_upper
            in {
                User.Role.ADMIN,
                User.Role.LEADERSHIP,
                User.Role.IT_ADMIN,
                User.Role.SUPERADMIN,
            }
            or request.user.is_superuser
        ),
        "finance": bool(
            role_upper
            in {
                User.Role.ADMIN,
                User.Role.LEADERSHIP,
                User.Role.IT_ADMIN,
                User.Role.BURSAR,
                User.Role.SUPERADMIN,
            }
            or request.user.is_superuser
        ),
        "site_settings": bool(can_manage_settings),
        "admin_panel": bool(
            request.user.is_staff
            or request.user.is_superuser
            or role_upper in {User.Role.ADMIN, User.Role.IT_ADMIN}
        ),
    }

    app_context = admin_site.each_context(request)
    modules = sum(
        len(app.get("models") or []) for app in app_context.get("available_apps", [])
    )
    kpi_data = admin_kpis()
    hero_stats = [
        {"label": "Students", "value": kpi_data["students"], "meta": "Active profiles"},
        {"label": "Subjects", "value": kpi_data["subjects"], "meta": "Catalog size"},
        {
            "label": "Report cards",
            "value": kpi_data["report_cards"],
            "meta": "Generated",
        },
        {"label": "Modules", "value": modules, "meta": "Registered apps"},
    ]
    hero_actions = [
        {"label": "Open parent portal", "url": reverse("portal:parent_dashboard")},
        {"label": "Backend config", "url": reverse("accounts:backend_dashboard")},
        {"label": "Frontend admin", "url": reverse("admin:index")},
    ]
    if can_manage_settings:
        hero_actions.append(
            {
                "label": "Open Full Site Settings",
                "url": reverse("siteconfig:user_preferences"),
            }
        )

    hero = {
        "tagline": "Admin hub",
        "title": "RunMyCampus",
        "subtitle": "Configure school apps, monitor health, and keep reports, finance, and portals aligned from one warm, modern dashboard.",
        "icon": "bi bi-pie-chart",
        "stats": hero_stats,
        "actions": hero_actions,
        "insight": ai_insight,
        "status_pills": [
            {
                "label": "Today’s reminders",
                "value": len(reminders),
                "meta": "queued alerts",
            },
            {
                "label": "Published terms",
                "value": stats["published_terms"],
                "meta": "published",
            },
        ],
    }
    dashboard_context = get_dashboard_context(request.user, "backend", request=request)
    allow_custom_layout = dashboard_context.get("allow_custom_layout", False)
    dashboard_settings = dashboard_context.get("dashboard_settings", {})
    dashboard_layout_url = dashboard_context.get("dashboard_layout_url", "")
    widget_meta_json = dashboard_context.get("widget_meta_json", "")
    try:
        from apps.runtime_blueprints.models import DashboardUserPreference

        pref, created = DashboardUserPreference.objects.get_or_create(
            user=request.user,
            defaults={
                "sidebar_collapsed": bool(
                    getattr(site, "default_sidebar_collapsed", False)
                )
            },
        )
        if created or not pref.pinned_sidebar_items:
            pref.pinned_sidebar_items = [
                "workflow_center",
                "import_grades",
                "documents",
                "preferences",
            ]
            pref.save(update_fields=["pinned_sidebar_items", "updated_at"])
    except DatabaseError:
        pass

    def _safe_reverse(name, default="#", kwargs=None):
        try:
            return reverse(name, kwargs=kwargs)
        except NoReverseMatch:
            return default

    feature_control_settings = (
        site.get_feature_control_settings()
        if callable(getattr(site, "get_feature_control_settings", None))
        else {}
    )
    portal_cfg = feature_control_settings.get("portal_features") or {}
    has_docs = bool(portal_cfg.get("documents"))

    def _item(
        item_id,
        label,
        url_name=None,
        *,
        url=None,
        icon="bi-circle",
        allow=True,
        kwargs=None,
    ):
        """Build a sidebar/shortcut item, dropping unresolved links."""
        if not allow:
            return None
        final_url = url if url is not None else _safe_reverse(url_name, kwargs=kwargs)
        if not final_url or final_url == "#":
            return None
        return {"id": item_id, "label": label, "url": final_url, "icon": icon}

    available_sidebar_items = [
        _item(
            "backend",
            "Backend Console",
            "accounts:backend_dashboard",
            icon="bi-speedometer2",
        ),
        _item(
            "workflow",
            "Workflow Center",
            "studio_os:workflow_center",
            icon="bi-diagram-3",
            allow=bool(action_perms.get("site_settings")),
        ),
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
            allow=bool(
                role_upper
                in {
                    User.Role.TEACHER,
                    User.Role.ADMIN,
                    User.Role.LEADERSHIP,
                    User.Role.IT_ADMIN,
                    User.Role.SUPERADMIN,
                }
                or request.user.is_staff
                or request.user.is_superuser
            ),
        ),
        _item(
            "announcements",
            "Announcements",
            "communication:announcement_create",
            icon="bi-megaphone",
            allow=bool(
                role_upper
                in {
                    User.Role.ADMIN,
                    User.Role.LEADERSHIP,
                    User.Role.IT_ADMIN,
                    User.Role.SUPERADMIN,
                }
                or request.user.is_staff
                or request.user.is_superuser
            ),
        ),
        _item(
            "reports",
            "Publish Results",
            "reports:publish_term_results",
            icon="bi-award",
            allow=bool(action_perms.get("people")),
        ),
        _item(
            "report_builder",
            "Report Card Builder",
            "siteconfig:reportcard_builder",
            icon="bi-file-earmark-richtext",
            allow=bool(action_perms.get("people")),
        ),
        _item(
            "report_library",
            "Outputs",
            "studio_os:output",
            icon="bi-journal-text",
            allow=bool(action_perms.get("people")),
        ),
        _item(
            "bulk_letters",
            "Bulk Letters",
            "siteconfig:bulk_letters",
            icon="bi-envelope-paper",
            allow=bool(action_perms.get("people")),
        ),
        _item(
            "certification",
            "Certification & Exams",
            "accounts:certification_home",
            icon="bi-award",
            allow=bool(
                year and getattr(year, "enable_gce_registration", False)
                if year
                else False
            ),
        ),
        _item(
            "finance",
            "Finance Dashboard",
            "finance:dashboard",
            icon="bi-cash-stack",
            allow=bool(action_perms.get("finance")),
        ),
        _item(
            "documents",
            "Document Library",
            "portal:document_library_manage",
            icon="bi-file-earmark-text",
            allow=bool(action_perms.get("site_settings") or admin_like),
        ),
        _item(
            "signatures",
            "Signature Requests",
            "portal:signature_requests_manage",
            icon="bi-pen",
            allow=bool(action_perms.get("site_settings") or admin_like),
        ),
        _item(
            "documents_portal",
            "Public Documents",
            "portal:portal_feature",
            kwargs={"feature": "documents"},
            icon="bi-folder-open",
            allow=has_docs,
        ),
        _item(
            "studio",
            "Studio",
            "studio_os:shell",
            icon="bi-grid-3x3-gap",
            allow=bool(action_perms.get("site_settings") or admin_like),
        ),
        _item("portal", "Parent Portal", "portal:parent_dashboard", icon="bi-people"),
        _item(
            "preferences",
            "Preferences",
            "siteconfig:user_preferences",
            icon="bi-sliders",
        ),
        _item("kb", "Help Center", "kb:kb_home", icon="bi-life-preserver"),
        _item(
            "admin",
            "Config center"
            if getattr(request, "public_host_kind", None) == "manager"
            else "Admin Panel",
            "siteconfig:console_domains_hub"
            if getattr(request, "public_host_kind", None) == "manager"
            else "admin:index",
            icon="bi-grid",
            allow=bool(action_perms.get("admin_panel")),
        ),
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
        finance_request_link = (
            f"{reverse('accounts:user_messages')}?subject=finance+access+request"
        )

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
    chart_enrollment_trend_json = ""
    recent_admissions = []
    top_performing_students = []
    at_risk_students = []
    if compliance_profile and finance_status_counts:
        status_labels = dict(Invoice.Status.choices)
        chart_finance_status_json = json.dumps(
            {
                "type": "doughnut",
                "data": {
                    "labels": [
                        status_labels.get(sc["status"], sc["status"])
                        for sc in finance_status_counts
                    ],
                    "datasets": [
                        {
                            "data": [sc["count"] for sc in finance_status_counts],
                            "backgroundColor": [
                                "#6c757d",
                                "#0d6efd",
                                "#ffc107",
                                "#198754",
                                "#dc3545",
                                "#adb5bd",
                            ][: len(finance_status_counts)],
                        }
                    ],
                },
            }
        )
    if finance_trend:
        chart_finance_trend_json = json.dumps(
            {
                "type": "line",
                "data": {
                    "labels": [t["label"] for t in finance_trend],
                    "datasets": [
                        {
                            "label": "Invoice total",
                            "data": [float(t.get("total", 0)) for t in finance_trend],
                            "fill": True,
                            "borderColor": "#0d6efd",
                            "backgroundColor": "rgba(13, 110, 253, 0.15)",
                            "tension": 0.3,
                        }
                    ],
                },
            }
        )
    if attendance_counts:
        labels = list(attendance_counts.keys())
        counts = list(attendance_counts.values())
        chart_attendance_donut_json = json.dumps(
            {
                "type": "doughnut",
                "data": {
                    "labels": labels,
                    "datasets": [
                        {
                            "data": counts,
                            "backgroundColor": [
                                "#198754",
                                "#ffc107",
                                "#dc3545",
                                "#6c757d",
                                "#0d6efd",
                            ][: len(labels)],
                        }
                    ],
                },
            }
        )
    # Dashboard data capping: top N roles by user count (see docs/DASHBOARD_DATA_CAPPING_POLICY.md)
    from apps.dashboard.context import DASHBOARD_CHART_TOP_N

    roles_qs = AccessRole.objects.prefetch_related("permissions", "users").order_by(
        "code"
    )
    role_user_counts = {r.code: r.users.count() for r in roles_qs}
    if role_user_counts:
        sorted_roles = sorted(role_user_counts.items(), key=lambda x: -x[1])[
            :DASHBOARD_CHART_TOP_N
        ]
        chart_rbac_roles_json = json.dumps(
            {
                "type": "bar",
                "data": {
                    "labels": [r[0] for r in sorted_roles],
                    "datasets": [
                        {
                            "label": "Users",
                            "data": [r[1] for r in sorted_roles],
                            "backgroundColor": "rgba(13, 110, 253, 0.8)",
                            "borderColor": "#0d6efd",
                            "borderWidth": 1,
                        }
                    ],
                },
                "options": {"indexAxis": "y"},
            }
        )

    # Enrollment trend + people lists for streamlined backend layout
    try:
        from django.db.models.functions import TruncMonth
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

        enrollment_qs = StudentProfile.objects.filter(
            is_active=True, joined_date__isnull=False
        )
        if year:
            enrollment_qs = enrollment_qs.filter(academic_year=year)
        monthly = list(
            enrollment_qs.annotate(month=TruncMonth("joined_date"))
            .values("month")
            .annotate(total=Count("id"))
            .order_by("month")
        )
        monthly = [row for row in monthly if row.get("month")][-6:]
        enroll_labels = [row["month"].strftime("%b") for row in monthly]
        enroll_values = [row["total"] for row in monthly]
        if not enroll_labels:
            enroll_labels = [
                item["date"].strftime("%a") for item in attendance_trend[-6:]
            ]
            enroll_values = [item["present"] for item in attendance_trend[-6:]]
        if enroll_labels:
            chart_enrollment_trend_json = json.dumps(
                {
                    "type": "line",
                    "data": {
                        "labels": enroll_labels,
                        "datasets": [
                            {
                                "label": "Enrollment",
                                "data": enroll_values,
                                "borderColor": "#60a5fa",
                                "backgroundColor": "rgba(96, 165, 250, 0.16)",
                                "fill": True,
                                "tension": 0.35,
                            }
                        ],
                    },
                }
            )
    except DatabaseError:
        chart_enrollment_trend_json = ""

    try:
        admissions_qs = StudentProfile.objects.select_related("classroom").filter(
            is_active=True
        )
        if year:
            admissions_qs = admissions_qs.filter(academic_year=year)
        for student in admissions_qs.order_by("-updated_at", "-id")[
            :backend_layout_max_items_per_list
        ]:
            recent_admissions.append(
                {
                    "name": student.get_full_name(),
                    "classroom": getattr(
                        getattr(student, "classroom", None), "name", ""
                    )
                    or "Unassigned",
                    "admission_number": student.admission_number
                    or student.student_code
                    or "--",
                }
            )
    except DatabaseError:
        recent_admissions = []

    score_rows = []
    try:
        from apps.evals.models import Evaluation

        eval_qs = Evaluation.objects.select_related("student", "student__classroom")
        if year:
            eval_qs = eval_qs.filter(academic_year=year)
        if term:
            eval_qs = eval_qs.filter(term=term)
        score_candidates = eval_qs.values(
            "student_id",
            "student__first_name",
            "student__last_name",
            "student__classroom__name",
        ).annotate(
            avg_exam=Avg("exam_score"),
            avg_seq1=Avg("seq1_score"),
            avg_seq2=Avg("seq2_score"),
        )[:300]

        for row in score_candidates:
            values = [
                float(v)
                for v in (row.get("avg_exam"), row.get("avg_seq1"), row.get("avg_seq2"))
                if v is not None
            ]
            if not values:
                continue
            score = round(sum(values) / len(values), 1)
            full_name = (
                " ".join(
                    part
                    for part in [
                        row.get("student__first_name"),
                        row.get("student__last_name"),
                    ]
                    if part
                ).strip()
                or "Student"
            )
            score_rows.append(
                {
                    "student_id": row.get("student_id"),
                    "name": full_name,
                    "classroom": row.get("student__classroom__name") or "Unassigned",
                    "score": score,
                }
            )
    except (DatabaseError, OperationalError, TypeError, ValueError):
        score_rows = []

    score_rows.sort(key=lambda item: item.get("score", 0), reverse=True)
    top_performing_students = score_rows[:backend_layout_max_items_per_list]
    top_score = max(
        (item.get("score", 0) for item in top_performing_students), default=0
    )
    for item in top_performing_students:
        score_value = float(item.get("score", 0) or 0)
        if top_score <= 0:
            item["ribbon_pct"] = 0
        else:
            item["ribbon_pct"] = max(
                8, min(100, int(round((score_value / top_score) * 100)))
            )

    at_risk_map = {}
    for row in score_rows:
        if row.get("score", 0) >= 10:
            continue
        sid = row.get("student_id")
        if sid in at_risk_map:
            continue
        at_risk_map[sid] = {
            "student_id": sid,
            "name": row.get("name") or "Student",
            "classroom": row.get("classroom") or "Unassigned",
            "tag": "Low performance",
            "value": f"{row.get('score', 0):.1f}/20",
        }
        if len(at_risk_map) >= backend_layout_max_items_per_list:
            break

    try:
        overdue_qs = (
            Invoice.objects.select_related("student__classroom")
            .filter(status=Invoice.Status.OVERDUE, student__isnull=False)
            .order_by("due_date", "-id")[:10]
        )
        for invoice in overdue_qs:
            student = invoice.student
            sid = student.id if student else None
            if sid in at_risk_map:
                continue
            full_name = student.get_full_name() if student else "Student"
            classroom_name = (
                getattr(getattr(student, "classroom", None), "name", "")
                if student
                else ""
            ) or "Unassigned"
            risk_value = "Action required"
            if invoice.due_date:
                days_overdue = (today - invoice.due_date).days
                if days_overdue > 0:
                    risk_value = f"{days_overdue}d overdue"
            at_risk_map[sid] = {
                "student_id": sid,
                "name": full_name,
                "classroom": classroom_name,
                "tag": "Overdue invoice",
                "value": risk_value,
            }
            if len(at_risk_map) >= backend_layout_max_items_per_list:
                break
    except (DatabaseError, OperationalError, TypeError, ValueError):
        pass

    at_risk_students = list(at_risk_map.values())[:backend_layout_max_items_per_list]
    total_students = max(stats.get("students", 0), 1)
    at_risk_ratio_pct = int(round((len(at_risk_students) / total_students) * 100))

    # Workflow progress and recommended next steps for dashboard (recommendation service)
    from apps.accounts.views_workflow import _workflow_progress as _wf_progress

    workflow_progress = _wf_progress(year)

    backend_main_module_count = sum(
        1
        for key in (
            "enrollment_trends",
            "outstanding_fees",
            "at_risk_students",
            "recent_admissions",
            "recent_activity",
            "top_performing",
            "attendance_today",
        )
        if backend_module_visibility.get(key, True)
    )
    backend_show_workspace_rail = any(
        backend_module_visibility.get(key, True)
        for key in ("ops_watch", "quick_links", "planner")
    )
    backend_workspace_fluid = not all(
        backend_module_visibility.get(key, True)
        for key in ("enrollment_trends", "outstanding_fees", "at_risk_students")
    )

    from apps.dashboard.action_registry import VALID_DASHBOARD_INTENTS

    role_intent_defaults = {
        User.Role.PRINCIPAL: "executive",
        User.Role.VICE_PRINCIPAL: "executive",
        User.Role.LEADERSHIP: "executive",
        User.Role.PROPRIETOR: "executive",
        User.Role.BURSAR: "finance",
        User.Role.ACCOUNTANT: "finance",
        User.Role.FINANCE_STAFF: "finance",
        User.Role.TEACHER: "academic",
        User.Role.SECRETARY: "operational",
        User.Role.IT_ADMIN: "setup",
        User.Role.ADMIN: "setup",
        User.Role.SUPERADMIN: "setup",
    }
    requested_intent = (request.GET.get("intent") or "").strip().lower()
    _intent = requested_intent or role_intent_defaults.get(role_upper, "operational")
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    if _intent not in VALID_DASHBOARD_INTENTS:
        _intent = "operational"
    pending_approvals_count = 0
    try:
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        from apps.requests.models import AccessRequest

        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        pending_approvals_count = AccessRequest.objects.filter(
            status=AccessRequest.Status.PENDING
        ).count()
    except (
        ImportError,
        AttributeError,
        DatabaseError,
        OperationalError,
        ProgrammingError,
    ):
        pending_approvals_count = 0
    recommended_next_steps = get_recommended_next_steps(
        workflow_progress,
        year=year,
        intent=_intent,
        priority_signals={
            "overdue_invoices": stats.get("overdue_invoices", 0),
            "pending_invites": stats.get("pending_invites", 0),
            "pending_approvals_count": pending_approvals_count,
            "draft_invoices": finance_summary.get("draft_invoices", 0)
            if isinstance(finance_summary, dict)
            else 0,
            "at_risk_students": len(at_risk_students),
        },
        max_steps=4,
    )
    context = {
        "site": site,
        "dashboard_intent": _intent,
        "backend_feature_flags": backend_flags,
        "backend_module_visibility": backend_module_visibility,
        "backend_visual_settings": backend_visual_settings,
        "backend_theme_settings": backend_theme_settings,
        "backend_layout_max_items_per_list": backend_layout_max_items_per_list,
        "backend_max_items_slice": backend_max_items_slice,
        "backend_main_module_count": backend_main_module_count,
        "backend_show_workspace_rail": backend_show_workspace_rail,
        "backend_workspace_fluid": backend_workspace_fluid,
        "at_risk_ratio_pct": at_risk_ratio_pct,
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
        "gce_enabled": year and getattr(year, "enable_gce_registration", False)
        if year
        else False,
        "pending_approvals_count": pending_approvals_count,
        "chart_finance_status_json": chart_finance_status_json,
        "chart_finance_trend_json": chart_finance_trend_json,
        "chart_attendance_donut_json": chart_attendance_donut_json,
        "chart_rbac_roles_json": chart_rbac_roles_json,
        "chart_enrollment_trend_json": chart_enrollment_trend_json,
        "recent_admissions": recent_admissions,
        "top_performing_students": top_performing_students,
        "at_risk_students": at_risk_students,
        "quick_student_create_url": _safe_reverse("accounts:backend_student_create")
        if _safe_reverse("accounts:backend_student_create") != "#"
        else _safe_reverse("admin:people_studentprofile_add"),
        "quick_teacher_create_url": _safe_reverse("accounts:backend_teacher_create")
        if _safe_reverse("accounts:backend_teacher_create") != "#"
        else _safe_reverse("admin:people_teacherprofile_add"),
        "breadcrumbs": [
            {
                "title": "Backend",
                "url": reverse("accounts:backend_dashboard"),
                "icon": "bi-speedometer2",
            }
        ],
        "BREADCRUMBS": [
            {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
            {"label": "Dashboard", "url": "", "active": True},
        ],
        "SHOW_HEADER_CONTEXT_STRIP": False,
    }
    # W1-6: First-login checklist aligned with Setup Studio (same labels, same deep links); thin entry to Setup Studio.
    try:
        from apps.runtime_blueprints.models import DashboardUserPreference
        from apps.customersuccess.services import get_guided_onboarding_steps

        pref, _created = DashboardUserPreference.objects.get_or_create(
            user=request.user, defaults={"dashboard_layout": {}}
        )
        layout = pref.dashboard_layout or {}
        context["first_login_checklist_show"] = not layout.get(
            "first_login_checklist_dismissed"
        )
        context["first_login_checklist_dismiss_url"] = reverse(
            "accounts:dismiss_first_login_checklist"
        )
        context["first_login_tour_show"] = not layout.get(
            "tour_backend_dashboard_completed"
        )
        try:
            from apps.siteconfig.tour_context import resolve_backend_tour_context

            tour_ctx = resolve_backend_tour_context(request.user) or "backend_dashboard_admin"
            context["tour_autostart_context"] = tour_ctx
            context["tour_steps_api_url"] = (
                reverse("siteconfig:tour_steps_api") + f"?context={tour_ctx}"
            )
            context["tour_complete_url"] = reverse("accounts:mark_tour_complete")
        except NoReverseMatch:
            context["tour_steps_api_url"] = ""
            context["tour_complete_url"] = ""
        _safe = _safe_reverse
        school = getattr(request, "school", None)
        if school:
            steps = get_guided_onboarding_steps(school)
            checklist_items = []
            for s in steps:
                if not s.get("done") and s.get("link"):
                    link = s["link"]
                    if link.startswith("/authentication/backend/students/"):
                        link = _safe("accounts:backend_student_list") or link
                    elif "/backend/" in link:
                        link = _safe("accounts:backend_dashboard") or link
                    checklist_items.append(
                        {"label": _(s.get("label", "")), "url": link}
                    )
            setup_studio_url = _safe("siteconfig:guided_onboarding") or "#"
            if setup_studio_url != "#":
                checklist_items.append(
                    {"label": _("Setup Studio (all steps)"), "url": setup_studio_url}
                )
            launch_base = _safe("studio_os:launch") or ""
            if launch_base and launch_base != "#":
                checklist_items.append(
                    {
                        "label": _("Launch Studio (readiness & checklists)"),
                        "url": f"{launch_base}?pane=overview",
                    }
                )
                role_upper = (getattr(request.user, "role", "") or "").upper()
                _op_roles = {
                    "IT_ADMIN",
                    "LEADERSHIP",
                    "ADMIN",
                    "PRINCIPAL",
                    "PROPRIETOR",
                    "SUPERADMIN",
                }
                _preview_roles = {"TEACHER", "PARENT", "STUDENT"}
                if role_upper in _op_roles or getattr(
                    request.user, "is_superuser", False
                ):
                    checklist_items.append(
                        {
                            "label": _("Launch Studio: data migration"),
                            "url": f"{launch_base}?pane=migration",
                        }
                    )
                if role_upper in _preview_roles:
                    checklist_items.append(
                        {
                            "label": _("Launch Studio: preview by role"),
                            "url": f"{launch_base}?pane=role_preview",
                        }
                    )
            context["first_login_checklist_items"] = checklist_items
        else:
            context["first_login_checklist_items"] = [
                {
                    "label": _("Setup Studio"),
                    "url": _safe("siteconfig:guided_onboarding") or "#",
                },
            ]
        context["first_login_settings_url"] = (
            _safe("studio_os:shell") or _safe("admin:index") or "#"
        )
        context["first_login_sensible_defaults_copy"] = _(
            "We've set up: academic year, terms, default classrooms, and subjects. You can change these in Settings."
        )
    except ACCOUNTS_SOFT_FAILURES:
        context["first_login_checklist_show"] = False
        context["first_login_checklist_items"] = []
        context["first_login_checklist_dismiss_url"] = ""
        context["first_login_settings_url"] = "#"
        context["first_login_sensible_defaults_copy"] = ""
        context["first_login_tour_show"] = False
        context["tour_steps_api_url"] = ""
        context["tour_complete_url"] = ""
    try:
        context.update(build_dashboard_extras(request, base=context))
    except ACCOUNTS_SOFT_FAILURES as e:
        import logging

        logging.getLogger(__name__).exception("build_dashboard_extras failed: %s", e)
        # Safe defaults so template does not 500; UX plan overview/CTAs/contextual_actions still work when extras succeed
        context.setdefault("primary_ctas", [])
        context.setdefault("overview_cards", [])
        context.setdefault("contextual_actions", [])
        context.setdefault("kpi_strip_cards", [])
    context["open_webui_url"] = getattr(settings, "OPEN_WEBUI_URL", None) or ""
    try:
        from apps.dashboard.services.insight_anomalies import (
            build_insight_anomaly_cards,
        )

        context["insight_anomaly_cards"] = build_insight_anomaly_cards(request)
    except ACCOUNTS_SOFT_FAILURES:
        context["insight_anomaly_cards"] = []
    try:
        context["insight_anomalies_api_url"] = reverse("api:api-insight-anomalies")
    except NoReverseMatch:
        context["insight_anomalies_api_url"] = ""
    # School activation: real-data onboarding + health (platform_runtime)
    try:
        from apps.platform_runtime.customer_health import (
            calculate_school_health,
            get_school_health_recommendations,
        )
        from apps.platform_runtime.onboarding import get_school_onboarding_progress

        _sch = getattr(request, "school", None)
        if _sch is not None:
            context["rmc_school_onboarding"] = get_school_onboarding_progress(
                _sch, user=request.user
            )
            context["rmc_school_health"] = calculate_school_health(_sch)
            context["rmc_school_health_nudges"] = get_school_health_recommendations(
                _sch, user=request.user, limit=3
            )
            try:
                from apps.platform_runtime.ai_system_layer import (
                    generate_onboarding_next_action_insight,
                    generate_school_health_insight,
                )

                context["rmc_ai_system_health_insight"] = generate_school_health_insight(
                    _sch, request.user
                )
                context["rmc_ai_system_onboarding_insight"] = (
                    generate_onboarding_next_action_insight(_sch, request.user)
                )
            except ACCOUNTS_SOFT_FAILURES:
                context["rmc_ai_system_health_insight"] = None
                context["rmc_ai_system_onboarding_insight"] = None
        else:
            context["rmc_school_onboarding"] = None
            context["rmc_school_health"] = None
            context["rmc_school_health_nudges"] = []
            context["rmc_ai_system_health_insight"] = None
            context["rmc_ai_system_onboarding_insight"] = None
    except ACCOUNTS_SOFT_FAILURES:
        context["rmc_school_onboarding"] = None
        context["rmc_school_health"] = None
        context["rmc_school_health_nudges"] = []
        context["rmc_ai_system_health_insight"] = None
        context["rmc_ai_system_onboarding_insight"] = None
    # Use module-level User import; a function-local import shadowed User and broke action_perms.
    from apps.portal.tenant_role_home import (
        build_tp_hero_context,
        role_home_show_legacy,
    )

    pending_access_requests = 0
    try:
        from apps.requests.models import AccessRequest

        _school_for_count = getattr(request, "school", None)
        if _school_for_count is not None:
            pending_access_requests = AccessRequest.objects.filter(
                school=_school_for_count,
                status=AccessRequest.Status.PENDING,
            ).count()
    except ACCOUNTS_SOFT_FAILURES:
        pending_access_requests = 0

    context.update(
        build_tp_hero_context(
            request,
            role=User.Role.ADMIN,
            pending_access_requests=pending_access_requests,
        )
    )
    from apps.platform_runtime.operator_queue_signals import (
        build_operator_queue_smart_link_context,
    )

    context.update(build_operator_queue_smart_link_context(request))
    context["backend_show_legacy_dashboard"] = role_home_show_legacy(request)

    # v3.99.24: surface promoted cockpit widgets + requested-new-widget ids
    # from the user's saved layout. Both are written by dashboard-layout.js
    # via the layout API; the template includes them at the end of the grid.
    try:
        from apps.siteconfig.dashboard_views import get_layout_for_page
        from apps.siteconfig.cockpit_widget_bridge import resolve_promoted_cockpit_partials

        layout_obj = get_layout_for_page(request.user, "backend")
        layout_data = (layout_obj.layout if layout_obj else {}) or {}
        layout_settings = layout_data.get("__settings__") or {}
        promoted_ids = list(layout_settings.get("promoted_cockpit_ids") or [])
        context["promoted_cockpit_widgets"] = resolve_promoted_cockpit_partials(promoted_ids)
        context["requested_widget_ids"] = list(layout_settings.get("requested_widget_ids") or [])
    except Exception:  # noqa: BLE001 — layout resolution is best-effort, never breaks dashboard
        context.setdefault("promoted_cockpit_widgets", [])
        context.setdefault("requested_widget_ids", [])

    # v4.00.13: cache the 3 extra cockpit helpers for 60s per (user, school).
    # backend_dashboard was running 3 extra DB queries (queue depth, resumable
    # wizards, enrollment forecast) every render — combined into one cached
    # bundle so steady-state renders do 0 extra queries.
    _school_for_extras = getattr(request, "school", None) or getattr(request, "tenant", None) \
        or getattr(getattr(request, "user", None), "school", None)
    _user_pk = getattr(getattr(request, "user", None), "pk", None) or "anon"
    _school_pk = getattr(_school_for_extras, "pk", None) or "noschool"
    _extras_cache_key = f"backend_dashboard_extras:user={_user_pk}:school={_school_pk}"

    try:
        from django.core.cache import cache
        _extras = cache.get(_extras_cache_key)
    except Exception:  # noqa: BLE001
        _extras = None
        cache = None  # type: ignore[assignment]

    if _extras is None:
        _extras = _compute_backend_dashboard_extras(request, _school_for_extras)
        try:
            if cache is not None:
                cache.set(_extras_cache_key, _extras, 60)
        except Exception:  # noqa: BLE001
            pass

    context["admissions_queue_rows"] = _extras.get("admissions_queue_rows", [])
    context["resumable_wizards"] = _extras.get("resumable_wizards", [])
    context["enrollment_forecast_rows"] = _extras.get("enrollment_forecast_rows", [])

    return render(request, "accounts/backend_dashboard.html", context)


def _compute_backend_dashboard_extras(request, school):
    """v4.00.13 — gather 3 cockpit extras (queue depth + resumable + forecast) in one call.

    Pure-Python aggregator. Returns a dict-of-lists; callers cache the result.
    Each lookup is wrapped so any single failure doesn't break the bundle.
    """
    out = {"admissions_queue_rows": [], "resumable_wizards": [], "enrollment_forecast_rows": []}
    try:
        from apps.admissions.queue_depth import compute_admissions_queue_depth

        out["admissions_queue_rows"] = compute_admissions_queue_depth(school)
    except Exception:  # noqa: BLE001
        pass
    try:
        from apps.setup_studio.models import SetupProgress  # local — avoids cold-import cost
        from apps.setup_studio.wizard_extras import list_resumable_wizards

        if school is not None and getattr(school, "pk", None) is not None:
            progress = SetupProgress.objects.filter(school=school).first()  # tenant-isolation-allow: scoped-via-school-filter-setup-progress
            if progress is not None:
                step_state = progress.step_state or {}
                wizards_namespace = step_state.get("wizards") if isinstance(step_state, dict) else None
                out["resumable_wizards"] = list_resumable_wizards(
                    wizards_namespace=wizards_namespace, within_days=7,
                )
    except Exception:  # noqa: BLE001
        pass
    try:
        from apps.api.enrollment_forecast import build_forecast
        from apps.people.models import StudentProfile

        if school is not None and getattr(school, "pk", None) is not None:
            current = StudentProfile.objects.filter(school=school, is_active=True).count()  # tenant-isolation-allow: scoped-via-school-filter-enrollment-forecast-tile
            out["enrollment_forecast_rows"] = build_forecast(
                school=school, current_count=current, horizon_terms=3,
            )
    except Exception:  # noqa: BLE001
        pass
    return out


BACKEND_STATUS_FRAGMENT_CACHE_KEY = "backend_dashboard_status_fragment"
BACKEND_STATUS_FRAGMENT_CACHE_TTL = 60  # seconds


@login_required
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def backend_dashboard_status_fragment(request):
    """Return HTML fragment for backend dashboard status strip (for HTMX partial load). Cached 60s to reduce DB load."""
    from django.http import HttpResponse
    from django.template import loader
    from django.core.cache import cache
    from apps.siteconfig.cache_utils import tenant_cache_key

    cache_key = tenant_cache_key(BACKEND_STATUS_FRAGMENT_CACHE_KEY, request)
    html = cache.get(cache_key)
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    if html is not None:
        return HttpResponse(html)

    pending_requests = 0
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    try:
        from apps.requests.models import AccessRequest
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

        pending_requests = AccessRequest.objects.filter(
            status=AccessRequest.Status.PENDING
        ).count()
    except (
        AttributeError,
        DatabaseError,
        ImportError,
        OperationalError,
        TypeError,
        ValueError,
    ):
        pass

    enable_offline_mode = False
    offline_queue_metrics = None
    try:
        site = get_effective_site_settings(request=request)
        offline_settings = (
            site.get_offline_runtime_settings()
            if callable(getattr(site, "get_offline_runtime_settings", None))
            else {
                "enable_offline_mode": bool(getattr(site, "enable_offline_mode", False))
            }
        )
        enable_offline_mode = bool(offline_settings.get("enable_offline_mode", False))
        if enable_offline_mode:
            from apps.siteconfig.cache_utils import tenant_cache_key

            offline_queue_metrics = cache.get(
                tenant_cache_key("sms_offline_queue_metrics", request)
            )
    except (AttributeError, DatabaseError, TypeError, ValueError):
        pass

    template = loader.get_template("accounts/backend_dashboard_status_fragment.html")
    html = template.render(
        {
            "request": request,
            "pending_requests": pending_requests,
            "enable_offline_mode": enable_offline_mode,
            "offline_queue_metrics": offline_queue_metrics,
        }
    )
    cache.set(cache_key, html, BACKEND_STATUS_FRAGMENT_CACHE_TTL)
    return HttpResponse(html)


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def backend_ops_watch_data(request):
    """Lightweight JSON payload for live Ops Watch refresh."""
    _site = get_effective_site_settings(request=request)
    backend_flags = get_effective_flags(request)

    if not bool(backend_flags.get("backend_module_ops_watch", True)):
        return JsonResponse(
            {
                "success": True,
                "operations_watch": [],
                "finance_requests": 0,
                "updated_at": timezone.localtime().isoformat(),
            }
        )

    try:
        max_items = int(backend_flags.get("backend_layout_max_items_per_list", 5))
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    except (TypeError, ValueError):
        max_items = 5
    max_items = max(3, min(12, max_items))

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    pending_approvals_count = 0
    try:
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        from apps.requests.models import AccessRequest

        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        pending_approvals_count = AccessRequest.objects.filter(
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            status=AccessRequest.Status.PENDING
        ).count()
    except (AttributeError, DatabaseError, OperationalError, TypeError, ValueError):
        pending_approvals_count = 0
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    base_stats = {
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        "pending_referrals": ReferralReward.objects.filter(
            status=ReferralReward.Status.PENDING
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        ).count(),
        "overdue_invoices": Invoice.objects.filter(
            status=Invoice.Status.OVERDUE
        ).count(),
    }
    finance_requests_count = FinanceNotification.objects.filter(
        recipient=request.user,
        title__icontains="finance access request",
        is_read=False,
    ).count()

    extras = build_dashboard_extras(
        request,
        base={
            "stats": base_stats,
            "finance_requests_count": finance_requests_count,
            "pending_approvals_count": pending_approvals_count,
        },
    )
    return JsonResponse(
        {
            "success": True,
            "operations_watch": (extras.get("operations_watch", []) or [])[:max_items],
            "finance_requests": extras.get("ops_watch_finance_requests", 0),
            "updated_at": extras.get("ops_watch_last_updated"),
        }
    )


# §3 Workflow/approval views moved to views_workflow.py (re-exported below).


class PasswordChangeView(DjangoPasswordChangeView):
    """Clear requires_password_change; persist zxcvbn score + rotation timestamp."""

    success_url = reverse_lazy("accounts:password_change_done")

    def form_valid(self, form):
        from django.utils import timezone
        from django.utils.translation import gettext as _

        from apps.accounts.models import User
        from apps.accounts.security_health import invalidate_security_strength_cache

        try:
            score = int(self.request.POST.get("password_strength_score", "0"))
        except (TypeError, ValueError):
            score = 0
        if score < 3:
            form.add_error(
                "new_password1",
                _("Choose a stronger password (score at least 3 of 4)."),
            )
            return self.form_invalid(form)
        response = super().form_valid(form)
        User.objects.filter(pk=form.user.pk).update(
            requires_password_change=False,
            password_strength_score=score,
            password_changed_at=timezone.now(),
        )
        invalidate_security_strength_cache(
            form.user, getattr(self.request, "school", None)
        )
        return response

    def get_success_url(self):
        next_url = self.request.session.pop("password_change_next", None)
        if next_url:
            from django.utils.http import url_has_allowed_host_and_scheme

            if url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={self.request.get_host()}
            ):
                return next_url
        return str(self.success_url)


LOGIN_INTENT_ROLE_KEY = "login_intent_role"


def _get_login_page_language(request):
    """
    Return the language code to use for the login page (tenant default or Accept-Language).
    Used only to activate language for this request; no session or DB change.
    """
    school = getattr(request, "school", None)
    if school:
        try:
            from apps.siteconfig.tenant_config import get_tenant_locale

            locale = get_tenant_locale(request=request, school=school)
            lang = (
                locale.get("default_language") or locale.get("locale") or ""
            ).strip() or None
        except ACCOUNTS_SOFT_FAILURES:
            lang = None
        if not lang and school:
            try:
                from apps.policies.policy_registry import get_effective_policy

                policy = get_effective_policy(school)
                lang = (policy.get("default_language") or "").strip() or None
            except ACCOUNTS_SOFT_FAILURES:
                pass
    else:
        lang = translation.get_language_from_request(request)
    if not lang:
        return None
    lang = lang.split("-")[0].lower()
    from django.conf import settings as django_settings

    supported = [
        c for c, _ in getattr(django_settings, "LANGUAGES", [("en", "English")])
    ]
    if not supported:
        supported = ["en", "fr"]
    return lang if lang in supported else (supported[0] if supported else "en")


# Display names for known SSO integration service_name (OAuth/SAML).
SSO_LABEL_MAP = {
    "azure": "Microsoft",
    "microsoft": "Microsoft",
    "google": "Google",
    "saml": "Single Sign-On",
    "oidc": "Single Sign-On",
}


def _get_login_sso_integrations(request):
    """Build list of {url, label} for school's active OAuth/SAML integrations (login template)."""
    school = getattr(request, "school", None)
    if not school:
        return []
    try:
        qs = ServiceIntegration.objects.filter(
            school=school,
            service_type=ServiceIntegration.ServiceType.OAUTH,
            is_active=True,
        )
        out = []
        for integration in qs:
            ref = integration.service_name or str(integration.pk)
            config = getattr(integration, "config", None) or {}
            idp_type = (config.get("idp_type") or "").lower()
            if idp_type == "saml":
                url = reverse("accounts:saml_start", args=[ref])
            else:
                url = reverse("accounts:oidc_start", args=[ref])
            label = (
                config.get("display_name")
                or SSO_LABEL_MAP.get((integration.service_name or "").lower())
                or integration.service_name
                or "Single Sign-On"
            )
            out.append({"url": url, "label": label})
        return out
    except ACCOUNTS_SOFT_FAILURES:
        return []


def auth_root_redirect(request):
    """Redirect /authentication/ to the canonical login URL and preserve the query string."""
    target = reverse("accounts:login")
    query_string = request.GET.urlencode()
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target)


def _login_challenge_required(request) -> bool:
    """True when the Turnstile widget should render (configured + a prior fail)."""
    try:
        from apps.accounts.turnstile import turnstile_enabled
    except ImportError:
        return False
    return (
        turnstile_enabled()
        and int(request.session.get("auth_failed_attempts", 0) or 0) >= 1
    )


@ratelimit(key="ip", rate="5/m", method="POST", block=True)
@trace_view("auth.login")
def login_view(request):
    # Optional: set login page language from tenant or Accept-Language (this request only).
    login_lang = _get_login_page_language(request)
    if login_lang:
        translation.activate(login_lang)

    if request.method == "POST":
        # Store role intent for post-login redirect (Student / Staff / Parent).
        role_param = (
            (request.POST.get("role") or request.GET.get("role") or "").strip().lower()
        )
        if role_param in ("student", "staff", "parent"):
            request.session[LOGIN_INTENT_ROLE_KEY] = role_param

        next_url = request.POST.get("next") or request.GET.get("next", "").strip()
        if next_url:
            from django.utils.http import url_has_allowed_host_and_scheme

            if not url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}
            ):
                next_url = ""

        # Brute-force / bot defense, layered on the per-IP @ratelimit above:
        #  1. login_guard — always-on cache lockout after N failed attempts.
        #  2. Cloudflare Turnstile — once configured, a challenge after the
        #     first failed attempt. Both fail open so an outage never blocks
        #     legitimate sign-in.
        from apps.accounts import login_guard
        from apps.accounts.turnstile import turnstile_enabled, verify_turnstile

        username = request.POST.get("username")
        guard_ip = login_guard.client_ip(request)
        user = None
        login_block_reason = None

        locked, retry_after = login_guard.lockout_state(request, username)
        if locked:
            login_block_reason = "locked"
            retry_minutes = max(1, (retry_after + 59) // 60)
            messages.error(
                request,
                _(
                    "Too many failed sign-in attempts. Please try again in "
                    "about %(minutes)d minute(s), or reset your password."
                )
                % {"minutes": retry_minutes},
            )
        else:
            failed_so_far = int(request.session.get("auth_failed_attempts", 0) or 0)
            challenge_required = turnstile_enabled() and failed_so_far >= 1
            if challenge_required and not verify_turnstile(
                request.POST.get("cf-turnstile-response", ""), guard_ip
            ):
                login_block_reason = "challenge"
                messages.error(
                    request,
                    _("Please complete the verification challenge to continue."),
                )
            else:
                user = authenticate(
                    request,
                    username=username,
                    password=request.POST.get("password"),
                )
        if user:
            # Pillar 1 (Identity): per-tenant passkey-only enforcement.
            # If the user's role is in PASSKEY_ONLY_ROLES, refuse password
            # auth even when credentials check out — they must come in
            # through the WebAuthn passkey flow. This prevents password-
            # phishing or password-stuffing attacks against high-trust
            # roles (super-admin, finance-admin, …).
            passkey_only_roles = tuple(
                str(r).strip().upper()
                for r in (getattr(settings, "PASSKEY_ONLY_ROLES", ()) or ())
                if str(r).strip()
            )
            user_role = (getattr(user, "role", "") or "").strip().upper()
            if passkey_only_roles and user_role in passkey_only_roles:
                messages.error(
                    request,
                    _(
                        "Password sign-in is disabled for your role. "
                        "Please use your passkey to continue."
                    ),
                )
                # No standalone "passkey-login" landing page exists today —
                # passkey ceremonies happen at /mfa/passkey/authentication/*
                # API endpoints invoked from the login page JS. Bounce back
                # to the login page; the flash message tells the user to use
                # the "Sign in with passkey" button there.
                login_url = reverse("accounts:login")
                if next_url:
                    return redirect(login_url + "?next=" + next_url)
                return redirect(login_url)

            login(request, user)

            # Successful sign-in clears the brute-force counters.
            login_guard.clear_attempts(request, username)
            request.session["auth_failed_attempts"] = 0

            # Tenant-aware: ensure session school_id and membership (Phase 2).
            school = getattr(request, "school", None)
            if school:
                from apps.schools.models import SchoolMembership

                if not SchoolMembership.objects.filter(
                    user=user, school=school
                ).exists():
                    request.session.pop("school_id", None)
                    if (
                        not getattr(user, "is_superuser", False)
                        and (getattr(user, "role", "") or "").upper() != User.Role.SUPERADMIN
                    ):
                        messages.warning(
                            request, _("You do not have access to this school.")
                        )
                        return redirect(reverse("accounts:school_picker"))
            else:
                from apps.schools.models import SchoolMembership

                primary = (
                    # tenant-isolation-allow: login flow — selecting which tenant the user belongs to (no school context yet); filtered by user
                    SchoolMembership.objects.filter(user=user, is_primary=True)
                    .select_related("school")
                    .first()
                )
                first_m = (
                    # tenant-isolation-allow: login flow — selecting first available tenant for the user; filtered by user
                    SchoolMembership.objects.filter(user=user)
                    .select_related("school")
                    .first()
                )
                if primary:
                    request.session["school_id"] = str(primary.school_id)
                elif first_m:
                    request.session["school_id"] = str(first_m.school_id)

            # Security Powerhouse: log successful login (tenant-scoped audit).
            try:
                from apps.accounts.security_audit import log_security_event
                from apps.accounts.models import SecurityAuditLog

                log_security_event(
                    user,
                    SecurityAuditLog.EventType.LOGIN,
                    request=request,
                    school=getattr(request, "school", None),
                )
                # Impossible-travel check: deferred to ImpossibleTravelMiddleware (single trigger).
                request._post_login_user = user
            except (AttributeError, DatabaseError, ImportError):
                pass

            # Enforce requires_password_change (e.g. after Emergency Lockdown).
            if getattr(user, "requires_password_change", False):
                password_change_url = reverse("accounts:password_change")
                if next_url:
                    from django.utils.http import url_has_allowed_host_and_scheme

                    if url_has_allowed_host_and_scheme(
                        next_url, allowed_hosts={request.get_host()}
                    ):
                        request.session["password_change_next"] = next_url
                messages.warning(request, _("You must set a new password to continue."))
                return redirect(password_change_url)

            # MFA enforcement: if required or configured, route to setup/verify first.
            try:
                from django_otp import user_has_device
                from django_otp.plugins.otp_totp.models import TOTPDevice

                site = get_effective_site_settings(request=request)
                require_all_staff = getattr(site, "require_mfa_all_staff", False)
                required_roles = getattr(site, "require_mfa_roles", None) or []

                role = (getattr(user, "role", "") or "").upper()
                must_have_mfa = False
                if require_all_staff and user.is_staff:
                    must_have_mfa = True
                elif required_roles:
                    required_normalized = [
                        r.upper() if isinstance(r, str) else str(r).upper()
                        for r in required_roles
                    ]
                    if role in required_normalized:
                        must_have_mfa = True

                try:
                    has_device = user_has_device(user, confirmed=True)
                except TypeError:
                    has_device = user_has_device(user)
                if not has_device:
                    has_device = TOTPDevice.objects.filter(
                        user=user, confirmed=True
                    ).exists()

                def _mfa_remembered():
                    until_raw = request.session.get("mfa_verified_until")
                    if not until_raw:
                        return False
                    try:
                        until_dt = timezone.datetime.fromisoformat(until_raw)
                        if timezone.is_naive(until_dt):
                            until_dt = timezone.make_aware(
                                until_dt, timezone.get_current_timezone()
                            )
                        if timezone.now() <= until_dt:
                            return True
                    except (TypeError, ValueError):
                        pass
                    request.session.pop("mfa_verified_until", None)
                    return False

                if must_have_mfa and not has_device:
                    mfa_setup_url = reverse("accounts:mfa_setup")
                    if next_url:
                        return redirect(mfa_setup_url + "?next=" + next_url)
                    return redirect(mfa_setup_url)

                if (has_device or must_have_mfa) and not _mfa_remembered():
                    if next_url:
                        request.session["mfa_next"] = next_url
                    return redirect(reverse("accounts:mfa_verify"))
            except ACCOUNTS_SOFT_FAILURES:
                pass

            # When on base domain and user has a school membership, send them to tenant subdomain (Backend is subdomain-only)
            if not getattr(request, "school", None):
                try:
                    from apps.schools.models import SchoolMembership
                    from apps.schools.tenant_url import (
                        is_base_domain,
                        build_tenant_backend_url,
                    )

                    if is_base_domain(request):
                        m = (
                            # tenant-isolation-allow: post-login redirect — picking the user's primary tenant subdomain to redirect to
                            SchoolMembership.objects.filter(user=user)
                            .select_related("school")
                            .order_by("-is_primary")
                            .first()
                        )
                        if m and m.school:
                            if next_url:
                                from django.utils.http import (
                                    url_has_allowed_host_and_scheme,
                                )

                                if url_has_allowed_host_and_scheme(
                                    next_url, allowed_hosts={request.get_host()}
                                ):
                                    target = build_tenant_backend_url(
                                        request, m.school, path=next_url
                                    )
                                else:
                                    target = build_tenant_backend_url(request, m.school)
                            else:
                                target = build_tenant_backend_url(request, m.school)
                            return redirect(target)
                except ACCOUNTS_SOFT_FAILURES:
                    pass

            if next_url:
                return redirect(next_url)
            return redirect(reverse("accounts:redirect"))

        # Reached only when sign-in did not succeed. Count a genuine credential
        # failure — locked / challenge-failed requests already flashed their own
        # message and must NOT be tallied as a password attempt.
        if login_block_reason is None:
            login_guard.record_failed_attempt(request, username)
            request.session["auth_failed_attempts"] = (
                int(request.session.get("auth_failed_attempts", 0) or 0) + 1
            )
            messages.error(request, _("Invalid username or password."))
    context = {
        "LOGIN_SSO_INTEGRATIONS": _get_login_sso_integrations(request),
        "is_manager_host": getattr(request, "public_host_kind", None) == "manager",
        "turnstile_site_key": getattr(settings, "TURNSTILE_SITE_KEY", ""),
        "turnstile_required": _login_challenge_required(request),
    }
    if getattr(request, "public_host_kind", None) == "manager":
        try:
            from apps.schools.tenant_url import build_public_absolute_url

            context["public_site_url"] = build_public_absolute_url(request, "/")
        except ACCOUNTS_SOFT_FAILURES:
            context["public_site_url"] = settings.PUBLIC_SITE_URL
    else:
        context["public_site_url"] = None
    template = (
        "auth/manager_login.html"
        if getattr(request, "public_host_kind", None) == "manager"
        else "auth/login.html"
    )
    return render(request, template, context)


def logout_view(request):
    if request.user.is_authenticated:
        try:
            from apps.accounts.security_audit import log_security_event
            from apps.accounts.models import SecurityAuditLog

            log_security_event(
                request.user,
                SecurityAuditLog.EventType.LOGOUT,
                request=request,
            )
        except (ImportError, AttributeError, DatabaseError):
            pass
    logout(request)
    return redirect(reverse("accounts:login"))


@login_required
def school_picker(request):
    """Let user pick which school to use when they have multiple or no access on current host."""
    from apps.schools.models import SchoolMembership

    memberships = (
        # tenant-isolation-allow: school picker — listing the user's tenant memberships to choose from
        SchoolMembership.objects.filter(user=request.user)
        .select_related("school")
        .order_by("-is_primary", "school__name")
    )
    if request.method == "POST":
        school_id = (request.POST.get("school_id") or "").strip()
        for m in memberships:
            if str(m.school_id) == school_id:
                request.session["school_id"] = school_id
                next_url = (
                    request.POST.get("next")
                    or request.GET.get("next")
                    or reverse("accounts:redirect")
                )
                from django.utils.http import url_has_allowed_host_and_scheme

                if url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()}
                ):
                    return redirect(next_url)
                return redirect("accounts:redirect")
        messages.warning(request, _("Invalid school."))
    context = {"memberships": memberships}
    if not memberships:
        return render(request, "auth/school_picker.html", context)
    return render(request, "auth/school_picker.html", context)


@ratelimit(key="ip", rate="10/h", method="POST", block=True)
def claim_invite(request):
    from apps.portal.services import link_guardian_via_invite

    if not getattr(request, "school", None):
        messages.info(
            request, _("Claim invite is available only inside a school workspace.")
        )
        return redirect("global_login_discovery")

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
            f"Welcome! You are now linked to {invite.student} and can view reports/finance.",
        )
        return redirect("portal:parent_dashboard")

    return render(request, "accounts/claim_invite.html", {"form": form})


# Phase E (optional): School-facing Request Waiver — form and view
class RequestWaiverForm(forms.Form):
    """Reason and optional proof file for a subscription waiver request."""

    reason = forms.CharField(
        required=True,
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "e.g. NGO / non-profit partnership, pilot program",
            }
        ),
        label="Reason for waiver",
    )
    proof_file = forms.FileField(required=False, label="Proof document (optional)")


@login_required
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_http_methods(["GET", "POST"])
def request_waiver(request):
    """
    Phase E (optional): School staff submit a waiver request (reason + optional proof).
    Super Admin approves/denies in Django admin (WaiverRequest).
    """
    from apps.siteconfig.models import WaiverRequest as WaiverRequestModel

    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, _("Select a school first."))
        return redirect(reverse("accounts:backend_dashboard"))
    if request.method == "POST":
        form = RequestWaiverForm(request.POST, request.FILES)
        if form.is_valid():
            proof = form.cleaned_data.get("proof_file")
            WaiverRequestModel.objects.create(
                school=school,
                reason=(form.cleaned_data["reason"] or "").strip()[:2000],
                proof_file=proof,
                status=WaiverRequestModel.Status.PENDING,
            )
            messages.success(
                request,
                _("Your waiver request has been submitted. Platform support will review it and notify you."),
            )
            return redirect("accounts:backend_dashboard")
    else:
        form = RequestWaiverForm()
    return render(
        request,
        "accounts/request_waiver.html",
        {
            "form": form,
            "school": school,
            "breadcrumbs": [
                {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
                {"label": "Request subscription waiver", "url": "", "active": True},
            ],
        },
    )


# Phase 10 — 2.1 / §3: Re-export decomposed views so urls.py and other importers keep working
