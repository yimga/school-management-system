from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.db import DatabaseError, OperationalError
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.dashboard.decision_surface_context import (
    build_backend_dashboard_phase7_de,
    build_role_home_declaration,
)
from apps.dashboard.role_home_engine import select_kpis_for_intent
from apps.dashboard.services.role_home_service import build_role_home_context
from apps.platform_runtime.helpers import (
    get_effective_flags,
    get_effective_site_settings,
)
from apps.platform_runtime.structured_logging import log_view_exception

logger = logging.getLogger(__name__)

# Typed exceptions for dashboard context (§2.4 broad-except policy)
_DASHBOARD_REVERSE_ERRORS = (
    NoReverseMatch,
    ImproperlyConfigured,
    ValueError,
    TypeError,
)
# Snapshot/query and optional feature failures (resilient counts; log and keep going)
_DASHBOARD_SNAPSHOT_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    ObjectDoesNotExist,
    DatabaseError,
    OperationalError,
)
_DASHBOARD_PERMISSION_CHECK_ERRORS = (
    AttributeError,
    TypeError,
    ValueError,
    ImportError,
)
_DASHBOARD_PARSING_ERRORS = (TypeError, ValueError)
_DASHBOARD_CONFIG_ERRORS = (ImproperlyConfigured,)


def __safe_reverse(name: str, fallback: str = "#") -> str:
    try:
        return reverse(name)
    except _DASHBOARD_REVERSE_ERRORS:
        return fallback


_safe_reverse = __safe_reverse


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except _DASHBOARD_PARSING_ERRORS:
        return default


def _status_from_value(value: int, warn_at: int, danger_at: int) -> str:
    if value >= danger_at:
        return "danger"
    if value >= warn_at:
        return "warn"
    return "ok"


# Heavy KPI snapshot cache TTL (seconds). Plan: 60-120s.
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
        except _DASHBOARD_PERMISSION_CHECK_ERRORS:
            continue
    return False


def _build_nav_item(
    label: str, icon: str, url: str, *, item_id: str = "", allow: bool = True
) -> Optional[Dict[str, str]]:
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
    except _DASHBOARD_SNAPSHOT_ERRORS:
        pass

    try:
        from apps.academics.models import Classroom, Subject

        classrooms = Classroom.objects.count()
        subjects = Subject.objects.count()
    except _DASHBOARD_SNAPSHOT_ERRORS:
        pass

    try:
        from apps.accounts.models import User

        users = User.objects.count()
        if hasattr(User, "role"):
            parents = User.objects.filter(role="PARENT").count()
    except _DASHBOARD_SNAPSHOT_ERRORS:
        pass

    try:
        from apps.finance.models import Invoice

        invoices = Invoice.objects.count()
        overdue = Invoice.objects.filter(status="OVERDUE").count()
        drafts = Invoice.objects.filter(status="DRAFT").count()
    except _DASHBOARD_SNAPSHOT_ERRORS:
        pass

    try:
        from apps.requests.models import AccessRequest

        pending_approvals = AccessRequest.objects.filter(
            status=AccessRequest.Status.PENDING
        ).count()
    except _DASHBOARD_SNAPSHOT_ERRORS:
        pass

    try:
        from apps.compliance.models_audit import AccessLog

        cutoff = timezone.now() - timedelta(hours=24)
        failed_logins_24h = (
            AccessLog.objects.filter(
                resource__in=["/authentication/login/", "/admin/login/"],
                request_method="POST",
                timestamp__gte=cutoff,
            )
            .exclude(status__in=["302", "303"])
            .count()
        )
    except _DASHBOARD_SNAPSHOT_ERRORS:
        failed_logins_24h = 0

    try:
        from apps.finance.models import Notification

        system_incidents = Notification.objects.filter(
            title__icontains="incident"
        ).count()
    except _DASHBOARD_SNAPSHOT_ERRORS:
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


def _build_priority_queue(
    items: list[Dict[str, Any]], *, max_items: int = 4
) -> list[Dict[str, Any]]:
    priority = {"danger": 0, "warn": 1, "ok": 2}
    ranked = sorted(
        [item for item in items if _safe_int(item.get("value")) > 0],
        key=lambda item: (
            priority.get(str(item.get("status")), 3),
            -_safe_int(item.get("value")),
        ),
    )
    if ranked:
        return ranked[:max_items]
    return [
        {
            "label": "No urgent blockers",
            "value": 0,
            "status": "ok",
            "url": __safe_reverse("studio_os:workflow_center"),
            "icon": "bi-check2-circle",
            "meta": "The main queues are clear right now.",
        }
    ]


def _build_recent_activity_block(
    activities: Any, *, max_items: int = 4
) -> list[Dict[str, Any]]:
    results: list[Dict[str, Any]] = []
    if not isinstance(activities, list):
        return results
    for activity in activities[:max_items]:
        user = (
            activity.get("user")
            if isinstance(activity, dict)
            else getattr(activity, "user", None)
        )
        actor = ""
        if user is not None:
            actor = getattr(user, "get_full_name", lambda: "")() or getattr(
                user, "username", ""
            )
        results.append(
            {
                "title": str(
                    activity.get("object")
                    if isinstance(activity, dict)
                    else getattr(activity, "object", "")
                )
                or "Platform update",
                "actor": actor or "System",
                "action": str(
                    activity.get("action")
                    if isinstance(activity, dict)
                    else getattr(activity, "action", "")
                )
                or "updated",
                "time_ago": str(
                    activity.get("time_ago")
                    if isinstance(activity, dict)
                    else getattr(activity, "time_ago", "")
                )
                or "just now",
            }
        )
    return results


def build_dashboard_extras(
    request, base: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
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
        "enabled": False,
        "label": "Weather",
        "lat": 0.0,
        "lon": 0.0,
        "unit": "celsius",
    }
    backend_defaults: Dict[str, Any] = {}
    backend_flags: Dict[str, Any] = {}

    site_id = "global"
    try:
        from apps.siteconfig.models import (
            default_header_weather_config,
            default_backend_feature_flags,
        )

        backend_defaults = default_backend_feature_flags()
        backend_flags = dict(backend_defaults)
        site = get_effective_site_settings(request=request)
        rt = getattr(request, "tenant_runtime", None)
        backend_flags.update(get_effective_flags(request))
        if rt:
            site_id = str(getattr(getattr(rt, "tenant", None), "id", None) or site.pk)
            if getattr(rt, "flags", None) and getattr(rt.flags, "flags", None):
                backend_flags.update(rt.flags.flags)
        else:
            site_id = str(site.pk)
        weather_defaults = default_header_weather_config()
        weather_cfg.update(
            {
                "enabled": backend_flags.get(
                    "show_header_context_weather", weather_cfg["enabled"]
                ),
                "label": backend_flags.get(
                    "header_weather_label", weather_defaults["header_weather_label"]
                ),
                "lat": backend_flags.get(
                    "header_weather_latitude",
                    weather_defaults["header_weather_latitude"],
                ),
                "lon": backend_flags.get(
                    "header_weather_longitude",
                    weather_defaults["header_weather_longitude"],
                ),
                "unit": backend_flags.get(
                    "header_weather_temperature_unit",
                    weather_defaults["header_weather_temperature_unit"],
                ),
            }
        )
    except _DASHBOARD_SNAPSHOT_ERRORS:
        pass
    except _DASHBOARD_CONFIG_ERRORS:
        log_view_exception(
            request,
            "dashboard backend flags/weather failed",
            extra={"step": "weather_cfg"},
        )

    def _clamp_max_items(value, default=5):
        try:
            parsed = int(value)
        except _DASHBOARD_PARSING_ERRORS:
            parsed = int(default)
        return max(3, min(12, parsed))

    max_items = _clamp_max_items(
        backend_flags.get("backend_layout_max_items_per_list"),
        backend_defaults.get("backend_layout_max_items_per_list", 5),
    )
    module_visibility = {
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
    visual_settings = {
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
    theme_settings = {
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

    snapshot = _build_cached_snapshot(site_id, role_code)

    fallback_stats = (
        (base.get("stats") or {}) if isinstance(base.get("stats"), dict) else {}
    )
    pending_approvals = snapshot.get("pending_approvals") or _safe_int(
        base.get("pending_approvals_count")
    )
    overdue = snapshot.get("overdue") or _safe_int(
        fallback_stats.get("overdue_invoices")
    )
    finance_requests = _safe_int(base.get("finance_requests_count"))
    failed_logins_24h = snapshot.get("failed_logins_24h") or _safe_int(
        base.get("failed_logins_24h")
    )
    system_incidents = snapshot.get("system_incidents")

    at_risk_value = _safe_int(fallback_stats.get("pending_referrals")) + overdue
    if at_risk_value == 0:
        at_risk_value = overdue

    admin_roles = {
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

    oa_meta, oa_delta = _meta_delta(
        snapshot.get("subjects"), snapshot.get("classrooms"), "subjects", "classrooms"
    )
    oacc_meta, oacc_delta = _meta_delta(
        snapshot.get("teachers"), snapshot.get("parents"), "staff", "parents"
    )

    def _sparkline_points(data: list) -> str:
        """Convert list of numbers to SVG polyline points for viewBox 0 0 100 24 (y inverted)."""
        if not data or len(data) < 2:
            return ""
        try:
            mx = max(data) or 1
            n = len(data)
            pts = [
                f"{i * 100 / (n - 1):.1f},{24 - (v / mx * 22):.1f}"
                for i, v in enumerate(data)
            ]
            return " ".join(pts)
        except (TypeError, ValueError, ZeroDivisionError):
            return ""

    students = snapshot.get("students", 0)
    academics_spark = []
    if students and students > 0:
        academics_spark = [
            max(0, students - 2),
            students - 1,
            students,
            min(students + 1, students + 2),
            students,
        ]
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
            "meta": f"{snapshot.get('teachers', 0)} staff",
            "delta": f"{snapshot.get('parents', 0)} parents",
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
            "url": _safe_reverse("studio_os:workflow_center"),
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
        or role_code
        in (
            admin_roles
            | {"SECRETARY", "BURSAR", "ACCOUNTANT", "PROPRIETOR", "DISCIPLINE_MASTER"}
        )
    )
    pending_signatures = 0
    if can_manage_settings or staff_like:
        try:
            from apps.portal.models import FormSignature

            pending_signatures = FormSignature.objects.filter(
                status=FormSignature.SignatureStatus.PENDING
            ).count()
        except _DASHBOARD_SNAPSHOT_ERRORS:
            pass
    if pending_signatures > 0:
        operations_watch.append(
            {
                "key": "pending_signatures",
                "label": "Pending Signatures",
                "value": pending_signatures,
                "status": _status_from_value(
                    pending_signatures, warn_at=1, danger_at=5
                ),
                "url": _safe_reverse("portal:signature_requests_manage"),
                "icon": "bi-pen",
            }
        )

    contact_requests_count = 0
    if staff_like:
        try:
            from apps.communication.models import ContactRequest

            contact_requests_count = ContactRequest.objects.exclude(
                status__in=(
                    ContactRequest.Status.RESOLVED,
                    ContactRequest.Status.CLOSED,
                )
            ).count()
        except _DASHBOARD_SNAPSHOT_ERRORS:
            pass
    if contact_requests_count > 0:
        operations_watch.append(
            {
                "key": "contact_requests",
                "label": "Contact Requests",
                "value": contact_requests_count,
                "status": _status_from_value(
                    contact_requests_count, warn_at=1, danger_at=5
                ),
                "url": _safe_reverse("portal:staff_contact_request_list"),
                "icon": "bi-inbox",
            }
        )

    messages_unread = _safe_int(getattr(request, "messages_unread_count", None))
    try:
        from apps.communication.models import Message

        if messages_unread == 0 and user:
            messages_unread = Message.objects.filter(
                recipient=user, is_read=False
            ).count()
    except _DASHBOARD_SNAPSHOT_ERRORS:
        pass
    if messages_unread > 0:
        operations_watch.append(
            {
                "key": "unread_messages",
                "label": "Unread Messages",
                "value": messages_unread,
                "status": _status_from_value(messages_unread, warn_at=1, danger_at=10),
                "url": _safe_reverse("accounts:user_messages"),
                "icon": "bi-chat-dots",
            }
        )

    announcements_pending = 0
    if can_use_messages:
        try:
            from apps.communication.models import Announcement

            announcements_pending = Announcement.objects.filter(
                status=Announcement.Status.PENDING_APPROVAL
            ).count()
        except _DASHBOARD_SNAPSHOT_ERRORS:
            pass
    if announcements_pending > 0:
        operations_watch.append(
            {
                "key": "announcements_pending",
                "label": "Announcements (pending)",
                "value": announcements_pending,
                "status": "warn",
                "url": _safe_reverse("communication:announcement_list_pending")
                or _safe_reverse("communication:announcement_create"),
                "icon": "bi-megaphone",
            }
        )

    can_access_control_plane = False
    try:
        from apps.schools.control_plane import user_has_control_plane_access

        can_access_control_plane = bool(user_has_control_plane_access(user))
    except _DASHBOARD_PERMISSION_CHECK_ERRORS:
        pass
    perms = {
        "can_manage_settings": can_manage_settings,
        "can_manage_people": can_manage_people,
        "can_manage_finance": can_manage_finance,
        "can_manage_reports": can_manage_reports,
        "can_use_messages": can_use_messages,
        "can_manage_rbac": can_manage_rbac,
        "can_access_control_plane": can_access_control_plane,
    }
    # Role-home slice from single service (RUNMYCAMPUS §6.13: move role-home logic into services)
    role_home_result = build_role_home_context(
        request,
        base,
        perms,
        safe_reverse=lambda name, fallback="#": _safe_reverse(name, fallback),
        build_nav_item=_build_nav_item,
        dedupe_nav_items=_dedupe_nav_items,
    )
    role_home = role_home_result["role_home"]
    intent = role_home_result["intent"]
    primary_ctas = role_home_result["primary_ctas"]
    action_chips = role_home_result["action_chips"]
    welcome_action_grid = role_home_result["welcome_action_grid"]
    quick_links = role_home_result["quick_links"]
    command_palette = role_home_result["command_palette"]
    contextual_actions = role_home_result["contextual_actions"]
    role_home_destinations = role_home_result["role_home_destinations"]
    role_home_primary_action = role_home_result["role_home_primary_action"]
    role_home_supporting_actions = role_home_result["role_home_supporting_actions"]
    dashboard_next_best_actions = (
        role_home_result.get("dashboard_next_best_actions") or []
    )

    upcoming_events = []
    try:
        from apps.academics.services import get_active_year_and_term
        from apps.portal.services import _merged_upcoming_events

        year, _ = get_active_year_and_term()
        upcoming_events = _merged_upcoming_events(year)[:7]
    except _DASHBOARD_SNAPSHOT_ERRORS:
        pass

    top_performing_students = base.get("top_performing_students") or []
    if not isinstance(top_performing_students, list):
        top_performing_students = []
    recent_admissions = base.get("recent_admissions") or []
    if not isinstance(recent_admissions, list):
        recent_admissions = []
    top_performing_students = top_performing_students[:max_items]
    recent_admissions = recent_admissions[:max_items]

    top_entry = top_performing_students[0] if top_performing_students else {}
    top_name = str((top_entry or {}).get("name") or "").strip() or "No marks entered"
    top_score = (top_entry or {}).get("score")
    try:
        top_score_value = f"{float(top_score):.1f}/20"
        top_status = "ok"
    except (TypeError, ValueError):
        top_score_value = "--"
        top_status = "warn"

    attended_today = _safe_int(base.get("attended_today"))
    attendance_trend_total = _safe_int(base.get("attendance_trend_total"))
    attendance_counts = base.get("attendance_counts") or {}
    if not isinstance(attendance_counts, dict):
        attendance_counts = {}
    attendance_total = sum(_safe_int(v) for v in attendance_counts.values())
    attendance_rate = None
    if attendance_total > 0:
        attendance_rate = round((attended_today / max(attendance_total, 1)) * 100)
    attendance_meta = (
        f"{attendance_rate}% present today"
        if attendance_rate is not None
        else "No attendance records yet"
    )
    if attendance_rate is None:
        attendance_status = "warn"
    elif attendance_rate < 50:
        attendance_status = "danger"
    elif attendance_rate < 75:
        attendance_status = "warn"
    else:
        attendance_status = "ok"

    kpi_strip_cards = [
        {
            "id": "top_performing",
            "label": "Top Performing",
            "value": top_score_value,
            "meta": top_name,
            "status": top_status,
            "icon": "bi-trophy",
        },
        {
            "id": "attendance_today",
            "label": "Attendance Today",
            "value": attended_today,
            "meta": attendance_meta,
            "status": attendance_status,
            "icon": "bi-person-check",
        },
        {
            "id": "recent_admissions",
            "label": "Recent Admissions",
            "value": len(recent_admissions),
            "meta": "Latest entries",
            "status": "ok" if recent_admissions else "warn",
            "icon": "bi-person-vcard",
        },
        {
            "id": "weekly_presence",
            "label": "Weekly Presence",
            "value": attendance_trend_total,
            "meta": "7-day present total",
            "status": "ok" if attendance_trend_total > 0 else "warn",
            "icon": "bi-activity",
        },
    ]
    kpi_strip_cards = select_kpis_for_intent(kpi_strip_cards, intent)
    dashboard_priority_queue = _build_priority_queue(operations_watch, max_items=4)
    dashboard_recent_activity = _build_recent_activity_block(
        base.get("recent_activities"), max_items=4
    )
    if not dashboard_recent_activity:
        dashboard_recent_activity = [
            {
                "title": "Role home is ready",
                "actor": "System",
                "action": "prepared your command center",
                "time_ago": "just now",
            }
        ]
    dashboard_contract = {
        "dominant_purpose": role_home["purpose"],
        "primary_action_count": len(primary_ctas[:1]),
        "metric_count": len(overview_cards) + len(kpi_strip_cards),
        "urgent_queue_count": len(dashboard_priority_queue),
        "recommended_count": len(dashboard_next_best_actions),
        "recent_count": len(dashboard_recent_activity),
    }

    phase7_de = build_backend_dashboard_phase7_de(
        role_home=role_home,
        kpi_strip_cards=kpi_strip_cards,
        dashboard_priority_queue=dashboard_priority_queue,
        dashboard_next_best_actions=dashboard_next_best_actions,
        role_home_primary_action=role_home_primary_action,
        role_home_supporting_actions=role_home_supporting_actions,
        dashboard_recent_activity=dashboard_recent_activity,
    )
    role_home_declaration = build_role_home_declaration(role_home)

    operations_watch = operations_watch[:max_items]
    quick_links = quick_links[:max_items]
    welcome_action_grid = welcome_action_grid[: max(6, max_items + 2)]
    upcoming_events = upcoming_events[:max_items]

    return {
        "local_time": now,
        "weather_cfg": weather_cfg,
        "overview_cards": overview_cards,
        "kpi_strip_cards": kpi_strip_cards,
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
        "backend_module_visibility": module_visibility,
        "backend_visual_settings": visual_settings,
        "backend_theme_settings": theme_settings,
        "backend_layout_max_items_per_list": max_items,
        # Backward-compatible aliases used by older templates/tests.
        "sidebar_quick_access": quick_links,
        "empty_panel_quick_actions": quick_links[:3],
        "dashboard_intent": intent or "operational",
        "backend_intent_emphasize_setup": intent == "setup",
        "contextual_actions": contextual_actions,
        "role_home": role_home,
        "role_home_focus_areas": list(role_home.get("focus_areas") or []),
        "role_home_primary_action": role_home_primary_action,
        "role_home_supporting_actions": role_home_supporting_actions,
        "role_home_destinations": role_home_destinations,
        "dashboard_priority_queue": dashboard_priority_queue,
        "dashboard_recent_activity": dashboard_recent_activity,
        "dashboard_next_best_actions": dashboard_next_best_actions,
        "dashboard_contract": dashboard_contract,
        "phase7_de": phase7_de,
        "role_home_declaration": role_home_declaration,
    }
