from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import (
    PasswordChangeView as DjangoPasswordChangeView,
    redirect_to_login,
)
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
from apps.platform_runtime.config_resolver import get_effective_config

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
        FinanceNotification.objects.notify_unread(
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

            # config-resolver-allow: bare site.pk identity read feeds site_settings_change_url; AttributeError fallback not foldable into default=
            site = get_effective_site_settings(request=request)
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


def _notification_inbox_queryset(request):
    """The caller's visible-inbox notification queryset (GAP-4/5).

    Scopes notifications to what the user should actually see in their inbox:

    * **Ownership** — rows the user is the recipient of, or created.
    * **Tenant** — when the request carries a school, only that school's rows plus
      global (``school__isnull``) rows; a notification stamped for another tenant
      never leaks into this inbox. Hosts without a school (e.g. manager) are not
      school-filtered (there is no tenant to bind to).
    * **Not dismissed** — rows the recipient dismissed are hidden.
    * **Not expired** — rows past their ``expires_at`` are hidden (they are
      retention-eligible, not inbox content).

    Returned newest-first. Used by both the SSR inbox and the per-row SSR actions
    so "what I can see" and "what I can act on" are defined in exactly one place.
    """
    from apps.finance.models import Notification
    from django.db.models import Q
    from django.utils import timezone

    from apps.accounts.context_processors import _reset_db_state

    # tenant-isolation-allow: scoped-to-recipient-or-creator-current-user
    qs = Notification.objects.filter(
        Q(recipient=request.user) | Q(created_by=request.user)
    )

    school = getattr(request, "school", None)
    if school is not None:
        # tenant-isolation-allow: inbox-scoped-to-request-school-plus-global-rows
        qs = qs.filter(Q(school=school) | Q(school__isnull=True))

    now = timezone.now()
    try:
        qs = qs.filter(dismissed_at__isnull=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gte=now)
        )
        return qs.order_by("-created_at")
    except DatabaseError:
        # finance_notification schema drift (0071 recorded but columns not landed;
        # healed by migration 0072 / heal_tenant_schema_drift): empty inbox beats 500.
        import logging

        logging.getLogger(__name__).warning(
            "notification_inbox_queryset: finance_notification schema drift",
            exc_info=True,
        )
        _reset_db_state()
        return Notification.objects.none()


@login_required
def user_notifications(request):
    """User notifications landing page (RBAC-safe)."""
    from apps.accounts.security_posture_notifications import (
        dedupe_notifications_for_inbox,
        ensure_quarterly_posture_notification,
    )

    ensure_quarterly_posture_notification(
        request.user, getattr(request, "school", None)
    )

    base_qs = _notification_inbox_queryset(request)

    # Stats from full queryset before slicing
    total_count = base_qs.count()
    unread_count = base_qs.filter(is_read=False).count()
    read_count = base_qs.filter(is_read=True).count()

    # Filter by status if requested, then slice for display
    status_filter = request.GET.get("status")
    if status_filter == "unread":
        notifications = dedupe_notifications_for_inbox(
            list(base_qs.filter(is_read=False)[:50])
        )
    elif status_filter == "read":
        notifications = dedupe_notifications_for_inbox(
            list(base_qs.filter(is_read=True)[:50])
        )
    else:
        notifications = dedupe_notifications_for_inbox(list(base_qs[:50]))

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
        # tenant-isolation-allow: recipient-scoped-current-user-owns-notification
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


def _safe_inbox_redirect(request):
    """Redirect back to the referring inbox page, falling back to the inbox URL.

    Only same-origin referers are honoured (an absolute off-site referer is
    ignored) so the per-row actions can't be turned into an open redirect.
    """
    from django.utils.http import url_has_allowed_host_and_scheme

    referer = request.META.get("HTTP_REFERER") or ""
    fallback = reverse("accounts:user_notifications")
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(referer)
    return redirect(fallback)


@login_required
@require_POST
def notification_mark_read(request, notification_id):
    """SSR action: mark ONE of the caller's notifications read, then redirect back.

    GAP-3: the inbox previously POSTed the per-row "mark read" form straight at
    the DRF JSON endpoint, which returned ``{"status": "success"}`` as a raw JSON
    body — the user saw JSON instead of their refreshed inbox. This server-rendered
    action marks the row read (scoped through :func:`_notification_inbox_queryset`,
    so a user can only touch rows they can see) and redirects back to the inbox.
    """
    notification = _notification_inbox_queryset(request).filter(
        pk=notification_id
    ).first()
    if notification is None:
        messages.info(request, _("That notification is no longer available."))
        return _safe_inbox_redirect(request)

    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return _safe_inbox_redirect(request)


@login_required
@require_POST
def notification_dismiss(request, notification_id):
    """SSR action: dismiss ONE notification from the caller's inbox (GAP-4).

    Dismissal removes the row from the inbox (and the unread count) without
    deleting it — it stamps ``dismissed_at`` and marks it read, so the row drops
    out of :func:`_notification_inbox_queryset` immediately while remaining on
    record (and retention-eligible). Scoped through the same inbox queryset, so a
    user can only dismiss rows they can see.
    """
    notification = _notification_inbox_queryset(request).filter(
        pk=notification_id
    ).first()
    if notification is None:
        messages.info(request, _("That notification is no longer available."))
        return _safe_inbox_redirect(request)

    from django.utils import timezone

    update_fields = []
    if notification.dismissed_at is None:
        notification.dismissed_at = timezone.now()
        update_fields.append("dismissed_at")
    if not notification.is_read:
        notification.is_read = True
        update_fields.append("is_read")
    if update_fields:
        notification.save(update_fields=update_fields)
    messages.success(request, _("Notification dismissed."))
    return _safe_inbox_redirect(request)


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


#: Per-section result cap and snippet radius for message search (IM-7).
_SEARCH_RESULT_LIMIT = 25
_SEARCH_SNIPPET_RADIUS = 60
_SEARCH_MIN_QUERY_LEN = 2


def _search_snippet(text, q):
    """A short excerpt of ``text`` centred on the first match of ``q``."""
    text = text or ""
    low = text.lower()
    i = low.find((q or "").lower())
    if i < 0:
        return text[: _SEARCH_SNIPPET_RADIUS * 2]
    start = max(0, i - _SEARCH_SNIPPET_RADIUS)
    end = min(len(text), i + len(q) + _SEARCH_SNIPPET_RADIUS)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end] + suffix


@login_required
def message_search(request):
    """Search the caller's own messages across direct + group threads (IM-7).

    Direct results are messages the caller sent or received; group results are
    posts in threads the caller is a member of. Both are membership/school
    scoped, so search never reaches another tenant's or another thread's content.
    """
    if getattr(request.user, "role", None) == User.Role.PARENT:
        return redirect(reverse("portal:parent_contact_school"))
    q = (request.GET.get("q") or "").strip()
    direct_results = []
    group_results = []
    searched = len(q) >= _SEARCH_MIN_QUERY_LEN
    if searched:
        from apps.communication.models import Message, ThreadMessage, MessageThread

        # Direct: messages to/from the caller (the pair is inherently scoped).
        # tenant-isolation-allow: direct-results-scoped-to-callers-own-sent-or-received
        dm_qs = (
            Message.objects.filter(
                Q(sender=request.user) | Q(recipient=request.user),
                body__icontains=q,
                is_archived=False,
            )
            .select_related("sender", "recipient")
            .order_by("-created_at")[:_SEARCH_RESULT_LIMIT]
        )
        for m in dm_qs:
            other = m.recipient if m.sender_id == request.user.id else m.sender
            direct_results.append(
                {
                    "snippet": _search_snippet(m.body, q),
                    "other": other,
                    "created_at": m.created_at,
                    "url": (
                        reverse("accounts:direct_thread", args=[other.pk])
                        if other
                        else ""
                    ),
                }
            )

        # Group: posts in threads the caller is a member of.
        # tenant-isolation-allow: member-threads-scoped-to-callers-own-membership
        member_thread_ids = list(
            MessageThread.objects.filter(members=request.user).values_list(
                "id", flat=True
            )
        )
        # tenant-isolation-allow: group-results-scoped-to-callers-own-member-threads
        tm_qs = (
            ThreadMessage.objects.filter(
                thread_id__in=member_thread_ids,
                is_deleted=False,
                content__icontains=q,
            )
            .select_related("author", "thread")
            .order_by("-created_at")[:_SEARCH_RESULT_LIMIT]
        )
        for m in tm_qs:
            group_results.append(
                {
                    "snippet": _search_snippet(m.content, q),
                    "author": m.author,
                    "thread": m.thread,
                    "created_at": m.created_at,
                    "url": reverse(
                        "communication:group_detail", args=[m.thread_id]
                    ),
                }
            )

    context = {
        "q": q,
        "direct_results": direct_results,
        "group_results": group_results,
        "result_count": len(direct_results) + len(group_results),
        "searched": searched,
    }
    return render(request, "accounts/message_search.html", context)


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


def _direct_ai_assist_enabled(request) -> bool:
    """Whether to show AI assist on the direct-thread compose box (IM-8).

    Staff/teacher only (students/parents excluded) AND the tenant owns the
    AI_TEACHER_COMMS entitlement. Fails closed on any error.
    """
    if not _can_access_direct_messages(request.user):
        return False
    school = getattr(request, "school", None)
    if school is None:
        return False
    try:
        from apps.billing.entitlements import can as _ent_can

        return bool(_ent_can(school, "AI_TEACHER_COMMS"))
    except Exception:  # noqa: BLE001 — fail closed
        return False


def _direct_message_user_queryset(request):
    """Active users the caller may direct-message — SAME SCHOOL only.

    Closes a cross-tenant leak: the recipient picker and the thread-target lookup
    previously used an unscoped ``User.objects.filter(is_active=True)``, exposing
    (and allowing messages to) every school's users on a shared instance. This
    binds the set to the caller's school via the canonical ``_school_user_queryset``
    pattern. Superusers are intentionally left unscoped (cross-tenant operator
    tooling); everyone else is school-bound, and an unresolvable school yields an
    empty set rather than the whole platform.
    """
    user = request.user
    if getattr(user, "is_superuser", False):
        return User.objects.filter(is_active=True).exclude(pk=user.pk)

    from apps.communication.api_views import _school_user_queryset

    school = getattr(request, "school", None)
    if school is None:
        # Hosts that don't bind request.school (rare for staff) — resolve the
        # caller's own school membership; never fall back to platform-wide.
        try:
            from apps.schools.models import SchoolMembership

            # tenant-isolation-allow: resolves-callers-own-membership-then-scopes-below
            membership = (
                SchoolMembership.objects.filter(user_id=user.pk)
                .select_related("school")
                .first()
            )
            school = getattr(membership, "school", None)
        except Exception:  # noqa: BLE001 — never break compose on a lookup hiccup
            school = None
    if school is None:
        return User.objects.none()
    return (
        _school_user_queryset(school)
        .filter(is_active=True)
        .exclude(pk=user.pk)
    )


#: Cap on attachments accepted per single message send — a defensive bound on one
#: multipart POST (each file is independently size/type validated below).
_MESSAGE_ATTACHMENT_MAX_FILES = 5


def _save_message_attachments(message, files, uploader):
    """Validate + persist uploaded files as ``MessageAttachment`` rows (GAP-6).

    Each file is checked with the shared KB-attachment validators (PDF / Office /
    image only) and a 10 MB size cap; the count is bounded. Nothing here is fatal
    to the send — the text message is already saved, so a rejected / unstorable
    file is collected into ``errors`` and surfaced to the user, never raised.
    Returns ``(saved_count, error_messages)``.
    """
    from apps.communication.models import MessageAttachment
    from apps.accounts.validators import (
        validate_kb_attachment_file,
        validate_file_size_10mb,
    )
    from django.core.exceptions import ValidationError

    saved = 0
    errors = []
    for f in (files or [])[:_MESSAGE_ATTACHMENT_MAX_FILES]:
        if not f:
            continue
        name = (getattr(f, "name", "") or "file")
        try:
            validate_file_size_10mb(f)
            validate_kb_attachment_file(f)
        except ValidationError as exc:
            errors.append("%s: %s" % (name, "; ".join(exc.messages)))
            continue
        try:
            MessageAttachment.objects.create(
                message=message,
                file=f,
                original_name=name[:255],
                content_type=(getattr(f, "content_type", "") or "")[:128],
                size_bytes=getattr(f, "size", 0) or 0,
                uploaded_by=uploader,
            )
            saved += 1
        except Exception:  # noqa: BLE001 — a storage hiccup never breaks the send
            logger.warning("message attachment save failed", exc_info=False)
            errors.append("%s: %s" % (name, _("could not be saved")))
    return saved, errors


@login_required
def message_attachment_download(request, attachment_id):
    """Serve a message attachment to the sender or recipient only (GAP-6).

    Access is gated on the parent message's sender / recipient (plus superuser),
    so a guessed id can't leak another conversation's file. Served as an
    attachment download with the stored content type.
    """
    from apps.communication.models import MessageAttachment
    from django.http import FileResponse, Http404

    # tenant-isolation-allow: access-gated-below-on-message-sender-or-recipient
    attachment = get_object_or_404(
        MessageAttachment.objects.select_related("message"), pk=attachment_id
    )
    message = attachment.message
    allowed = request.user.pk in (
        getattr(message, "sender_id", None),
        getattr(message, "recipient_id", None),
    ) or request.user.is_superuser
    if not allowed:
        return HttpResponseForbidden("You don't have access to this attachment.")

    try:
        handle = attachment.file.open("rb")
    except (FileNotFoundError, ValueError):
        raise Http404("Attachment file is unavailable.")
    response = FileResponse(
        handle,
        as_attachment=True,
        filename=attachment.original_name or "attachment",
    )
    if attachment.content_type:
        response["Content-Type"] = attachment.content_type
    return response


@login_required
def direct_thread(request, user_id):
    """View 1-on-1 thread. Parents and students can only open threads with staff/teacher (view/reply). Staff can close the loop."""
    from apps.communication.models import Message, DirectConversation, MessageBlock
    from django.utils import timezone

    User = request.user.__class__
    if user_id == request.user.pk:
        return redirect("accounts:user_messages")
    # Same-school only — the target must be in the caller's messageable user set
    # (closes the cross-tenant thread-open leak). 404 (not 403) so a probed id
    # outside the school is indistinguishable from a non-existent one.
    other = get_object_or_404(_direct_message_user_queryset(request), pk=user_id)

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

    # Block state (IM-7): a block in either direction severs direct messaging.
    is_blocked = MessageBlock.is_blocked_between(request.user.pk, other.pk)
    # tenant-isolation-allow: block-row-scoped-to-caller-and-this-thread-peer
    i_blocked_them = MessageBlock.objects.filter(
        blocker=request.user, blocked=other
    ).exists()

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
        attachment_files = request.FILES.getlist("attachments")
        if body or attachment_files:
            if conv and conv.closed_at:
                messages.error(request, _("This conversation is closed."))
            elif is_blocked:
                messages.error(
                    request,
                    _("You can't message this person while a block is in place."),
                )
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
                if attachment_files:
                    _saved, attach_errors = _save_message_attachments(
                        msg, attachment_files, request.user
                    )
                    if attach_errors:
                        messages.warning(
                            request,
                            _("Some attachments were not added: %(errs)s")
                            % {"errs": "; ".join(attach_errors)},
                        )
                _notify_new_direct_message(request.user, other, msg)
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                Message.objects.filter(
                    sender=other, recipient=request.user, is_read=False
                ).update(is_read=True, read_at=timezone.now())
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
        .prefetch_related("attachments")
        .order_by("created_at")
    )

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    Message.objects.filter(sender=other, recipient=request.user, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )

    conversation_closed = conv.closed_at if conv else False
    can_close = (
        _is_staff_or_teacher(request.user)
        and other_is_parent
        and conv
        and not conv.closed_at
    )
    can_reply = not conversation_closed and not is_blocked

    context = {
        "other_user": other,
        "messages": list(messages_qs),
        "conversation_closed": conversation_closed,
        "can_close": can_close,
        "can_reply": can_reply,
        "is_blocked": is_blocked,
        "i_blocked_them": i_blocked_them,
        "can_block": _can_access_direct_messages(request.user),
        "typing_endpoint": reverse(
            "accounts:direct_thread_typing", args=[other.pk]
        ),
        "ai_assist_enabled": _direct_ai_assist_enabled(request),
        "ai_improve_endpoint": reverse("portal:ai_rewrite_plain_language"),
        "ai_summarize_endpoint": reverse("portal:ai_summarize_thread"),
    }
    return render(request, "accounts/direct_thread.html", context)


@login_required
def direct_thread_read_state(request, user_id):
    """JSON read-state of the caller's OWN messages to ``user_id`` (GAP-6).

    Powers the live "Seen" receipt: the sender polls this to learn when the
    recipient opened the thread (which stamps ``read_at``), without a full reload.
    Only the caller's *sent* messages are exposed, so this leaks nothing the
    sender doesn't already own.
    """
    from apps.communication.models import Message
    from django.http import JsonResponse

    # Same school-scoped set as the thread itself (the payload only ever exposes
    # the caller's OWN sent messages, but scoping the lookup keeps it consistent
    # and avoids confirming a cross-tenant user exists).
    other = get_object_or_404(_direct_message_user_queryset(request), pk=user_id)

    # tenant-isolation-allow: scoped-to-callers-own-sent-messages-to-other
    rows = (
        Message.objects.filter(
            sender=request.user, recipient=other, is_read=True
        )
        .exclude(read_at__isnull=True)
        .values("id", "read_at")
    )
    payload = [
        {"id": row["id"], "read_at": row["read_at"].isoformat()} for row in rows
    ]
    return JsonResponse({"messages": payload})


#: Max messages returned by one live-poll fetch (bounds the payload; a backlog
#: larger than this drains across successive polls).
_THREAD_LIVE_POLL_LIMIT = 50


@login_required
def direct_thread_messages_since(request, user_id):
    """JSON of thread messages newer than ``?after`` for live delivery (IM-3).

    Powers the open-thread live updater: the client passes the highest message id
    it has rendered, and this returns anything newer between the two participants
    (same school-scoped target as the thread itself). It also marks the OTHER
    party's now-visible messages read — the user is actively looking — so the
    sender's "Seen" receipt updates without either side reloading.
    """
    from apps.communication.models import Message
    from django.http import JsonResponse

    other = get_object_or_404(_direct_message_user_queryset(request), pk=user_id)
    try:
        after = int(request.GET.get("after") or 0)
    except (TypeError, ValueError):
        after = 0

    # tenant-isolation-allow: thread-rows-scoped-to-caller-and-other-participant
    new_qs = (
        Message.objects.filter(
            Q(sender=request.user, recipient=other)
            | Q(sender=other, recipient=request.user)
        )
        .filter(is_archived=False, id__gt=after)
        .select_related("sender")
        .order_by("created_at")[:_THREAD_LIVE_POLL_LIMIT]
    )

    items = []
    for msg in new_qs:
        sender = msg.sender
        items.append(
            {
                "id": msg.id,
                "mine": msg.sender_id == request.user.id,
                "sender_name": (
                    (sender.get_full_name() if sender else "")
                    or getattr(sender, "username", "")
                    or "Someone"
                ),
                "body": msg.body or "",
                "created_at": msg.created_at.isoformat(),
                "is_read": bool(msg.is_read),
            }
        )

    # The viewer is live on the thread → mark the other party's unread as read.
    # tenant-isolation-allow: scoped-to-messages-other-sent-to-caller
    Message.objects.filter(
        sender=other, recipient=request.user, is_read=False
    ).update(is_read=True, read_at=timezone.now())

    return JsonResponse({"messages": items})


@login_required
def direct_block_toggle(request, user_id):
    """Block / unblock a user from direct-messaging the caller (IM-7).

    Blocking severs direct messaging both ways: the blocked user can no longer
    open or post to a thread with the caller, and the caller stops receiving
    their messages and notifications. Group threads are unaffected.
    """
    if getattr(request.user, "role", None) == User.Role.PARENT:
        return redirect(reverse("portal:parent_contact_school"))
    if not _can_access_direct_messages(request.user):
        return HttpResponseForbidden("You don't have permission to block users.")
    other = get_object_or_404(_direct_message_user_queryset(request), pk=user_id)
    from apps.communication.models import MessageBlock

    if request.method == "POST":
        # tenant-isolation-allow: block-row-scoped-to-caller-and-the-resolved-peer
        existing = MessageBlock.objects.filter(
            blocker=request.user, blocked=other
        ).first()
        if existing:
            existing.delete()
            messages.success(request, _("Unblocked. They can message you again."))
        else:
            MessageBlock.objects.create(blocker=request.user, blocked=other)
            messages.success(request, _("Blocked. They can no longer message you."))
    return redirect("accounts:direct_thread", user_id=other.pk)


@login_required
def direct_thread_typing(request, user_id):
    """Typing indicator for a 1:1 direct thread (IM-7), cache-backed (no DB).

    POST marks the caller typing; GET returns whether the other party is typing.
    Scoped to the same school-bound peer set as the thread itself.
    """
    other = get_object_or_404(_direct_message_user_queryset(request), pk=user_id)
    from apps.communication.typing import typing_cache_key, typing_response

    pair = "-".join(str(p) for p in sorted((request.user.pk, other.pk)))
    return typing_response(request, typing_cache_key("dm", pair))


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
        attachment_files = request.FILES.getlist("attachments")
        if not recipient_id or (not body and not attachment_files):
            messages.error(
                request, _("Select a recipient and enter a message or attach a file.")
            )
            return redirect("accounts:direct_compose")
        # Validate the recipient against the SAME school-scoped set the picker was
        # built from, so a tampered POST can't message across tenants.
        recipient = (
            _direct_message_user_queryset(request).filter(pk=recipient_id).first()
        )
        if not recipient:
            messages.error(request, _("Selected recipient is not available."))
            return redirect("accounts:direct_compose")
        from apps.communication.models import DirectConversation, MessageBlock

        if MessageBlock.is_blocked_between(request.user.pk, recipient.pk):
            messages.error(
                request,
                _("You can't message this person while a block is in place."),
            )
            return redirect("accounts:direct_compose")

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
        if attachment_files:
            _saved, attach_errors = _save_message_attachments(
                msg, attachment_files, request.user
            )
            if attach_errors:
                messages.warning(
                    request,
                    _("Some attachments were not added: %(errs)s")
                    % {"errs": "; ".join(attach_errors)},
                )
        _notify_new_direct_message(request.user, recipient, msg)
        return redirect("accounts:direct_thread", user_id=recipient.pk)

    # GET: list SAME-SCHOOL active users (exclude self) for recipient dropdown;
    # limit for large schools. School-scoped via _direct_message_user_queryset so
    # the picker never exposes another tenant's users.
    recipients = (
        _direct_message_user_queryset(request)
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


def _owner_onboarding_resume_name(request, user):
    """URL name to resume a school owner's guided onboarding, or ``None``.

    Returns a wizard step name only when the user is an active owner of the
    resolved tenant school AND that school's guided onboarding was *started but
    not completed* (``School.settings['owner_onboarding']`` present, not
    ``completed``). Schools that never entered the wizard have empty state and are
    left alone — this never force-routes an established owner, and the wizard's own
    ``completed`` gate breaks any loop once they finish/skip. Fail-soft: any error
    yields ``None`` so post-login routing is never blocked.
    """
    try:
        school = getattr(request, "school", None)
        if school is None or getattr(school, "pk", None) is None:
            return None
        from apps.schools.models import SchoolMembership

        is_owner = SchoolMembership.objects.filter(
            school=school,
            user_id=getattr(user, "pk", None),
            is_school_owner=True,
            suspended_at__isnull=True,
        ).exists()
        if not is_owner:
            return None
        from apps.accounts.views_owner_onboarding import onboarding_state

        state = onboarding_state(school)
        if not state or state.get("completed"):
            return None
        # Steps 2-3 are @login_required tenant-host views; resume at the recorded
        # step (default to the school step).
        if state.get("step") == "done":
            return "accounts:owner_onboarding_done"
        if state.get("step") == "mfa":
            return "accounts:owner_onboarding_mfa"
        return "accounts:owner_onboarding_school"
    except Exception:  # noqa: BLE001 — a post-login resume must never break login
        logging.getLogger(__name__).debug(
            "owner onboarding resume check failed", exc_info=True
        )
        return None


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
        host_kind = getattr(request, "public_host_kind", None)
        if host_kind is None:
            try:
                from apps.schools.host_routing import public_host_kind

                host_kind = public_host_kind((request.get_host() or "").split(":")[0])
            except (ImportError, AttributeError, TypeError, ValueError):
                host_kind = None
        if host_kind == "base":
            return redirect(reverse("global_login_discovery"))
        return redirect(reverse("accounts:login"))

    # Manager host is for platform operators; tenant staff belong on the public host.
    try:
        from apps.schools.host_routing import public_host_kind

        host = (request.get_host() or "").split(":")[0].lower()
        if public_host_kind(host) == "manager":
            from apps.accounts.manager_login_next import (
                build_public_post_login_url,
                tenant_staff_should_use_public_host,
            )
            from apps.schools.control_plane import user_has_control_plane_access

            if tenant_staff_should_use_public_host(user):
                from apps.schools.tenant_login_redirect import (
                    resolve_public_post_login_handoff,
                )

                handoff = resolve_public_post_login_handoff(request, user)
                if handoff is not None:
                    return handoff
                return redirect(build_public_post_login_url())
            if user_has_control_plane_access(user):
                return redirect("super:dashboard")
            return redirect(build_public_post_login_url())
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
            from apps.schools.tenant_url import is_base_domain
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

            if is_base_domain(request):
                from apps.schools.tenant_login_redirect import (
                    resolve_public_post_login_handoff,
                )

                handoff = resolve_public_post_login_handoff(request, user)
                if handoff is not None:
                    return handoff
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

    from apps.accounts.portal_roles import get_nav_portal_role

    nav_role = get_nav_portal_role(request) or getattr(user, "role", None)

    if nav_role == User.Role.TEACHER:
        if dash_view == "WORKFLOW":
            return _redirect_with_params("portal:teacher_workflow")
        return _redirect_with_params("evals:teacher_dashboard")
    if nav_role == User.Role.PARENT:
        if dash_view == "WORKFLOW":
            return _redirect_with_params("portal:parent_workflow")
        if dash_view == "FINANCE":
            return _redirect_with_params("portal:parent_finance")
        if dash_view == "ACADEMICS":
            return _redirect_with_params("portal:parent_performance")
        if dash_view == "ATTENDANCE":
            return _redirect_with_params("portal:parent_dashboard")
        return _redirect_with_params("portal:parent_dashboard")
    if nav_role == User.Role.STUDENT:
        if dash_view == "WORKFLOW":
            return _redirect_with_params("portal:student_workflow")
        return _redirect_with_params("portal:student_portal_grades")

    # Owner still mid-setup: resume the guided onboarding wizard instead of the
    # bare dashboard, so an owner who abandoned setup is walked back through it on
    # their next sign-in. Fail-soft (None when not applicable) — never blocks login.
    onboarding_resume = _owner_onboarding_resume_name(request, user)
    if onboarding_resume:
        return _redirect_with_params(onboarding_resume)

    # Staff/backend: only after family/student/teacher hats are ruled out.
    if user.has_feature_permission("settings.manage"):
        if dash_view == "WORKFLOW":
            return _redirect_with_params("studio_os:workflow_center")
        return _redirect_with_params("accounts:backend_dashboard")

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


def _rbac_redirect(request):
    from services.post_delete_navigation import redirect_after_save

    fallback = request.get_full_path() or reverse("accounts:rbac")
    return redirect_after_save(
        request,
        fallback,
        list_url=reverse("accounts:rbac"),
    )


def _posted_rbac_user_outside_school(request, *, field_name: str, school) -> bool:
    from apps.accounts.tenant_identity import user_has_school_membership

    raw_user_id = request.POST.get(field_name)
    if not raw_user_id:
        return False
    try:
        user = User.objects.get(pk=raw_user_id)
    except (User.DoesNotExist, ValueError):
        return False
    return not user_has_school_membership(user, school)


@login_required
@require_school
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@rbac_dashboard_pdp
def rbac_dashboard(request):
    from apps.accounts.tenant_identity import user_has_school_membership
    from services.post_delete_navigation import mutation_return_url

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
                return _rbac_redirect(request)
        elif form_type == "permission":
            permission_form = PermissionForm(request.POST, prefix="permission")
            if permission_form.is_valid():
                permission_form.save()
                messages.success(request, _("Permission created successfully."))
                return _rbac_redirect(request)
        elif form_type == "user_roles":
            user_role_form = UserRoleForm(request.POST, prefix="user_role", school=school)
            if user_role_form.is_valid():
                user = user_role_form.cleaned_data["user"]
                if not user_has_school_membership(user, school):
                    messages.error(request, _("User is not a member of this school."))
                    return _rbac_redirect(request)
                roles = user_role_form.cleaned_data["roles"]
                for role in roles:
                    if not role_applies_to_school(role, school):
                        messages.error(
                            request,
                            _("Role %(code)s is not valid for this school.")
                            % {"code": role.code},
                        )
                        return _rbac_redirect(request)
                user.roles.set(roles)
                messages.success(request, f"Roles updated for {user.username}.")
                return _rbac_redirect(request)
            else:
                if _posted_rbac_user_outside_school(
                    request, field_name="user_role-user", school=school
                ):
                    messages.error(request, _("User is not a member of this school."))
                    return _rbac_redirect(request)
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
                    return _rbac_redirect(request)
                permissions = user_permission_form.cleaned_data["permissions"]
                user.feature_permissions.set(permissions)
                messages.success(request, f"Permissions updated for {user.username}.")
                return _rbac_redirect(request)
            if _posted_rbac_user_outside_school(
                request, field_name="user_permission-user", school=school
            ):
                messages.error(request, _("User is not a member of this school."))
                return _rbac_redirect(request)
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
                return _rbac_redirect(request)
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
                    return _rbac_redirect(request)
                role = temporary_grant_form.cleaned_data["role"]
                if not role_applies_to_school(role, school):
                    messages.error(
                        request,
                        _("Role %(code)s is not valid for this school.")
                        % {"code": role.code},
                    )
                    return _rbac_redirect(request)
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
                return _rbac_redirect(request)
            if _posted_rbac_user_outside_school(
                request, field_name="temp_grant-user", school=school
            ):
                messages.error(request, _("User is not a member of this school."))
                return _rbac_redirect(request)

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
        "return_url": mutation_return_url(
            request,
            request.get_full_path() or reverse("accounts:rbac"),
            list_url=reverse("accounts:rbac"),
        ),
    }
    return render(request, "accounts/rbac_dashboard.html", context)


# Adaptive admin landing (2026-06-19): while a school is still onboarding, the
# admin dashboard collapses the dense operations center to a focused setup
# surface (hero + readiness + setup checklist + setup banner). These are the
# backend_module_visibility keys flipped off in that mode — the per-widget
# template gates already exist, so no parallel template branches are needed.
BACKEND_SETUP_LANDING_HIDDEN_MODULES = (
    "overview",
    "welcome",
    "admin_portal",
    "enrollment_trends",
    "at_risk_students",
    "outstanding_fees",
    "recent_admissions",
    "recent_activity",
    "top_performing",
    "attendance_today",
    "ops_watch",
    "quick_links",
    "planner",
)
# Default onboarding %% below which the setup surface engages (operator-tunable
# via the backend_setup_landing_threshold flag; whole behaviour gated by
# backend_adaptive_setup_landing).
BACKEND_SETUP_LANDING_DEFAULT_THRESHOLD = 70


def _resolve_setup_landing(
    onboarding_percent,
    backend_flags,
    *,
    launch_ready: bool | None = None,
    has_launched: bool | None = None,
) -> bool:
    """Adaptive-landing decision: True when a school is still onboarding (below
    the operator-tunable setup threshold), so the admin dashboard collapses the
    dense operations center to a focused setup surface. The whole behaviour is
    gated by the backend_adaptive_setup_landing flag (default on); the cutover
    point is backend_setup_landing_threshold (default
    BACKEND_SETUP_LANDING_DEFAULT_THRESHOLD). Post-setup cockpit shows after
    execute_launch records launched_at (Go live ceremony)."""
    if not bool(backend_flags.get("backend_adaptive_setup_landing", True)):
        return False
    if has_launched is True:
        return False
    try:
        pct = int(onboarding_percent or 0)
    except (TypeError, ValueError):
        pct = 0
    try:
        threshold = int(
            backend_flags.get("backend_setup_landing_threshold")
            or BACKEND_SETUP_LANDING_DEFAULT_THRESHOLD
        )
    except (TypeError, ValueError):
        threshold = BACKEND_SETUP_LANDING_DEFAULT_THRESHOLD
    return pct < threshold


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

    # config-resolver-allow: namespace passed to template context ('site') plus method/attr fan-out (compliance_profile, feature-control methods, social links)
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
    grading_scale_max = 20  # local-first: overwritten from the tenant's score scale below
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

    # Local-first grading scale for this tenant: the pass mark is half the scale and
    # the display denominator is the scale max. A /20 (Cameroon) school keeps pass-at-10
    # and "/20" exactly; a /100 or GPA school gets correct thresholds + labels.
    from apps.evals.grading_provisioning import resolve_school_score_scale

    # Display denominator only (never an upper bound), so the unknown case opts in
    # explicitly to the neutral 100 rather than getting it silently.
    _dash_scale = float(resolve_school_score_scale(school, default=100))
    grading_scale_max = (
        int(_dash_scale) if _dash_scale == int(_dash_scale) else round(_dash_scale, 1)
    )
    _dash_pass_mark = _dash_scale / 2.0

    at_risk_map = {}
    for row in score_rows:
        if row.get("score", 0) >= _dash_pass_mark:
            continue
        sid = row.get("student_id")
        if sid in at_risk_map:
            continue
        at_risk_map[sid] = {
            "student_id": sid,
            "name": row.get("name") or "Student",
            "classroom": row.get("classroom") or "Unassigned",
            "tag": "Low performance",
            "value": f"{row.get('score', 0):.1f}/{grading_scale_max}",
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
        "grading_scale_max": grading_scale_max,
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
        from apps.dashboard.pressing_issues import build_tenant_pressing_issues

        context["pressing_issues"] = build_tenant_pressing_issues(request)
    except ACCOUNTS_SOFT_FAILURES:
        context["pressing_issues"] = None
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
            _launch_ready = None
            _has_launched = False
            try:
                from apps.setup_studio.models import SetupProgress
                from apps.setup_studio.services import get_setup_studio_payload

                _studio_payload = get_setup_studio_payload(_sch) or {}
                _launch_ready = bool(_studio_payload.get("launch_ready"))
                _progress = SetupProgress.objects.filter(school=_sch).first()
                _has_launched = bool(_progress and _progress.launched_at)
            except ACCOUNTS_SOFT_FAILURES:
                _launch_ready = None
                _has_launched = False
            context["rmc_school_readiness_launch_ready"] = _launch_ready
            context["rmc_school_has_launched"] = _has_launched
            try:
                from apps.schools.school_readiness import build_school_readiness

                context["rmc_school_readiness"] = build_school_readiness(
                    _sch, user=request.user
                )
            except ACCOUNTS_SOFT_FAILURES:
                context["rmc_school_readiness"] = None
            try:
                from apps.schools.launch_playbook import build_launch_playbook

                context["rmc_launch_playbook"] = build_launch_playbook(
                    _sch, user=request.user
                )
            except ACCOUNTS_SOFT_FAILURES:
                context["rmc_launch_playbook"] = None
            try:
                from apps.platform_runtime.tenant_operational_lifecycle import (
                    resolve_operational_lifecycle_state,
                )

                context["rmc_operational_lifecycle"] = resolve_operational_lifecycle_state(
                    _sch
                )
            except ACCOUNTS_SOFT_FAILURES:
                context["rmc_operational_lifecycle"] = None
            try:
                from apps.schools.year_close_checklist import build_year_close_checklist

                context["rmc_year_close_checklist"] = build_year_close_checklist(
                    _sch, user=request.user
                )
            except ACCOUNTS_SOFT_FAILURES:
                context["rmc_year_close_checklist"] = None
            try:
                from apps.runtime_blueprints.models import DashboardUserPreference

                context["rmc_dashboard_visual_preset_choices"] = (
                    DashboardUserPreference.VISUAL_PRESET_CHOICES
                )
            except ACCOUNTS_SOFT_FAILURES:
                context["rmc_dashboard_visual_preset_choices"] = ()
            # Adaptive landing: below the setup threshold, collapse the ops center
            # to a focused setup surface by flipping the existing per-widget
            # visibility gates (no parallel template branches). Reversible.
            _setup_landing = _resolve_setup_landing(
                (context.get("rmc_school_onboarding") or {}).get("percent"),
                backend_flags,
                launch_ready=_launch_ready,
                has_launched=_has_launched,
            )
            context["show_setup_landing"] = _setup_landing
            if request.GET.get("launched") == "1" or request.session.pop(
                "rmc_launch_ceremony_show", False
            ):
                context["rmc_show_launch_ceremony"] = True
            else:
                context["rmc_show_launch_ceremony"] = False
            if _setup_landing:
                for _mod in BACKEND_SETUP_LANDING_HIDDEN_MODULES:
                    backend_module_visibility[_mod] = False
                context["backend_intent_emphasize_setup"] = True
                # Real setup-studio wizards, grouped by lifecycle stage, for the
                # command-surface landing (built only while the setup surface
                # shows). Fully failure-isolated → empty stages fall back to the
                # onboarding-milestone cards.
                try:
                    from apps.setup_studio.setup_surface import (
                        build_setup_wizard_stages,
                    )
                    from apps.setup_studio.services import get_setup_studio_payload

                    context["rmc_setup_wizard_stages"] = build_setup_wizard_stages(
                        _sch
                    )
                    _studio_payload = get_setup_studio_payload(_sch) or {}
                    context["rmc_setup_recommended_next"] = _studio_payload.get(
                        "recommended_next"
                    )
                    context["rmc_setup_migration_flow"] = _studio_payload.get(
                        "migration_path_flow"
                    )
                    context["rmc_setup_data_path_choices"] = _studio_payload.get(
                        "data_path_choices"
                    )
                except ACCOUNTS_SOFT_FAILURES:
                    context["rmc_setup_wizard_stages"] = None
                    context["rmc_setup_recommended_next"] = None
                    context["rmc_setup_migration_flow"] = None
                    context["rmc_setup_data_path_choices"] = None
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

    from apps.schools.tenant_operational_health import resolve_tenant_operational_health

    context["tenant_health"] = resolve_tenant_operational_health(
        getattr(request, "school", None), request=request, surface="admin"
    )

    # MAX Wave 3: Admin Home masthead (Mission twin) — interactive role + season.
    try:
        from django.urls import reverse as _rev

        from apps.platform_runtime.page_status_tags import (
            STATUS_ATTENTION,
            STATUS_HEALTHY,
            build_masthead,
            build_mission_role_tabs,
            chip,
            mission_role_chips,
            resolve_mission_role_from_request,
            resolve_operational_season,
            sparkline_from_count,
        )
        from apps.schools.setup_health import setup_health_score

        th = context.get("tenant_health") or {}
        health = setup_health_score(getattr(request, "school", None))
        unmet = [label for _n, passed, label in health.get("checks", []) if not passed]
        role_raw = getattr(getattr(request, "user", None), "role", None) or "admin"
        role_key = resolve_mission_role_from_request(request, default_role=str(role_raw))
        chips = list(mission_role_chips(role_key, host="tenant"))
        # Attach sparklines to the first priority chip from live setup score.
        if chips:
            chips[0] = chip(
                label=chips[0]["label"],
                tone=chips[0]["tone"],
                sparkline=sparkline_from_count(int(health.get("score") or 0)),
            )
        tier = str(th.get("tier") or "").lower()
        if tier in {"up", "ok", "healthy"}:
            status_key = STATUS_HEALTHY
        elif tier in {"degraded", "warn", "warning", "down", "critical"}:
            chips.insert(0, chip(label="Needs attention", tone="warning"))
            status_key = STATUS_ATTENTION
        else:
            chips.insert(
                0,
                chip(
                    label=f"{health.get('score', 0)}% setup",
                    tone="warning" if unmet else "success",
                    sparkline=sparkline_from_count(int(health.get("score") or 0)),
                ),
            )
            status_key = STATUS_ATTENTION if unmet else STATUS_HEALTHY
        for label in unmet[:2]:
            chips.append(chip(label=label, tone="danger"))
        chips.append(chip(label="Updated just now", tone="fresh"))
        season = resolve_operational_season()
        try:
            base_url = _rev("accounts:backend_dashboard")
        except Exception:  # noqa: BLE001
            base_url = "/authentication/backend/"
        context["mission_season"] = season
        context["mission_role_tabs"] = build_mission_role_tabs(
            active=role_key, base_url=base_url, host="tenant"
        )
        context.update(
            build_masthead(
                archetype="mission",
                host="tenant",
                eyebrow=f"Mission · {season['label']}",
                title="Admin Home",
                purpose=(
                    "What is happening, what needs attention, and your next step — "
                    "Configuration, Studio, and Finance stay one click away."
                ),
                chips=chips,
                primary_url="/school/configuration/",
                primary_label="Configuration",
                secondary_url="/finance/",
                secondary_label="Finance",
                status_key=status_key,
            )
        )
    except Exception:  # noqa: BLE001
        pass

    context.setdefault("show_setup_landing", False)

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
        # config-resolver-allow: method call get_offline_runtime_settings() on the namespace object
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

    from apps.accounts.manager_login_next import request_is_manager_host

    is_manager_host = request_is_manager_host(request)
    host_kind = getattr(request, "public_host_kind", None)
    if host_kind is None:
        try:
            from apps.schools.host_routing import public_host_kind

            host_kind = public_host_kind((request.get_host() or "").split(":")[0])
        except (ImportError, AttributeError, TypeError, ValueError):
            host_kind = None
    if host_kind == "base" and not is_manager_host:
        return redirect(reverse("global_login_discovery"))
    if request.method == "GET" and is_manager_host:
        from apps.accounts.manager_login_next import (
            build_public_login_redirect_url,
            is_toxic_login_next_for_manager,
            should_show_manager_login_surface,
        )

        next_raw = (request.GET.get("next") or "").strip()
        if next_raw and is_toxic_login_next_for_manager(next_raw):
            return redirect(build_public_login_redirect_url(request))
        if not should_show_manager_login_surface(request):
            return redirect(build_public_login_redirect_url(request))

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
        if is_manager_host:
            from apps.accounts.manager_login_next import sanitize_manager_login_next

            next_url = sanitize_manager_login_next(next_url)

        # Brute-force / bot defense, layered on the per-IP @ratelimit above:
        #  1. login_guard — always-on cache lockout after N failed attempts.
        #  2. bot_defense — always-on invisible honeypot + timing traps, plus a
        #     self-hosted proof-of-work challenge after the first failed attempt
        #     (no account, no third party, works offline). Cloudflare Turnstile
        #     stays an opt-in fallback only when LOGIN_POW_ENABLED is off.
        # Everything fails open so an outage never blocks a legitimate sign-in.
        from apps.accounts import bot_defense, login_guard
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
        elif bot_defense.honeypot_tripped(request) or bot_defense.timing_tripped(request):
            # Invisible traps: behave exactly like a wrong password so an
            # automated submitter gets no signal it was caught. Counts toward
            # the lockout via the failed-attempt recorder below.
            user = None
        else:
            failed_so_far = int(request.session.get("auth_failed_attempts", 0) or 0)
            # IP+username counter survives a fresh/cookie-less session, so a
            # distributed stuffer that already missed this username still hits
            # the challenge even with a brand-new cookie.
            guard_count = login_guard.attempt_count(request, username)
            use_pow = bot_defense.pow_enabled()
            use_turnstile = (not use_pow) and turnstile_enabled()
            prior_miss = failed_so_far >= 1 or guard_count >= 1
            challenge_required = prior_miss and (use_pow or use_turnstile)
            if challenge_required and use_pow:
                challenge_ok = bot_defense.verify_pow(
                    request.POST.get("pow_token", ""),
                    request.POST.get("pow_nonce", ""),
                    session_key=request.session.session_key or "",
                )
            elif challenge_required:
                challenge_ok = verify_turnstile(
                    request.POST.get("cf-turnstile-response", ""), guard_ip
                )
            else:
                challenge_ok = True
            if not challenge_ok:
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

            # MFA BEFORE any cross-host handoff. Handoff used to run first on the
            # manager host and bounce tenant staff to a school login/backend URL
            # without ever showing MFA (password → spinner → sign-in again).
            try:
                from apps.accounts.post_login_mfa import resolve_post_login_mfa_redirect

                mfa_resp = resolve_post_login_mfa_redirect(
                    request, user, next_url=next_url or ""
                )
                if mfa_resp is not None:
                    return mfa_resp
            except ACCOUNTS_SOFT_FAILURES:
                pass

            # Tenant staff must not stay on manager-host activation next chains.
            if is_manager_host:
                from apps.accounts.manager_login_next import (
                    build_public_login_redirect_url,
                    tenant_staff_should_use_public_host,
                )
                from apps.schools.tenant_login_redirect import (
                    resolve_public_post_login_handoff,
                )

                if tenant_staff_should_use_public_host(user):
                    handoff = resolve_public_post_login_handoff(request, user)
                    if handoff is not None:
                        return handoff
                    return redirect(build_public_login_redirect_url(request))

            # When on base domain and user has a school membership, send them to tenant subdomain (Backend is subdomain-only)
            if not getattr(request, "school", None):
                try:
                    from apps.schools.models import SchoolMembership
                    from apps.schools.tenant_url import (
                        is_base_domain,
                        build_tenant_backend_url,
                    )

                    if is_base_domain(request):
                        from apps.schools.provision_email_urls import (
                            school_subdomain_redirect_is_safe,
                        )
                        from apps.schools.tenant_login_redirect import (
                            resolve_post_login_tenant_membership,
                            resolve_public_post_login_handoff,
                        )

                        if not next_url:
                            handoff = resolve_public_post_login_handoff(request, user)
                            if handoff is not None:
                                return handoff
                        m = resolve_post_login_tenant_membership(user, request)
                        if m and m.school:
                            if not school_subdomain_redirect_is_safe(m.school):
                                from apps.schools.tenant_login_redirect import (
                                    redirect_to_tenant_workspace,
                                )

                                return redirect_to_tenant_workspace(request, m.school)
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
    from apps.accounts import bot_defense, login_guard

    _pow_on = bot_defense.pow_enabled()
    _failed_now = int(request.session.get("auth_failed_attempts", 0) or 0)
    _guard_now = (
        login_guard.attempt_count(request, request.POST.get("username"))
        if request.method == "POST"
        else 0
    )
    _pow_required = _pow_on and (_failed_now >= 1 or _guard_now >= 1)
    _pow_challenge = None
    if _pow_required:
        # Bind the challenge to this session so a solved token can't be replayed
        # from another session; mint a session key if the visitor has none yet.
        if not request.session.session_key:
            request.session.create()
        _pow_challenge = bot_defense.issue_pow_challenge(
            session_key=request.session.session_key or ""
        )
    context = {
        "LOGIN_SSO_INTEGRATIONS": _get_login_sso_integrations(request),
        "is_manager_host": getattr(request, "public_host_kind", None) == "manager",
        # Cloudflare Turnstile is only the active challenge when PoW is disabled.
        "turnstile_site_key": getattr(settings, "TURNSTILE_SITE_KEY", ""),
        "turnstile_required": (not _pow_on) and _login_challenge_required(request),
        # Self-hosted proof-of-work + always-on honeypot/timing traps.
        "pow_required": _pow_required,
        "pow_challenge": _pow_challenge,
        "honeypot_field": bot_defense.honeypot_field_name(),
        "form_ts": bot_defense.issue_form_timestamp(),
    }
    if getattr(request, "public_host_kind", None) == "manager":
        try:
            from apps.schools.tenant_url import build_public_absolute_url

            context["public_site_url"] = build_public_absolute_url(request, "/")
        except ACCOUNTS_SOFT_FAILURES:
            context["public_site_url"] = settings.PUBLIC_SITE_URL
        try:
            from apps.schools.provision_email_urls import build_public_site_url

            context["password_reset_public_url"] = build_public_site_url(
                "/authentication/password_reset/"
            )
        except ACCOUNTS_SOFT_FAILURES:
            context["password_reset_public_url"] = (
                f"{(context.get('public_site_url') or 'https://runmycampus.com').rstrip('/')}"
                "/authentication/password_reset/"
            )
    else:
        from apps.accounts.manager_login_next import use_operator_login_template

        if use_operator_login_template(request):
            try:
                from apps.schools.provision_email_urls import build_public_site_url

                context["public_site_url"] = build_public_site_url("/")
                context["password_reset_public_url"] = build_public_site_url(
                    "/authentication/password_reset/"
                )
            except ACCOUNTS_SOFT_FAILURES:
                context["public_site_url"] = getattr(
                    settings, "PUBLIC_SITE_URL", "https://runmycampus.com"
                )
                context["password_reset_public_url"] = (
                    f"{(context.get('public_site_url') or 'https://runmycampus.com').rstrip('/')}"
                    "/authentication/password_reset/"
                )
        else:
            context["public_site_url"] = None
            context["password_reset_public_url"] = None
    context["public_tenant_login_hub"] = False
    context["login_workspace_schools"] = []
    from apps.accounts.manager_login_next import use_operator_login_template

    operator_login_surface = use_operator_login_template(request)
    context["is_operator_login_surface"] = operator_login_surface
    if not operator_login_surface:
        context["post_role"] = (
            request.POST.get("role") or request.GET.get("role") or "staff"
        )
        try:
            from apps.accounts.login_immersive_context import build_login_immersive_context

            context["LOGIN_IMMERSIVE"] = build_login_immersive_context(request)
        except Exception:
            context["LOGIN_IMMERSIVE"] = {
                "ticker_items": [_("Welcome — sign in to reach your school workspace.")],
                "carousel_slides": [],
                "bento_stats": [],
                "dash_feed": [],
                "moments": [],
                "clock_label": "",
                "date_label": "",
                "dash_preview": {},
                "role_preview_labels": {
                    "default": _("School pulse"),
                    "staff": _("Staff dashboard"),
                    "parent": _("Family portal"),
                    "student": _("Student hub"),
                },
            }
    template = (
        "auth/manager_login.html" if operator_login_surface else "auth/login.html"
    )
    context["RMC_AUTH_LANDING_LITE"] = template == "auth/login.html"
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
    host_kind = getattr(request, "public_host_kind", None)
    if host_kind is None:
        try:
            from apps.schools.host_routing import public_host_kind

            host_kind = public_host_kind((request.get_host() or "").split(":")[0])
        except (ImportError, AttributeError, TypeError, ValueError):
            host_kind = None
    if host_kind == "base":
        return redirect("marketing_landing")
    return redirect(reverse("accounts:login"))


def school_picker(request):
    """Let user pick which school to use when they have multiple or no access on current host."""
    host_kind = getattr(request, "public_host_kind", None)
    if host_kind is None:
        try:
            from apps.schools.host_routing import public_host_kind

            host_kind = public_host_kind((request.get_host() or "").split(":")[0])
        except (ImportError, AttributeError, TypeError, ValueError):
            host_kind = None
    if not request.user.is_authenticated:
        if host_kind == "base":
            return redirect(reverse("global_login_discovery"))
        return redirect_to_login(request.get_full_path(), login_url=reverse("accounts:login"))
    if host_kind == "base":
        from apps.schools.tenant_login_redirect import resolve_public_post_login_handoff

        handoff = resolve_public_post_login_handoff(request, request.user)
        if handoff is not None:
            return handoff
        return redirect(reverse("global_login_discovery"))

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
                from apps.schools.tenant_login_redirect import (
                    redirect_to_tenant_workspace,
                )

                return redirect_to_tenant_workspace(request, m.school)
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
        # save_user() creates the User via create_user() (never through
        # authenticate()), so it carries no `.backend` attribute. With multiple
        # AUTHENTICATION_BACKENDS configured, login() must be given an explicit
        # backend or it raises ValueError → 500 on every successful claim. Use
        # the vanilla ModelBackend, matching the SAML/OIDC login() calls.
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
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
