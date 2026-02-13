from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

from django.core.cache import cache
from django.urls import NoReverseMatch, reverse
from django.utils import timezone


def _safe_reverse(name: str, fallback: str = "#") -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return fallback
    except Exception:
        return fallback


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return default


def _status_from_value(value: int, warn_at: int, danger_at: int) -> str:
    if value >= danger_at:
        return "danger"
    if value >= warn_at:
        return "warn"
    return "ok"


def _snapshot_cache_key(site_id: str, role_code: str) -> str:
    return f"dashboard:backend:v2:snapshot:{site_id}:{role_code or 'unknown'}"


def _has_permission(user, *codes: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    checker = getattr(user, "has_feature_permission", None)
    if not callable(checker):
        return False
    for code in codes:
        try:
            if code and checker(code):
                return True
        except Exception:
            continue
    return False


def _build_nav_item(label: str, icon: str, url: str, *, item_id: str = "", allow: bool = True) -> Optional[Dict[str, str]]:
    if not allow:
        return None
    if not url or url == "#":
        return None
    payload = {"label": label, "icon": icon, "url": url}
    if item_id:
        payload["id"] = item_id
    return payload


def _build_cached_snapshot(site_id: str, role_code: str) -> Dict[str, int]:
    key = _snapshot_cache_key(site_id, role_code)
    cached = cache.get(key)
    if cached:
        return cached

    students = classrooms = subjects = 0
    users = teachers = parents = 0
    invoices = overdue = drafts = 0
    pending_approvals = failed_logins_24h = system_incidents = 0

    try:
        from apps.people.models import StudentProfile, TeacherProfile
        students = StudentProfile.objects.filter(is_active=True).count()
        teachers = TeacherProfile.objects.filter(is_active=True).count()
    except Exception:
        pass

    try:
        from apps.academics.models import Classroom, Subject
        classrooms = Classroom.objects.filter(is_active=True).count()
        subjects = Subject.objects.filter(is_active=True).count()
    except Exception:
        pass

    try:
        from apps.accounts.models import User
        users = User.objects.count()
        if hasattr(User, "role"):
            parents = User.objects.filter(role="PARENT").count()
    except Exception:
        pass

    try:
        from apps.finance.models import Invoice
        invoices = Invoice.objects.count()
        overdue = Invoice.objects.filter(status="OVERDUE").count()
        drafts = Invoice.objects.filter(status="DRAFT").count()
    except Exception:
        pass

    try:
        from apps.requests.models import AccessRequest
        pending_approvals = AccessRequest.objects.filter(status=AccessRequest.Status.PENDING).count()
    except Exception:
        pass

    try:
        from apps.compliance.models_audit import AccessLog
        cutoff = timezone.now() - timedelta(hours=24)
        failed_logins_24h = AccessLog.objects.filter(
            resource__in=["/authentication/login/", "/admin/login/"],
            request_method="POST",
            timestamp__gte=cutoff,
        ).exclude(status__in=["302", "303"]).count()
    except Exception:
        failed_logins_24h = 0

    try:
        from apps.finance.models import Notification
        system_incidents = Notification.objects.filter(title__icontains="incident").count()
    except Exception:
        system_incidents = 0

    snapshot = {
        "students": students,
        "classrooms": classrooms,
        "subjects": subjects,
        "users": users,
        "teachers": teachers,
        "parents": parents,
        "invoices": invoices,
        "overdue": overdue,
        "drafts": drafts,
        "pending_approvals": pending_approvals,
        "failed_logins_24h": failed_logins_24h,
        "system_incidents": system_incidents,
    }
    cache.set(key, snapshot, 60)
    return snapshot


def build_dashboard_extras(request, base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Backend dashboard additions:
    - Overview cards
    - Admin portal band (Academics / Accounts / Finance)
    - Ops Watch
    - Welcome chips/action grid
    - Quick links
    - Command palette list
    - Local time + weather config from SiteSettings flags where available
    """
    base = base or {}
    now = timezone.localtime()
    user = getattr(request, "user", None)
    role_code = (getattr(user, "role", "") or "").upper()

    weather_cfg = {
        "enabled": True,
        "label": "Buea, Cameroon",
        "lat": 4.1527,
        "lon": 9.2410,
        "unit": "celsius",
    }

    site_id = "global"
    try:
        from apps.siteconfig.models import SiteSettings
        site = SiteSettings.get_solo()
        site_id = str(site.pk)
        flags = getattr(site, "backend_feature_flags", None) or {}
        weather_cfg.update({
            "enabled": flags.get("show_header_context_weather", weather_cfg["enabled"]),
            "label": flags.get("header_weather_label", weather_cfg["label"]),
            "lat": flags.get("header_weather_latitude", weather_cfg["lat"]),
            "lon": flags.get("header_weather_longitude", weather_cfg["lon"]),
            "unit": flags.get("header_weather_temperature_unit", weather_cfg["unit"]),
        })
    except Exception:
        pass

    snapshot = _build_cached_snapshot(site_id, role_code)

    fallback_stats = (base.get("stats") or {}) if isinstance(base.get("stats"), dict) else {}
    pending_approvals = snapshot.get("pending_approvals") or _safe_int(base.get("pending_approvals_count"))
    overdue = snapshot.get("overdue") or _safe_int(fallback_stats.get("overdue_invoices"))
    finance_requests = _safe_int(base.get("finance_requests_count"))
    failed_logins_24h = snapshot.get("failed_logins_24h") or _safe_int(base.get("failed_logins_24h"))
    system_incidents = snapshot.get("system_incidents")

    at_risk_value = _safe_int(fallback_stats.get("pending_referrals")) + overdue
    if at_risk_value == 0:
        at_risk_value = overdue

    admin_roles = {
        "SUPERADMIN",
        "ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
        "IT_ADMIN",
        "HOD",
        "DEPT_LEAD",
        "PROPRIETOR",
    }
    people_roles = admin_roles | {"SECRETARY", "ACADEMICS_STAFF"}
    finance_roles = admin_roles | {"BURSAR", "FINANCE_STAFF", "ACCOUNTANT"}
    reports_roles = people_roles | {"TEACHER"}
    comms_roles = admin_roles | {"COMMS_STAFF", "TEACHER", "SECRETARY"}

    can_manage_settings = bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or role_code in admin_roles
        or _has_permission(user, "settings.manage")
    )
    can_manage_people = bool(
        getattr(user, "is_superuser", False)
        or role_code in people_roles
        or _has_permission(user, "students.manage", "people.manage", "teachers.manage")
    )
    can_manage_finance = bool(
        getattr(user, "is_superuser", False)
        or role_code in finance_roles
        or _has_permission(user, "finance.manage", "finance.approve")
    )
    can_manage_reports = bool(
        getattr(user, "is_superuser", False)
        or role_code in reports_roles
        or _has_permission(user, "reports.manage", "reports.publish")
    )
    can_use_messages = bool(
        getattr(user, "is_superuser", False)
        or role_code in comms_roles
        or _has_permission(user, "messages.manage", "communication.manage")
    )
    can_manage_rbac = bool(
        getattr(user, "is_superuser", False)
        or role_code in admin_roles
        or _has_permission(user, "rbac.manage", "accounts.manage")
    )

    admin_portal = {
        "academics": [
            {"label": "Students", "value": snapshot.get("students", 0)},
            {"label": "Classrooms", "value": snapshot.get("classrooms", 0)},
            {"label": "Subjects", "value": snapshot.get("subjects", 0)},
        ],
        "accounts": [
            {"label": "Users", "value": snapshot.get("users", 0)},
            {"label": "Teachers", "value": snapshot.get("teachers", 0)},
            {"label": "Parents", "value": snapshot.get("parents", 0)},
        ],
        "finance": [
            {"label": "Invoices", "value": snapshot.get("invoices", 0)},
            {"label": "Overdue", "value": snapshot.get("overdue", 0)},
            {"label": "Draft", "value": snapshot.get("drafts", 0)},
        ],
    }

    overview_cards = [
        {
            "title": "Academics",
            "value": snapshot.get("students", 0),
            "meta": f'{snapshot.get("subjects", 0)} subjects',
            "delta": f'{snapshot.get("classrooms", 0)} classrooms',
            "status": "ok",
            "icon": "bi-mortarboard",
        },
        {
            "title": "Accounts",
            "value": snapshot.get("users", 0),
            "meta": f'{snapshot.get("teachers", 0)} staff',
            "delta": f'{snapshot.get("parents", 0)} parents',
            "status": "ok",
            "icon": "bi-people",
        },
        {
            "title": "At-Risk Students",
            "value": at_risk_value,
            "meta": f"{overdue} overdue invoices",
            "delta": f"{_safe_int(fallback_stats.get('pending_referrals'))} pending referrals",
            "status": _status_from_value(at_risk_value, warn_at=1, danger_at=5),
            "icon": "bi-exclamation-triangle",
        },
    ]

    operations_watch = [
        {
            "key": "pending_approvals",
            "label": "Pending Approvals",
            "value": pending_approvals,
            "status": _status_from_value(pending_approvals, warn_at=1, danger_at=4),
            "url": _safe_reverse("accounts:workflow_center"),
            "icon": "bi-hourglass-split",
        },
        {
            "key": "overdue_invoices",
            "label": "Overdue Invoices",
            "value": overdue,
            "status": _status_from_value(overdue, warn_at=1, danger_at=3),
            "url": _safe_reverse("finance:dashboard"),
            "icon": "bi-receipt-cutoff",
        },
        {
            "key": "failed_logins_24h",
            "label": "Failed Logins (24h)",
            "value": failed_logins_24h,
            "status": _status_from_value(failed_logins_24h, warn_at=2, danger_at=6),
            "url": _safe_reverse("accounts:user_messages"),
            "icon": "bi-shield-exclamation",
        },
        {
            "key": "system_incidents",
            "label": "System Incidents",
            "value": system_incidents,
            "status": _status_from_value(system_incidents, warn_at=1, danger_at=2),
            "url": _safe_reverse("accounts:backend_dashboard"),
            "icon": "bi-bug",
        },
    ]

    primary_ctas = [
        {"label": "Manage Staff", "icon": "bi-person-gear", "url": _safe_reverse("accounts:backend_teacher_list", _safe_reverse("accounts:backend_dashboard"))},
        {"label": "School Settings", "icon": "bi-building-gear", "url": _safe_reverse("siteconfig:customizer", _safe_reverse("siteconfig:user_preferences"))},
    ]

    action_chips = [
        _build_nav_item("Workflow Center", "bi-diagram-3", _safe_reverse("accounts:workflow_center"), allow=True),
        _build_nav_item("Messages", "bi-chat-dots", _safe_reverse("accounts:user_messages"), allow=can_use_messages),
        _build_nav_item("Report Card Builder", "bi-file-earmark-richtext", _safe_reverse("siteconfig:reportcard_builder"), allow=can_manage_reports),
        _build_nav_item("My Preferences", "bi-sliders", _safe_reverse("siteconfig:user_preferences"), allow=True),
        _build_nav_item(
            "Customize layout",
            "bi-grid-1x2",
            f'{_safe_reverse("accounts:backend_dashboard")}?customize=1',
            allow=True,
        ),
        _build_nav_item("Configuration Engine", "bi-gear-wide-connected", _safe_reverse("admin:index"), allow=can_manage_settings),
    ]
    action_chips = [item for item in action_chips if item]

    welcome_action_grid = [
        _build_nav_item("Add Student", "bi-person-plus", _safe_reverse("accounts:backend_student_create", _safe_reverse("admin:index")), item_id="add_student", allow=can_manage_people),
        _build_nav_item("Add Teacher", "bi-person-badge", _safe_reverse("accounts:backend_teacher_create", _safe_reverse("admin:index")), item_id="add_teacher", allow=can_manage_people),
        _build_nav_item("Onboard Student", "bi-mortarboard", _safe_reverse("portal:student_onboarding"), item_id="onboard_student", allow=can_manage_people),
        _build_nav_item("Create Invoice", "bi-receipt", _safe_reverse("finance:dashboard"), item_id="create_invoice", allow=can_manage_finance),
        _build_nav_item("Manage Exams", "bi-journal-text", _safe_reverse("reports:publish_term_results"), item_id="manage_exams", allow=can_manage_reports),
        _build_nav_item("Announcements", "bi-megaphone", _safe_reverse("communication:announcement_create"), item_id="announcements", allow=can_use_messages),
        _build_nav_item("Roles & Permissions", "bi-shield-lock", _safe_reverse("accounts:rbac"), item_id="roles_permissions", allow=can_manage_rbac),
        _build_nav_item("Document Library", "bi-folder2-open", _safe_reverse("portal:document_library_manage"), item_id="document_library", allow=can_manage_settings),
    ]
    welcome_action_grid = [item for item in welcome_action_grid if item]

    if role_code in {"BURSAR", "FINANCE_STAFF"}:
        finance_console = _build_nav_item(
            "Finance Console",
            "bi-cash-stack",
            _safe_reverse("finance:dashboard"),
            item_id="finance_console",
            allow=can_manage_finance,
        )
        if finance_console:
            welcome_action_grid.insert(0, finance_console)

    quick_links = [
        _build_nav_item("Import Grades", "bi-upload", _safe_reverse("evals:grade_import_upload"), item_id="import_grades", allow=can_manage_reports),
        _build_nav_item("Exams", "bi-journal-check", _safe_reverse("reports:publish_term_results"), item_id="exams", allow=can_manage_reports),
        _build_nav_item("Certification", "bi-award", _safe_reverse("accounts:certification_home"), item_id="certification", allow=can_manage_reports),
        _build_nav_item("Documents", "bi-folder2", _safe_reverse("portal:document_library_manage"), item_id="documents", allow=can_manage_settings),
        _build_nav_item("Workflow Center", "bi-diagram-3", _safe_reverse("accounts:workflow_center"), item_id="workflow_center", allow=True),
        _build_nav_item("Preferences", "bi-sliders", _safe_reverse("siteconfig:user_preferences"), item_id="preferences", allow=True),
    ]
    quick_links = [item for item in quick_links if item]

    pinned_order = []
    try:
        prefs = getattr(user, "dashboard_preferences", None)
        if prefs and isinstance(prefs.pinned_sidebar_items, list):
            pinned_order = [str(x).strip() for x in prefs.pinned_sidebar_items if str(x).strip()]
    except Exception:
        pinned_order = []
    if pinned_order:
        order_map = {key: idx for idx, key in enumerate(pinned_order)}
        quick_links.sort(key=lambda x: order_map.get(x.get("id", ""), 999))

    command_palette = [
        _build_nav_item("Add Student", "bi-person-plus", _safe_reverse("accounts:backend_student_create", _safe_reverse("admin:index")), allow=can_manage_people),
        _build_nav_item("Manage Staff", "bi-people", _safe_reverse("accounts:backend_teacher_list", _safe_reverse("accounts:backend_dashboard")), allow=can_manage_people),
        _build_nav_item("Manage Exams", "bi-journal-check", _safe_reverse("reports:publish_term_results"), allow=can_manage_reports),
        _build_nav_item("Import Grades", "bi-upload", _safe_reverse("evals:grade_import_upload"), allow=can_manage_reports),
        _build_nav_item("Finance Dashboard", "bi-cash-stack", _safe_reverse("finance:dashboard"), allow=can_manage_finance),
        _build_nav_item("School Settings", "bi-building-gear", _safe_reverse("siteconfig:customizer", _safe_reverse("siteconfig:user_preferences")), allow=can_manage_settings),
        _build_nav_item("Workflow Center", "bi-diagram-3", _safe_reverse("accounts:workflow_center"), allow=True),
    ]
    command_palette = [item for item in command_palette if item]

    return {
        "local_time": now,
        "weather_cfg": weather_cfg,
        "overview_cards": overview_cards,
        "admin_portal": admin_portal,
        "operations_watch": operations_watch,
        "primary_ctas": primary_ctas,
        "action_chips": action_chips,
        "welcome_action_grid": welcome_action_grid,
        "quick_links": quick_links,
        "command_palette": command_palette,
        "ops_watch_finance_requests": finance_requests,
        "ops_watch_last_updated": now.isoformat(),
        "ops_watch_refresh_url": _safe_reverse("accounts:backend_ops_watch_data", ""),
    }
