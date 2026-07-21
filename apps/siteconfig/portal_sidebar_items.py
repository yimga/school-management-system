"""
Build portal sidebar nav items for the current user, optionally sorted by ``portal_sidebar_order`` on the siteconfig settings singleton.

Section order (by role):
- Home, Account (all)
- Communication (role-dependent)
- Teacher: My Workflow, Learning Management, Human Resources, Settings (Portal Stats)
- Parent: My Workflow, Children & Learning, Performance Tracking
- Portal Tools: Community, Video; Documents under Content & Documents
- Staff: Support, Content & Documents, People & Access, Academic Management, Financial Management,
  Analytics & Reports, then Admin Panel last (Dashboard Layout, Feature Control, Backend Console,
  Workflow Center, Customizer, Site Settings, Region Configuration, Django Admin)

Visibility is permission- and role-based; teachers never see Admin/People/Finance/Analytics.
No duplicate sections or links: each item appears in one section only (same for staff, teachers, parents).
"""

from django.db import DatabaseError
from django.urls import reverse
from django.urls import NoReverseMatch
from django.contrib.auth import get_user_model
from django.core.cache import cache

User = get_user_model()
OPTIONAL_SIDEBAR_ERRORS = (
    AttributeError,
    DatabaseError,
    ImportError,
    RuntimeError,
    TypeError,
    ValueError,
)
OPTIONAL_REVERSE_ERRORS = (AttributeError, NoReverseMatch, TypeError, ValueError)

# Tenant ops/config split: portal sections that hold platform configuration rather
# than day-to-day work. The config zone is rendered as one contiguous block AFTER
# all day-to-day sections so the operational sidebar stays focused. Tenants keep
# configuration in-portal (not Django /admin/) because tenant admins are typically
# not Django staff — the portal IS their backend.
# Config zone (sorted to the bottom as a contiguous block). The legacy single
# "Admin Panel" grab-bag was split into themed sub-groups (2026-06-28) so each
# config submenu relates to its heading; "Admin Panel" is kept for the resilient
# baseline nav (build_portal_sidebar_baseline) which still uses it.
PORTAL_CONFIG_SECTIONS = frozenset(
    {
        "Admin Panel",
        "Configuration",
        "Display & Platform",
        "Templates & Branding",
        "Access & Roles",
        "Integrations & Data",
    }
)


def _portal_item_surface(section):
    """Return "config" for configuration sections, else "ops" (day-to-day)."""
    return "config" if (section or "") in PORTAL_CONFIG_SECTIONS else "ops"


def _order_sections_ops_then_config(section_order):
    """Keep first-occurrence order within each surface, but push every config
    section after all ops sections so configuration forms a contiguous bottom zone."""
    ops_sections = [s for s in section_order if _portal_item_surface(s) == "ops"]
    config_sections = [s for s in section_order if _portal_item_surface(s) == "config"]
    return ops_sections + config_sections


def _dashboard_layout_url(request, user):
    """Link to Backend dashboard + ?customize=1 (only backend supports layout customization)."""
    try:
        from apps.siteconfig.dashboard_views import _can_customize

        if not _can_customize(user):
            return None
        return _safe_reverse("accounts:backend_dashboard") + "?customize=1"
    except OPTIONAL_SIDEBAR_ERRORS:
        return _safe_reverse("accounts:backend_dashboard") + "?customize=1"


def _safe_reverse(url_name, kwargs=None, args=None, default=None):
    try:
        if args is not None:
            return reverse(url_name, args=args)
        return reverse(url_name, kwargs=kwargs or {})
    except OPTIONAL_REVERSE_ERRORS:
        return default


def _baseline_reverse(url_name):
    """Reverse sidebar baseline targets (tenant urlconf for school configuration routes).

    Restores the request's *live* urlconf in ``finally`` — NOT ``settings.ROOT_URLCONF``.
    This function runs from the sidebar context processor on every render, so clobbering
    the thread-local with ROOT_URLCONF (``config.urls``) used to strand the rest of the
    render on the wrong urlconf: on a manager/operator host the handler activates
    ``config.manager_urls``, but after this call any page-body ``{% url 'sales:…' %}`` /
    ``{% url 'super:…' %}`` (namespaces that live only in ``manager_urls``) raised
    ``NoReverseMatch: '…' is not a registered namespace``. Preserving ``get_urlconf()``
    keeps the temporary tenant switch fully local to this reverse.
    """
    from django.conf import settings
    from django.urls import get_urlconf, set_urlconf

    tenant_conf = getattr(settings, "TENANT_SCHEMA_URLCONF", None)
    prev_conf = get_urlconf()
    if tenant_conf:
        set_urlconf(tenant_conf)
    try:
        url = _safe_reverse(url_name)
        if not url and url_name == "school_configuration_center_canonical":
            url = _safe_reverse("school_configuration_center")
        return url
    finally:
        if tenant_conf:
            set_urlconf(prev_conf)


def _badge_or_none(value):
    try:
        count = int(value or 0)
    except (TypeError, ValueError):
        return None
    return count if count > 0 else None


def _sidebar_badge_counts(user, role, staff_like):
    """
    Compute compact sidebar badge counts.
    Returns (workflow_pending, finance_pending, signatures_pending).
    """
    workflow_pending = None
    finance_pending = None
    signatures_pending = None

    if role == User.Role.TEACHER:
        try:
            from django.db.models import Q
            from apps.people.models import TeacherProfile, TeacherLeaveRequest
            from apps.evals.models import Evaluation
            from apps.academics.services import get_active_year_and_term

            teacher_profile = (
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                TeacherProfile.objects.filter(user=user).only("id").first()
            )
            if teacher_profile:
                year, _term = get_active_year_and_term()
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                eval_qs = Evaluation.objects.filter(teacher=teacher_profile)
                if year:
                    eval_qs = eval_qs.filter(academic_year=year)
                pending_marks = eval_qs.filter(
                    Q(seq1_score__isnull=True)
                    | Q(seq2_score__isnull=True)
                    | Q(exam_score__isnull=True)
                ).count()
                pending_leaves = TeacherLeaveRequest.objects.filter(
                    teacher=teacher_profile,
                    status=TeacherLeaveRequest.Status.PENDING,
                ).count()
                workflow_pending = _badge_or_none(pending_marks + pending_leaves)
        except OPTIONAL_SIDEBAR_ERRORS:
            workflow_pending = None
        return workflow_pending, finance_pending, signatures_pending

    if role == User.Role.PARENT:
        try:
            from apps.portal.models import FormSignature
            from apps.portal.services import (
                guardian_student_links,
                parent_dashboard_widget_data,
            )

            links = guardian_student_links(user, results_only=True)
            students = [link.student for link in links]
            widget_data = parent_dashboard_widget_data(students)
            tasks = (
                widget_data.get("tasks", {}) if isinstance(widget_data, dict) else {}
            )
            workflow_pending = _badge_or_none(tasks.get("pending_evaluations"))
            finance_pending = _badge_or_none(tasks.get("pending_payments"))
            signatures_pending = _badge_or_none(
                FormSignature.objects.filter(parent=user, status="PENDING").count()
            )
        except OPTIONAL_SIDEBAR_ERRORS:
            pass
        return workflow_pending, finance_pending, signatures_pending

    if staff_like:
        try:
            from apps.finance.models import Notification

            finance_pending = _badge_or_none(
                # tenant-isolation-allow: recipient-scoped-current-user-owns-notification
                Notification.objects.filter(
                    recipient=user,
                    title__icontains="finance access request",
                    is_read=False,
                ).count()
            )
        except OPTIONAL_SIDEBAR_ERRORS:
            finance_pending = None

        try:
            from apps.portal.models import FormSignature

            signatures_pending = _badge_or_none(
                FormSignature.objects.filter(status="PENDING").count()
            )
        except OPTIONAL_SIDEBAR_ERRORS:
            signatures_pending = None

        try:
            from apps.academics.models import Classroom
            from apps.academics.services import get_active_year_and_term
            from apps.people.models import StudentProfile, TeacherProfile

            year, _term = get_active_year_and_term()
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            if year:
                missing_steps = 0
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                if not Classroom.objects.filter(academic_year=year).exists():
                    missing_steps += 1
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                if not StudentProfile.objects.filter(
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    academic_year=year, is_active=True
                ).exists():
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    missing_steps += 1
                if not TeacherProfile.objects.filter(is_active=True).exists():
                    missing_steps += 1
                workflow_pending = _badge_or_none(missing_steps)
        except OPTIONAL_SIDEBAR_ERRORS:
            workflow_pending = None

    return workflow_pending, finance_pending, signatures_pending


def _cached_sidebar_badge_counts(user, role, staff_like, request=None):
    """
    Cache badge counts briefly to avoid repeated expensive sidebar queries per request.
    World Engine F.2: cache key includes tenant/school so same user in multiple schools has separate counts.
    """
    user_id = getattr(user, "pk", None)
    if not user_id:
        return _sidebar_badge_counts(user, role, staff_like)
    try:
        from apps.siteconfig.cache_utils import get_tenant_cache_prefix

        prefix = get_tenant_cache_prefix(request)
    except OPTIONAL_SIDEBAR_ERRORS:
        prefix = "public"
    cache_key = (
        f"{prefix}:portal_sidebar_badges:{user_id}:{role}:{1 if staff_like else 0}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    counts = _sidebar_badge_counts(user, role, staff_like)
    cache.set(cache_key, counts, 60)
    return counts


def _backend_flags_for_sidebar(request, site):
    """Resolve backend feature flags for sidebar visibility. Prefer request.tenant_runtime.flags when available."""
    try:
        from apps.platform_runtime.helpers import (
            get_effective_feature_control_settings,
            get_effective_flags,
        )

        runtime_flags = get_effective_flags(request) or {}
        if runtime_flags:
            return runtime_flags
        if callable(getattr(site, "get_backend_feature_flags", None)):
            return site.get_backend_feature_flags()
        feature_settings = get_effective_feature_control_settings(request=request)
        scoped_flags = feature_settings.get("backend_feature_flags") or {}
        if scoped_flags:
            return scoped_flags
        return getattr(site, "backend_feature_flags", None) or {}
    except OPTIONAL_SIDEBAR_ERRORS:
        if callable(getattr(site, "get_backend_feature_flags", None)):
            return site.get_backend_feature_flags()
        return getattr(site, "backend_feature_flags", None) or {}


def _dedupe_sidebar_items(items):
    """Collapse duplicate nav rows. Pure (list[dict] -> list[dict]); order-stable.

    Three guards, in order of strength:
      1. ``id`` — same item id added by two code paths.
      2. ``(label, url)`` — pinned-order / re-emitted identical rows.
      3. NORMALIZED ``label`` — the final backstop. The same surface is often
         reachable via two route names (e.g. ``studio_os:experience`` vs
         ``siteconfig:theme_experience_hub``), so a second item carries an
         identical visible label but a DIFFERENT id AND url — invisible to the
         first two guards. This is what produced the live double-rows for
         "Theme & Experience" / "District & LMS interop" / "Class Ranking".

    A nav rail must never show the same visible label twice; the first occurrence
    (the canonical static entry, appended earliest) wins.
    """
    deduped = []
    seen_item_ids = set()
    seen_label_urls = set()
    seen_labels = set()
    for item in items:
        item_id = item.get("id")
        if item_id and item_id in seen_item_ids:
            continue
        raw_label = item.get("label") or ""
        label_url = (raw_label, item.get("url") or "")
        if label_url[1] and label_url in seen_label_urls:
            continue
        norm_label = " ".join(raw_label.split()).casefold()
        if norm_label and norm_label in seen_labels:
            continue
        if item_id:
            seen_item_ids.add(item_id)
        if label_url[1]:
            seen_label_urls.add(label_url)
        if norm_label:
            seen_labels.add(norm_label)
        deduped.append(item)
    return deduped


def build_portal_sidebar_items(request, site):
    """
    Return a list of sidebar items {id, label, url, icon, section, badge} for the current user.
    If site.portal_sidebar_order is non-empty, sort items so that IDs in that list come first in that order,
    then append any remaining items in their original order.
    Uses effective portal role (session) when user has both teacher and parent hats.
    Visibility is runtime-aware: when request.tenant_runtime is present, entitlements.modules and flags govern item visibility.
    """
    if not request or not request.user.is_authenticated:
        return []
    user = request.user
    backend_flags = _backend_flags_for_sidebar(request, site)
    from apps.accounts.portal_roles import get_nav_portal_role

    primary_role = (getattr(user, "role", "") or "").upper()
    nav_role = get_nav_portal_role(request) or primary_role
    # Nav hat (session PARENT/STUDENT on staff accounts) drives all sidebar sections.
    role = nav_role
    is_staff = getattr(user, "is_staff", False)
    is_superuser = getattr(user, "is_superuser", False)
    messages_unread_count = getattr(request, "messages_unread_count", None)
    _STAFF_PRIMARY_ROLES = frozenset(
        {
            "ADMIN",
            "LEADERSHIP",
            "IT_ADMIN",
            "PRINCIPAL",
            "VICE_PRINCIPAL",
            "DEAN",
            "BURSAR",
            "ACCOUNTANT",
            "PROPRIETOR",
            "DISCIPLINE_MASTER",
            "SECRETARY",
        }
    )
    # Privileged for badges / studio shell — independent of active portal hat.
    staff_privileged = (
        is_staff or is_superuser or primary_role in _STAFF_PRIMARY_ROLES
    )
    # Admin sidebar only when the effective hat is staff/admin — never on family surfaces.
    family_effective_role = nav_role in (User.Role.PARENT, User.Role.STUDENT)
    show_staff_admin_nav = (
        staff_privileged
        and not family_effective_role
        and nav_role != User.Role.TEACHER
    )
    staff_like = staff_privileged
    workflow_badge, finance_badge, signatures_badge = _cached_sidebar_badge_counts(
        user, role, staff_like, request=request
    )
    # Single entry via Studio OS for operational hubs; resolve once for staff.
    studio_shell_url = _safe_reverse("studio_os:shell") if show_staff_admin_nav else None

    items = []

    # --- Home ---
    items.append(
        {
            "id": "dashboard",
            "label": "Dashboard",
            "url": _safe_reverse("accounts:redirect"),
            "icon": "bi-speedometer2",
            "section": "Home",
            "badge": None,
        }
    )
    # --- Account ---
    items.append(
        {
            "id": "profile",
            "label": "My Profile",
            "url": _safe_reverse("accounts:user_profile"),
            "icon": "bi-person",
            "section": "Account",
            "badge": None,
        }
    )
    items.append(
        {
            "id": "preferences",
            "label": "Preferences",
            "url": _safe_reverse("siteconfig:user_preferences"),
            "icon": "bi-sliders",
            "section": "Account",
            "badge": None,
        }
    )
    items.append(
        {
            "id": "notifications",
            "label": "Notifications",
            "url": _safe_reverse("accounts:user_notifications"),
            "icon": "bi-bell",
            "section": "Account",
            "badge": None,
        }
    )
    items.append(
        {
            "id": "help_center",
            "label": "Help center",
            "url": _safe_reverse("feedback:help_center"),
            "icon": "bi-life-preserver",
            "section": "Account",
            "badge": None,
        }
    )
    items.append(
        {
            "id": "kb",
            "label": "Knowledge Base",
            "url": _safe_reverse("kb:kb_home"),
            "icon": "bi-journal-text",
            "section": "Account",
            "badge": None,
        }
    )

    # --- Communication (role-dependent) ---
    if role == User.Role.TEACHER:
        items.append(
            {
                "id": "messages",
                "label": "Messages",
                "url": _safe_reverse("accounts:user_messages"),
                "icon": "bi-chat-dots",
                "section": "Communication",
                "badge": messages_unread_count,
            }
        )
        items.append(
            {
                "id": "message_groups",
                "label": "Message Groups",
                "url": _safe_reverse("communication:group_list"),
                "icon": "bi-people",
                "section": "Communication",
                "badge": None,
            }
        )
    elif role == User.Role.PARENT:
        items.append(
            {
                "id": "contact_school",
                "label": "Contact School",
                "url": _safe_reverse("portal:parent_contact_school"),
                "icon": "bi-envelope-paper",
                "section": "Communication",
                "badge": None,
            }
        )
    elif role == User.Role.STUDENT:
        items.append(
            {
                "id": "messages",
                "label": "Messages",
                "url": _safe_reverse("accounts:user_messages"),
                "icon": "bi-chat-dots",
                "section": "Communication",
                "badge": messages_unread_count,
            }
        )
    elif (
        is_staff
        or is_superuser
        or role
        in (
            "ADMIN",
            "LEADERSHIP",
            "IT_ADMIN",
            "PRINCIPAL",
            "VICE_PRINCIPAL",
            "DEAN",
            "PROPRIETOR",
            "SECRETARY",
        )
    ):
        items.append(
            {
                "id": "messages",
                "label": "Messages",
                "url": _safe_reverse("accounts:user_messages"),
                "icon": "bi-chat-dots",
                "section": "Communication",
                "badge": messages_unread_count,
            }
        )
        _msg_url = studio_shell_url or _safe_reverse("communication:group_list")
        if _msg_url:
            items.append(
                {
                    "id": "message_groups",
                    "label": "Message Groups",
                    "url": _msg_url,
                    "icon": "bi-people",
                    "section": "Communication",
                    "badge": None,
                }
            )
        try:
            from apps.communication.views_announcements import (
                _can_create_school_wide_announcement,
                _can_access_school_wide_announcement_create,
            )

            if _can_access_school_wide_announcement_create(user):
                _ann_url = studio_shell_url or _safe_reverse(
                    "communication:announcement_create"
                )
                if _ann_url:
                    items.append(
                        {
                            "id": "announcements",
                            "label": "School-wide Announcements",
                            "url": _ann_url,
                            "icon": "bi-megaphone",
                            "section": "Communication",
                            "badge": None,
                        }
                    )
            if _can_create_school_wide_announcement(user):
                _pend_url = studio_shell_url or _safe_reverse(
                    "communication:announcement_list_pending"
                )
                if _pend_url:
                    items.append(
                        {
                            "id": "announcements_pending",
                            "label": "Pending approval",
                            "url": _pend_url,
                            "icon": "bi-hourglass-split",
                            "section": "Communication",
                            "badge": None,
                        }
                    )
        except OPTIONAL_SIDEBAR_ERRORS:
            pass

    # --- Teacher ---
    if role == User.Role.TEACHER:
        items.append(
            {
                "id": "class_announcement",
                "label": "Class Announcement",
                "url": _safe_reverse("communication:class_announcement_create"),
                "icon": "bi-journal-text",
                "section": "Communication",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "teacher_workflow",
                "label": "My Workflow",
                "url": _safe_reverse("portal:teacher_workflow"),
                "icon": "bi-diagram-3",
                "section": "My Workflow",
                "badge": workflow_badge,
            }
        )
        items.append(
            {
                "id": "teacher_homework",
                "label": "Homework",
                "url": _safe_reverse("portal:teacher_assignments"),
                "icon": "bi-journal-text",
                "section": "Learning Management",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "marks_entry",
                "label": "Enter Marks",
                "url": _safe_reverse("evals:teacher_marks_entry"),
                "icon": "bi-pencil-square",
                "section": "Learning Management",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "marks_list",
                "label": "Marks History",
                "url": _safe_reverse("evals:teacher_marks_list"),
                "icon": "bi-table",
                "section": "Learning Management",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "attendance",
                "label": "Attendance",
                "url": _safe_reverse("portal:teacher_attendance"),
                "icon": "bi-clipboard-check",
                "section": "Learning Management",
                "badge": None,
            }
        )
        if getattr(user, "has_feature_permission", lambda _: False)(
            "attendance.manage"
        ):
            items.append(
                {
                    "id": "take_student_attendance",
                    "label": "Take student attendance",
                    "url": _safe_reverse("portal:take_student_attendance"),
                    "icon": "bi-clipboard-check",
                    "section": "Learning Management",
                    "badge": None,
                }
            )
            items.append(
                {
                    "id": "take_teacher_attendance",
                    "label": "Take teacher attendance",
                    "url": _safe_reverse("portal:record_teacher_attendance"),
                    "icon": "bi-person-check",
                    "section": "Learning Management",
                    "badge": None,
                }
            )
        items.append(
            {
                "id": "timetable",
                "label": "My Timetable",
                "url": _safe_reverse("portal:teacher_timetable"),
                "icon": "bi-calendar-week",
                "section": "Learning Management",
                "badge": None,
            }
        )
        if backend_flags.get("enable_cahier_de_texte"):
            items.append(
                {
                    "id": "cahier",
                    "label": "Cahier de Texte",
                    "url": _safe_reverse("portal:cahier_list"),
                    "icon": "bi-journal-text",
                    "section": "Learning Management",
                    "badge": None,
                    "feature": "cahier_de_texte",
                }
            )
        items.append(
            {
                "id": "payslips",
                "label": "Payslips",
                "url": _safe_reverse("payroll:employee_payslips"),
                "icon": "bi-wallet2",
                "section": "Human Resources",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "leave",
                "label": "Leave Requests",
                "url": _safe_reverse("payroll:employee_leave"),
                "icon": "bi-calendar-check",
                "section": "Human Resources",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "pay_history",
                "label": "Pay History",
                "url": _safe_reverse("portal:teacher_pay_history"),
                "icon": "bi-receipt",
                "section": "Human Resources",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "portal_stats",
                "label": "Portal Stats",
                "url": _safe_reverse("portal:portal_stats"),
                "icon": "bi-graph-up",
                # Same view the parent gets under "Performance Tracking"; "Settings"
                # was a misnomer (a stats link, not configuration). Keep it ops, named
                # consistently across roles. — 2026-06-10
                "section": "Performance Tracking",
                "badge": None,
            }
        )

    # --- Parent ---
    if role == User.Role.PARENT:
        items.append(
            {
                "id": "parent_workflow",
                "label": "My Workflow",
                "url": _safe_reverse("portal:parent_workflow"),
                "icon": "bi-diagram-3",
                "section": "My Workflow",
                "badge": workflow_badge,
            }
        )
        items.append(
            {
                "id": "my_children",
                "label": "My Children",
                "url": _safe_reverse("portal:parent_dashboard"),
                "icon": "bi-people",
                "section": "Children & Learning",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "parent_athletics",
                "label": "Sports",
                "url": _safe_reverse("athletics:family_my_team"),
                "icon": "bi-trophy",
                "section": "Children & Learning",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "finance",
                "label": "Finance & Fees",
                "url": _safe_reverse("portal:parent_finance"),
                "icon": "bi-cash-coin",
                "section": "Children & Learning",
                "badge": finance_badge,
            }
        )
        items.append(
            {
                "id": "pending_signatures",
                "label": "Pending Signatures",
                "url": _safe_reverse("portal:signature_pending_list"),
                "icon": "bi-pen",
                "section": "Children & Learning",
                "badge": signatures_badge,
            }
        )
        items.append(
            {
                "id": "link_child",
                "label": "Link Child",
                "url": _safe_reverse("portal:link_child"),
                "icon": "bi-person-plus",
                "section": "Children & Learning",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "claim_invite",
                "label": "Claim Invite",
                "url": _safe_reverse("portal:claim_invite"),
                "icon": "bi-ticket",
                "section": "Children & Learning",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "academic_stats",
                "label": "Academic Stats",
                "url": _safe_reverse("portal:portal_stats"),
                "icon": "bi-graph-up",
                "section": "Performance Tracking",
                "badge": None,
            }
        )

    # --- Student ---
    if role == User.Role.STUDENT:
        if getattr(site, "enable_student_portal", True):
            items.append(
                {
                    "id": "student_workflow",
                    "label": "My Workflow",
                    "url": _safe_reverse("portal:student_workflow"),
                    "icon": "bi-diagram-3",
                    "section": "My Workflow",
                    "badge": workflow_badge,
                }
            )
            items.append(
                {
                    "id": "student_home",
                    "label": "Student Home",
                    "url": _safe_reverse("portal:student_portal_grades"),
                    "icon": "bi-house",
                    "section": "Learning",
                    "badge": None,
                }
            )
            items.append(
                {
                    "id": "student_homework",
                    "label": "Homework",
                    "url": _safe_reverse("portal:student_assignments"),
                    "icon": "bi-pencil-square",
                    "section": "Learning",
                    "badge": None,
                }
            )
            items.append(
                {
                    "id": "student_syllabus",
                    "label": "Syllabus Coverage",
                    "url": _safe_reverse("portal:portal_syllabus"),
                    "icon": "bi-journal-bookmark",
                    "section": "Learning",
                    "badge": None,
                }
            )
            items.append(
                {
                    "id": "student_athletics",
                    "label": "My Team",
                    "url": _safe_reverse("athletics:family_my_team"),
                    "icon": "bi-trophy",
                    "section": "Learning",
                    "badge": None,
                }
            )
        items.append(
            {
                "id": "student_help",
                "label": "Help Center",
                "url": _safe_reverse("feedback:help_center"),
                "icon": "bi-life-preserver",
                "section": "Support",
                "badge": None,
            }
        )

    # --- Portal Tools (per-feature RBAC). Documents goes under Content & Documents; for staff it's added in staff block to avoid duplicate section. ---
    if callable(getattr(site, "get_feature_control_settings", None)):
        portal_cfg = site.get_feature_control_settings().get("portal_features") or {}
    else:
        try:
            from apps.platform_runtime.helpers import (
                get_effective_feature_control_settings,
            )

            portal_cfg = (
                get_effective_feature_control_settings(request=request).get(
                    "portal_features"
                )
                or {}
            )
        except OPTIONAL_SIDEBAR_ERRORS:
            portal_cfg = {}
    if portal_cfg.get("forums") and getattr(
        user, "has_feature_permission", lambda _: False
    )("portal.forums"):
        items.append(
            {
                "id": "portal_forums",
                "label": "Community",
                "url": _safe_reverse(
                    "portal:portal_feature", kwargs={"feature": "forums"}
                ),
                "icon": "bi-people",
                "section": "Portal Tools",
                "badge": None,
            }
        )
    if portal_cfg.get("video") and getattr(
        user, "has_feature_permission", lambda _: False
    )("portal.video"):
        items.append(
            {
                "id": "portal_video",
                "label": "Video Hub",
                "url": _safe_reverse(
                    "portal:portal_feature", kwargs={"feature": "video"}
                ),
                "icon": "bi-camera-video",
                "section": "Portal Tools",
                "badge": None,
            }
        )
    # Documents: for teachers/parents add here (one Content & Documents section); for staff add in staff block below
    staff_gets_content_docs = show_staff_admin_nav
    if (
        portal_cfg.get("documents")
        and getattr(user, "has_feature_permission", lambda _: False)("portal.documents")
        and not staff_gets_content_docs
    ):
        items.append(
            {
                "id": "portal_documents",
                "label": "Documents",
                "url": _safe_reverse(
                    "portal:portal_feature", kwargs={"feature": "documents"}
                ),
                "icon": "bi-file-earmark-text",
                "section": "Content & Documents",
                "badge": None,
            }
        )

    # --- Admin / Staff (exclude teachers + family hats: parent/student never see admin nav) ---
    can_manage_site = show_staff_admin_nav and (
        getattr(user, "has_feature_permission", lambda _: False)("settings.manage")
        or is_superuser
    )
    if show_staff_admin_nav:
        # Support, Content & Documents, People & Access, Academic, Financial, Analytics first; Admin Panel last
        items.append(
            {
                "id": "contact_requests",
                "label": "Contact Requests",
                "url": _safe_reverse("portal:staff_contact_request_list"),
                "icon": "bi-inbox",
                "section": "Support",
                "badge": None,
            }
        )
        if role in ("DISCIPLINE_MASTER", "CENSOR"):
            items.append(
                {
                    "id": "discipline_incidents",
                    "label": "Disciplinary Incidents",
                    "url": _safe_reverse("portal:discipline_incidents_list"),
                    "icon": "bi-shield-exclamation",
                    "section": "Support",
                    "badge": None,
                }
            )
        # Content & Documents: Document Library Manager, Signature Requests, and portal Documents (single section)
        if can_manage_site:
            items.append(
                {
                    "id": "document_library_manage",
                    "label": "Document Library Manager",
                    "url": _safe_reverse("portal:document_library_manage"),
                    "icon": "bi-folder2-open",
                    "section": "Content & Documents",
                    "badge": None,
                }
            )
            items.append(
                {
                    "id": "signature_requests",
                    "label": "Signature Requests",
                    "url": _safe_reverse("portal:signature_requests_manage"),
                    "icon": "bi-pen",
                    "section": "Content & Documents",
                    "badge": signatures_badge,
                }
            )
        if portal_cfg.get("documents") and getattr(
            user, "has_feature_permission", lambda _: False
        )("portal.documents"):
            items.append(
                {
                    "id": "portal_documents",
                    "label": "Documents",
                    "url": _safe_reverse(
                        "portal:portal_feature", kwargs={"feature": "documents"}
                    ),
                    "icon": "bi-file-earmark-text",
                    "section": "Content & Documents",
                    "badge": None,
                }
            )
        # Certification & Exams (GCE): admins get quick access; certification home handles disabled state.
        items.append(
            {
                "id": "certification",
                "label": "Certification & Exams",
                "url": _safe_reverse("accounts:certification_home"),
                "icon": "bi-award",
                "section": "Academic Management",
                "badge": None,
            }
        )
        if backend_flags.get("enable_cahier_de_texte") and (
            getattr(user, "has_feature_permission", lambda _: False)("cahier.verify")
            or role == "CENSOR"
        ):
            items.append(
                {
                    "id": "cahier_verify",
                    "label": "Cahier verification",
                    "url": _safe_reverse("portal:cahier_verify_list"),
                    "icon": "bi-journal-check",
                    "section": "Academic Management",
                    "badge": None,
                }
            )
        if getattr(user, "has_feature_permission", lambda _: False)(
            "attendance.manage"
        ):
            items.append(
                {
                    "id": "take_student_attendance",
                    "label": "Take student attendance",
                    "url": _safe_reverse("portal:take_student_attendance"),
                    "icon": "bi-clipboard-check",
                    "section": "Academic Management",
                    "badge": None,
                }
            )
            items.append(
                {
                    "id": "take_teacher_attendance",
                    "label": "Take teacher attendance",
                    "url": _safe_reverse("portal:record_teacher_attendance"),
                    "icon": "bi-person-check",
                    "section": "Academic Management",
                    "badge": None,
                }
            )
        in_backend = (
            request.path.startswith("/backend")
            or "/authentication/backend" in request.path
        )
        student_list_url = _safe_reverse("accounts:backend_student_list")
        if not student_list_url and is_superuser and not in_backend:
            student_list_url = _safe_reverse("admin:people_studentprofile_changelist")
        if student_list_url:
            items.append(
                {
                    "id": "students",
                    "label": "Student Profiles",
                    "url": student_list_url,
                    "icon": "bi-person-lines-fill",
                    "section": "People & Access",
                    "badge": None,
                }
            )
        guardian_list_url = _safe_reverse("accounts:backend_guardian_list")
        if guardian_list_url:
            items.append(
                {
                    "id": "guardians_backend",
                    "label": "Guardians",
                    "url": guardian_list_url,
                    "icon": "bi-people-fill",
                    "section": "People & Access",
                    "badge": None,
                }
            )
        if is_superuser and not in_backend:
            items.append(
                {
                    "id": "guardians",
                    "label": "Student Guardians",
                    "url": _safe_reverse("admin:people_studentguardian_changelist"),
                    "icon": "bi-people-fill",
                    "section": "People & Access",
                    "badge": None,
                }
            )
            items.append(
                {
                    "id": "groups",
                    "label": "Authentication Groups",
                    "url": _safe_reverse("admin:auth_group_changelist"),
                    "icon": "bi-unlock",
                    # Permission-group configuration = config, not a people roster.
                    "section": "Access & Roles",
                    "badge": None,
                }
            )
        _rbac_url = studio_shell_url or _safe_reverse("accounts:rbac")
        _tenant_identity_url = _safe_reverse("accounts:tenant_identity_roster")
        if _tenant_identity_url and (
            is_superuser
            or (getattr(user, "role", "") or "").upper() in ("ADMIN", "IT_ADMIN", "LEADERSHIP")
        ):
            items.append(
                {
                    "id": "tenant_identity",
                    "label": "Staff Identity & Access",
                    "url": _tenant_identity_url,
                    "icon": "bi-person-badge",
                    # Identity/access provisioning = config, not a people roster.
                    "section": "Access & Roles",
                    "badge": None,
                }
            )
        if _rbac_url:
            items.append(
                {
                    "id": "rbac",
                    "label": "RBAC & Access Control",
                    "url": _rbac_url,
                    "icon": "bi-diagram-3",
                    # Access-control rules = config, not a people roster.
                    "section": "Access & Roles",
                    "badge": None,
                }
            )
        items.append(
            {
                "id": "eval_admin",
                "label": "Evaluation Admin",
                "url": _safe_reverse("evals:evaluation_admin"),
                "icon": "bi-clipboard-data",
                "section": "Academic Management",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "class_ranking",
                "label": "Class Ranking",
                "url": _safe_reverse("evals:class_ranking"),
                "icon": "bi-trophy",
                "section": "Academic Management",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "school_ranking",
                "label": "School Ranking",
                "url": _safe_reverse("evals:school_ranking"),
                "icon": "bi-bar-chart-line",
                "section": "Academic Management",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "publish_results",
                "label": "Publish Results",
                "url": _safe_reverse("reports:publish_term_results"),
                "icon": "bi-megaphone",
                "section": "Academic Management",
                "badge": None,
            }
        )
        # Athletics admin console (seasons + fixtures) — for academic leadership.
        # Surfaced to the admin tier or anyone granted athletics.manage/athletics.view.
        if (
            can_manage_site
            or _safe_has_feature_permission(user, "athletics.manage")
            or _safe_has_feature_permission(user, "athletics.view")
        ):
            items.append(
                {
                    "id": "athletics_admin",
                    "label": "Athletics",
                    "url": _safe_reverse("athletics:admin_seasons"),
                    "icon": "bi-trophy",
                    "section": "Academic Management",
                    "badge": None,
                }
            )
        # Executive dashboard: Principal, Vice Principal, and Secretary do not see Bursar/accounting
        if role not in ("PRINCIPAL", "VICE_PRINCIPAL", "SECRETARY"):
            items.append(
                {
                    "id": "finance_dashboard",
                    "label": "Finance Dashboard",
                    "url": _safe_reverse("finance:dashboard"),
                    "icon": "bi-currency-exchange",
                    "section": "Financial Management",
                    "badge": finance_badge,
                }
            )
            items.append(
                {
                    "id": "payroll",
                    "label": "Payroll",
                    "url": _safe_reverse("payroll:dashboard"),
                    "icon": "bi-cash-stack",
                    "section": "Financial Management",
                    "badge": None,
                }
            )
        if role == "ACCOUNTANT":
            items.append(
                {
                    "id": "bursar_entries",
                    "label": "Bursar Entries Report",
                    "url": _safe_reverse("finance:bursar_entries_report"),
                    "icon": "bi-journal-bookmark",
                    "section": "Financial Management",
                    "badge": None,
                }
            )
            items.append(
                {
                    "id": "expense_vs_budget",
                    "label": "Expense vs Budget",
                    "url": _safe_reverse("finance:expense_vs_budget"),
                    "icon": "bi-pie-chart",
                    "section": "Financial Management",
                    "badge": None,
                }
            )
        items.append(
            {
                "id": "analytics",
                "label": "Analytics",
                "url": _safe_reverse("analytics:dashboard"),
                "icon": "bi-graph-up-arrow",
                "section": "Analytics & Reports",
                "badge": None,
            }
        )
        if role in ("PROPRIETOR", "LEADERSHIP", "ADMIN"):
            items.append(
                {
                    "id": "strategic_report",
                    "label": "Strategic Report",
                    "url": _safe_reverse("analytics:strategic_report"),
                    "icon": "bi-flag",
                    "section": "Analytics & Reports",
                    "badge": None,
                }
            )
        _report_base = studio_shell_url or _safe_reverse("studio_os:output")
        if _report_base:
            _rq = "&" if "?" in _report_base else "?"
            _report_url = f"{_report_base}{_rq}pane=reports"
            items.append(
                {
                    "id": "report_library",
                    "label": "Report Library",
                    "url": _report_url,
                    "icon": "bi-journal-text",
                    "section": "Analytics & Reports",
                    "badge": None,
                }
            )
        items.append(
            {
                "id": "bulk_letters",
                "label": "Bulk Letters",
                "url": _safe_reverse("siteconfig:bulk_letters"),
                "icon": "bi-envelope-paper",
                # Mail-merge template management = configuration, not a day-to-day
                # report — belongs in the config zone, not Analytics & Reports.
                "section": "Templates & Branding",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "reportcard_builder",
                "label": "Report Card Builder",
                "url": _safe_reverse("siteconfig:reportcard_builder"),
                "icon": "bi-file-earmark-richtext",
                # Report-card template builder = configuration, not a day-to-day
                # report — belongs in the config zone, not Analytics & Reports.
                "section": "Templates & Branding",
                "badge": None,
            }
        )
        items.append(
            {
                "id": "portal_stats",
                "label": "Portal Stats",
                "url": _safe_reverse("portal:portal_stats"),
                "icon": "bi-graph-up",
                "section": "Analytics & Reports",
                "badge": None,
            }
        )
        # Admin Panel last: Dashboard Layout, Feature Control, Backend Console, Workflow Center, Customizer, Site Settings, Region Configuration, Django Admin
        dashboard_layout_url = _dashboard_layout_url(request, user)
        if dashboard_layout_url:
            items.append(
                {
                    "id": "dashboard_layout",
                    "label": "Dashboard Layout",
                    "url": dashboard_layout_url,
                    "icon": "bi-grid-3x3-gap",
                    "section": "Display & Platform",
                    "badge": None,
                }
            )
        if is_superuser or getattr(user, "has_feature_permission", lambda _: False)(
            "settings.feature_control"
        ):
            _fc_url = studio_shell_url or _safe_reverse(
                "siteconfig:feature_control_panel"
            )
            if _fc_url:
                items.append(
                    {
                        "id": "feature_control",
                        "label": "Feature Control",
                        "url": _fc_url,
                        "icon": "bi-toggle-on",
                        "section": "Display & Platform",
                        "badge": None,
                    }
                )
            _fca_url = studio_shell_url or _safe_reverse(
                "siteconfig:feature_control_audit"
            )
            if _fca_url:
                items.append(
                    {
                        "id": "feature_control_audit",
                        "label": "Feature Control Audit",
                        "url": _fca_url,
                        "icon": "bi-clock-history",
                        "section": "Display & Platform",
                        "badge": None,
                    }
                )
        if backend_flags.get("enable_api_center") and (
            getattr(user, "has_feature_permission", lambda _: False)(
                "api_center.manage"
            )
            or role in ("ADMIN", "IT_ADMIN")
        ):
            items.append(
                {
                    "id": "api_center",
                    "label": "Integrations & API Center",
                    "url": _safe_reverse("apicenter:dashboard"),
                    "icon": "bi-plug",
                    "section": "Integrations & Data",
                    "badge": None,
                }
            )
        items.append(
            {
                "id": "backend",
                "label": "Admin Home",
                "url": _safe_reverse("accounts:backend_dashboard"),
                "icon": "bi-gear-fill",
                "section": "Display & Platform",
                "badge": None,
            }
        )
        if role in ("ADMIN", "IT_ADMIN", "PROPRIETOR", "LEADERSHIP") or is_superuser:
            _dinterop = _safe_reverse("accounts:district_lms_interop")
            if _dinterop:
                items.append(
                    {
                        "id": "district_lms_interop",
                        "label": "District & LMS interop",
                        "url": _dinterop,
                        "icon": "bi-link-45deg",
                        "section": "Integrations & Data",
                        "badge": None,
                    }
                )
            _iw = _safe_reverse("accounts:institution_profile_wizard")
            if _iw:
                items.append(
                    {
                        "id": "institution_profile_wizard",
                        "label": "Institution profile",
                        "url": _iw,
                        "icon": "bi-building",
                        "section": "Configuration",
                        "badge": None,
                    }
                )
        # Studio OS as single entry: Workflow Center and Approval Hub open from Studio (legacy URLs redirect when not from_studio=1).
        # Workflow Center → its OWN procedural-checklist view (distinct destination);
        # Workflow Hub below → the automation builder. Prioritising workflow_center
        # here stops the two sidebar rows collapsing onto the same /studio/automation/
        # URL. Falls back to automation only if the dedicated view is unregistered.
        workflow_center_url = _safe_reverse("studio_os:workflow_center") or _safe_reverse(
            "studio_os:automation"
        )
        if workflow_center_url:
            items.append(
                {
                    "id": "workflow_center",
                    "label": "Workflow Center",
                    "url": workflow_center_url,
                    "icon": "bi-diagram-3",
                    # Day-to-day operations (carries a pending badge) — not config.
                    "section": "Workflows & Approvals",
                    "badge": workflow_badge,
                }
            )
        approval_hub_url = studio_shell_url or _safe_reverse("studio_os:approval_hub")
        if approval_hub_url:
            items.append(
                {
                    "id": "approval_hub",
                    "label": "Approval Hub",
                    "url": approval_hub_url,
                    "icon": "bi-clipboard-check",
                    # Day-to-day approvals work — not config.
                    "section": "Workflows & Approvals",
                    "badge": None,
                }
            )
        # v4.00.12: DSL safeguarding inbox sidebar entry. The kernel
        # (apps/safeguarding/dsl_notify.py) shipped at v3.97.0; this is the
        # missing sidebar wiring. Badge = urgent-unacknowledged count for the
        # current school, computed once per render (cheap dict read). Visible
        # only when the inbox has entries — keeps the rail uncluttered for
        # schools without active concerns.
        _safeguarding_school = getattr(request, "school", None)
        if _safeguarding_school is not None:
            try:
                from apps.safeguarding.dsl_notify import count_urgent_unacknowledged

                _settings_dict = getattr(_safeguarding_school, "settings", None) or {}
                _sg_bucket = (
                    _settings_dict.get("safeguarding") if isinstance(_settings_dict, dict) else None
                ) or {}
                _inbox = _sg_bucket.get("dsl_inbox") if isinstance(_sg_bucket, dict) else None
                if isinstance(_inbox, list) and _inbox:
                    _badge_count = count_urgent_unacknowledged(_inbox)
                    try:
                        from django.urls import reverse

                        _sg_url = reverse("accounts:safeguarding_inbox")
                    except Exception:  # noqa: BLE001
                        _sg_url = "/authentication/backend/safeguarding/"
                    items.append(
                        {
                            "id": "safeguarding_inbox",
                            "label": "Safeguarding",
                            "url": _sg_url,
                            "icon": "bi-shield-exclamation",
                            # Urgent child-protection alerts (urgent badge) — day-to-day, not config.
                            "section": "Workflows & Approvals",
                            "badge": _badge_count if _badge_count > 0 else None,
                        }
                    )
            except Exception:  # noqa: BLE001 — sidebar must never break on dsl_notify import errors
                pass
        _school = getattr(request, "school", None)
        if _school:
            workflow_hub_url = _safe_reverse("studio_os:automation")
            if workflow_hub_url:
                items.append(
                    {
                        "id": "workflow_hub",
                        "label": "Workflow Hub",
                        "url": workflow_hub_url,
                        "icon": "bi-diagram-3-fill",
                        # Day-to-day workflow operations — not config.
                        "section": "Workflows & Approvals",
                        "badge": None,
                    }
                )
            dashboard_hub_url = _safe_reverse("siteconfig:dashboard_hub")
            if dashboard_hub_url:
                items.append(
                    {
                        "id": "dashboard_hub",
                        "label": "Dashboard Hub",
                        "url": dashboard_hub_url,
                        "icon": "bi-grid-3x3-gap",
                        "section": "Display & Platform",
                        "badge": None,
                    }
                )
            get_blueprints_url = _safe_reverse("siteconfig:get_blueprints")
            if get_blueprints_url:
                items.append(
                    {
                        "id": "get_blueprints",
                        "label": "Blueprints",
                        "url": get_blueprints_url,
                        "icon": "bi-journal-richtext",
                        "section": "Templates & Branding",
                        "badge": None,
                    }
                )
        # Import & bulk: entry via Studio OS Overview when available; else legacy import hub.
        import_hub_url = studio_shell_url or _safe_reverse("studio_os:import_hub")
        if import_hub_url:
            items.append(
                {
                    "id": "import_hub",
                    "label": "Import & bulk",
                    "url": import_hub_url,
                    "icon": "bi-upload",
                    "section": "Integrations & Data",
                    "badge": None,
                }
            )
        if can_manage_site:
            # §6.14 Connect portal to Experience Studio: direct link for theme/branding (RUNMYCAMPUS SOT)
            experience_url = _safe_reverse("studio_os:experience")
            if experience_url:
                items.append(
                    {
                        "id": "experience_studio",
                        "label": "Theme & Experience",
                        "url": experience_url,
                        "icon": "bi-palette",
                        "section": "Templates & Branding",
                        "badge": None,
                    }
                )
            items.append(
                {
                    "id": "studio",
                    "label": "Studio",
                    "url": _safe_reverse("studio_os:shell"),
                    "icon": "bi-grid-3x3-gap",
                    "section": "Templates & Branding",
                    "badge": None,
                }
            )
        # Multi-tenant: Modules and Grading are per-school; show only when a school is in context.
        _school = getattr(request, "school", None)
        if _school and (
            role in ("ADMIN", "LEADERSHIP", "IT_ADMIN", "PRINCIPAL", "VICE_PRINCIPAL")
            or is_staff
            or is_superuser
        ):
            _mm_url = _safe_reverse("siteconfig:module_market")
            if _mm_url:
                items.append(
                    {
                        "id": "module_market",
                        "label": "Modules",
                        "url": _mm_url,
                        "icon": "bi-puzzle",
                        "section": "Configuration",
                        "badge": None,
                    }
                )
            _gs_url = _safe_reverse("siteconfig:grading_settings")
            if _gs_url:
                items.append(
                    {
                        "id": "grading_settings",
                        "label": "Grading & language",
                        "url": _gs_url,
                        "icon": "bi-translate",
                        "section": "Configuration",
                        "badge": None,
                    }
                )
        if is_superuser and not in_backend:
            site_pk = getattr(site, "pk", 1)
            from apps.siteconfig.staff_navigation import site_settings_change_url

            _ss_url = site_settings_change_url(request, site_pk)
            if _ss_url:
                items.append(
                    {
                        "id": "site_settings",
                        "label": "Site Settings",
                        "url": _ss_url,
                        "icon": "bi-gear-wide",
                        "section": "Configuration",
                        "badge": None,
                    }
                )
            items.append(
                {
                    "id": "region_config",
                    "label": "Region Configuration",
                    "url": _safe_reverse(
                        "admin:global_registries_regionconfig_changelist"
                    ),
                    "icon": "bi-geo-alt",
                    "section": "Configuration",
                    "badge": None,
                }
            )
        if is_superuser:
            items.append(
                {
                    "id": "admin_panel",
                    "label": "Config center",
                    "url": _safe_reverse("siteconfig:console_domains_hub"),
                    "icon": "bi-gear-wide-connected",
                    "section": "Configuration",
                    "badge": None,
                }
            )

    # Grant-responsive operational nav: a user whose ROLE isn't in the staff floor but who
    # was explicitly GRANTED a granular feature permission (e.g. a custom "Bursar" role with
    # finance.manage, or an HR role with payroll.manage) still needs to DISCOVER the surface
    # they can now reach. Staff-role users already got these in the admin block above, so this
    # only fires for non-staff, non-family, non-teacher effective roles. Each item is gated on
    # its own code, so nothing is surfaced that the back-end would then 403.
    if (
        not show_staff_admin_nav
        and not family_effective_role
        and nav_role != User.Role.TEACHER
    ):
        if _safe_has_feature_permission(
            user, "finance.view"
        ) or _safe_has_feature_permission(user, "finance.manage"):
            items.append(
                {
                    "id": "finance_dashboard",
                    "label": "Finance Dashboard",
                    "url": _safe_reverse("finance:dashboard"),
                    "icon": "bi-currency-exchange",
                    "section": "Financial Management",
                    "badge": finance_badge,
                }
            )
        if _safe_has_feature_permission(
            user, "payroll.view"
        ) or _safe_has_feature_permission(user, "payroll.manage"):
            items.append(
                {
                    "id": "payroll",
                    "label": "Payroll",
                    "url": _safe_reverse("payroll:dashboard"),
                    "icon": "bi-cash-stack",
                    "section": "Financial Management",
                    "badge": None,
                }
            )
        if _safe_has_feature_permission(user, "analytics.view"):
            items.append(
                {
                    "id": "analytics",
                    "label": "Analytics",
                    "url": _safe_reverse("analytics:dashboard"),
                    "icon": "bi-graph-up-arrow",
                    "section": "Analytics & Reports",
                    "badge": None,
                }
            )
        # A COACH (custom role, not in the staff floor) granted athletics.view still
        # needs to discover their coach console — mirror the finance/payroll grant path.
        if _safe_has_feature_permission(
            user, "athletics.view"
        ) or _safe_has_feature_permission(user, "athletics.manage"):
            items.append(
                {
                    "id": "coach_console",
                    "label": "Athletics",
                    "url": _safe_reverse("athletics:coach_dashboard"),
                    "icon": "bi-trophy",
                    "section": "Academic Management",
                    "badge": None,
                }
            )

    # Drop items with no URL
    items = [x for x in items if x.get("url")]

    # Sort by portal_sidebar_order if set
    order = getattr(site, "portal_sidebar_order", None) or []
    if isinstance(order, list) and len(order) > 0:
        id_to_item = {x["id"]: x for x in items}
        ordered_ids = []
        seen_order_ids = set()
        for raw_id in order:
            if not isinstance(raw_id, str):
                continue
            item_id = raw_id.strip()
            if not item_id or item_id not in id_to_item or item_id in seen_order_ids:
                continue
            seen_order_ids.add(item_id)
            ordered_ids.append(item_id)
        remaining = [x for x in items if x["id"] not in ordered_ids]
        items = [id_to_item[i] for i in ordered_ids] + remaining

    items = _dedupe_sidebar_items(items)

    # Multi-tenant: hide items for modules the school has not enabled.
    # Prefer request.tenant_runtime (entitlements.modules, flags) when available; else Policy Registry / is_feature_enabled.
    school = getattr(request, "school", None)
    runtime = getattr(request, "tenant_runtime", None)
    if (
        runtime
        and getattr(runtime, "entitlements", None)
        and getattr(runtime.entitlements, "modules", None)
    ):
        allowed_modules = set(
            m.lower() if isinstance(m, str) else str(m).lower()
            for m in runtime.entitlements.modules
        )
        # Feature-gated items: show only if feature key is in entitlements or flags
        flags = getattr(getattr(runtime, "flags", None), "flags", None) or {}

        def _item_visible(it):
            feat = it.get("feature")
            if feat is None:
                return True
            return (
                flags.get(feat, False)
                or feat.replace("_", ".") in allowed_modules
                or any(feat in m for m in allowed_modules)
            )

        items = [it for it in items if _item_visible(it)]
    elif school:
        from apps.schools.models import is_feature_enabled

        items = [
            it
            for it in items
            if it.get("feature") is None
            or is_feature_enabled(school, it.get("feature") or "")
        ]

    # Tag each item with its surface (day-to-day "ops" vs platform "config") so the
    # template / callers can tell them apart, and so configuration never interleaves
    # into the operational sidebar.
    for it in items:
        it["surface"] = _portal_item_surface(it.get("section"))

    # Group by section so each section title appears only once ({% ifchanged item.section %}).
    # Section order = first occurrence within each surface, but all config sections sort
    # to the bottom as one contiguous configuration zone (the tenant ops/config split).
    section_order = []
    seen = set()
    for it in items:
        sec = it.get("section") or ""
        if sec not in seen:
            seen.add(sec)
            section_order.append(sec)
    section_order = _order_sections_ops_then_config(section_order)
    by_section = {}
    for it in items:
        sec = it.get("section") or ""
        by_section.setdefault(sec, []).append(it)
    items = []
    for sec in section_order:
        items.extend(by_section.get(sec, []))

    # Server-side active state. The template already reads item.is_current /
    # section_is_active but nothing populated them, so on first paint no nav item
    # was highlighted and the active section's group rendered collapsed (only the
    # first group opened). Client JS refines this, but computing it server-side
    # fixes the no-highlight / collapsed-active flash. Additive only; getattr with
    # a default never raises, and an empty path leaves every flag falsy.
    current_path = getattr(request, "path", "") or ""
    if current_path:
        exact = [it for it in items if it.get("url") == current_path]
        if exact:
            for it in exact:
                it["is_current"] = True
        else:
            # No exact match (e.g. a detail page) -> the longest non-root URL
            # prefix wins, so a child page highlights its section's nav item.
            best = None
            best_len = 0
            for it in items:
                url = it.get("url") or ""
                if len(url) > 1 and current_path.startswith(url) and len(url) > best_len:
                    best, best_len = it, len(url)
            if best is not None:
                best["is_current"] = True
        active_sections = {
            it.get("section") for it in items if it.get("is_current")
        }
        for it in items:
            it["section_is_active"] = it.get("section") in active_sections

    return items


# ---------------------------------------------------------------------------
# Resilient baseline nav (under-provisioned tenant / transient-failure safety net)
# ---------------------------------------------------------------------------
#
# When the full builder above raises or yields nothing — the classic
# under-provisioned new-tenant symptom — the context processor used to return ``[]``,
# which made ``portal_base.html`` fall through to a HARDCODED, role-only, NON
# permission-gated fallback nav. This baseline replaces that dead-end: a small set of
# KNOWN-GOOD routes, role + permission gated, every URL resolved through
# ``_safe_reverse`` so a route absent on a half-provisioned tenant is skipped rather
# than rendered broken. It never raises (anonymous users get ``[]`` so the template's
# last-resort fallback still applies).

# (id, label, url_name, icon, section) — shown to every authenticated user.
_BASELINE_COMMON = (
    ("home", "Home", "accounts:redirect", "bi-speedometer2", "Home"),
    ("profile", "My Profile", "accounts:user_profile", "bi-person", "Account"),
    ("preferences", "Preferences", "siteconfig:user_preferences", "bi-sliders", "Account"),
    ("notifications", "Notifications", "accounts:user_notifications", "bi-bell", "Account"),
    ("kb", "Knowledge Base", "kb:kb_home", "bi-journal-text", "Account"),
)

# Per-role operational floor (mirrors the known-good routes the legacy hardcoded
# fallback used, so nothing here is a guessed URL name).
_BASELINE_BY_ROLE = {
    User.Role.TEACHER.value: (
        ("teacher_home", "My Classes", "portal:teacher_dashboard_alias", "bi-grid", "Workspace"),
        ("teacher_workflow", "My Workflow", "portal:teacher_workflow", "bi-diagram-3", "Workspace"),
        ("teacher_homework", "Homework", "portal:teacher_assignments", "bi-journal-text", "Learning Management"),
        ("teacher_marks", "Gradebook / Marks", "evals:teacher_marks_list", "bi-table", "Workspace"),
        ("teacher_attendance", "Attendance", "portal:teacher_attendance", "bi-clipboard-check", "Workspace"),
        ("teacher_timetable", "Timetable", "portal:teacher_timetable", "bi-calendar-week", "Workspace"),
    ),
    User.Role.PARENT.value: (
        ("parent_home", "Family Home", "portal:parent_dashboard", "bi-house", "Home"),
        ("parent_workflow", "My Workflow", "portal:parent_workflow", "bi-diagram-3", "My Workflow"),
        ("parent_finance", "Finance", "portal:parent_finance", "bi-cash-coin", "Finance"),
        ("parent_calendar", "Calendar", "portal:unified_calendar", "bi-calendar3", "Calendar"),
    ),
    User.Role.STUDENT.value: (
        ("student_home", "Student Home", "portal:student_portal_grades", "bi-house", "Home"),
        ("student_homework", "Homework", "portal:student_assignments", "bi-pencil-square", "Learning"),
        ("student_workflow", "My Workflow", "portal:student_workflow", "bi-diagram-3", "My Workflow"),
    ),
}

# Admin/leadership floor — (id, label, url_name, icon, section, feature_perm_or_None).
# The Command Center + Setup wizards are ALWAYS present (no feature gate) so a brand-new
# admin can finish provisioning even when the full builder can't run.
_BASELINE_ADMIN = (
    ("backend_dashboard", "Admin Home", "accounts:backend_dashboard", "bi-gear-fill", "Admin Panel", None),
    ("setup_wizards", "Setup wizards", "setup_studio:tenant_wizard_index", "bi-magic", "Admin Panel", None),
    ("people", "Student Profiles", "accounts:backend_student_list", "bi-person-lines-fill", "People & Access", None),
    ("rbac", "RBAC & Access Control", "accounts:rbac", "bi-diagram-3", "People & Access", None),
    ("finance", "Money Center", "finance:dashboard", "bi-currency-exchange", "Financial Management", "settings.manage"),
    ("config", "School Configuration", "school_configuration_center_canonical", "bi-sliders", "Configuration", "settings.manage"),
)

# ADMIN is canonical (User.Role); LEADERSHIP/IT_ADMIN/PRINCIPAL/BURSAR are extended
# tenant roles not present in User.Role TextChoices (see role_registry).
_BASELINE_ADMIN_ROLES = frozenset(
    {User.Role.ADMIN.value, "LEADERSHIP", "IT_ADMIN", "PRINCIPAL", "BURSAR"}  # role-string-allow: sidebar-baseline-admin-floor-extended-roles
)


def _safe_has_feature_permission(user, codename):
    """Best-effort feature-permission check that never raises (fail-closed)."""
    try:
        if getattr(user, "is_superuser", False):
            return True
        checker = getattr(user, "has_feature_permission", None)
        if callable(checker):
            return bool(checker(codename))
    except OPTIONAL_SIDEBAR_ERRORS:
        return False
    return False


def _baseline_item(item_id, label, url_name, icon, section):
    url = _baseline_reverse(url_name)
    if not url:
        return None
    return {
        "id": item_id,
        "label": label,
        "url": url,
        "icon": icon,
        "section": section,
        "surface": _portal_item_surface(section),
    }


def build_portal_sidebar_baseline(request, site=None):
    """Resilient minimal sidebar for authenticated users.

    Served when ``build_portal_sidebar_items`` raises or returns nothing. Returns
    a role + permission gated list of known-good nav items; NEVER raises. Returns
    ``[]`` only for anonymous users (so the template's last-resort fallback applies).
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    # Role resolution must never break the resilient baseline. get_nav_portal_role
    # reaches into request.session, which a degenerate / middleware-bypassing
    # request may lack — fall back to the user's own role so the safety net still
    # delivers a gated nav instead of raising (the function's "NEVER raises" contract).
    try:
        from apps.accounts.portal_roles import get_nav_portal_role

        nav_role = get_nav_portal_role(request) or (getattr(user, "role", "") or "").upper()
    except Exception:  # noqa: BLE001 — baseline degrades to user.role, never raises
        nav_role = (getattr(user, "role", "") or "").upper()
    staff_privileged = bool(getattr(user, "is_staff", False)) or bool(
        getattr(user, "is_superuser", False)
    )
    family_effective_role = nav_role in (User.Role.PARENT, User.Role.STUDENT)
    show_admin_baseline = staff_privileged and not family_effective_role

    items = []
    for spec in _BASELINE_COMMON:
        it = _baseline_item(*spec)
        if it:
            items.append(it)
    for spec in _BASELINE_BY_ROLE.get(nav_role, ()):  # role-specific operational floor
        it = _baseline_item(*spec)
        if it:
            items.append(it)
    if show_admin_baseline or (
        not family_effective_role and nav_role in _BASELINE_ADMIN_ROLES
    ):
        for item_id, label, url_name, icon, section, perm in _BASELINE_ADMIN:
            if perm and not _safe_has_feature_permission(user, perm):
                continue
            it = _baseline_item(item_id, label, url_name, icon, section)
            if it:
                items.append(it)
    return items
