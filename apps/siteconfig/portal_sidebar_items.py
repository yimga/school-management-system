"""
Build portal sidebar nav items for the current user, optionally sorted by SiteSettings.portal_sidebar_order.

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
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache

User = get_user_model()


def _dashboard_layout_url(request, user):
    """Link to Backend dashboard + ?customize=1 (only backend supports layout customization)."""
    try:
        from apps.siteconfig.dashboard_views import _can_customize
        if not _can_customize(user):
            return None
        return _safe_reverse("accounts:backend_dashboard") + "?customize=1"
    except Exception:
        return _safe_reverse("accounts:backend_dashboard") + "?customize=1"


def _safe_reverse(url_name, kwargs=None, args=None, default=None):
    try:
        if args is not None:
            return reverse(url_name, args=args)
        return reverse(url_name, kwargs=kwargs or {})
    except Exception:
        return default


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

    if role == "TEACHER":
        try:
            from django.db.models import Q
            from apps.people.models import TeacherProfile, TeacherLeaveRequest
            from apps.evals.models import Evaluation
            from apps.academics.services import get_active_year_and_term

            teacher_profile = TeacherProfile.objects.filter(user=user).only("id").first()
            if teacher_profile:
                year, _term = get_active_year_and_term()
                eval_qs = Evaluation.objects.filter(teacher=teacher_profile)
                if year:
                    eval_qs = eval_qs.filter(academic_year=year)
                pending_marks = eval_qs.filter(
                    Q(seq1_score__isnull=True) |
                    Q(seq2_score__isnull=True) |
                    Q(exam_score__isnull=True)
                ).count()
                pending_leaves = TeacherLeaveRequest.objects.filter(
                    teacher=teacher_profile,
                    status=TeacherLeaveRequest.Status.PENDING,
                ).count()
                workflow_pending = _badge_or_none(pending_marks + pending_leaves)
        except Exception:
            workflow_pending = None
        return workflow_pending, finance_pending, signatures_pending

    if role == "PARENT":
        try:
            from apps.portal.models import FormSignature
            from apps.portal.services import guardian_student_links, parent_dashboard_widget_data

            links = guardian_student_links(user, results_only=True)
            students = [link.student for link in links]
            widget_data = parent_dashboard_widget_data(students)
            tasks = widget_data.get("tasks", {}) if isinstance(widget_data, dict) else {}
            workflow_pending = _badge_or_none(tasks.get("pending_evaluations"))
            finance_pending = _badge_or_none(tasks.get("pending_payments"))
            signatures_pending = _badge_or_none(
                FormSignature.objects.filter(parent=user, status="PENDING").count()
            )
        except Exception:
            pass
        return workflow_pending, finance_pending, signatures_pending

    if staff_like:
        try:
            from apps.finance.models import Notification
            finance_pending = _badge_or_none(
                Notification.objects.filter(
                    recipient=user,
                    title__icontains="finance access request",
                    is_read=False,
                ).count()
            )
        except Exception:
            finance_pending = None

        try:
            from apps.portal.models import FormSignature
            signatures_pending = _badge_or_none(
                FormSignature.objects.filter(status="PENDING").count()
            )
        except Exception:
            signatures_pending = None

        try:
            from apps.academics.models import Classroom
            from apps.academics.services import get_active_year_and_term
            from apps.people.models import StudentProfile, TeacherProfile

            year, _term = get_active_year_and_term()
            if year:
                missing_steps = 0
                if not Classroom.objects.filter(academic_year=year, is_active=True).exists():
                    missing_steps += 1
                if not StudentProfile.objects.filter(academic_year=year, is_active=True).exists():
                    missing_steps += 1
                if not TeacherProfile.objects.filter(is_active=True).exists():
                    missing_steps += 1
                workflow_pending = _badge_or_none(missing_steps)
        except Exception:
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
    except Exception:
        prefix = "public"
    cache_key = f"{prefix}:portal_sidebar_badges:{user_id}:{role}:{1 if staff_like else 0}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    counts = _sidebar_badge_counts(user, role, staff_like)
    cache.set(cache_key, counts, 60)
    return counts


def _backend_flags_for_sidebar(request, site):
    """Resolve backend feature flags for sidebar visibility. Prefer request.tenant_runtime.flags when available."""
    try:
        from apps.platform_runtime.helpers import get_effective_flags
        return get_effective_flags(request) or getattr(site, "backend_feature_flags", None) or {}
    except Exception:
        return getattr(site, "backend_feature_flags", None) or {}


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
    from apps.accounts.portal_roles import get_effective_portal_role
    primary_role = (getattr(user, "role", "") or "").upper()
    role = get_effective_portal_role(request) or primary_role
    is_staff = getattr(user, "is_staff", False)
    is_superuser = getattr(user, "is_superuser", False)
    messages_unread_count = getattr(request, "messages_unread_count", None)
    # Staff-like: full or partial backend nav (use primary role so dual-hat users don't get staff nav when viewing as Parent)
    staff_like = is_staff or is_superuser or primary_role in (
        "ADMIN", "LEADERSHIP", "IT_ADMIN",
        "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "BURSAR", "ACCOUNTANT", "PROPRIETOR", "DISCIPLINE_MASTER", "SECRETARY",
    )
    workflow_badge, finance_badge, signatures_badge = _cached_sidebar_badge_counts(
        user, role, staff_like, request=request
    )

    items = []

    # --- Home ---
    items.append({"id": "dashboard", "label": "Dashboard", "url": _safe_reverse("accounts:redirect"), "icon": "bi-speedometer2", "section": "Home", "badge": None})
    # --- Account ---
    items.append({"id": "profile", "label": "My Profile", "url": _safe_reverse("accounts:user_profile"), "icon": "bi-person", "section": "Account", "badge": None})
    items.append({"id": "preferences", "label": "Preferences", "url": _safe_reverse("siteconfig:user_preferences"), "icon": "bi-sliders", "section": "Account", "badge": None})
    items.append({"id": "notifications", "label": "Notifications", "url": _safe_reverse("accounts:user_notifications"), "icon": "bi-bell", "section": "Account", "badge": None})
    items.append({"id": "kb", "label": "Knowledge Base", "url": _safe_reverse("kb:kb_home"), "icon": "bi-journal-text", "section": "Account", "badge": None})

    # --- Communication (role-dependent) ---
    if role == "TEACHER":
        items.append({"id": "messages", "label": "Messages", "url": _safe_reverse("accounts:user_messages"), "icon": "bi-chat-dots", "section": "Communication", "badge": messages_unread_count})
        items.append({"id": "message_groups", "label": "Message Groups", "url": _safe_reverse("communication:group_list"), "icon": "bi-people", "section": "Communication", "badge": None})
    elif role == "PARENT":
        items.append({"id": "contact_school", "label": "Contact School", "url": _safe_reverse("portal:parent_contact_school"), "icon": "bi-envelope-paper", "section": "Communication", "badge": None})
    elif role == "STUDENT":
        items.append({"id": "messages", "label": "Messages", "url": _safe_reverse("accounts:user_messages"), "icon": "bi-chat-dots", "section": "Communication", "badge": messages_unread_count})
    elif is_staff or is_superuser or role in ("ADMIN", "LEADERSHIP", "IT_ADMIN", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "PROPRIETOR", "SECRETARY"):
        items.append({"id": "messages", "label": "Messages", "url": _safe_reverse("accounts:user_messages"), "icon": "bi-chat-dots", "section": "Communication", "badge": messages_unread_count})
        items.append({"id": "message_groups", "label": "Message Groups", "url": _safe_reverse("communication:group_list"), "icon": "bi-people", "section": "Communication", "badge": None})
        try:
            from apps.communication.views_announcements import _can_create_school_wide_announcement, _can_access_school_wide_announcement_create
            if _can_access_school_wide_announcement_create(user):
                items.append({"id": "announcements", "label": "School-wide Announcements", "url": _safe_reverse("communication:announcement_create"), "icon": "bi-megaphone", "section": "Communication", "badge": None})
            if _can_create_school_wide_announcement(user):
                items.append({"id": "announcements_pending", "label": "Pending approval", "url": _safe_reverse("communication:announcement_list_pending"), "icon": "bi-hourglass-split", "section": "Communication", "badge": None})
        except Exception:
            pass

    # --- Teacher ---
    if role == "TEACHER":
        items.append({"id": "class_announcement", "label": "Class Announcement", "url": _safe_reverse("communication:class_announcement_create"), "icon": "bi-journal-text", "section": "Communication", "badge": None})
        items.append({"id": "teacher_workflow", "label": "My Workflow", "url": _safe_reverse("portal:teacher_workflow"), "icon": "bi-diagram-3", "section": "My Workflow", "badge": workflow_badge})
        items.append({"id": "marks_entry", "label": "Enter Marks", "url": _safe_reverse("evals:teacher_marks_entry"), "icon": "bi-pencil-square", "section": "Learning Management", "badge": None})
        items.append({"id": "marks_list", "label": "Marks History", "url": _safe_reverse("evals:teacher_marks_list"), "icon": "bi-table", "section": "Learning Management", "badge": None})
        items.append({"id": "attendance", "label": "Attendance", "url": _safe_reverse("portal:teacher_attendance"), "icon": "bi-clipboard-check", "section": "Learning Management", "badge": None})
        if getattr(user, "has_feature_permission", lambda _: False)("attendance.manage"):
            items.append({"id": "take_student_attendance", "label": "Take student attendance", "url": _safe_reverse("portal:take_student_attendance"), "icon": "bi-clipboard-check", "section": "Learning Management", "badge": None})
            items.append({"id": "take_teacher_attendance", "label": "Take teacher attendance", "url": _safe_reverse("portal:record_teacher_attendance"), "icon": "bi-person-check", "section": "Learning Management", "badge": None})
        items.append({"id": "timetable", "label": "My Timetable", "url": _safe_reverse("portal:teacher_timetable"), "icon": "bi-calendar-week", "section": "Learning Management", "badge": None})
        if backend_flags.get("enable_cahier_de_texte"):
            items.append({"id": "cahier", "label": "Cahier de Texte", "url": _safe_reverse("portal:cahier_list"), "icon": "bi-journal-text", "section": "Learning Management", "badge": None, "feature": "cahier_de_texte"})
        items.append({"id": "payslips", "label": "Payslips", "url": _safe_reverse("payroll:employee_payslips"), "icon": "bi-wallet2", "section": "Human Resources", "badge": None})
        items.append({"id": "leave", "label": "Leave Requests", "url": _safe_reverse("payroll:employee_leave"), "icon": "bi-calendar-check", "section": "Human Resources", "badge": None})
        items.append({"id": "pay_history", "label": "Pay History", "url": _safe_reverse("portal:teacher_pay_history"), "icon": "bi-receipt", "section": "Human Resources", "badge": None})
        items.append({"id": "portal_stats", "label": "Portal Stats", "url": _safe_reverse("portal:portal_stats"), "icon": "bi-graph-up", "section": "Settings", "badge": None})

    # --- Parent ---
    if role == "PARENT":
        items.append({"id": "parent_workflow", "label": "My Workflow", "url": _safe_reverse("portal:parent_workflow"), "icon": "bi-diagram-3", "section": "My Workflow", "badge": workflow_badge})
        items.append({"id": "my_children", "label": "My Children", "url": _safe_reverse("portal:parent_dashboard"), "icon": "bi-people", "section": "Children & Learning", "badge": None})
        items.append({"id": "finance", "label": "Finance & Fees", "url": _safe_reverse("portal:parent_finance"), "icon": "bi-cash-coin", "section": "Children & Learning", "badge": finance_badge})
        items.append({"id": "pending_signatures", "label": "Pending Signatures", "url": _safe_reverse("portal:signature_pending_list"), "icon": "bi-pen", "section": "Children & Learning", "badge": signatures_badge})
        items.append({"id": "link_child", "label": "Link Child", "url": _safe_reverse("portal:link_child"), "icon": "bi-person-plus", "section": "Children & Learning", "badge": None})
        items.append({"id": "claim_invite", "label": "Claim Invite", "url": _safe_reverse("portal:claim_invite"), "icon": "bi-ticket", "section": "Children & Learning", "badge": None})
        items.append({"id": "academic_stats", "label": "Academic Stats", "url": _safe_reverse("portal:portal_stats"), "icon": "bi-graph-up", "section": "Performance Tracking", "badge": None})

    # --- Portal Tools (per-feature RBAC). Documents goes under Content & Documents; for staff it's added in staff block to avoid duplicate section. ---
    portal_cfg = getattr(site, "portal_features", None) or {}
    if portal_cfg.get("forums") and getattr(user, "has_feature_permission", lambda _: False)("portal.forums"):
        items.append({"id": "portal_forums", "label": "Community", "url": _safe_reverse("portal:portal_feature", kwargs={"feature": "forums"}), "icon": "bi-people", "section": "Portal Tools", "badge": None})
    if portal_cfg.get("video") and getattr(user, "has_feature_permission", lambda _: False)("portal.video"):
        items.append({"id": "portal_video", "label": "Video Hub", "url": _safe_reverse("portal:portal_feature", kwargs={"feature": "video"}), "icon": "bi-camera-video", "section": "Portal Tools", "badge": None})
    # Documents: for teachers/parents add here (one Content & Documents section); for staff add in staff block below
    staff_gets_content_docs = (is_staff or is_superuser or role in ("ADMIN", "LEADERSHIP", "IT_ADMIN", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "BURSAR", "ACCOUNTANT", "PROPRIETOR", "DISCIPLINE_MASTER")) and role != "TEACHER"
    if portal_cfg.get("documents") and getattr(user, "has_feature_permission", lambda _: False)("portal.documents") and not staff_gets_content_docs:
        items.append({"id": "portal_documents", "label": "Documents", "url": _safe_reverse("portal:portal_feature", kwargs={"feature": "documents"}), "icon": "bi-file-earmark-text", "section": "Content & Documents", "badge": None})

    # --- Admin / Staff (exclude teachers: they get only Academic Management + HR, no Admin Panel/People/Finance/Analytics) ---
    can_manage_site = staff_like and (getattr(user, "has_feature_permission", lambda _: False)("settings.manage") or is_superuser)
    if staff_like and role != "TEACHER":
        # Support, Content & Documents, People & Access, Academic, Financial, Analytics first; Admin Panel last
        if staff_like:
            items.append({"id": "contact_requests", "label": "Contact Requests", "url": _safe_reverse("portal:staff_contact_request_list"), "icon": "bi-inbox", "section": "Support", "badge": None})
        if role in ("DISCIPLINE_MASTER", "CENSOR"):
            items.append({"id": "discipline_incidents", "label": "Disciplinary Incidents", "url": _safe_reverse("portal:discipline_incidents_list"), "icon": "bi-shield-exclamation", "section": "Support", "badge": None})
        # Content & Documents: Document Library Manager, Signature Requests, and portal Documents (single section)
        if can_manage_site:
            items.append({"id": "document_library_manage", "label": "Document Library Manager", "url": _safe_reverse("portal:document_library_manage"), "icon": "bi-folder2-open", "section": "Content & Documents", "badge": None})
            items.append({"id": "signature_requests", "label": "Signature Requests", "url": _safe_reverse("portal:signature_requests_manage"), "icon": "bi-pen", "section": "Content & Documents", "badge": signatures_badge})
        if portal_cfg.get("documents") and getattr(user, "has_feature_permission", lambda _: False)("portal.documents"):
            items.append({"id": "portal_documents", "label": "Documents", "url": _safe_reverse("portal:portal_feature", kwargs={"feature": "documents"}), "icon": "bi-file-earmark-text", "section": "Content & Documents", "badge": None})
        # Certification & Exams (GCE): admins get quick access; certification home handles disabled state.
        items.append({"id": "certification", "label": "Certification & Exams", "url": _safe_reverse("accounts:certification_home"), "icon": "bi-award", "section": "Academic Management", "badge": None})
        if backend_flags.get("enable_cahier_de_texte") and (getattr(user, "has_feature_permission", lambda _: False)("cahier.verify") or role == "CENSOR"):
            items.append({"id": "cahier_verify", "label": "Cahier verification", "url": _safe_reverse("portal:cahier_verify_list"), "icon": "bi-journal-check", "section": "Academic Management", "badge": None})
        if getattr(user, "has_feature_permission", lambda _: False)("attendance.manage"):
            items.append({"id": "take_student_attendance", "label": "Take student attendance", "url": _safe_reverse("portal:take_student_attendance"), "icon": "bi-clipboard-check", "section": "Academic Management", "badge": None})
            items.append({"id": "take_teacher_attendance", "label": "Take teacher attendance", "url": _safe_reverse("portal:record_teacher_attendance"), "icon": "bi-person-check", "section": "Academic Management", "badge": None})
        in_backend = request.path.startswith("/backend") or "/authentication/backend" in request.path
        student_list_url = _safe_reverse("accounts:backend_student_list")
        if not student_list_url and is_superuser and not in_backend:
            student_list_url = _safe_reverse("admin:people_studentprofile_changelist")
        if student_list_url:
            items.append({"id": "students", "label": "Student Profiles", "url": student_list_url, "icon": "bi-person-lines-fill", "section": "People & Access", "badge": None})
        guardian_list_url = _safe_reverse("accounts:backend_guardian_list")
        if guardian_list_url:
            items.append({"id": "guardians_backend", "label": "Guardians", "url": guardian_list_url, "icon": "bi-people-fill", "section": "People & Access", "badge": None})
        if is_superuser and not in_backend:
            items.append({"id": "guardians", "label": "Student Guardians", "url": _safe_reverse("admin:people_studentguardian_changelist"), "icon": "bi-people-fill", "section": "People & Access", "badge": None})
            items.append({"id": "groups", "label": "Authentication Groups", "url": _safe_reverse("admin:auth_group_changelist"), "icon": "bi-unlock", "section": "People & Access", "badge": None})
        items.append({"id": "rbac", "label": "RBAC & Access Control", "url": _safe_reverse("accounts:rbac"), "icon": "bi-diagram-3", "section": "People & Access", "badge": None})
        items.append({"id": "eval_admin", "label": "Evaluation Admin", "url": _safe_reverse("evals:evaluation_admin"), "icon": "bi-clipboard-data", "section": "Academic Management", "badge": None})
        items.append({"id": "class_ranking", "label": "Class Ranking", "url": _safe_reverse("evals:class_ranking"), "icon": "bi-trophy", "section": "Academic Management", "badge": None})
        items.append({"id": "school_ranking", "label": "School Ranking", "url": _safe_reverse("evals:school_ranking"), "icon": "bi-bar-chart-line", "section": "Academic Management", "badge": None})
        items.append({"id": "publish_results", "label": "Publish Results", "url": _safe_reverse("reports:publish_term_results"), "icon": "bi-megaphone", "section": "Academic Management", "badge": None})
        # Executive dashboard: Principal, Vice Principal, and Secretary do not see Bursar/accounting
        if role not in ("PRINCIPAL", "VICE_PRINCIPAL", "SECRETARY"):
            items.append({"id": "finance_dashboard", "label": "Finance Dashboard", "url": _safe_reverse("finance:dashboard"), "icon": "bi-currency-exchange", "section": "Financial Management", "badge": finance_badge})
            items.append({"id": "payroll", "label": "Payroll", "url": _safe_reverse("payroll:dashboard"), "icon": "bi-cash-stack", "section": "Financial Management", "badge": None})
        if role == "ACCOUNTANT":
            items.append({"id": "bursar_entries", "label": "Bursar Entries Report", "url": _safe_reverse("finance:bursar_entries_report"), "icon": "bi-journal-bookmark", "section": "Financial Management", "badge": None})
            items.append({"id": "expense_vs_budget", "label": "Expense vs Budget", "url": _safe_reverse("finance:expense_vs_budget"), "icon": "bi-pie-chart", "section": "Financial Management", "badge": None})
        items.append({"id": "analytics", "label": "Analytics", "url": _safe_reverse("analytics:dashboard"), "icon": "bi-graph-up-arrow", "section": "Analytics & Reports", "badge": None})
        if role in ("PROPRIETOR", "LEADERSHIP", "ADMIN"):
            items.append({"id": "strategic_report", "label": "Strategic Report", "url": _safe_reverse("analytics:strategic_report"), "icon": "bi-flag", "section": "Analytics & Reports", "badge": None})
        items.append({"id": "report_library", "label": "Report Library", "url": _safe_reverse("siteconfig:report_library"), "icon": "bi-journal-text", "section": "Analytics & Reports", "badge": None})
        items.append({"id": "bulk_letters", "label": "Bulk Letters", "url": _safe_reverse("siteconfig:bulk_letters"), "icon": "bi-envelope-paper", "section": "Analytics & Reports", "badge": None})
        items.append({"id": "reportcard_builder", "label": "Report Card Builder", "url": _safe_reverse("siteconfig:reportcard_builder"), "icon": "bi-file-earmark-richtext", "section": "Analytics & Reports", "badge": None})
        items.append({"id": "portal_stats", "label": "Portal Stats", "url": _safe_reverse("portal:portal_stats"), "icon": "bi-graph-up", "section": "Analytics & Reports", "badge": None})
        # Admin Panel last: Dashboard Layout, Feature Control, Backend Console, Workflow Center, Customizer, Site Settings, Region Configuration, Django Admin
        dashboard_layout_url = _dashboard_layout_url(request, user)
        if dashboard_layout_url:
            items.append({"id": "dashboard_layout", "label": "Dashboard Layout", "url": dashboard_layout_url, "icon": "bi-grid-3x3-gap", "section": "Admin Panel", "badge": None})
        if is_superuser or getattr(user, "has_feature_permission", lambda _: False)("settings.feature_control"):
            items.append({"id": "feature_control", "label": "Feature Control", "url": _safe_reverse("siteconfig:feature_control_panel"), "icon": "bi-toggle-on", "section": "Admin Panel", "badge": None})
            items.append({"id": "feature_control_audit", "label": "Feature Control Audit", "url": _safe_reverse("siteconfig:feature_control_audit"), "icon": "bi-clock-history", "section": "Admin Panel", "badge": None})
        if backend_flags.get("enable_api_center") and (getattr(user, "has_feature_permission", lambda _: False)("api_center.manage") or role in ("ADMIN", "IT_ADMIN")):
            items.append({"id": "api_center", "label": "Integrations & API Center", "url": _safe_reverse("apicenter:dashboard"), "icon": "bi-plug", "section": "Admin Panel", "badge": None})
        items.append({"id": "backend", "label": "Backend Console", "url": _safe_reverse("accounts:backend_dashboard"), "icon": "bi-gear-fill", "section": "Admin Panel", "badge": None})
        items.append({"id": "workflow_center", "label": "Workflow Center", "url": _safe_reverse("accounts:workflow_center"), "icon": "bi-diagram-3", "section": "Admin Panel", "badge": workflow_badge})
        approval_hub_url = _safe_reverse("accounts:approval_workflow_hub")
        if approval_hub_url:
            items.append({"id": "approval_hub", "label": "Approval Hub", "url": approval_hub_url, "icon": "bi-clipboard-check", "section": "Admin Panel", "badge": None})
        _school = getattr(request, "school", None)
        if _school:
            workflow_hub_url = _safe_reverse("siteconfig:workflow_hub")
            if workflow_hub_url:
                items.append({"id": "workflow_hub", "label": "Workflow Hub", "url": workflow_hub_url, "icon": "bi-diagram-3-fill", "section": "Admin Panel", "badge": None})
            dashboard_hub_url = _safe_reverse("siteconfig:dashboard_hub")
            if dashboard_hub_url:
                items.append({"id": "dashboard_hub", "label": "Dashboard Hub", "url": dashboard_hub_url, "icon": "bi-grid-3x3-gap", "section": "Admin Panel", "badge": None})
            get_blueprints_url = _safe_reverse("siteconfig:get_blueprints")
            if get_blueprints_url:
                items.append({"id": "get_blueprints", "label": "Blueprints", "url": get_blueprints_url, "icon": "bi-journal-richtext", "section": "Admin Panel", "badge": None})
        import_hub_url = _safe_reverse("accounts:import_hub")
        if import_hub_url:
            items.append({"id": "import_hub", "label": "Import & bulk", "url": import_hub_url, "icon": "bi-upload", "section": "Admin Panel", "badge": None})
        if can_manage_site:
            items.append({"id": "customizer", "label": "Customizer", "url": _safe_reverse("siteconfig:customizer"), "icon": "bi-palette", "section": "Admin Panel", "badge": None})
        # Multi-tenant: Modules and Grading are per-school; show only when a school is in context.
        _school = getattr(request, "school", None)
        if _school and (role in ("ADMIN", "LEADERSHIP", "IT_ADMIN", "PRINCIPAL", "VICE_PRINCIPAL") or is_staff or is_superuser):
            _mm_url = _safe_reverse("siteconfig:module_market")
            if _mm_url:
                items.append({"id": "module_market", "label": "Modules", "url": _mm_url, "icon": "bi-puzzle", "section": "Admin Panel", "badge": None})
            _gs_url = _safe_reverse("siteconfig:grading_settings")
            if _gs_url:
                items.append({"id": "grading_settings", "label": "Grading & language", "url": _gs_url, "icon": "bi-translate", "section": "Admin Panel", "badge": None})
        if is_superuser and not in_backend:
            site_pk = getattr(site, "pk", 1)
            items.append({"id": "site_settings", "label": "Site Settings", "url": _safe_reverse("admin:siteconfig_sitesettings_change", args=[site_pk]), "icon": "bi-gear-wide", "section": "Admin Panel", "badge": None})
            items.append({"id": "region_config", "label": "Region Configuration", "url": _safe_reverse("admin:siteconfig_regionconfig_changelist"), "icon": "bi-geo-alt", "section": "Admin Panel", "badge": None})
        if is_superuser:
            items.append({"id": "admin_panel", "label": "Configuration Engine", "url": _safe_reverse("admin:index"), "icon": "bi-gear-wide-connected", "section": "Admin Panel", "badge": None})

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

    # Global de-duplication safety (id-based) to prevent repeated nav items.
    deduped = []
    seen_item_ids = set()
    for item in items:
        item_id = item.get("id")
        if item_id and item_id in seen_item_ids:
            continue
        if item_id:
            seen_item_ids.add(item_id)
        deduped.append(item)
    items = deduped

    # Multi-tenant: hide items for modules the school has not enabled.
    # Prefer request.tenant_runtime (entitlements.modules, flags) when available; else Policy Registry / is_feature_enabled.
    school = getattr(request, "school", None)
    runtime = getattr(request, "tenant_runtime", None)
    if runtime and getattr(runtime, "entitlements", None) and getattr(runtime.entitlements, "modules", None):
        allowed_modules = set(m.lower() if isinstance(m, str) else str(m).lower() for m in runtime.entitlements.modules)
        # Feature-gated items: show only if feature key is in entitlements or flags
        flags = getattr(getattr(runtime, "flags", None), "flags", None) or {}
        def _item_visible(it):
            feat = it.get("feature")
            if feat is None:
                return True
            return flags.get(feat, False) or feat.replace("_", ".") in allowed_modules or any(feat in m for m in allowed_modules)
        items = [it for it in items if _item_visible(it)]
    elif school:
        from apps.schools.models import is_feature_enabled
        items = [
            it for it in items
            if it.get("feature") is None or is_feature_enabled(school, it.get("feature") or "")
        ]

    # Group by section so each section title appears only once ({% ifchanged item.section %}).
    # Section order = order of first occurrence in current list; items within each section keep relative order.
    section_order = []
    seen = set()
    for it in items:
        sec = it.get("section") or ""
        if sec not in seen:
            seen.add(sec)
            section_order.append(sec)
    by_section = {}
    for it in items:
        sec = it.get("section") or ""
        by_section.setdefault(sec, []).append(it)
    items = []
    for sec in section_order:
        items.extend(by_section.get(sec, []))

    return items
