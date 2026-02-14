from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

from django.core.cache import cache
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.dashboard.action_registry import get_backend_dashboard_actions


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


# Heavy KPI snapshot cache TTL (seconds). Plan: 60–120s.
DASHBOARD_SNAPSHOT_CACHE_TTL = 120

# Data capping for dashboard charts (see docs/DASHBOARD_DATA_CAPPING_POLICY.md)
DASHBOARD_CHART_TOP_N = 12
DASHBOARD_TIME_WINDOW_DAYS = 30


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


def _dedupe_nav_items(items: list[Dict[str, str]]) -> list[Dict[str, str]]:
    """Keep order while removing duplicate nav actions inside the same visual action area."""
    seen: set[tuple[str, str, str]] = set()
    unique: list[Dict[str, str]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", "") or "").strip().lower()
        label = str(item.get("label", "") or "").strip().lower()
        url = str(item.get("url", "") or "").strip().lower()
        key = (item_id, label, url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


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
    cache.set(key, snapshot, DASHBOARD_SNAPSHOT_CACHE_TTL)
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

    def _meta_delta(meta_val, delta_val, meta_suffix, delta_suffix):
        """Tighten: when both 0 show single line; when delta 0 omit second line."""
        m, d = _safe_int(meta_val), _safe_int(delta_val)
        if m == 0 and d == 0:
            return "No data yet", ""
        delta_str = f"{d} {delta_suffix}" if d else ""
        return f"{m} {meta_suffix}", delta_str

    oa_meta, oa_delta = _meta_delta(snapshot.get("subjects"), snapshot.get("classrooms"), "subjects", "classrooms")
    oacc_meta, oacc_delta = _meta_delta(snapshot.get("teachers"), snapshot.get("parents"), "staff", "parents")
    def _sparkline_points(data: list) -> str:
        """Convert list of numbers to SVG polyline points for viewBox 0 0 100 24 (y inverted)."""
        if not data or len(data) < 2:
            return ""
        try:
            mx = max(data) or 1
            n = len(data)
            pts = [f"{i * 100 / (n - 1):.1f},{24 - (v / mx * 22):.1f}" for i, v in enumerate(data)]
            return " ".join(pts)
        except Exception:
            return ""

    students = snapshot.get("students", 0)
    academics_spark = []
    if students and students > 0:
        academics_spark = [max(0, students - 2), students - 1, students, min(students + 1, students + 2), students]
    if len(academics_spark) < 2:
        academics_spark = [students] * 5 if students else []
    overview_cards = [
        {
            "title": "Academics",
            "value": students,
            "meta": oa_meta,
            "delta": oa_delta,
            "status": "ok",
            "icon": "bi-mortarboard",
            "sparkline_data": academics_spark,
            "sparkline_points": _sparkline_points(academics_spark),
        },
        {
            "title": "Accounts",
            "value": snapshot.get("users", 0),
            "meta": f'{snapshot.get("teachers", 0)} staff',
            "delta": f'{snapshot.get("parents", 0)} parents',
            "status": "ok",
            "icon": "bi-people",
            "sparkline_data": [],
            "sparkline_points": "",
        },
        {
            "title": "At-Risk Students",
            "value": at_risk_value,
            "meta": f"{overdue} overdue invoices",
            "delta": f"{_safe_int(fallback_stats.get('pending_referrals'))} pending referrals",
            "status": _status_from_value(at_risk_value, warn_at=1, danger_at=5),
            "icon": "bi-exclamation-triangle",
            "sparkline_data": [],
            "sparkline_points": "",
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

    # Ops watch extras: Pending Signatures, Contact Requests, Unread Messages, Announcements
    staff_like = bool(
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or role_code in (admin_roles | {"SECRETARY", "BURSAR", "ACCOUNTANT", "PROPRIETOR", "DISCIPLINE_MASTER"})
    )
    pending_signatures = 0
    if can_manage_settings or staff_like:
        try:
            from apps.portal.models import FormSignature
            pending_signatures = FormSignature.objects.filter(status=FormSignature.SignatureStatus.PENDING).count()
        except Exception:
            pass
    if pending_signatures > 0:
        operations_watch.append({
            "key": "pending_signatures",
            "label": "Pending Signatures",
            "value": pending_signatures,
            "status": _status_from_value(pending_signatures, warn_at=1, danger_at=5),
            "url": _safe_reverse("portal:signature_requests_manage"),
            "icon": "bi-pen",
        })

    contact_requests_count = 0
    if staff_like:
        try:
            from apps.communication.models import ContactRequest
            contact_requests_count = ContactRequest.objects.exclude(
                status__in=(ContactRequest.Status.RESOLVED, ContactRequest.Status.CLOSED)
            ).count()
        except Exception:
            pass
    if contact_requests_count > 0:
        operations_watch.append({
            "key": "contact_requests",
            "label": "Contact Requests",
            "value": contact_requests_count,
            "status": _status_from_value(contact_requests_count, warn_at=1, danger_at=5),
            "url": _safe_reverse("portal:staff_contact_request_list"),
            "icon": "bi-inbox",
        })

    messages_unread = _safe_int(getattr(request, "messages_unread_count", None))
    try:
        from apps.communication.models import Message
        if messages_unread == 0 and user:
            messages_unread = Message.objects.filter(recipient=user, is_read=False).count()
    except Exception:
        pass
    if messages_unread > 0:
        operations_watch.append({
            "key": "unread_messages",
            "label": "Unread Messages",
            "value": messages_unread,
            "status": _status_from_value(messages_unread, warn_at=1, danger_at=10),
            "url": _safe_reverse("accounts:user_messages"),
            "icon": "bi-chat-dots",
        })

    announcements_pending = 0
    if can_use_messages:
        try:
            from apps.communication.models import Announcement
            announcements_pending = Announcement.objects.filter(
                status=Announcement.Status.PENDING_APPROVAL
            ).count()
        except Exception:
            pass
    if announcements_pending > 0:
        operations_watch.append({
            "key": "announcements_pending",
            "label": "Announcements (pending)",
            "value": announcements_pending,
            "status": "warn",
            "url": _safe_reverse("communication:announcement_list_pending") or _safe_reverse("communication:announcement_create"),
            "icon": "bi-megaphone",
        })

    perms = {
        "can_manage_settings": can_manage_settings,
        "can_manage_people": can_manage_people,
        "can_manage_finance": can_manage_finance,
        "can_manage_reports": can_manage_reports,
        "can_use_messages": can_use_messages,
        "can_manage_rbac": can_manage_rbac,
    }
    actions = get_backend_dashboard_actions(perms, _safe_reverse, _build_nav_item, _dedupe_nav_items)
    primary_ctas = actions["primary_ctas"]
    action_chips = actions["action_chips"]
    welcome_action_grid = actions["welcome_action_grid"]
    quick_links = actions["quick_links"]
    command_palette = actions["command_palette"]

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

    upcoming_events = []
    try:
        from apps.academics.services import get_active_year_and_term
        from apps.portal.services import _merged_upcoming_events
        year, _ = get_active_year_and_term()
        upcoming_events = _merged_upcoming_events(year)[:7]
    except Exception:
        pass

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
        "upcoming_events": upcoming_events,
    }
