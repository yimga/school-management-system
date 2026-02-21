"""
Observability endpoints: /healthz and /metrics.
"""

import logging
from functools import wraps
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.db import connection
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db.models import Count, Q, Sum, Avg
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from django.core.cache import cache

logger = logging.getLogger(__name__)

WEATHER_CACHE_TTL_SECONDS = 300
WEATHER_STALE_CACHE_TTL_SECONDS = 1800
OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_CODE_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Foggy",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Light showers",
    81: "Showers",
    82: "Heavy showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Heavy thunderstorm",
}


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_admin_weather_config() -> dict:
    from apps.siteconfig.models import SiteSettings, default_header_weather_config

    site = SiteSettings.get_solo()
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
        "enabled": bool(flags.get("show_header_context_weather", True)),
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


def _weather_cache_key(config: dict, *, scope: str) -> str:
    lat = round(float(config.get("latitude", 0.0)), 4)
    lon = round(float(config.get("longitude", 0.0)), 4)
    unit = str(config.get("temperature_unit", "celsius")).lower()
    timezone_name = str(config.get("timezone", "UTC"))
    return f"weather:{scope}:v1:{lat}:{lon}:{unit}:{timezone_name}"


def _fetch_weather_snapshot(config: dict) -> dict:
    params = {
        "latitude": config["latitude"],
        "longitude": config["longitude"],
        "current": "temperature_2m,weather_code",
        "temperature_unit": config["temperature_unit"],
        "timezone": config["timezone"],
    }
    url = f"{OPEN_METEO_BASE_URL}?{urlencode(params)}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        payload = {}
    current = payload.get("current") if isinstance(payload, dict) else None
    if not isinstance(current, dict):
        raise ValueError("Weather provider response missing current data.")

    temperature = current.get("temperature_2m")
    weather_code = current.get("weather_code")
    if temperature is None or weather_code is None:
        raise ValueError("Weather provider response missing required fields.")

    code = int(weather_code)
    return {
        "temperature": float(temperature),
        "weather_code": code,
        "description": WEATHER_CODE_DESCRIPTIONS.get(code, "Unknown"),
    }


def _build_admin_weather_response(config: dict, weather: dict, *, status: str, cached: bool, stale: bool = False) -> dict:
    return {
        "status": status,
        "enabled": True,
        "label": config["label"],
        "latitude": config["latitude"],
        "longitude": config["longitude"],
        "temperature_unit": config["temperature_unit"],
        "timezone": config["timezone"],
        "cached": cached,
        "stale": stale,
        "weather": weather,
    }


def _build_weather_disabled_response(config: dict) -> dict:
    return {
        "status": "disabled",
        "enabled": False,
        "label": config["label"],
        "latitude": config["latitude"],
        "longitude": config["longitude"],
        "temperature_unit": config["temperature_unit"],
        "timezone": config["timezone"],
        "cached": False,
        "stale": False,
        "weather": None,
    }


def _build_weather_degraded_response(config: dict) -> dict:
    return {
        "status": "degraded",
        "enabled": True,
        "label": config["label"],
        "latitude": config["latitude"],
        "longitude": config["longitude"],
        "temperature_unit": config["temperature_unit"],
        "timezone": config["timezone"],
        "cached": False,
        "stale": False,
        "weather": None,
    }


def _resolve_weather_payload(config: dict, *, scope: str) -> dict:
    if not config["enabled"]:
        return _build_weather_disabled_response(config)

    cache_key = _weather_cache_key(config, scope=scope)
    stale_cache_key = f"{cache_key}:stale"

    cached_payload = cache.get(cache_key)
    if isinstance(cached_payload, dict):
        response_payload = dict(cached_payload)
        response_payload["cached"] = True
        response_payload.setdefault("stale", False)
        return response_payload

    try:
        weather = _fetch_weather_snapshot(config)
        payload = _build_admin_weather_response(
            config,
            weather,
            status="success",
            cached=False,
            stale=False,
        )
        cache.set(cache_key, payload, WEATHER_CACHE_TTL_SECONDS)
        cache.set(stale_cache_key, payload, WEATHER_STALE_CACHE_TTL_SECONDS)
        return payload
    except Exception:
        logger.warning(
            "Weather provider request failed (scope=%s).",
            scope,
            exc_info=True,
        )

    stale_payload = cache.get(stale_cache_key)
    if isinstance(stale_payload, dict):
        response_payload = dict(stale_payload)
        response_payload["status"] = "degraded"
        response_payload["cached"] = True
        response_payload["stale"] = True
        return response_payload

    return _build_weather_degraded_response(config)


def _is_observability_authorized(request) -> bool:
    """Allow staff users or holders of the observability API key."""
    api_key = getattr(settings, "OBSERVABILITY_API_KEY", "")
    if api_key:
        header_key = request.headers.get("X-OBSERVABILITY-KEY") or request.META.get("HTTP_X_OBSERVABILITY_KEY")
        if header_key == api_key:
            return True

    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return user.is_staff or user.is_superuser or getattr(user, "role", None) == "ADMIN"
    return False


def observability_auth_required(view_func):
    """Require staff session auth; allow API key for safe GET/HEAD requests."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.method in ("GET", "HEAD"):
            if _is_observability_authorized(request):
                return view_func(request, *args, **kwargs)
        else:
            user = getattr(request, "user", None)
            if user and user.is_authenticated and (user.is_staff or user.is_superuser or getattr(user, "role", None) == "ADMIN"):
                return view_func(request, *args, **kwargs)

        return HttpResponseForbidden("Forbidden")
    return _wrapped


@require_GET
@observability_auth_required
def healthz(request):
    """Internal health check including DB connectivity (RBAC/API-key protected)."""
    try:
        # Simple DB round-trip
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        status = "ok"
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"status": "error", "error": str(exc)}, status=500)

    return JsonResponse({"status": status})


@require_GET
def public_health(request):
    """Public health endpoint for load balancers and uptime checks.

    This endpoint intentionally does not require observability auth and avoids
    DB/cache dependencies so cold starts and platform probes stay reliable.
    """
    return JsonResponse({"status": "healthy"})


@require_GET
@observability_auth_required
def metrics(request):
    """Prometheus metrics endpoint."""
    base_output = generate_latest()

    # Append AI Copilot lightweight counters from cache in Prometheus text format
    lines = []
    try:
        total = cache.get('ai_copilot_usage_total') or 0
        denied = cache.get('ai_copilot_usage_denied_total') or 0
        errors = cache.get('ai_copilot_usage_errors_total') or 0
        last_success_ts = cache.get('ai_copilot_last_success_ts') or 0
        last_error_ts = cache.get('ai_copilot_last_error_ts') or 0
        roles = cache.get('ai_copilot_usage_roles') or []

        lines.append('# HELP ai_copilot_usage_total Total AI Copilot queries processed')
        lines.append('# TYPE ai_copilot_usage_total counter')
        lines.append(f'ai_copilot_usage_total {int(total)}')

        lines.append('# HELP ai_copilot_usage_denied_total Total AI Copilot queries denied (RBAC/Rate limit)')
        lines.append('# TYPE ai_copilot_usage_denied_total counter')
        lines.append(f'ai_copilot_usage_denied_total {int(denied)}')

        lines.append('# HELP ai_copilot_usage_errors_total Total AI Copilot errors')
        lines.append('# TYPE ai_copilot_usage_errors_total counter')
        lines.append(f'ai_copilot_usage_errors_total {int(errors)}')

        lines.append('# HELP ai_copilot_last_success_timestamp_seconds Last successful AI Copilot response time')
        lines.append('# TYPE ai_copilot_last_success_timestamp_seconds gauge')
        lines.append(f'ai_copilot_last_success_timestamp_seconds {float(last_success_ts)}')

        lines.append('# HELP ai_copilot_last_error_timestamp_seconds Last AI Copilot error time')
        lines.append('# TYPE ai_copilot_last_error_timestamp_seconds gauge')
        lines.append(f'ai_copilot_last_error_timestamp_seconds {float(last_error_ts)}')

        lines.append('# HELP ai_copilot_usage_role AI Copilot queries by role')
        lines.append('# TYPE ai_copilot_usage_role counter')
        for role in roles:
            val = cache.get(f'ai_copilot_usage_role:{role}') or 0
            # Sanitize role label value
            role_label = str(role).replace('"', '')
            lines.append(f'ai_copilot_usage_role{{role="{role_label}"}} {int(val)}')
    except Exception:
        # If cache backend doesn't support this, skip appending
        pass

    extra = ('\n'.join(lines) + '\n').encode('utf-8') if lines else b''
    return HttpResponse(base_output + extra, content_type=CONTENT_TYPE_LATEST)


@require_GET
@observability_auth_required
def copilot_metrics_json(request):
    """JSON endpoint for AI Copilot usage counters.

    Returns: { total: int, denied: int, roles: [{role: str, count: int}] }
    """
    try:
        total = cache.get('ai_copilot_usage_total') or 0
        denied = cache.get('ai_copilot_usage_denied_total') or 0
        errors = cache.get('ai_copilot_usage_errors_total') or 0
        last_success_ts = cache.get('ai_copilot_last_success_ts') or 0
        last_error_ts = cache.get('ai_copilot_last_error_ts') or 0
        roles = cache.get('ai_copilot_usage_roles') or []

        role_counts = []
        for role in roles:
            val = cache.get(f'ai_copilot_usage_role:{role}') or 0
            role_counts.append({
                'role': str(role),
                'count': int(val),
            })

        return JsonResponse({
            'success': True,
            'total': int(total),
            'denied': int(denied),
            'errors': int(errors),
            'last_success_ts': float(last_success_ts) if last_success_ts else None,
            'last_error_ts': float(last_error_ts) if last_error_ts else None,
            'roles': role_counts,
        })
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({
            'success': True,
            'total': 0,
            'denied': 0,
            'errors': 0,
            'last_success_ts': None,
            'last_error_ts': None,
            'roles': [],
            'warning': str(exc),
        })


# ============================================
# ADMIN DASHBOARD API ENDPOINTS
# ============================================

@require_http_methods(["GET", "HEAD"])
@observability_auth_required
def api_health(request):
    """API endpoint for dashboard health checks.
    
    Returns system health status, active users, database status.
    Used by dashboard to display system state.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        
        return JsonResponse({
            "status": "healthy",
            "database": "connected",
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "uptime": "running",
            "cache": "available"
        })
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "error": str(exc)
        }, status=500)


@require_GET
@observability_auth_required
def api_admin_weather(request):
    """Server-side weather snapshot for admin dashboard widgets."""
    payload = _resolve_weather_payload(_build_admin_weather_config(), scope="admin")
    return JsonResponse(payload)


@require_GET
def api_weather_context(request):
    """Public-safe weather snapshot for shared header/backend widgets."""
    payload = _resolve_weather_payload(_build_admin_weather_config(), scope="context")
    return JsonResponse(payload)


@require_POST
@login_required
def api_notifications_mark_all_read(request):
    """Mark all notifications for the current user as read."""
    try:
        from apps.finance.models import Notification

        user = request.user
        qs = Notification.objects.filter(
            Q(recipient=user) | Q(created_by=user)
        ).filter(is_read=False)
        updated = qs.update(is_read=True)
        return JsonResponse({
            "status": "success",
            "message": "All notifications marked as read",
            "count": updated
        })
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "error": str(exc)
        }, status=500)


@require_GET
@login_required
def api_notifications(request):
    """API endpoint to fetch recent notifications.
    
    Returns a list of recent system notifications and alerts.
    """
    try:
        from apps.finance.models import Notification

        user = request.user
        notifications_qs = Notification.objects.filter(
            Q(recipient=user) | Q(created_by=user)
        ).order_by('-created_at')[:50]
        mapped = []
        for notif in notifications_qs:
            notif_type = "info"
            if notif.severity == Notification.Severity.ALERT:
                notif_type = "alert"
            elif notif.severity == Notification.Severity.WARNING:
                notif_type = "warning"

            mapped.append({
                "id": notif.id,
                "title": notif.title,
                "message": notif.message,
                "type": notif_type,
                "category": notif.severity,
                "is_read": notif.is_read,
                "created_at": notif.created_at.isoformat(),
                "timestamp": notif.created_at.isoformat(),
                "link": notif.link,
            })

        return JsonResponse({
            "status": "success",
            "notifications": mapped,
            "count": len(mapped)
        })
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "error": str(exc)
        }, status=500)


@require_GET
@observability_auth_required
def api_activities(request):
    """API endpoint to fetch recent activities/audit logs.
    
    Returns a list of recent system activities, admin actions, and student changes.
    Supports filtering by type and pagination.
    """
    try:
        from django.contrib.admin.models import LogEntry

        page = int(request.GET.get('page', 1))
        per_page = 10

        logs = LogEntry.objects.select_related("user", "content_type").order_by("-action_time")
        total = logs.count()
        logs = logs[(page - 1) * per_page: page * per_page]

        activities = []
        for entry in logs:
            if entry.is_addition():
                action_type = "add"
            elif entry.is_change():
                action_type = "change"
            elif entry.is_deletion():
                action_type = "delete"
            else:
                action_type = "activity"

            activities.append({
                "id": entry.id,
                "type": action_type,
                "title": entry.object_repr,
                "description": entry.get_change_message() or action_type.title(),
                "timestamp": entry.action_time.isoformat(),
                "user": getattr(entry.user, "username", None),
            })

        return JsonResponse({
            "status": "success",
            "activities": activities,
            "count": len(activities),
            "total": total,
            "page": page
        })
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "error": str(exc)
        }, status=500)


@require_GET
@observability_auth_required
def api_dashboard_charts(request):
    """API endpoint for dashboard chart data.
    
    Returns data for enrollment trends, fee collection, performance analytics, etc.
    """
    try:
        from apps.people.models import StudentProfile, TeacherAttendance
        from apps.academics.models import Classroom
        from apps.finance.models import Invoice, Payment
        from apps.evals.models import Evaluation

        # Enrollment by classroom
        classrooms = Classroom.objects.annotate(
            total=Count("students", filter=Q(students__is_active=True))
        ).order_by("-total")[:6]
        enrollment_labels = [c.name for c in classrooms]
        enrollment_data = [c.total for c in classrooms]
        enrollment = {
            "labels": enrollment_labels,
            "datasets": [{
                "label": "Active students",
                "data": enrollment_data,
                "borderColor": "#ff6a88",
                "backgroundColor": "rgba(255, 106, 136, 0.1)",
                "tension": 0.4,
                "fill": True,
                "pointRadius": 4,
                "pointHoverRadius": 6,
            }],
        }

        # Fee collection
        invoiced = Invoice.objects.exclude(status=Invoice.Status.VOID).aggregate(total=Sum("total_amount")).get("total") or 0
        paid = Payment.objects.filter(status="completed").aggregate(total=Sum("amount")).get("total") or 0
        overdue_amount = Invoice.objects.filter(status=Invoice.Status.OVERDUE).aggregate(total=Sum("balance_amount")).get("total") or 0
        fee_collection = {
            "labels": ["Paid", "Pending", "Overdue"],
            "datasets": [{
                "data": [
                    float(paid),
                    float(max(invoiced - paid, 0)),
                    float(overdue_amount or 0),
                ],
                "backgroundColor": ['#2dd4bf', '#9b6bff', '#ff6a88'],
            }],
        }

        # Performance by subject (exam score average)
        subject_scores = (
            Evaluation.objects.exclude(exam_score__isnull=True)
            .values("subject_assignment__subject__name")
            .annotate(avg=Avg("exam_score"))
            .order_by("-avg")[:6]
        )
        perf_labels = [row["subject_assignment__subject__name"] or "Subject" for row in subject_scores]
        perf_data = [round(float(row["avg"]), 1) for row in subject_scores]
        performance = {
            "labels": perf_labels,
            "datasets": [{
                "label": "Average Grade",
                "data": perf_data,
                "borderColor": "#9b6bff",
                "backgroundColor": "rgba(155, 107, 255, 0.1)",
                "fill": True,
            }],
        }

        # Attendance snapshot for the past 7 days
        today = timezone.localdate()
        window = TeacherAttendance.objects.filter(date__range=(today - __import__('datetime').timedelta(days=6), today))
        attendance_counts = {
            "Present": window.filter(status=TeacherAttendance.Status.PRESENT).count(),
            "Absent": window.filter(status=TeacherAttendance.Status.ABSENT).count(),
            "Late": window.filter(status=TeacherAttendance.Status.LATE).count(),
            "On leave": window.filter(status=TeacherAttendance.Status.ON_LEAVE).count(),
        }
        attendance = {
            "labels": list(attendance_counts.keys()),
            "datasets": [{
                "data": list(attendance_counts.values()),
                "backgroundColor": ['#2dd4bf', '#ff6a88', '#9b6bff', '#f59e0b'],
            }],
        }

        return JsonResponse({
            "status": "success",
            "enrollment": enrollment,
            "feeCollection": fee_collection,
            "performance": performance,
            "attendance": attendance,
        })
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "error": str(exc)
        }, status=500)


# ============================================
# ADMIN DASHBOARD - Backend/System Management
# ============================================

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser or getattr(u, "role", None) == "ADMIN")
def admin_dashboard(request):
    """Legacy alias for the admin dashboard."""
    return redirect("admin:index")
