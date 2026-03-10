from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import PasswordChangeView as DjangoPasswordChangeView
from django.db.models import Avg, Count, Q
from django.shortcuts import redirect, render, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import reverse, reverse_lazy, NoReverseMatch
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils import translation
import json
from django_ratelimit.decorators import ratelimit
from config.admin import admin_site
from apps.finance.models import Invoice, ReferralReward, PaymentReminder, Notification as FinanceNotification
from apps.finance.services import finance_dashboard_data
from apps.people.models import StudentGuardian, StudentProfile, TeacherAttendance, TeacherProfile, Badge, BadgeType
from apps.academics.models import AcademicYear, Classroom
from apps.reports.models import TermPublishStatus
from apps.siteconfig.models import SiteSettings, default_backend_feature_flags
from apps.academics.services import get_active_year_and_term
from apps.academics.services_year_setup import clone_academic_year
from apps.accounts.decorators import permission_required
from apps.dashboard.context import build_dashboard_extras
from apps.dashboard.recommendation_service import get_recommended_next_steps
from apps.siteconfig.templatetags.admin_health import admin_section_stats
from apps.siteconfig.templatetags.admin_kpis import admin_kpis
from apps.siteconfig.models_dashboard import get_dashboard_widget_metadata, DashboardWidget
from apps.siteconfig.dashboard_views import effective_chart_types
from apps.accounts.utils import get_dashboard_context
from apps.platform_runtime.helpers import get_effective_flags, get_effective_site_settings

from .forms import (
    ClaimInviteAccountForm,
    EditRoleForm,
    PermissionForm,
    RoleForm,
    TemporaryRoleGrantForm,
    UserPermissionForm,
    UserRoleForm,
)
from .models import AccessRole, Permission, User, TemporaryRoleGrant, RolloverProposal, RolloverProposalItem


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
        by_class = {}
        for ta in qs:
            sa = ta.subject_assignment
            if not sa:
                continue
            cname = sa.classroom.name if sa.classroom else "-"
            if cname not in by_class:
                by_class[cname] = []
            by_class[cname].append(sa.subject.name if sa.subject else "-")
        assignments = [{"classroom": c, "subjects": list(set(subs))} for c, subs in sorted(by_class.items())]

    def _node_payload(profile, relation):
        if not profile:
            return None
        target_user = getattr(profile, "user", None)
        display_name = (
            (target_user.get_full_name() if target_user and hasattr(target_user, "get_full_name") else "")
            or (target_user.username if target_user else "")
            or "Staff"
        )
        initials_parts = display_name.strip().split()
        initials = "".join(part[:1].upper() for part in initials_parts[:2]) or "S"
        photo_url = ""
        profile_photo = getattr(profile, "profile_photo", None)
        user_photo = getattr(target_user, "profile_photo", None) if target_user else None
        try:
            if profile_photo and getattr(profile_photo, "url", ""):
                photo_url = profile_photo.url
            elif user_photo and getattr(user_photo, "url", ""):
                photo_url = user_photo.url
        except Exception:
            photo_url = ""
        return {
            "id": profile.pk,
            "name": display_name,
            "title": getattr(profile, "position_title", "") or "Staff member",
            "department": getattr(getattr(profile, "department", None), "name", "") or "",
            "photo_url": photo_url,
            "initials": initials,
            "is_self": bool(target_user and target_user.pk == getattr(user, "pk", None)),
            "relation": relation,
        }

    chain_profiles = get_org_chain_to_staff(teacher)
    chain_nodes = [_node_payload(profile, "chain") for profile in chain_profiles]
    chain_nodes = [node for node in chain_nodes if node]

    direct_reports = list(
        TeacherProfile.objects.filter(
            reports_to=teacher,
            is_active=True,
        )
        .select_related("user", "department")
        .order_by("position_title", "user__first_name", "user__last_name")[:8]
    )
    direct_report_nodes = [_node_payload(profile, "direct_report") for profile in direct_reports]
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
        year_name = getattr(getattr(classroom, "academic_year", None), "name", "") or "-"
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
            site = get_effective_site_settings(request=request)
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
    teacher_profile = TeacherProfile.objects.filter(user=request.user).select_related("department", "reports_to").first()
    if teacher_profile:
        context["org_chain"] = get_org_chain_to_staff(teacher_profile)
    if role == "TEACHER" and teacher_profile:
        context["teacher_org_tree"] = _teacher_org_tree(request.user)
        context["staff_id"] = getattr(teacher_profile, "staff_id", None) or (f"Staff #{request.user.pk}" if teacher_profile else None)
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
            ).filter(
                Q(expiry_at__isnull=True) | Q(expiry_at__gt=tz.now())
            ).select_related("badge_type").order_by("-issued_at")[:20]
        )
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
    except Exception:
        context["can_show_pii"] = True
        context["pii_masked_dob"] = None

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
    """Messages hub: Direct and Groups. Parents use Contact School only (redirected). Students see Direct only. Staff/teachers see both."""
    role = getattr(request.user, "role", None)
    if role == User.Role.PARENT:
        return redirect(reverse("portal:parent_contact_school"))
    from apps.portal.services import threads_for_user

    # Students: show only Direct tab (conversations with staff); staff/teachers see both
    direct_only = role == User.Role.STUDENT
    if direct_only:
        active_tab = "direct"
        threads = []
    else:
        active_tab = request.GET.get("tab", "groups")
        try:
            threads = threads_for_user(request.user, limit=12)
        except Exception:
            threads = []

    try:
        direct_list = _direct_conversations(request.user)
    except Exception:
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
    return user.is_staff or user.is_superuser or role in (
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
    if not i_am_parent and not i_am_student and not _can_access_direct_messages(request.user):
        return HttpResponseForbidden("You don't have permission to send direct messages.")

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
    if not _can_access_direct_messages(request.user):
        return HttpResponseForbidden("You don't have permission to compose direct messages.")
    from apps.communication.models import Message

    if request.method == "POST":
        recipient_id = request.POST.get("recipient")
        body = (request.POST.get("body") or "").strip()
        subject = (request.POST.get("subject") or "").strip() or "Direct message"
        if not body or not recipient_id:
            messages.error(request, "Select a recipient and enter a message.")
            return redirect("accounts:direct_compose")
        recipient = User.objects.filter(pk=recipient_id, is_active=True).exclude(pk=request.user.pk).first()
        if not recipient:
            messages.error(request, "Selected recipient is not available.")
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
    site = get_effective_site_settings(request=request)
    flags = get_effective_flags(request)
    allowed_roles = [r.upper() for r in flags.get("allowed_roles_entity_import", [])]
    if not flags.get("enable_entity_import", True):
        return HttpResponseForbidden("Entity import is disabled by admin.")
    if allowed_roles:
        role = (getattr(request.user, "role", "") or "").upper()
        if role not in allowed_roles and not (request.user.is_staff or request.user.is_superuser):
            return HttpResponseForbidden("You are not allowed to access Entity Import.")
    return render(request, "accounts/entity_import.html", {
        "BREADCRUMBS": [
            {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
            {"label": "Import & bulk", "url": reverse("accounts:import_hub")},
            {"label": "Entity import", "url": "", "active": True},
        ],
    })


@permission_required("settings.manage")
@user_passes_test(lambda u: u.is_authenticated and (u.is_staff or u.is_superuser or getattr(u, "role", None) == User.Role.ADMIN))
def backend_entity_console(request):
    """Admin-only page for EntityForm/Table beta UI."""
    site = get_effective_site_settings(request=request)
    flags = get_effective_flags(request)
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
    except Exception:
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
            if (getattr(user, "role", "") or "").upper() == "STUDENT":
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

    # Base domain: send users with a school membership to tenant URL (subdomain or /t/<slug>/)
    if not getattr(request, "school", None):
        try:
            from apps.schools.models import SchoolMembership
            from apps.schools.tenant_url import is_base_domain, build_tenant_backend_url
            if is_base_domain(request):
                m = SchoolMembership.objects.filter(user=user).select_related("school").order_by("-is_primary").first()
                if m and m.school:
                    target = build_tenant_backend_url(request, m.school)
                    return redirect(target)
        except Exception:
            pass

    # Respect the user's "Dashboard view" preference (Portal Preferences) when possible.
    dash_view = None
    try:
        from apps.siteconfig.models import UserPreference as PortalUserPreference

        pref = PortalUserPreference.objects.filter(user=user).only("dashboard_view").first()
        dash_view = getattr(pref, "dashboard_view", None)
    except Exception:
        dash_view = None

    from apps.accounts.portal_roles import get_effective_portal_role
    role = get_effective_portal_role(request) or getattr(user, "role", None)

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
    if role == "TEACHER" and not has_teacher_hat(request.user):
        return redirect(reverse("accounts:redirect"))
    if role == "PARENT" and not has_parent_hat(request.user):
        return redirect(reverse("accounts:redirect"))
    request.session[ACTIVE_PORTAL_ROLE_KEY] = role
    try:
        from apps.siteconfig.models import UserPreference
        pref, _ = UserPreference.objects.get_or_create(user=request.user, defaults={})
        pref.last_portal_role = role
        pref.save(update_fields=["last_portal_role", "updated_at"])
    except Exception:
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


@login_required
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def rbac_dashboard(request):
    roles_qs = AccessRole.objects.prefetch_related("permissions").order_by("code")
    permissions_qs = Permission.objects.order_by("code")
    initial_user_roles = {}
    if request.method == "GET" and request.GET.get("user"):
        try:
            u = User.objects.get(pk=request.GET.get("user"))
            initial_user_roles = {"user": u, "roles": list(u.roles.all())}
        except (User.DoesNotExist, ValueError):
            pass

    edit_role_id = None
    edit_role_form = None
    if request.method == "GET" and request.GET.get("edit_role"):
        try:
            edit_role = AccessRole.objects.prefetch_related("permissions").get(pk=request.GET.get("edit_role"))
            edit_role_form = EditRoleForm(role=edit_role)
            edit_role_id = edit_role.pk
        except (AccessRole.DoesNotExist, ValueError):
            pass

    role_form = RoleForm(prefix="role")
    permission_form = PermissionForm(prefix="permission")
    user_role_form = UserRoleForm(prefix="user_role", initial=initial_user_roles or None)
    user_permission_form = UserPermissionForm(prefix="user_permission")
    temporary_grant_form = TemporaryRoleGrantForm(prefix="temp_grant")

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
            else:
                try:
                    initial_user_roles = {"roles": [AccessRole.objects.get(pk=int(pk)) for pk in request.POST.getlist("user_role-roles")]}
                except (ValueError, AccessRole.DoesNotExist):
                    initial_user_roles = {}
        elif form_type == "user_permissions":
            user_permission_form = UserPermissionForm(request.POST, prefix="user_permission")
            if user_permission_form.is_valid():
                user = user_permission_form.cleaned_data["user"]
                permissions = user_permission_form.cleaned_data["permissions"]
                user.feature_permissions.set(permissions)
                messages.success(request, f"Permissions updated for {user.username}.")
                return redirect("accounts:rbac")
        elif form_type == "edit_role":
            edit_role_form = EditRoleForm(request.POST)
            if edit_role_form.is_valid():
                role = get_object_or_404(AccessRole, pk=edit_role_form.cleaned_data["role_id"])
                role.description = edit_role_form.cleaned_data["description"] or ""
                role.permissions.set(edit_role_form.cleaned_data["permissions"])
                role.save()
                messages.success(request, f"Role '{role.name}' updated.")
                return redirect("accounts:rbac")
            edit_role_id = edit_role_form.cleaned_data.get("role_id") or request.POST.get("role_id")
        elif form_type == "temporary_grant":
            temporary_grant_form = TemporaryRoleGrantForm(request.POST, prefix="temp_grant")
            if temporary_grant_form.is_valid():
                from datetime import datetime, time
                user = temporary_grant_form.cleaned_data["user"]
                role = temporary_grant_form.cleaned_data["role"]
                expires_date = temporary_grant_form.cleaned_data["expires_at"]
                valid_from_date = temporary_grant_form.cleaned_data.get("valid_from")
                notes = (temporary_grant_form.cleaned_data.get("notes") or "").strip()[:255]
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

    selected_role_ids = set()
    if initial_user_roles and "roles" in initial_user_roles:
        selected_role_ids = {r.pk for r in initial_user_roles["roles"]}
    elif request.method == "POST" and request.POST.get("form_type") == "user_roles":
        for pk in request.POST.getlist("user_role-roles"):
            try:
                selected_role_ids.add(int(pk))
            except ValueError:
                pass

    now = timezone.now()
    active_temporary_grants = TemporaryRoleGrant.objects.filter(
        expires_at__gt=now,
    ).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=now),
    ).select_related("user", "role", "created_by").order_by("expires_at")[:50]

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
    # Tenant Backend is subdomain-only: on base domain redirect to tenant subdomain
    if not getattr(request, "school", None):
        try:
            from apps.schools.models import SchoolMembership
            from apps.schools.tenant_url import is_base_domain, build_tenant_backend_url
            if is_base_domain(request):
                m = SchoolMembership.objects.filter(user=request.user).select_related("school").order_by("-is_primary").first()
                if m and m.school:
                    return redirect(build_tenant_backend_url(request, m.school))
        except Exception:
            pass

    from .activity_helper import get_recent_activity

    site = get_effective_site_settings(request=request)
    year, term = get_active_year_and_term()

    backend_defaults = default_backend_feature_flags()
    backend_flags = dict(getattr(site, "backend_feature_flags", {}) or {})
    for key, default_val in backend_defaults.items():
        backend_flags.setdefault(key, default_val)

    def _clamp_backend_int(value, default, minimum=3, maximum=12):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = int(default)
        return max(minimum, min(maximum, parsed))

    backend_layout_max_items_per_list = _clamp_backend_int(
        backend_flags.get("backend_layout_max_items_per_list"),
        backend_defaults.get("backend_layout_max_items_per_list", 5),
    )
    backend_max_items_slice = f":{backend_layout_max_items_per_list}"

    backend_module_visibility = {
        "overview": bool(backend_flags.get("backend_module_overview", True)),
        "admin_portal": bool(backend_flags.get("backend_module_admin_portal", True)),
        "welcome": bool(backend_flags.get("backend_module_welcome", True)),
        "enrollment_trends": bool(backend_flags.get("backend_module_enrollment_trends", True)),
        "at_risk_students": bool(backend_flags.get("backend_module_at_risk_students", True)),
        "outstanding_fees": bool(backend_flags.get("backend_module_outstanding_fees", True)),
        "recent_admissions": bool(backend_flags.get("backend_module_recent_admissions", True)),
        "recent_activity": bool(backend_flags.get("backend_module_recent_activity", True)),
        "top_performing": bool(backend_flags.get("backend_module_top_performing", True)),
        "attendance_today": bool(backend_flags.get("backend_module_attendance_today", True)),
        "ops_watch": bool(backend_flags.get("backend_module_ops_watch", True)),
        "quick_links": bool(backend_flags.get("backend_module_quick_links", True)),
        "planner": bool(backend_flags.get("backend_module_planner", True)),
    }
    backend_visual_settings = {
        "show_trend_ribbons": bool(backend_flags.get("backend_viz_show_trend_ribbons", True)),
        "show_progress_rings": bool(backend_flags.get("backend_viz_show_progress_rings", True)),
        "show_rank_sparklines": bool(backend_flags.get("backend_viz_show_rank_sparklines", True)),
    }
    backend_theme_settings = {
        "warm_palette": bool(backend_flags.get("backend_warm_palette", True)),
        "reduce_card_flatness": bool(backend_flags.get("backend_reduce_card_flatness", True)),
        "high_depth_surfaces": bool(backend_flags.get("backend_high_depth_surfaces", True)),
        "balanced_motion": bool(backend_flags.get("backend_balanced_motion", True)),
        "layout_equal_heights": bool(backend_flags.get("backend_layout_equal_heights", True)),
    }
    from apps.portal.models import PendingGuardianInvite

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
    recent_activities = get_recent_activity(limit=max(backend_layout_max_items_per_list, 5))
    
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
        for section, stats in admin_section_stats({"request": request}).items()
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
        "title": "RunMyCampus",
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
    try:
        from apps.siteconfig.models_dashboard import DashboardUserPreference
        pref, created = DashboardUserPreference.objects.get_or_create(
            user=request.user,
            defaults={"sidebar_collapsed": bool(getattr(site, "default_sidebar_collapsed", False))},
        )
        if created or not pref.pinned_sidebar_items:
            pref.pinned_sidebar_items = [
                "workflow_center",
                "import_grades",
                "documents",
                "preferences",
            ]
            pref.save(update_fields=["pinned_sidebar_items", "updated_at"])
    except Exception:
        pass
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
    chart_enrollment_trend_json = ""
    recent_admissions = []
    top_performing_students = []
    at_risk_students = []
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
    # Dashboard data capping: top N roles by user count (see docs/DASHBOARD_DATA_CAPPING_POLICY.md)
    from apps.dashboard.context import DASHBOARD_CHART_TOP_N
    roles_qs = AccessRole.objects.prefetch_related("permissions", "users").order_by("code")
    role_user_counts = {r.code: r.users.count() for r in roles_qs}
    if role_user_counts:
        sorted_roles = sorted(role_user_counts.items(), key=lambda x: -x[1])[:DASHBOARD_CHART_TOP_N]
        chart_rbac_roles_json = json.dumps({
            "type": "bar",
            "data": {
                "labels": [r[0] for r in sorted_roles],
                "datasets": [{
                    "label": "Users",
                    "data": [r[1] for r in sorted_roles],
                    "backgroundColor": "rgba(13, 110, 253, 0.8)",
                    "borderColor": "#0d6efd",
                    "borderWidth": 1,
                }],
            },
            "options": {"indexAxis": "y"},
        })

    # Enrollment trend + people lists for streamlined backend layout
    try:
        from django.db.models.functions import TruncMonth

        enrollment_qs = StudentProfile.objects.filter(is_active=True, joined_date__isnull=False)
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
            enroll_labels = [item["date"].strftime("%a") for item in attendance_trend[-6:]]
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
    except Exception:
        chart_enrollment_trend_json = ""

    try:
        admissions_qs = StudentProfile.objects.select_related("classroom").filter(is_active=True)
        if year:
            admissions_qs = admissions_qs.filter(academic_year=year)
        for student in admissions_qs.order_by("-updated_at", "-id")[: backend_layout_max_items_per_list]:
            recent_admissions.append(
                {
                    "name": student.get_full_name(),
                    "classroom": getattr(getattr(student, "classroom", None), "name", "") or "Unassigned",
                    "admission_number": student.admission_number or student.student_code or "--",
                }
            )
    except Exception:
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
            full_name = " ".join(
                part for part in [row.get("student__first_name"), row.get("student__last_name")] if part
            ).strip() or "Student"
            score_rows.append(
                {
                    "student_id": row.get("student_id"),
                    "name": full_name,
                    "classroom": row.get("student__classroom__name") or "Unassigned",
                    "score": score,
                }
            )
    except Exception:
        score_rows = []

    score_rows.sort(key=lambda item: item.get("score", 0), reverse=True)
    top_performing_students = score_rows[: backend_layout_max_items_per_list]
    top_score = max((item.get("score", 0) for item in top_performing_students), default=0)
    for item in top_performing_students:
        score_value = float(item.get("score", 0) or 0)
        if top_score <= 0:
            item["ribbon_pct"] = 0
        else:
            item["ribbon_pct"] = max(8, min(100, int(round((score_value / top_score) * 100))))

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
                getattr(getattr(student, "classroom", None), "name", "") if student else ""
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
    except Exception:
        pass

    at_risk_students = list(at_risk_map.values())[: backend_layout_max_items_per_list]
    total_students = max(stats.get("students", 0), 1)
    at_risk_ratio_pct = int(round((len(at_risk_students) / total_students) * 100))

    # Workflow progress and recommended next steps for dashboard (recommendation service)
    workflow_progress = _workflow_progress(year)

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
    if _intent not in VALID_DASHBOARD_INTENTS:
        _intent = "operational"
    recommended_next_steps = get_recommended_next_steps(
        workflow_progress,
        year=year,
        intent=_intent,
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
        "gce_enabled": year and getattr(year, "enable_gce_registration", False) if year else False,
        "chart_finance_status_json": chart_finance_status_json,
        "chart_finance_trend_json": chart_finance_trend_json,
        "chart_attendance_donut_json": chart_attendance_donut_json,
        "chart_rbac_roles_json": chart_rbac_roles_json,
        "chart_enrollment_trend_json": chart_enrollment_trend_json,
        "recent_admissions": recent_admissions,
        "top_performing_students": top_performing_students,
        "at_risk_students": at_risk_students,
        "quick_student_create_url": _safe_reverse("accounts:backend_student_create") if _safe_reverse("accounts:backend_student_create") != "#" else _safe_reverse("admin:people_studentprofile_add"),
        "quick_teacher_create_url": _safe_reverse("accounts:backend_teacher_create") if _safe_reverse("accounts:backend_teacher_create") != "#" else _safe_reverse("admin:people_teacherprofile_add"),
        "breadcrumbs": [{"title": "Backend", "url": reverse("accounts:backend_dashboard"), "icon": "bi-speedometer2"}],
        "BREADCRUMBS": [
            {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
            {"label": "Dashboard", "url": "", "active": True},
        ],
        "SHOW_HEADER_CONTEXT_STRIP": False,
    }
    # W1-6: First-login checklist aligned with Setup Studio (same labels, same deep links); thin entry to Setup Studio.
    try:
        from apps.siteconfig.models_dashboard import DashboardUserPreference
        from apps.customersuccess.services import get_guided_onboarding_steps
        pref, _ = DashboardUserPreference.objects.get_or_create(user=request.user, defaults={"dashboard_layout": {}})
        layout = pref.dashboard_layout or {}
        context["first_login_checklist_show"] = not layout.get("first_login_checklist_dismissed")
        context["first_login_checklist_dismiss_url"] = reverse("accounts:dismiss_first_login_checklist")
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
                    checklist_items.append({"label": _(s.get("label", "")), "url": link})
            setup_studio_url = _safe("siteconfig:guided_onboarding") or "#"
            if setup_studio_url != "#":
                checklist_items.append({"label": _("Setup Studio (all steps)"), "url": setup_studio_url})
            context["first_login_checklist_items"] = checklist_items
        else:
            context["first_login_checklist_items"] = [
                {"label": _("Setup Studio"), "url": _safe("siteconfig:guided_onboarding") or "#"},
            ]
        context["first_login_settings_url"] = _safe("siteconfig:customizer") or _safe("admin:index") or "#"
        context["first_login_sensible_defaults_copy"] = _(
            "We've set up: academic year, terms, default classrooms, and subjects. You can change these in Settings."
        )
    except Exception:
        context["first_login_checklist_show"] = False
        context["first_login_checklist_items"] = []
        context["first_login_checklist_dismiss_url"] = ""
        context["first_login_settings_url"] = "#"
        context["first_login_sensible_defaults_copy"] = ""
    try:
        context.update(build_dashboard_extras(request, base=context))
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("build_dashboard_extras failed: %s", e)
        # Safe defaults so template does not 500; UX plan overview/CTAs/contextual_actions still work when extras succeed
        context.setdefault("primary_ctas", [])
        context.setdefault("overview_cards", [])
        context.setdefault("contextual_actions", [])
        context.setdefault("kpi_strip_cards", [])
    return render(request, "accounts/backend_dashboard.html", context)


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
    if html is not None:
        return HttpResponse(html)

    pending_requests = 0
    try:
        from apps.requests.models import AccessRequest
        pending_requests = AccessRequest.objects.filter(status=AccessRequest.Status.PENDING).count()
    except Exception:
        pass

    enable_offline_mode = False
    offline_queue_metrics = None
    try:
        from apps.siteconfig.models import SiteSettings
        site = get_effective_site_settings(request=request)
        enable_offline_mode = getattr(site, "enable_offline_mode", False)
        if enable_offline_mode:
            from apps.siteconfig.cache_utils import tenant_cache_key
            offline_queue_metrics = cache.get(tenant_cache_key("sms_offline_queue_metrics", request))
    except Exception:
        pass

    template = loader.get_template("accounts/backend_dashboard_status_fragment.html")
    html = template.render({
        "request": request,
        "pending_requests": pending_requests,
        "enable_offline_mode": enable_offline_mode,
        "offline_queue_metrics": offline_queue_metrics,
    })
    cache.set(cache_key, html, BACKEND_STATUS_FRAGMENT_CACHE_TTL)
    return HttpResponse(html)


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def backend_ops_watch_data(request):
    """Lightweight JSON payload for live Ops Watch refresh."""
    site = get_effective_site_settings(request=request)
    backend_defaults = default_backend_feature_flags()
    backend_flags = dict(getattr(site, "backend_feature_flags", {}) or {})
    for key, default_val in backend_defaults.items():
        backend_flags.setdefault(key, default_val)

    if not bool(backend_flags.get("backend_module_ops_watch", True)):
        return JsonResponse({"success": True, "operations_watch": [], "finance_requests": 0, "updated_at": timezone.localtime().isoformat()})

    try:
        max_items = int(backend_flags.get("backend_layout_max_items_per_list", backend_defaults.get("backend_layout_max_items_per_list", 5)))
    except (TypeError, ValueError):
        max_items = int(backend_defaults.get("backend_layout_max_items_per_list", 5))
    max_items = max(3, min(12, max_items))

    pending_approvals_count = 0
    try:
        from apps.requests.models import AccessRequest
        pending_approvals_count = AccessRequest.objects.filter(
            status=AccessRequest.Status.PENDING
        ).count()
    except Exception:
        pending_approvals_count = 0

    base_stats = {
        "pending_referrals": ReferralReward.objects.filter(
            status=ReferralReward.Status.PENDING
        ).count(),
        "overdue_invoices": Invoice.objects.filter(status=Invoice.Status.OVERDUE).count(),
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
        site = get_effective_site_settings(request=request)
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
    """Hub linking to Entity Import, Grade Import, Migration Wizard, templates."""
    return render(request, "accounts/import_hub.html", {
        "BREADCRUMBS": [
            {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
            {"label": "Import & bulk", "url": "", "active": True},
        ],
    })


# Plan XII: Migration Hub — upload → field mapping → preview → run
MIGRATION_TYPES = {
    "students": {
        "label": "Students",
        "target_fields": ["first_name", "last_name", "admission_number", "academic_year", "classroom", "specialty", "status"],
        "required": ["first_name", "last_name"],
    },
    "grades": {
        "label": "Grades",
        "target_fields": [
            "student_code", "subject_assignment_id", "term_id", "teacher_username",
            "seq1", "seq2", "exam", "mock", "practical", "test1", "test2", "remarks",
        ],
        "required": ["student_code", "subject_assignment_id", "term_id"],
    },
}


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_http_methods(["GET", "POST"])
def migration_wizard(request):
    """
    One-click data migration: upload CSV → optional field mapping → preview → run.
    Backed by existing bulk-preview/bulk-commit (students) and evals apply_import (grades).
    """
    import csv
    import io
    import json

    session_key = "migration_wizard"
    wizard_data = request.session.get(session_key) or {}

    if request.method == "GET" and request.GET.get("clear") == "1":
        request.session.pop(session_key, None)
        return redirect("accounts:migration_wizard")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "select_system":
            source_system = (request.POST.get("source_system") or "").strip()
            allowed = ("powerschool", "blackbaud", "veracross", "infinite_campus", "other")
            if source_system not in allowed:
                source_system = "other"
            request.session[session_key] = {**wizard_data, "source_system": source_system}
            return redirect("accounts:migration_wizard")

        if action == "upload":
            from apps.automation.models import MigrationProfile
            profile_slug = request.POST.get("profile_slug")
            if profile_slug:
                profile = MigrationProfile.objects.filter(slug=profile_slug, is_active=True).first()
                if profile:
                    migration_type = profile.domain  # "students", "grades", etc.
                else:
                    migration_type = request.POST.get("migration_type") or "students"
                    profile_slug = None
            else:
                migration_type = request.POST.get("migration_type")
                profile_slug = None
            if migration_type not in MIGRATION_TYPES:
                messages.error(request, "Invalid migration type.")
                return redirect("accounts:migration_wizard")
            file_obj = request.FILES.get("file")
            if not file_obj:
                messages.error(request, "Please upload a CSV file.")
                return redirect("accounts:migration_wizard")
            try:
                content = file_obj.read().decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(content))
                headers = list(reader.fieldnames or [])
                rows = list(reader)[:500]
            except Exception as e:
                messages.error(request, f"Could not read the CSV file. Use UTF-8 encoding and check the file is not corrupted. Details: {e}")
                return redirect("accounts:migration_wizard")
            request.session[session_key] = {
                "source_system": wizard_data.get("source_system", "other"),
                "migration_type": migration_type,
                "profile_slug": profile_slug,
                "headers": headers,
                "rows": rows,
                "row_count": len(rows),
            }
            return redirect("accounts:migration_wizard")

        if action == "dry_run" and wizard_data:
            migration_type = wizard_data.get("migration_type")
            rows = wizard_data.get("rows", [])
            mapping_json = request.POST.get("mapping")
            if not rows:
                messages.error(request, "No data to validate. Upload again.")
                return redirect("accounts:migration_wizard")
            mapping = json.loads(mapping_json) if mapping_json else {}
            transformed = []
            for row in rows:
                t = {}
                for csv_col, target_field in mapping.items():
                    if target_field and target_field != "__skip__":
                        t[target_field] = row.get(csv_col, "")
                transformed.append(t)
            from apps.accounts.migration_services import run_dry_run
            school = getattr(request, "school", None)
            scorecard = run_dry_run(
                school, migration_type, transformed,
                user=request.user, create_audit=True,
                legacy_snapshot=transformed,
            )
            request.session["migration_wizard_scorecard"] = scorecard
            return redirect("accounts:migration_wizard")

        if action == "run" and wizard_data:
            migration_type = wizard_data.get("migration_type")
            rows = wizard_data.get("rows", [])
            mapping_json = request.POST.get("mapping")
            if not rows:
                messages.error(request, "No data to import. Upload again.")
                request.session.pop(session_key, None)
                return redirect("accounts:migration_wizard")
            mapping = json.loads(mapping_json) if mapping_json else {}
            transformed = []
            for row in rows:
                t = {}
                for csv_col, target_field in mapping.items():
                    if target_field and target_field != "__skip__":
                        t[target_field] = row.get(csv_col, "")
                transformed.append(t)
            from apps.accounts.migration_services import run_migration_start, run_migration_finish
            school = getattr(request, "school", None)
            run = run_migration_start(
                school, migration_type, len(transformed),
                user=request.user, legacy_snapshot=transformed,
            )
            result = {"created": 0, "updated": 0, "error_count": 0, "errors": []}
            if migration_type == "students":
                try:
                    from django.test import Client
                    from django.urls import reverse as rev
                    client = Client()
                    client.force_login(request.user)
                    for k, v in request.session.items():
                        client.session[k] = v
                    client.session.save()
                    url = rev("api:entity-student-bulk-commit")
                    resp = client.post(url, data=json.dumps({"rows": transformed}), content_type="application/json")
                    try:
                        data = json.loads(resp.content.decode("utf-8"))
                    except Exception:
                        data = {}
                    if resp.status_code in (200, 201):
                        result["created"] = len(data.get("created", []))
                        result["errors"] = data.get("errors", [])
                        result["error_count"] = len(result["errors"])
                        result["rollback_snapshot"] = {"created_ids": data.get("created", [])}
                        run_migration_finish(run, result)
                        p = result.get("parity", {})
                        messages.success(request, f"Students: created {result['created']}, errors {result['error_count']}. Parity: {p.get('total_processed', 0)} rows processed.")
                    else:
                        result["error_count"] = len(transformed)
                        result["error_message"] = data.get("error") or "Student import failed."
                        result["errors"] = [result["error_message"]]
                        run_migration_finish(run, result)
                        messages.error(request, result["error_message"])
                except Exception as e:
                    result["error_count"] = len(transformed)
                    result["error_message"] = str(e)
                    result["errors"] = [str(e)]
                    run_migration_finish(run, result)
                    messages.error(request, f"Import failed: {e}. Check your CSV format and mapping.")
            elif migration_type == "grades":
                from apps.academics.services import get_active_year_and_term
                active_year, _ = get_active_year_and_term()
                if not active_year:
                    result["error_count"] = len(transformed)
                    result["errors"] = ["No active academic year set."]
                    run_migration_finish(run, result)
                    messages.error(request, "No active academic year. Set one in Academics.")
                else:
                    try:
                        from apps.evals.importers import apply_import, preview_import
                        preview = preview_import(transformed)
                        apply_result = apply_import(preview, active_year)
                        result["created"] = apply_result.get("created", 0)
                        result["updated"] = apply_result.get("updated", 0)
                        result["duration_seconds"] = apply_result.get("duration_seconds", 0)
                        result["error_count"] = len(transformed) - result["created"] - result["updated"]
                        result["rollback_snapshot"] = {
                            "created_ids": apply_result.get("created_ids", []),
                            "updated_ids": apply_result.get("updated_ids", []),
                        }
                        run_migration_finish(run, result)
                        p = result.get("parity", {})
                        messages.success(request, f"Grades: created {result['created']}, updated {result['updated']}, errors {result['error_count']}. Parity: {p.get('total_processed', 0)} rows processed.")
                    except Exception as e:
                        result["error_count"] = len(transformed)
                        result["error_message"] = str(e)
                        result["errors"] = [str(e)]
                        run_migration_finish(run, result)
                        messages.error(request, f"Grade import failed. Details: {e}")
            else:
                run_migration_finish(run, result)
            request.session.pop(session_key, None)
            return redirect("accounts:migration_wizard")

        if request.POST.get("action") == "clear":
            request.session.pop(session_key, None)
            return redirect("accounts:migration_wizard")

    # GET or after POST without run
    from apps.automation.models import MigrationProfile
    source_system = wizard_data.get("source_system") or "other"
    # Profiles for dropdown: match source_system or generic (null/other)
    if source_system == "other":
        profiles = list(
            MigrationProfile.objects.filter(
                is_active=True,
                slug__in=("students", "grades"),
                source_system__isnull=True,
            ).order_by("sort_order", "slug")
        )
    else:
        profiles = list(
            MigrationProfile.objects.filter(is_active=True, source_system=source_system).order_by("sort_order", "slug")
        )
    if not profiles:
        profiles = list(
            MigrationProfile.objects.filter(is_active=True, slug__in=("students", "grades")).order_by("sort_order")[:2]
        )
    profile_choices = [(p.slug, p.name) for p in profiles]
    migration_types_for_dropdown = dict(profile_choices) if profile_choices else MIGRATION_TYPES

    has_data = bool(wizard_data.get("rows"))
    config = MIGRATION_TYPES.get(wizard_data.get("migration_type", "")) or {}
    profile_slug = wizard_data.get("profile_slug")
    schema_hints = {}
    if has_data:
        if profile_slug:
            prof = MigrationProfile.objects.filter(slug=profile_slug).first()
            if prof and isinstance(prof.config, dict):
                schema_hints = prof.config.get("schema_hints") or {}
        if not schema_hints and headers and config.get("target_fields"):
            from apps.accounts.migration_services import infer_schema_mapping
            schema_hints = infer_schema_mapping(headers, config.get("target_fields", []))
    headers = wizard_data.get("headers", [])
    rows = wizard_data.get("rows", [])[:15]
    preview_matrix = []
    for row in rows:
        preview_matrix.append([str(row.get(h, "")) for h in headers])
    scorecard = request.session.pop("migration_wizard_scorecard", None)
    if scorecard and scorecard.get("validation_issues"):
        # Phase C: build drill-down list for template (category, label, issues)
        vi = scorecard["validation_issues"]
        labels = {"duplicates": "Duplicates", "missing_required": "Missing required fields", "invalid_refs": "Invalid references"}
        scorecard["validation_issues_list"] = [
            {"category": cat, "label": labels.get(cat, cat), "issues": vi.get(cat, [])}
            for cat in ("duplicates", "missing_required", "invalid_refs")
            if vi.get(cat)
        ]
    schema_hints_json = json.dumps(schema_hints)
    return render(request, "accounts/migration_wizard.html", {
        "migration_types": MIGRATION_TYPES,
        "migration_type_choices": profile_choices,
        "wizard_data": wizard_data,
        "has_data": has_data,
        "source_system": source_system,
        "source_system_choices": [
            ("powerschool", "PowerSchool"),
            ("blackbaud", "Blackbaud"),
            ("veracross", "Veracross"),
            ("infinite_campus", "Infinite Campus"),
            ("other", "Other"),
        ],
        "target_fields": config.get("target_fields", []),
        "required_fields": config.get("required", []),
        "preview_matrix": preview_matrix,
        "scorecard": scorecard,
        "schema_hints": schema_hints,
        "schema_hints_json": schema_hints_json,
    })


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_http_methods(["GET"])
def migration_run_list(request):
    """Section 11.1: List migration runs for this school with links to read-only legacy view and rollback UI."""
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "No school context.")
        return redirect("accounts:backend_dashboard")
    from apps.automation.models import MigrationRun
    runs = MigrationRun.objects.filter(school=school).select_related("triggered_by").order_by("-started_at")[:50]
    return render(request, "accounts/migration_run_list.html", {
        "runs": runs,
        "school": school,
    })


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_http_methods(["POST"])
def migration_rollback(request, run_id):
    """Section 11.1: Trigger rollback for a migration run (UI for MigrationRun.trigger_rollback)."""
    if request.method != "POST":
        return redirect("accounts:migration_run_list")
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "No school context.")
        return redirect("accounts:backend_dashboard")
    from apps.automation.models import MigrationRun
    run = get_object_or_404(MigrationRun, pk=run_id, school=school)
    if not run.can_rollback:
        messages.error(request, "This run cannot be rolled back (dry run, already rolled back, or no snapshot).")
        return redirect("accounts:migration_run_list")
    rollback_run, result = run.trigger_rollback(user=request.user)
    if result.get("success"):
        messages.success(request, f"Rollback created (run #{rollback_run.pk}). {result.get('message', '')} Reverted: {result.get('reverted_count', 0)}.")
    else:
        messages.error(request, result.get("message", "Rollback failed."))
    return redirect("accounts:migration_run_list")


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_http_methods(["GET"])
def migration_legacy_view(request, run_id):
    """Section 11.1: Read-only legacy view — show uploaded rows snapshot for a migration run."""
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "No school context.")
        return redirect("accounts:backend_dashboard")
    from apps.automation.models import MigrationRun
    run = get_object_or_404(MigrationRun, pk=run_id, school=school)
    raw_rows = (run.legacy_snapshot or {}).get("rows") or []
    headers = list(raw_rows[0].keys()) if raw_rows else []
    rows_matrix = [[r.get(h, "") for h in headers] for r in raw_rows]
    return render(request, "accounts/migration_legacy_view.html", {
        "run": run,
        "rows_matrix": rows_matrix,
        "headers": headers,
    })


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_http_methods(["GET", "POST"])
def legacy_data_cleaner_view(request):
    """Section 11.1: Legacy data cleaner — detect and optionally clean legacy/invalid data."""
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "No school context.")
        return redirect("accounts:backend_dashboard")
    from apps.accounts.legacy_data_cleaner import detect_legacy_issues, clean_legacy_data
    if request.method == "POST" and request.POST.get("action") == "clean":
        dry_run = request.POST.get("dry_run") == "1"
        result = clean_legacy_data(school, dry_run=dry_run)
        messages.success(request, f"Cleaner run (dry_run={dry_run}). Actions: {len(result.get('actions', []))}.")
        return render(request, "accounts/legacy_data_cleaner.html", {
            "school": school,
            "issues": detect_legacy_issues(school),
            "clean_result": result,
        })
    issues = detect_legacy_issues(school)
    return render(request, "accounts/legacy_data_cleaner.html", {
        "school": school,
        "issues": issues,
        "clean_result": None,
    })


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def workflow_center(request):
    """
    Operator-friendly entry point to the end-to-end school workflow.
    Keeps admins out of scattered menus and makes the Cameroon-first lifecycle discoverable.
    Every link is resolved defensively so one broken URL does not 500 the page.
    """
    site = get_effective_site_settings(request=request)
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
        carry_forward_arrears_check = request.POST.get("carry_forward_arrears") == "on"
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
        site = get_effective_site_settings(request=request)
        flags = get_effective_flags(request)
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
        if carry_forward_arrears_check and flags.get("carry_forward_arrears_on_rollover", True):
            try:
                from apps.finance.services import carry_forward_arrears
                arrears_created = carry_forward_arrears(source_year, target_year)
                if arrears_created:
                    messages.success(
                        request,
                        f"Created {arrears_created} opening balance (arrears) invoice(s) in {target_year.name}.",
                    )
            except Exception as e:
                messages.error(
                    request,
                    f"Arrears carry-forward failed: {e}. Please check Finance configuration.",
                )
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
    context = {"years": years, "rows": [], "source_year": None, "target_year": None, "target_classrooms": [], "checklist": [], "block_promotion_if_outstanding_returns": False, "carry_forward_arrears_on_rollover": False}
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
            site = get_effective_site_settings(request=request)
            context["block_promotion_if_outstanding_returns"] = (
                get_effective_flags(request).get("block_promotion_if_outstanding_returns", False)
            )
            context["carry_forward_arrears_on_rollover"] = (
                (getattr(site, "backend_feature_flags", None) or {}).get("carry_forward_arrears_on_rollover", True)
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
    context["rollover_queue_url"] = reverse("accounts:rollover_queue")
    return render(request, "accounts/rollover_year.html", context)


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_http_methods(["GET"])
def rollover_queue(request):
    """Plan II: List PENDING and APPROVED rollover proposals for the current school."""
    school = getattr(request, "school", None)
    school_id = school.pk if school else None
    if not school_id:
        messages.error(request, "School context required.")
        return redirect("accounts:rollover_year")
    proposals = list(
        RolloverProposal.objects.filter(school_id=school_id)
        .exclude(status__in=[RolloverProposal.Status.APPLIED, RolloverProposal.Status.CANCELLED])
        .select_related("source_year", "target_year", "created_by")
        .order_by("-created_at")[:50]
    )
    return render(request, "accounts/rollover_queue.html", {"proposals": proposals})


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_http_methods(["GET", "POST"])
def rollover_proposal_detail(request, proposal_id):
    """Plan II: Review/edit proposal items (approved_next_classroom, is_graduate) and Approve or Apply."""
    proposal = get_object_or_404(RolloverProposal, pk=proposal_id)
    school = getattr(request, "school", None)
    if not school or proposal.school_id != school.pk:
        return HttpResponseForbidden()
    target_classrooms = list(
        Classroom.objects.filter(academic_year=proposal.target_year).order_by("name")
    )
    items = list(
        RolloverProposalItem.objects.filter(proposal=proposal)
        .select_related("student", "student__classroom", "suggested_next_classroom", "approved_next_classroom")
        .order_by("student__last_name", "student__first_name")
    )
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            for item in items:
                key_room = f"classroom_{item.id}"
                key_graduate = f"graduate_{item.id}"
                room_id = request.POST.get(key_room)
                if request.POST.get(key_graduate) == "on":
                    item.is_graduate = True
                    item.approved_next_classroom_id = None
                else:
                    item.is_graduate = False
                    if room_id:
                        try:
                            item.approved_next_classroom_id = int(room_id)
                        except (ValueError, TypeError):
                            item.approved_next_classroom_id = item.suggested_next_classroom_id
                    else:
                        item.approved_next_classroom_id = item.suggested_next_classroom_id
                item.save(update_fields=["is_graduate", "approved_next_classroom_id"])
            proposal.status = RolloverProposal.Status.APPROVED
            proposal.approved_at = timezone.now()
            proposal.approved_by = request.user
            proposal.save(update_fields=["status", "approved_at", "approved_by"])
            messages.success(request, "Rollover proposal approved. You can now Apply it.")
            return redirect("accounts:rollover_proposal_detail", proposal_id=proposal_id)
        if action == "apply":
            lock_source = request.POST.get("lock_source") == "on"
            notify_parents = request.POST.get("notify_parents") == "on"
            allow_outstanding = request.POST.get("allow_outstanding_returns") == "on"
            carry_arrears = request.POST.get("carry_forward_arrears") == "on"
            from apps.accounts.tasks import apply_rollover_proposal
            apply_rollover_proposal.apply(
                args=[proposal_id],
                kwargs=dict(lock_source=lock_source, notify_parents=notify_parents, allow_outstanding_returns=allow_outstanding, carry_forward_arrears=carry_arrears),
            )
            messages.success(request, "Rollover applied. Students have been moved to the target year.")
            return redirect("accounts:rollover_queue")
    return render(
        request,
        "accounts/rollover_proposal_detail.html",
        {"proposal": proposal, "items": items, "target_classrooms": target_classrooms},
    )


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_http_methods(["POST"])
def rollover_prepare(request):
    """Plan II: Enqueue or run prepare_rollover_proposal and redirect to proposal detail or queue."""
    source_id = request.POST.get("source_year")
    target_id = request.POST.get("target_year")
    if not source_id or not target_id:
        messages.error(request, "Select source and target year.")
        return redirect("accounts:rollover_year")
    source_year = get_object_or_404(AcademicYear, id=source_id)
    target_year = get_object_or_404(AcademicYear, id=target_id)
    school = getattr(request, "school", None)
    school_id = school.pk if school else None
    if not school_id:
        messages.error(request, "School context required.")
        return redirect("accounts:rollover_year")
    if getattr(source_year, "is_locked", False):
        messages.error(request, "Source year is locked.")
        return redirect("accounts:rollover_year")
    from apps.accounts.tasks import prepare_rollover_proposal
    result = prepare_rollover_proposal.apply(
        args=[school_id, source_year.id, target_year.id],
        kwargs={"created_by_id": request.user.pk},
    )
    if getattr(result, "result", {}).get("ok"):
        proposal_id = result.result.get("proposal_id")
        if proposal_id:
            messages.success(request, f"Rollover proposal created with {result.result.get('items', 0)} students. Review and approve below.")
            return redirect("accounts:rollover_proposal_detail", proposal_id=proposal_id)
    messages.error(request, (getattr(result, "result", None) or {}).get("error", "Failed to prepare proposal."))
    return redirect("accounts:rollover_year")


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def academic_rules(request):
    """
    Single page showing promotion thresholds, grading scale, and who can edit grades (academic rules summary).
    """
    from apps.reports.models import PromotionRule

    site = get_effective_site_settings(request=request)
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


class PasswordChangeView(DjangoPasswordChangeView):
    """Clear requires_password_change after successful change (Security Powerhouse)."""
    success_url = reverse_lazy("accounts:password_change_done")

    def form_valid(self, form):
        from apps.accounts.models import User
        User.objects.filter(pk=form.user.pk).update(requires_password_change=False)
        return super().form_valid(form)

    def get_success_url(self):
        next_url = self.request.session.pop("password_change_next", None)
        if next_url:
            from django.utils.http import url_has_allowed_host_and_scheme
            if url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}):
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
            lang = (locale.get("default_language") or locale.get("locale") or "").strip() or None
        except Exception:
            lang = None
        if not lang and school:
            try:
                from apps.policies.policy_registry import get_effective_policy
                policy = get_effective_policy(school)
                lang = (policy.get("default_language") or "").strip() or None
            except Exception:
                pass
    else:
        lang = translation.get_language_from_request(request)
    if not lang:
        return None
    lang = lang.split("-")[0].lower()
    from django.conf import settings as django_settings
    supported = [c for c, _ in getattr(django_settings, "LANGUAGES", [("en", "English")])]
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
        from apps.siteconfig.models import ServiceIntegration
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
            label = config.get("display_name") or SSO_LABEL_MAP.get(
                (integration.service_name or "").lower()
            ) or integration.service_name or "Single Sign-On"
            out.append({"url": url, "label": label})
        return out
    except Exception:
        return []


def auth_root_redirect(request):
    """Redirect /authentication/ to the canonical login URL and preserve the query string."""
    target = reverse("accounts:login")
    query_string = request.GET.urlencode()
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target)


@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def login_view(request):
    # Optional: set login page language from tenant or Accept-Language (this request only).
    login_lang = _get_login_page_language(request)
    if login_lang:
        translation.activate(login_lang)

    if request.method == "POST":
        # Store role intent for post-login redirect (Student / Staff / Parent).
        role_param = (request.POST.get("role") or request.GET.get("role") or "").strip().lower()
        if role_param in ("student", "staff", "parent"):
            request.session[LOGIN_INTENT_ROLE_KEY] = role_param

        next_url = request.POST.get("next") or request.GET.get("next", "").strip()
        if next_url:
            from django.utils.http import url_has_allowed_host_and_scheme
            if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                next_url = ""

        user = authenticate(
            request,
            username=request.POST.get("username"),
            password=request.POST.get("password"),
        )
        if user:
            login(request, user)

            # Tenant-aware: ensure session school_id and membership (Phase 2).
            school = getattr(request, "school", None)
            if school:
                from apps.schools.models import SchoolMembership
                if not SchoolMembership.objects.filter(user=user, school=school).exists():
                    request.session.pop("school_id", None)
                    if not getattr(user, "is_superuser", False) and (getattr(user, "role", "") or "").upper() != "SUPERADMIN":
                        messages.warning(request, "You do not have access to this school.")
                        return redirect(reverse("accounts:school_picker"))
            else:
                from apps.schools.models import SchoolMembership
                primary = SchoolMembership.objects.filter(user=user, is_primary=True).select_related("school").first()
                first_m = SchoolMembership.objects.filter(user=user).select_related("school").first()
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
            except Exception:
                pass

            # Enforce requires_password_change (e.g. after Emergency Lockdown).
            if getattr(user, "requires_password_change", False):
                password_change_url = reverse("accounts:password_change")
                if next_url:
                    from django.utils.http import url_has_allowed_host_and_scheme
                    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                        request.session["password_change_next"] = next_url
                messages.warning(request, "You must set a new password to continue.")
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
                    has_device = TOTPDevice.objects.filter(user=user, confirmed=True).exists()

                def _mfa_remembered():
                    until_raw = request.session.get("mfa_verified_until")
                    if not until_raw:
                        return False
                    try:
                        until_dt = timezone.datetime.fromisoformat(until_raw)
                        if timezone.is_naive(until_dt):
                            until_dt = timezone.make_aware(until_dt, timezone.get_current_timezone())
                        if timezone.now() <= until_dt:
                            return True
                    except Exception:
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
            except Exception:
                pass

            # When on base domain and user has a school membership, send them to tenant subdomain (Backend is subdomain-only)
            if not getattr(request, "school", None):
                try:
                    from apps.schools.models import SchoolMembership
                    from apps.schools.tenant_url import is_base_domain, build_tenant_backend_url
                    if is_base_domain(request):
                        m = SchoolMembership.objects.filter(user=user).select_related("school").order_by("-is_primary").first()
                        if m and m.school:
                            if next_url:
                                from django.utils.http import url_has_allowed_host_and_scheme
                                if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                                    target = build_tenant_backend_url(request, m.school, path=next_url)
                                else:
                                    target = build_tenant_backend_url(request, m.school)
                            else:
                                target = build_tenant_backend_url(request, m.school)
                            return redirect(target)
                except Exception:
                    pass

            if next_url:
                return redirect(next_url)
            return redirect(reverse("accounts:redirect"))

        messages.error(request, "Invalid username or password.")
    context = {
        "LOGIN_SSO_INTEGRATIONS": _get_login_sso_integrations(request),
        "is_manager_host": getattr(request, "public_host_kind", None) == "manager",
    }
    if getattr(request, "public_host_kind", None) == "manager":
        try:
            from apps.schools.tenant_url import build_public_absolute_url
            context["public_site_url"] = build_public_absolute_url(request, "/")
        except Exception:
            context["public_site_url"] = "https://runmycampus.com"
    else:
        context["public_site_url"] = None
    template = "auth/manager_login.html" if getattr(request, "public_host_kind", None) == "manager" else "auth/login.html"
    return render(request, template, context)

def logout_view(request):
    logout(request)
    return redirect(reverse("accounts:login"))


@login_required
def school_picker(request):
    """Let user pick which school to use when they have multiple or no access on current host."""
    from apps.schools.models import SchoolMembership
    memberships = SchoolMembership.objects.filter(user=request.user).select_related("school").order_by("-is_primary", "school__name")
    if request.method == "POST":
        school_id = (request.POST.get("school_id") or "").strip()
        for m in memberships:
            if str(m.school_id) == school_id:
                request.session["school_id"] = school_id
                next_url = request.POST.get("next") or request.GET.get("next") or reverse("accounts:redirect")
                from django.utils.http import url_has_allowed_host_and_scheme
                if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    return redirect(next_url)
                return redirect("accounts:redirect")
        messages.warning(request, "Invalid school.")
    context = {"memberships": memberships}
    if not memberships:
        return render(request, "auth/school_picker.html", context)
    return render(request, "auth/school_picker.html", context)


@ratelimit(key="ip", rate="10/h", method="POST", block=True)
def claim_invite(request):
    from apps.portal.services import link_guardian_via_invite

    if not getattr(request, "school", None):
        messages.info(request, "Claim invite is available only inside a school workspace.")
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
            f"Welcome! You are now linked to {invite.student} and can view reports/finance."
        )
        return redirect("portal:parent_dashboard")

    return render(request, "accounts/claim_invite.html", {"form": form})


# Phase E (optional): School-facing Request Waiver — form and view
class RequestWaiverForm(forms.Form):
    """Reason and optional proof file for a subscription waiver request."""
    reason = forms.CharField(
        required=True,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "e.g. NGO / non-profit partnership, pilot program"}),
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
        messages.warning(request, "Select a school first.")
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
                "Your waiver request has been submitted. Platform support will review it and notify you.",
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
