"""Shared context builder for the Unfold admin dashboard."""

from __future__ import annotations

import datetime
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

import django
from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.db import DatabaseError, OperationalError, connection
from django.db.models import Count, Q, Value
from django.db.models.functions import Coalesce
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.dashboard.action_registry import get_admin_header_actions
from apps.finance.models import Notification
from apps.platform_runtime.helpers import get_effective_site_settings
from apps.platform_runtime.structured_logging import log_view_exception
from apps.siteconfig.models import SiteSettings
from apps.siteconfig.models_support import default_header_weather_config

logger = logging.getLogger(__name__)

# Typed exceptions for admin dashboard context (§2.4 broad-except policy)
_ADMIN_REVERSE_ERRORS = (NoReverseMatch, ImproperlyConfigured, ValueError, TypeError)
_ADMIN_WIDGET_QUERY_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    DatabaseError,
    OperationalError,
    ObjectDoesNotExist,
    NoReverseMatch,
    ImproperlyConfigured,
)


def _safe_reverse(name: str, fallback: str = "#") -> str:
    try:
        return reverse(name)
    except _ADMIN_REVERSE_ERRORS:
        return fallback


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_admin_weather_config(site: SiteSettings) -> dict[str, Any]:
    if callable(getattr(site, "get_backend_feature_flags", None)):
        flags = site.get_backend_feature_flags()
    else:
        flags = getattr(site, "backend_feature_flags", None) or {}
    weather_defaults = default_header_weather_config()
    raw_unit = str(
        flags.get("header_weather_temperature_unit", weather_defaults["header_weather_temperature_unit"])
    ).lower()
    temp_unit = "fahrenheit" if raw_unit in {"f", "fahrenheit"} else "celsius"
    timezone_name = str(
        flags.get("header_weather_timezone")
        or weather_defaults["header_weather_timezone"]
        or settings.TIME_ZONE
        or "UTC"
    )
    return {
        "enabled": bool(flags.get("show_header_context_weather", False)),
        "label": str(flags.get("header_weather_label", weather_defaults["header_weather_label"])),
        "latitude": _safe_float(
            flags.get("header_weather_latitude", weather_defaults["header_weather_latitude"]),
            weather_defaults["header_weather_latitude"],
        ),
        "longitude": _safe_float(
            flags.get("header_weather_longitude", weather_defaults["header_weather_longitude"]),
            weather_defaults["header_weather_longitude"],
        ),
        "temperature_unit": temp_unit,
        "timezone": timezone_name,
    }


def _build_admin_control_links() -> list[dict[str, Any]]:
    return [
        {
            "label": "Manage Users",
            "icon": "groups",
            "url": _safe_reverse("admin:accounts_user_changelist"),
        },
        {
            "label": "Site Settings",
            "icon": "settings",
            "url": _safe_reverse("admin:siteconfig_sitesettings_changelist"),
        },
        {
            "label": "Feature Control",
            "icon": "toggle_on",
            "url": _safe_reverse("siteconfig:feature_control_panel"),
        },
        {
            "label": "Report Library",
            "icon": "library_books",
            "url": _safe_reverse("studio_os:output"),
        },
        {
            "label": "Knowledge Base",
            "icon": "menu_book",
            "url": _safe_reverse("kb:kb_home"),
        },
        {
            "label": "API Health",
            "icon": "monitor_heart",
            "url": _safe_reverse("api_health"),
            "target": "_blank",
            "rel": "noopener",
        },
        {
            "label": "My Preferences",
            "icon": "tune",
            "url": _safe_reverse("siteconfig:user_preferences"),
            "append_next": True,
        },
    ]


def _build_kpi_cards(
    *,
    total_users: int,
    admin_count: int,
    student_count: int,
    teacher_count: int,
    parent_count: int,
    db_engine_display: str,
    active_sessions: int,
    sessions_24h: int,
    mfa_compliance_percent: int,
    mfa_enabled_count: int,
    mfa_staff_total: int,
    mfa_by_role: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_role_summary = ", ".join(
        [
            f"{row.get('role', 'Unknown')} {row.get('enabled', 0)}/{row.get('total', 0)} ({row.get('percent', 0)}%)"
            for row in (mfa_by_role or [])
        ]
    )

    mfa_rows: list[dict[str, Any]] = [
        {
            "label": "Staff with MFA",
            "value": mfa_enabled_count,
            "value_class": "admin-kpi-val",
        },
        {
            "label": "Total staff",
            "value": mfa_staff_total,
            "value_class": "admin-kpi-val",
        },
    ]
    if by_role_summary:
        mfa_rows.append(
            {
                "label": "By role",
                "value": by_role_summary,
                "value_class": "admin-kpi-val",
            }
        )
    mfa_rows.append(
        {
            "link_label": "Site Settings",
            "link_url": _safe_reverse("admin:siteconfig_sitesettings_changelist"),
            "link_class": "admin-kpi-val admin-kpi-val--small",
        }
    )

    return [
        {
            "id": "admin-total-users",
            "label": "Total Users",
            "icon": "groups",
            "value": total_users,
            "rows": [
                {
                    "label": "Admins",
                    "value": admin_count,
                    "value_class": "admin-kpi-val admin-stat admin-stat--admins",
                },
                {
                    "label": "Students",
                    "value": student_count,
                    "value_class": "admin-kpi-val admin-stat admin-stat--students",
                },
                {
                    "label": "Teachers",
                    "value": teacher_count,
                    "value_class": "admin-kpi-val admin-stat admin-stat--teachers",
                },
                {
                    "label": "Parents",
                    "value": parent_count,
                    "value_class": "admin-kpi-val",
                },
            ],
        },
        {
            "id": "admin-db-app-stats",
            "label": "Database & App Stats",
            "icon": "database",
            "value": None,
            "rows": [
                {
                    "label": "Connection",
                    "value": "Ready",
                    "value_id": "dbConnectionStatus",
                    "value_class": "admin-stat admin-stat--success",
                },
                {
                    "label": "Database Health",
                    "value": "Optimal",
                    "value_id": "dbHealthStatus",
                    "value_class": "admin-stat admin-stat--success",
                },
                {
                    "label": "Engine",
                    "value": db_engine_display,
                    "value_class": "admin-kpi-val",
                },
                {
                    "label": "Active Sessions",
                    "value": active_sessions,
                    "value_class": "admin-kpi-val",
                },
            ],
        },
        {
            "id": "admin-system-health",
            "label": "System Health",
            "icon": "monitor_heart",
            "value": "Operational",
            "value_id": "apiHealthStatus",
            "value_link": _safe_reverse("api_health"),
            "value_link_class": "admin-stat admin-stat--success",
            "value_target": "_blank",
            "value_rel": "noopener",
            "value_title": "View API health",
            "rows": [
                {
                    "label": "Status",
                    "value": "Online",
                    "value_id": "systemStatus",
                    "value_class": "admin-stat admin-stat--success",
                },
                {
                    "label": "Sessions (24h)",
                    "value": sessions_24h,
                    "value_class": "admin-kpi-val",
                },
            ],
        },
        {
            "id": "admin-mfa-compliance",
            "label": "MFA Compliance",
            "icon": "shield_lock",
            "value": f"{mfa_compliance_percent}%",
            "rows": mfa_rows,
        },
    ]


@dataclass(frozen=True)
class AdminDashboardWidgetSpec:
    widget_id: str
    template_name: str
    permission_check: Callable[[dict[str, Any]], bool]
    query_fn: Callable[[dict[str, Any]], dict[str, Any]]
    cache_ttl_seconds: int = 0
    cache_scope: str = "global"


def _allow_all(_query_context: dict[str, Any]) -> bool:
    return True


def _allow_compliance(query_context: dict[str, Any]) -> bool:
    return bool(query_context.get("can_see_compliance"))


def _allow_finance_inbox(query_context: dict[str, Any]) -> bool:
    return bool(query_context.get("can_see_finance_inbox"))


def _query_kpi_cards(query_context: dict[str, Any]) -> dict[str, Any]:
    can_see_user_stats = bool(query_context.get("can_see_user_stats"))
    can_see_sessions = bool(query_context.get("can_see_sessions"))
    role_field_exists = bool(query_context.get("role_field_exists"))
    user_model = query_context["user_model"]

    total_users = int(query_context.get("total_users", 0)) if can_see_user_stats else 0
    admin_count = int(query_context.get("admin_count", 0)) if can_see_user_stats else 0
    student_count = int(query_context.get("student_count", 0)) if can_see_user_stats else 0
    teacher_count = int(query_context.get("teacher_count", 0)) if can_see_user_stats else 0
    parent_count = int(query_context.get("parent_count", 0)) if can_see_user_stats else 0
    active_sessions = int(query_context.get("active_sessions", 0)) if can_see_sessions else 0
    sessions_24h = int(query_context.get("sessions_24h", 0)) if can_see_sessions else 0

    mfa_enabled_count = 0
    mfa_staff_total = admin_count
    mfa_compliance_percent = 0
    mfa_by_role: list[dict[str, Any]] = []
    try:
        from django_otp.plugins.otp_totp.models import TOTPDevice

        staff_ids = list(
            user_model.objects.filter(is_staff=True).values_list("id", flat=True)
        )
        if staff_ids:
            mfa_enabled_count = (
                TOTPDevice.objects.filter(user_id__in=staff_ids, confirmed=True)
                .values_list("user_id", flat=True)
                .distinct()
                .count()
            )
            mfa_compliance_percent = round(100 * mfa_enabled_count / len(staff_ids))

        if role_field_exists:
            staff_qs = (
                user_model.objects.filter(is_staff=True)
                .exclude(role__isnull=True)
                .exclude(role="")
            )
            for role in staff_qs.values_list("role", flat=True).distinct():
                total = staff_qs.filter(role=role).count()
                enabled = (
                    TOTPDevice.objects.filter(
                        user__in=staff_qs.filter(role=role), confirmed=True
                    )
                    .values_list("user_id", flat=True)
                    .distinct()
                    .count()
                )
                mfa_by_role.append(
                    {
                        "role": role,
                        "enabled": enabled,
                        "total": total,
                        "percent": round(100 * enabled / total) if total else 0,
                    }
                )
    except _ADMIN_WIDGET_QUERY_ERRORS:
        logger.debug("Failed to compute MFA KPI widget payload.", exc_info=True)

    return {
        "total_users": total_users,
        "admin_count": admin_count,
        "student_count": student_count,
        "teacher_count": teacher_count,
        "parent_count": parent_count,
        "active_sessions": active_sessions,
        "sessions_24h": sessions_24h,
        "mfa_enabled_count": mfa_enabled_count,
        "mfa_staff_total": mfa_staff_total,
        "mfa_compliance_percent": mfa_compliance_percent,
        "mfa_by_role": mfa_by_role,
        "dashboard_kpi_cards": _build_kpi_cards(
            total_users=total_users,
            admin_count=admin_count,
            student_count=student_count,
            teacher_count=teacher_count,
            parent_count=parent_count,
            db_engine_display=query_context["db_engine_display"],
            active_sessions=active_sessions,
            sessions_24h=sessions_24h,
            mfa_compliance_percent=mfa_compliance_percent,
            mfa_enabled_count=mfa_enabled_count,
            mfa_staff_total=mfa_staff_total,
            mfa_by_role=mfa_by_role,
        ),
    }


def _query_security_compliance(query_context: dict[str, Any]) -> dict[str, Any]:
    data = {
        "new_logins_24h": 0,
        "failed_logins_24h": 0,
        "failed_logins_by_role": [],
        "security_alerts_24h": 0,
        "access_denials_24h": 0,
    }
    if not query_context.get("can_see_compliance"):
        return data

    now = query_context["now"]
    try:
        from apps.compliance.models_audit import AccessLog, AuditLog

        cutoff_24h = now - datetime.timedelta(hours=24)
        login_paths = ["/authentication/login/", "/admin/login/"]
        login_attempts = AccessLog.objects.filter(
            resource__in=login_paths,
            request_method="POST",
            timestamp__gte=cutoff_24h,
        )

        new_logins_24h = login_attempts.filter(status__in=["302", "303"]).count()
        failed_logins = login_attempts.exclude(status__in=["302", "303"])
        failed_logins_24h = failed_logins.count()
        failed_logins_by_role = list(
            failed_logins.values(role=Coalesce("user__role", Value("Unknown")))
            .annotate(count=Count("id"))
            .order_by("-count")[:3]
        )

        security_alerts_24h = (
            AuditLog.objects.filter(timestamp__gte=cutoff_24h)
            .filter(
                Q(action=AuditLog.Action.ACCESS_DENIED)
                | Q(sensitivity__in=["HIGH", "CRITICAL"])
            )
            .count()
        )
        access_denials_24h = AuditLog.objects.filter(
            action=AuditLog.Action.ACCESS_DENIED,
            timestamp__gte=cutoff_24h,
        ).count()
        data.update(
            {
                "new_logins_24h": new_logins_24h,
                "failed_logins_24h": failed_logins_24h,
                "failed_logins_by_role": failed_logins_by_role,
                "security_alerts_24h": security_alerts_24h,
                "access_denials_24h": access_denials_24h,
            }
        )
    except _ADMIN_WIDGET_QUERY_ERRORS:
        logger.debug("Failed to compute security/compliance widget payload.", exc_info=True)
    return data


def _query_action_queue(query_context: dict[str, Any]) -> dict[str, Any]:
    pending_approvals_count = 0
    pending_approvals_list: list[dict[str, str]] = []
    try:
        from apps.requests.models import AccessRequest
        from apps.requests.views import _can_manage_requests

        if _can_manage_requests(query_context["user"]):
            pending_qs = (
                AccessRequest.objects.filter(status=AccessRequest.Status.PENDING)
                .select_related("requester")
                .order_by("-requested_at")
            )
            pending_approvals_count = pending_qs.count()
            pending_approvals_list = [
                {
                    "reference": request_row.reference or f"#{request_row.pk}",
                    "request_type_display": request_row.get_request_type_display(),
                }
                for request_row in pending_qs[:5]
            ]
    except _ADMIN_WIDGET_QUERY_ERRORS:
        logger.debug("Failed to compute action queue widget payload.", exc_info=True)
    return {
        "pending_approvals_count": pending_approvals_count,
        "pending_approvals_list": pending_approvals_list,
    }


def _query_finance_inbox(query_context: dict[str, Any]) -> dict[str, Any]:
    finance_inbox_preview: list[dict[str, str]] = []
    finance_inbox_unread = 0
    if not query_context.get("can_see_finance_inbox"):
        return {
            "finance_inbox_preview": finance_inbox_preview,
            "finance_inbox_unread": finance_inbox_unread,
        }

    try:
        finance_requests_qs = Notification.objects.filter(
            recipient=query_context["request"].user,
            title__icontains="finance access request",
        ).order_by("-created_at")
        finance_inbox_unread = finance_requests_qs.filter(is_read=False).count()
        finance_inbox_preview = [
            {
                "title": note.title,
                "created_at_display": timezone.localtime(note.created_at).strftime(
                    "%b %d, %H:%M"
                ),
            }
            for note in finance_requests_qs[:3]
        ]
    except _ADMIN_WIDGET_QUERY_ERRORS:
        logger.debug("Failed to compute finance inbox widget payload.", exc_info=True)
    return {
        "finance_inbox_preview": finance_inbox_preview,
        "finance_inbox_unread": finance_inbox_unread,
    }


def _query_settings_audit(_query_context: dict[str, Any]) -> dict[str, Any]:
    settings_change_log: list[dict[str, str]] = []
    try:
        ct = ContentType.objects.get_for_model(SiteSettings)
        entries = LogEntry.objects.filter(content_type=ct).order_by("-action_time")[:5]
        settings_change_log = [
            {
                "user_display": str(entry.user) if entry.user else "System",
                "action_time_display": timezone.localtime(entry.action_time).strftime(
                    "%b %d, %H:%M"
                ),
            }
            for entry in entries
        ]
    except _ADMIN_WIDGET_QUERY_ERRORS:
        logger.debug("Failed to compute site settings audit widget payload.", exc_info=True)
    return {"settings_change_log": settings_change_log}


def _query_admin_controls(_query_context: dict[str, Any]) -> dict[str, Any]:
    return {"admin_control_links": _build_admin_control_links()}


ADMIN_DASHBOARD_WIDGET_REGISTRY: tuple[AdminDashboardWidgetSpec, ...] = (
    AdminDashboardWidgetSpec(
        widget_id="kpi_cards",
        template_name="admin/components/dashboard_kpi_card.html",
        permission_check=_allow_all,
        query_fn=_query_kpi_cards,
        cache_ttl_seconds=60,
        cache_scope="global",
    ),
    AdminDashboardWidgetSpec(
        widget_id="security_compliance",
        template_name="admin/components/dashboard_security_stat.html",
        permission_check=_allow_compliance,
        query_fn=_query_security_compliance,
        cache_ttl_seconds=45,
        cache_scope="global",
    ),
    AdminDashboardWidgetSpec(
        widget_id="action_queue",
        template_name="admin/components/dashboard_security_stat.html",
        permission_check=_allow_all,
        query_fn=_query_action_queue,
        cache_ttl_seconds=30,
        cache_scope="global",
    ),
    AdminDashboardWidgetSpec(
        widget_id="finance_inbox",
        template_name="admin/components/dashboard_security_stat.html",
        permission_check=_allow_finance_inbox,
        query_fn=_query_finance_inbox,
        cache_ttl_seconds=45,
        cache_scope="user",
    ),
    AdminDashboardWidgetSpec(
        widget_id="settings_audit",
        template_name="admin/components/dashboard_settings_change_row.html",
        permission_check=_allow_all,
        query_fn=_query_settings_audit,
        cache_ttl_seconds=60,
        cache_scope="global",
    ),
    AdminDashboardWidgetSpec(
        widget_id="admin_controls",
        template_name="admin/components/dashboard_control_link.html",
        permission_check=_allow_all,
        query_fn=_query_admin_controls,
        cache_ttl_seconds=600,
        cache_scope="global",
    ),
)


def _default_widget_payload() -> dict[str, Any]:
    return {
        "dashboard_kpi_cards": [],
        "admin_control_links": [],
        "dashboard_widget_telemetry": [],
        "total_users": 0,
        "admin_count": 0,
        "student_count": 0,
        "teacher_count": 0,
        "parent_count": 0,
        "active_sessions": 0,
        "sessions_24h": 0,
        "mfa_enabled_count": 0,
        "mfa_staff_total": 0,
        "mfa_compliance_percent": 0,
        "mfa_by_role": [],
        "new_logins_24h": 0,
        "failed_logins_24h": 0,
        "failed_logins_by_role": [],
        "security_alerts_24h": 0,
        "access_denials_24h": 0,
        "pending_approvals_count": 0,
        "pending_approvals_list": [],
        "finance_inbox_preview": [],
        "finance_inbox_unread": 0,
        "settings_change_log": [],
    }


def _widget_cache_key(
    spec: AdminDashboardWidgetSpec, query_context: dict[str, Any]
) -> str:
    from apps.siteconfig.cache_utils import get_tenant_cache_prefix
    user = query_context["user"]
    site_pk = query_context.get("site_pk") or "global"
    role_code = (getattr(user, "role", "") or "unknown").upper()
    request = query_context.get("request")
    prefix = get_tenant_cache_prefix(request)

    key_parts = [
        prefix,
        "dashboard",
        "admin",
        "widget",
        spec.widget_id,
        f"site={site_pk}",
    ]
    if spec.cache_scope == "user":
        key_parts.append(f"user={getattr(user, 'pk', 'anon')}")
    elif spec.cache_scope == "role":
        key_parts.append(f"role={role_code}")
    return ":".join(key_parts)


def _resolve_widget_payload(
    spec: AdminDashboardWidgetSpec, query_context: dict[str, Any]
) -> tuple[dict[str, Any], float, bool, bool]:
    enabled = bool(spec.permission_check(query_context))
    if not enabled:
        return {}, 0.0, False, False

    cache_hit = False
    cache_key = _widget_cache_key(spec, query_context)
    if spec.cache_ttl_seconds > 0:
        cached_payload = cache.get(cache_key)
        if isinstance(cached_payload, dict):
            cache_hit = True
            logger.debug(
                "Admin dashboard widget '%s' cache hit (scope=%s).",
                spec.widget_id,
                spec.cache_scope,
            )
            return cached_payload, 0.0, cache_hit, True

    start = time.perf_counter()
    try:
        payload = spec.query_fn(query_context)
        if not isinstance(payload, dict):
            payload = {}
    except _ADMIN_WIDGET_QUERY_ERRORS:
        request = query_context.get("request")
        msg = "Admin dashboard widget '%s' query failed." % spec.widget_id
        if request:
            log_view_exception(request, msg, extra={"widget_id": spec.widget_id})
        else:
            logger.exception(msg)
        payload = {}
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.debug(
        "Admin dashboard widget '%s' resolved in %.2fms (cache_hit=%s).",
        spec.widget_id,
        elapsed_ms,
        cache_hit,
    )

    if spec.cache_ttl_seconds > 0 and payload:
        cache.set(cache_key, payload, spec.cache_ttl_seconds)
    return payload, elapsed_ms, cache_hit, True


def _resolve_dashboard_widgets(
    query_context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, float], dict[str, bool], list[dict[str, Any]]]:
    merged_payload: dict[str, Any] = {}
    widget_timings_ms: dict[str, float] = {}
    widget_cache_hits: dict[str, bool] = {}
    widget_registry_meta: list[dict[str, Any]] = []

    for spec in ADMIN_DASHBOARD_WIDGET_REGISTRY:
        payload, elapsed_ms, cache_hit, enabled = _resolve_widget_payload(
            spec, query_context
        )
        widget_timings_ms[spec.widget_id] = round(elapsed_ms, 3)
        widget_cache_hits[spec.widget_id] = cache_hit
        widget_registry_meta.append(
            {
                "id": spec.widget_id,
                "template": spec.template_name,
                "cache_ttl_seconds": spec.cache_ttl_seconds,
                "cache_scope": spec.cache_scope,
                "enabled": enabled,
            }
        )
        if payload:
            merged_payload.update(payload)

    return merged_payload, widget_timings_ms, widget_cache_hits, widget_registry_meta


def build_admin_dashboard_context(
    request,
    *,
    base_context: dict[str, Any] | None = None,
    title: str = "Administration Dashboard",
) -> dict[str, Any]:
    """Build context for the canonical /admin dashboard template."""
    user = request.user
    user_model = get_user_model()
    now = timezone.now()

    role_field_exists = any(
        getattr(field, "name", "") == "role" for field in user_model._meta.get_fields()
    )

    total_users = user_model.objects.count()
    admin_count = user_model.objects.filter(is_staff=True).count()
    if role_field_exists:
        student_count = user_model.objects.filter(role="STUDENT").count()
        teacher_count = user_model.objects.filter(role="TEACHER").count()
        parent_count = user_model.objects.filter(role="PARENT").count()
    else:
        student_count = 0
        teacher_count = 0
        parent_count = 0

    active_sessions = Session.objects.filter(expire_date__gte=now).count()
    sessions_24h = Session.objects.filter(
        expire_date__gte=now - datetime.timedelta(hours=24)
    ).count()

    site = get_effective_site_settings(request=request)
    admin_theme = site.get_admin_theme()
    admin_palette: dict[str, Any] = {}
    if (
        admin_theme
        and getattr(admin_theme, "palette", None)
        and isinstance(admin_theme.palette, dict)
    ):
        admin_palette = admin_theme.palette.get("admin_dashboard") or {}

    preview_data = {
        "preview_mode_enabled": getattr(site, "preview_mode_enabled", False),
        "preview_toggle_enabled": getattr(site, "preview_toggle_enabled", True),
        "preview_banner_text": getattr(site, "preview_banner_text", ""),
        "preview_note": getattr(site, "preview_note", ""),
        "preview_colors": {
            "primary": getattr(site, "primary_color", "#0d6efd"),
            "accent": getattr(site, "accent_color", "#198754"),
        },
    }
    admin_weather = _build_admin_weather_config(site)

    can_see_user_stats = user.is_superuser or user.has_perm("auth.view_user")
    can_see_sessions = user.is_superuser or user.has_perm("sessions.view_session")
    can_see_compliance = user.is_superuser or user.has_perm(
        "compliance.view_auditlog"
    ) or user.has_perm("compliance.view_accesslog")
    can_see_finance_inbox = user.is_superuser or getattr(
        user, "has_feature_permission", lambda _: False
    )("finance.view_invoice")

    db_engine = connection.vendor
    db_engine_display = {
        "sqlite": "SQLite3",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
        "oracle": "Oracle",
    }.get(db_engine, db_engine.title())

    query_context: dict[str, Any] = {
        "request": request,
        "user": user,
        "site_pk": getattr(site, "pk", "global"),
        "now": now,
        "user_model": user_model,
        "role_field_exists": role_field_exists,
        "total_users": total_users,
        "admin_count": admin_count,
        "student_count": student_count,
        "teacher_count": teacher_count,
        "parent_count": parent_count,
        "active_sessions": active_sessions,
        "sessions_24h": sessions_24h,
        "db_engine_display": db_engine_display,
        "can_see_user_stats": can_see_user_stats,
        "can_see_sessions": can_see_sessions,
        "can_see_compliance": can_see_compliance,
        "can_see_finance_inbox": can_see_finance_inbox,
    }
    (
        widget_payload,
        widget_timings_ms,
        widget_cache_hits,
        widget_registry_meta,
    ) = _resolve_dashboard_widgets(query_context)
    dashboard_widget_telemetry = [
        {
            **widget_meta,
            "timing_ms": float(widget_timings_ms.get(widget_meta["id"], 0.0)),
            "cache_hit": bool(widget_cache_hits.get(widget_meta["id"], False)),
        }
        for widget_meta in widget_registry_meta
    ]

    context: dict[str, Any] = {}
    if base_context:
        context.update(base_context)

    context.update(_default_widget_payload())
    context.update(
        {
            "title": title,
            "preview_data": preview_data,
            "admin_weather": admin_weather,
            "admin_theme": admin_theme,
            "admin_palette": admin_palette,
            "django_version": django.get_version(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "db_engine_display": db_engine_display,
            "is_debug": settings.DEBUG,
            "header_actions": get_admin_header_actions(_safe_reverse),
            "dashboard_widget_registry": widget_registry_meta,
            "dashboard_widget_timings_ms": widget_timings_ms,
            "dashboard_widget_cache_hits": widget_cache_hits,
            "dashboard_widget_telemetry": dashboard_widget_telemetry,
        }
    )
    context.update(widget_payload)
    return context
