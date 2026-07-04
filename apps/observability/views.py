"""
Observability endpoints: /healthz and /metrics.
"""

import json
import logging
import math
import os
import re
from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from apps.observability.db_liveness import check_db_liveness
from apps.platform_runtime.structured_logging import log_view_exception
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.shortcuts import redirect, render
from django.urls import reverse, NoReverseMatch
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db import DatabaseError, IntegrityError
from django.db.models import Count, Q, Sum, Avg
from django.core.exceptions import ValidationError
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from django.core.cache import cache
from apps.siteconfig.config_service import get_effective_site_settings

logger = logging.getLogger(__name__)

# Load-balancer probe + human status page live in public_status.py.
from apps.observability.public_status import (  # noqa: E402
    public_health as public_health,
    public_status as public_status,
)

# Reduced external API traffic: longer TTL; enable weather per-tenant where needed.
WEATHER_CACHE_TTL_SECONDS = 900
WEATHER_STALE_CACHE_TTL_SECONDS = 3600
WEATHER_PROVIDER_BACKOFF_SECONDS = 600
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


def _percent(numerator: int, denominator: int, fallback: float = 100.0) -> float:
    if denominator <= 0:
        return float(fallback)
    return round((float(numerator) / float(denominator)) * 100.0, 2)


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    index = max(int(math.ceil(len(ordered) * 0.95)) - 1, 0)
    return round(ordered[index], 2)


def _build_admin_weather_config(request=None) -> dict:
    from apps.siteconfig.models import default_header_weather_config

    site = get_effective_site_settings(request=request)
    flags = getattr(site, "backend_feature_flags", None) or {}
    weather_defaults = default_header_weather_config()
    raw_unit = str(
        flags.get(
            "header_weather_temperature_unit",
            weather_defaults["header_weather_temperature_unit"],
        )
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
        "label": str(
            flags.get("header_weather_label", weather_defaults["header_weather_label"])
        ),
        "latitude": _safe_float(
            flags.get(
                "header_weather_latitude", weather_defaults["header_weather_latitude"]
            ),
            weather_defaults["header_weather_latitude"],
        ),
        "longitude": _safe_float(
            flags.get(
                "header_weather_longitude", weather_defaults["header_weather_longitude"]
            ),
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


def _weather_coords_configured(config: dict) -> bool:
    """True when operator configured a real campus location (not null-island defaults)."""
    lat = _safe_float(config.get("latitude"), 0.0)
    lon = _safe_float(config.get("longitude"), 0.0)
    return abs(lat) > 0.01 or abs(lon) > 0.01


def _weather_provider_backoff_key(cache_key: str) -> str:
    return f"{cache_key}:provider_backoff"


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


def _build_admin_weather_response(
    config: dict, weather: dict, *, status: str, cached: bool, stale: bool = False
) -> dict:
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


def _resolve_weather_payload(config: dict, *, scope: str, request=None) -> dict:
    if not config["enabled"]:
        return _build_weather_disabled_response(config)

    if not _weather_coords_configured(config):
        return _build_weather_degraded_response(config)

    try:
        from apps.siteconfig.cache_utils import get_tenant_cache_prefix

        prefix = get_tenant_cache_prefix(request)
    except (ImportError, AttributeError, TypeError):
        logger.debug("get_tenant_cache_prefix unavailable, using public prefix")
        prefix = "public"
    base_key = _weather_cache_key(config, scope=scope)
    cache_key = f"{prefix}:{base_key}"
    stale_cache_key = f"{cache_key}:stale"
    backoff_key = _weather_provider_backoff_key(cache_key)

    cached_payload = cache.get(cache_key)
    if isinstance(cached_payload, dict):
        response_payload = dict(cached_payload)
        response_payload["cached"] = True
        response_payload.setdefault("stale", False)
        return response_payload

    if cache.get(backoff_key):
        stale_payload = cache.get(stale_cache_key)
        if isinstance(stale_payload, dict):
            response_payload = dict(stale_payload)
            response_payload["status"] = "degraded"
            response_payload["cached"] = True
            response_payload["stale"] = True
            return response_payload
        return _build_weather_degraded_response(config)

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
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code == 429:
            cache.set(backoff_key, 1, WEATHER_PROVIDER_BACKOFF_SECONDS)
            logger.warning(
                "Weather provider rate limited (scope=%s); backing off %ss",
                scope,
                WEATHER_PROVIDER_BACKOFF_SECONDS,
            )
        else:
            logger.warning(
                "Weather provider request failed (scope=%s): %s",
                scope,
                exc,
                exc_info=True,
            )
    except (OSError, requests.RequestException, ValueError, KeyError) as exc:
        logger.warning(
            "Weather provider request failed (scope=%s): %s",
            scope,
            exc,
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
        header_key = request.headers.get("X-OBSERVABILITY-KEY") or request.META.get(
            "HTTP_X_OBSERVABILITY_KEY"
        )
        if header_key == api_key:
            return True

    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return (
            user.is_staff or user.is_superuser or getattr(user, "role", None) == "ADMIN"
        )
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
            if (
                user
                and user.is_authenticated
                and (
                    user.is_staff
                    or user.is_superuser
                    or getattr(user, "role", None) == "ADMIN"
                )
            ):
                return view_func(request, *args, **kwargs)

        return HttpResponseForbidden("Forbidden")

    return _wrapped


def _check_cache_liveness() -> dict:
    """Pass 11: best-effort cache (Redis) liveness for /healthz/. Never throws."""
    try:
        from django.core.cache import cache

        token = "healthz:cache:ping"
        cache.set(token, "1", timeout=5)
        return {"status": "ok" if cache.get(token) == "1" else "degraded"}
    except Exception as exc:  # noqa: BLE001 - liveness check must never crash the probe
        return {"status": "degraded", "error": str(exc)[:120]}


def _check_celery_broker_liveness() -> dict:
    """Best-effort Celery broker reachability for /healthz/. Never throws and
    never FAILS the probe: /healthz is the liveness signal, so a transient
    broker outage must not trigger web-tier restarts while DB + app are healthy.
    Operators read this field for readiness/alerting (a dead broker = silent
    task backlog). Bounded connect timeout so a down broker can't hang the probe."""
    try:
        from config.celery import app as celery_app

        conn = celery_app.connection()
        try:
            conn.ensure_connection(max_retries=1, timeout=2)
        finally:
            try:
                conn.release()
            except Exception:  # noqa: BLE001 - connection release is best-effort
                pass
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 - liveness check must never crash the probe
        return {"status": "degraded", "error": str(exc)[:120]}


# Queue-depth alert threshold. A configured-but-deep backlog is "degraded"
# (operators alert), not "ok": a worker may be down or saturated while the
# broker keeps accepting work. Env-tunable; never hardcoded into the contract.
def _queue_depth_warn_threshold() -> int:
    raw = getattr(settings, "HEALTHZ_QUEUE_DEPTH_WARN", None)
    if raw is None:
        raw = os.getenv("HEALTHZ_QUEUE_DEPTH_WARN", "1000")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 1000
    return value if value > 0 else 1000  # magic-number-allow: env-tunable backlog alert default


def _check_celery_queue_depth() -> dict:
    """Best-effort BROKER queue-depth (backlog) probe for /healthz/.

    DISTINCT from `_check_celery_broker_liveness` (reachability) and from
    public_status._probe_celery_queue_depth (which counts tasks already
    reserved/active ON workers via an inspect broadcast — that reports ~0 when
    no worker is up even if the broker holds thousands of unconsumed tasks).
    This probe asks the broker directly how many messages are sitting in the
    primary queue (`queue_declare(passive=True).message_count`), which is the
    AMQP-compatible call kombu maps to BOTH Redis/Valkey (LLEN) and RabbitMQ —
    so it works for whichever broker is configured and reports the TRUE backlog
    a down/saturated worker would let pile up.

    Fail-SOFT contract: never raises; on any failure (broker unreachable, probe
    error, transport without a depth API) it returns a benign status
    ("unavailable"/"unknown") + short detail, so /healthz keeps its normal
    response and NEVER becomes a 500. A bounded connect/socket timeout means a
    down broker cannot hang the endpoint.
    """
    try:
        broker = (getattr(settings, "CELERY_BROKER_URL", "") or "").strip()
        if not broker:
            # No broker provisioned: tasks run inline (eager). There is no
            # queue to back up, so report unavailable, not degraded.
            return {"status": "unavailable", "detail": "broker not configured (eager mode)"}

        from config.celery import app as celery_app

        queue_name = (
            getattr(celery_app.conf, "task_default_queue", None) or "celery"
        )

        conn = celery_app.connection()
        try:
            # Bound the connect so a down broker can't hang /healthz.
            conn.ensure_connection(max_retries=1, timeout=2)
            channel = conn.default_channel
            # passive=True: never CREATE the queue, only read its current
            # message_count. Works on Redis/Valkey + RabbitMQ via kombu.
            declared = channel.queue_declare(queue=queue_name, passive=True)
            depth = int(getattr(declared, "message_count", 0))
        finally:
            try:
                conn.release()
            except Exception:  # noqa: BLE001 - connection release is best-effort
                pass

        if depth < 0:
            return {"status": "unknown", "queue": queue_name}
        threshold = _queue_depth_warn_threshold()
        status = "degraded" if depth >= threshold else "ok"
        return {"status": status, "depth": depth, "queue": queue_name}
    except Exception as exc:  # noqa: BLE001 - backlog probe must never crash the endpoint
        return {"status": "unavailable", "error": str(exc)[:120]}


@require_GET
def csrf_token_refresh(request):
    """Offline foundational: return a freshly-rotated CSRF token.

    The service worker calls this immediately before replaying queued POSTs
    so the X-CSRFToken header matches the current csrftoken cookie. The
    response is uncacheable; ensure_csrf_cookie rotates the cookie when the
    user's session is older than CSRF_COOKIE_AGE.

    This view is intentionally NOT gated by `observability_auth_required` —
    the SW replays POSTs on behalf of parents/students whose original requests
    were queued offline, so any authenticated user must be able to refresh
    the token. CSRF tokens are not secret; rotation is the entire point.
    """
    from django.middleware.csrf import get_token
    from django.views.decorators.csrf import ensure_csrf_cookie

    @ensure_csrf_cookie
    def _emit(req):
        return JsonResponse(
            {"csrf_token": get_token(req)},
            headers={"Cache-Control": "no-store"},
        )

    return _emit(request)


def healthz(request):
    """Internal health check including DB + cache connectivity (RBAC/API-key protected)."""
    try:
        result = check_db_liveness()
        db_status = "ok" if result.get("status") == "healthy" else "error"
        if db_status != "ok":
            return JsonResponse(
                {
                    "status": "error",
                    "database": "error",
                    "error": result.get("error", "db check failed"),
                },
                status=500,
            )
    except (ValueError, TypeError, KeyError) as exc:
        log_view_exception(
            request,
            "observability.views.healthz: check_db_liveness result handling failed",
            extra={"error": str(exc)},
        )
        return JsonResponse({"status": "error", "error": str(exc)}, status=500)

    # Cache (Redis) + Celery broker (liveness + queue depth) are best-effort: a
    # degraded result is reported but does NOT fail the healthz (liveness)
    # response. The queue-depth probe surfaces task backlog (a silent worker
    # outage) as a structured sub-field without ever turning /healthz into a 500.
    cache_result = _check_cache_liveness()
    broker_result = _check_celery_broker_liveness()
    queue_depth_result = _check_celery_queue_depth()

    return JsonResponse(
        {
            "status": "ok",
            "database": "ok",
            "cache": cache_result.get("status", "unknown"),
            "celery_broker": broker_result.get("status", "unknown"),
            "celery_queue_depth": queue_depth_result,
        }
    )


@require_POST
def client_event_capture(request):
    """
    Pass 11.B: server-side bridge for browser + service-worker errors.

    Accepts a small JSON payload from the frontend (`message`, `level`, `url`,
    `line`, `col`, `stack`, `source` ∈ {"window", "sw", "unhandled_rejection"}).
    Sanitizes + forwards via the server-side sentry_sdk so we never need a
    CDN-loaded Sentry-Browser SDK on the page.

    Returns 204 on success; the call is fire-and-forget for the frontend.
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    message = str(payload.get("message") or "")[:500]
    if not message:
        return JsonResponse({"ok": False, "error": "missing_message"}, status=400)

    level = str(payload.get("level") or "error").lower()
    if level not in {"info", "warning", "error", "fatal"}:
        level = "error"

    source = str(payload.get("source") or "window")[:24]
    if source not in {"window", "sw", "unhandled_rejection"}:
        source = "window"

    # PII / size guard: drop stack frames past 4kB total.
    stack = str(payload.get("stack") or "")[:4000]  # magic-number-allow: client-error-stack-cap-chars
    url = str(payload.get("url") or "")[:500]
    line = payload.get("line")
    col = payload.get("col")
    user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:300]

    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            scope.set_tag("source", source)
            scope.set_tag("client_capture", "1")
            scope.set_extra("url", url)
            scope.set_extra("line", line)
            scope.set_extra("col", col)
            scope.set_extra("stack", stack)
            scope.set_extra("user_agent", user_agent)
            user = getattr(request, "user", None)
            if user is not None and getattr(user, "is_authenticated", False):
                scope.user = {"id": str(user.pk), "username": user.username}
            sentry_sdk.capture_message(message, level=level)
    except (ImportError, AttributeError, TypeError, ValueError):
        logger.warning("client_event_capture: sentry_sdk forward failed: %s", message)

    return HttpResponse(status=204)


def _safe_version_value(*names: str, default: str = "unknown") -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value[:128]
    return default


@require_GET
def public_version(request):
    """
    Safe build metadata for live parity certification.

    This endpoint intentionally exposes only a small allowlisted payload. It does
    not dump environment variables or include any credentials.
    """
    del request
    commit_sha = _safe_version_value(
        "RENDER_GIT_COMMIT",
        "GIT_COMMIT",
        "SOURCE_VERSION",
        "COMMIT_SHA",
    )
    if commit_sha != "unknown" and not re.fullmatch(r"[0-9a-fA-F]{7,64}", commit_sha):
        commit_sha = "unknown"
    build_time = _safe_version_value(
        "BUILD_TIME",
        "BUILD_TIMESTAMP",
        "RENDER_CREATED_AT",
    )
    return JsonResponse(
        {
            "commit_sha": commit_sha,
            "build_time": build_time,
            "app_version": str(getattr(settings, "APP_VERSION", "unknown")),
            "environment": _safe_version_value(
                "RENDER_SERVICE_NAME",
                "DJANGO_ENV",
                "ENVIRONMENT",
                default="unknown",
            ),
        }
    )


@require_GET
@observability_auth_required
def metrics(request):
    """Prometheus metrics endpoint."""
    base_output = generate_latest()

    # Append AI Copilot lightweight counters from cache (tenant-scoped when request has tenant)
    lines = []
    try:
        from apps.siteconfig.cache_utils import tenant_cache_key

        def _ck(b):
            return tenant_cache_key(b, request)

        total = cache.get(_ck("ai_copilot_usage_total")) or 0
        denied = cache.get(_ck("ai_copilot_usage_denied_total")) or 0
        errors = cache.get(_ck("ai_copilot_usage_errors_total")) or 0
        last_success_ts = cache.get(_ck("ai_copilot_last_success_ts")) or 0
        last_error_ts = cache.get(_ck("ai_copilot_last_error_ts")) or 0
        roles = cache.get(_ck("ai_copilot_usage_roles")) or []

        lines.append("# HELP ai_copilot_usage_total Total AI Copilot queries processed")
        lines.append("# TYPE ai_copilot_usage_total counter")
        lines.append(f"ai_copilot_usage_total {int(total)}")

        lines.append(
            "# HELP ai_copilot_usage_denied_total Total AI Copilot queries denied (RBAC/Rate limit)"
        )
        lines.append("# TYPE ai_copilot_usage_denied_total counter")
        lines.append(f"ai_copilot_usage_denied_total {int(denied)}")

        lines.append("# HELP ai_copilot_usage_errors_total Total AI Copilot errors")
        lines.append("# TYPE ai_copilot_usage_errors_total counter")
        lines.append(f"ai_copilot_usage_errors_total {int(errors)}")

        lines.append(
            "# HELP ai_copilot_last_success_timestamp_seconds Last successful AI Copilot response time"
        )
        lines.append("# TYPE ai_copilot_last_success_timestamp_seconds gauge")
        lines.append(
            f"ai_copilot_last_success_timestamp_seconds {float(last_success_ts)}"
        )

        lines.append(
            "# HELP ai_copilot_last_error_timestamp_seconds Last AI Copilot error time"
        )
        lines.append("# TYPE ai_copilot_last_error_timestamp_seconds gauge")
        lines.append(f"ai_copilot_last_error_timestamp_seconds {float(last_error_ts)}")

        lines.append("# HELP ai_copilot_usage_role AI Copilot queries by role")
        lines.append("# TYPE ai_copilot_usage_role counter")
        for role in roles:
            val = cache.get(_ck(f"ai_copilot_usage_role:{role}")) or 0
            # Sanitize role label value
            role_label = str(role).replace('"', "")
            lines.append(f'ai_copilot_usage_role{{role="{role_label}"}} {int(val)}')
    except (ImportError, AttributeError, TypeError) as _exc:
        logger.debug("metrics: cache/copilot counters skipped: %s", _exc)

    extra = ("\n".join(lines) + "\n").encode("utf-8") if lines else b""
    return HttpResponse(base_output + extra, content_type=CONTENT_TYPE_LATEST)


@require_GET
@observability_auth_required
def copilot_metrics_json(request):
    """JSON endpoint for AI Copilot usage counters.

    Returns: { total: int, denied: int, roles: [{role: str, count: int}] }
    """
    try:
        from apps.siteconfig.cache_utils import tenant_cache_key

        def _ck(b):
            return tenant_cache_key(b, request)

        total = cache.get(_ck("ai_copilot_usage_total")) or 0
        denied = cache.get(_ck("ai_copilot_usage_denied_total")) or 0
        errors = cache.get(_ck("ai_copilot_usage_errors_total")) or 0
        last_success_ts = cache.get(_ck("ai_copilot_last_success_ts")) or 0
        last_error_ts = cache.get(_ck("ai_copilot_last_error_ts")) or 0
        roles = cache.get(_ck("ai_copilot_usage_roles")) or []

        role_counts = []
        for role in roles:
            val = cache.get(_ck(f"ai_copilot_usage_role:{role}")) or 0
            role_counts.append(
                {
                    "role": str(role),
                    "count": int(val),
                }
            )

        return JsonResponse(
            {
                "success": True,
                "total": int(total),
                "denied": int(denied),
                "errors": int(errors),
                "last_success_ts": float(last_success_ts) if last_success_ts else None,
                "last_error_ts": float(last_error_ts) if last_error_ts else None,
                "roles": role_counts,
            }
        )
    except (ImportError, AttributeError, TypeError, ValueError, KeyError) as exc:
        logger.warning(
            "copilot_metrics_json: cache read failed: %s", exc, exc_info=True
        )
        return JsonResponse(
            {
                "success": True,
                "total": 0,
                "denied": 0,
                "errors": 0,
                "last_success_ts": None,
                "last_error_ts": None,
                "roles": [],
                "warning": str(exc),
            }
        )


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
        result = check_db_liveness()
        if result.get("status") != "healthy":
            return JsonResponse(
                {
                    "status": "unhealthy",
                    "database": "disconnected",
                    "error": result.get("error", "db check failed"),
                },
                status=503,
            )
        return JsonResponse(
            {
                "status": "healthy",
                "database": "connected",
                "timestamp": __import__("datetime").datetime.now().isoformat(),
                "uptime": "running",
                "cache": "available",
            }
        )
    except (ValueError, TypeError, KeyError) as exc:
        log_view_exception(
            request,
            "observability.views.api_health: unexpected error after check_db_liveness",
            extra={"error": str(exc)},
        )
        return JsonResponse({"status": "error", "error": str(exc)}, status=500)


@require_GET
@observability_auth_required
def api_admin_weather(request):
    """Server-side weather snapshot for admin dashboard widgets (tenant-scoped cache)."""
    payload = _resolve_weather_payload(
        _build_admin_weather_config(request=request),
        scope="admin",
        request=request,
    )
    return JsonResponse(payload)


@require_GET
def api_weather_context(request):
    """Public-safe weather snapshot for shared header/backend widgets. Never raises; returns disabled payload on error."""
    try:
        config = _build_admin_weather_config(request=request)
        payload = _resolve_weather_payload(config, scope="context", request=request)
        return JsonResponse(payload)
    except (
        OSError,
        requests.RequestException,
        ValueError,
        KeyError,
        ImportError,
        AttributeError,
    ) as exc:
        logger.warning("api_weather_context failed: %s", exc, exc_info=True)
        return JsonResponse(
            {
                "status": "disabled",
                "enabled": False,
                "label": "Weather",
                "latitude": 0.0,
                "longitude": 0.0,
                "temperature_unit": "celsius",
                "timezone": "UTC",
                "cached": False,
                "stale": False,
                "weather": None,
            },
            status=200,
        )


@require_POST
@login_required
def api_notifications_mark_all_read(request):
    """Mark all notifications for the current user as read."""
    try:
        from apps.finance.models import Notification

        user = request.user
        # tenant-isolation-allow: scoped-to-recipient-or-creator-current-user
        qs = Notification.objects.filter(Q(recipient=user) | Q(created_by=user)).filter(
            is_read=False
        )
        updated = qs.update(is_read=True)
        return JsonResponse(
            {
                "status": "success",
                "message": "All notifications marked as read",
                "count": updated,
            }
        )
    except (IntegrityError, ValidationError, DatabaseError) as exc:
        log_view_exception(
            request,
            "observability.views.api_notifications_mark_all_read: update failed",
            extra={"error": str(exc)},
        )
        return JsonResponse({"status": "error", "error": str(exc)}, status=500)


@require_GET
@login_required
def api_notifications(request):
    """API endpoint to fetch recent notifications.

    Returns a list of recent system notifications and alerts.
    """
    try:
        from apps.finance.models import Notification

        user = request.user
        # tenant-isolation-allow: scoped-to-recipient-or-creator-current-user
        notifications_qs = Notification.objects.filter(
            Q(recipient=user) | Q(created_by=user)
        ).order_by("-created_at")[:50]
        mapped = []
        for notif in notifications_qs:
            notif_type = "info"
            if notif.severity == Notification.Severity.ALERT:
                notif_type = "alert"
            elif notif.severity == Notification.Severity.WARNING:
                notif_type = "warning"

            mapped.append(
                {
                    "id": notif.id,
                    "title": notif.title,
                    "message": notif.message,
                    "type": notif_type,
                    "category": notif.severity,
                    "is_read": notif.is_read,
                    "created_at": notif.created_at.isoformat(),
                    "timestamp": notif.created_at.isoformat(),
                    "link": notif.link,
                }
            )

        return JsonResponse(
            {"status": "success", "notifications": mapped, "count": len(mapped)}
        )
    except (IntegrityError, ValidationError, DatabaseError) as exc:
        log_view_exception(
            request,
            "observability.views.api_notifications: query failed",
            extra={"error": str(exc)},
        )
        return JsonResponse({"status": "error", "error": str(exc)}, status=500)


@require_GET
@observability_auth_required
def api_activities(request):
    """API endpoint to fetch recent activities/audit logs.

    Returns a list of recent system activities, admin actions, and student changes.
    Supports filtering by type and pagination.
    """
    try:
        from django.contrib.admin.models import LogEntry

        page = int(request.GET.get("page", 1))
        per_page = settings.DEFAULT_WIDGET_PAGE_SIZE

        logs = LogEntry.objects.select_related("user", "content_type").order_by(
            "-action_time"
        )
        total = logs.count()
        logs = logs[(page - 1) * per_page : page * per_page]

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

            activities.append(
                {
                    "id": entry.id,
                    "type": action_type,
                    "title": entry.object_repr,
                    "description": entry.get_change_message() or action_type.title(),
                    "timestamp": entry.action_time.isoformat(),
                    "user": getattr(entry.user, "username", None),
                }
            )

        return JsonResponse(
            {
                "status": "success",
                "activities": activities,
                "count": len(activities),
                "total": total,
                "page": page,
            }
        )
    except (DatabaseError, ValueError, TypeError) as exc:
        log_view_exception(
            request,
            "observability.views.api_activities: LogEntry query failed",
            extra={"error": str(exc)},
        )
        return JsonResponse({"status": "error", "error": str(exc)}, status=500)


@require_GET
@observability_auth_required
def api_dashboard_charts(request):
    """API endpoint for dashboard chart data.

    Returns data for enrollment trends, fee collection, performance analytics, etc.
    """
    try:
        from apps.people.models import TeacherAttendance
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
            "datasets": [
                {
                    "label": "Active students",
                    "data": enrollment_data,
                    "borderColor": "#ff6a88",
                    "backgroundColor": "rgba(255, 106, 136, 0.1)",
                    "tension": 0.4,
                    "fill": True,
                    "pointRadius": 4,
                    "pointHoverRadius": 6,
                }
            ],
        }

        # Fee collection
        invoiced = (
            Invoice.objects.exclude(status=Invoice.Status.VOID)
            .aggregate(total=Sum("total_amount"))
            .get("total")
            or 0
        )
        paid = (
            # tenant-isolation-allow: control-plane finance aggregate across tenants (reviewed 2026-05-14)
            Payment.objects.filter(status="completed")
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )
        overdue_amount = (
            # tenant-isolation-allow: control-plane finance aggregate across tenants (reviewed 2026-05-14)
            Invoice.objects.filter(status=Invoice.Status.OVERDUE)
            .aggregate(total=Sum("balance_amount"))
            .get("total")
            or 0
        )
        fee_collection = {
            "labels": ["Paid", "Pending", "Overdue"],
            "datasets": [
                {
                    "data": [
                        float(paid),
                        float(max(invoiced - paid, 0)),
                        float(overdue_amount or 0),
                    ],
                    "backgroundColor": ["#2dd4bf", "#9b6bff", "#ff6a88"],
                }
            ],
        }

        # Performance by subject (exam score average)
        subject_scores = (
            Evaluation.objects.exclude(exam_score__isnull=True)
            .values("subject_assignment__subject__name")
            .annotate(avg=Avg("exam_score"))
            .order_by("-avg")[:6]
        )
        perf_labels = [
            row["subject_assignment__subject__name"] or "Subject"
            for row in subject_scores
        ]
        perf_data = [round(float(row["avg"]), 1) for row in subject_scores]
        performance = {
            "labels": perf_labels,
            "datasets": [
                {
                    "label": "Average Grade",
                    "data": perf_data,
                    "borderColor": "#9b6bff",
                    "backgroundColor": "rgba(155, 107, 255, 0.1)",
                    "fill": True,
                }
            ],
        }

        # Attendance snapshot for the past 7 days
        today = timezone.localdate()
        window = TeacherAttendance.objects.filter(
            date__range=(today - __import__("datetime").timedelta(days=6), today)
        )
        attendance_counts = {
            "Present": window.filter(status=TeacherAttendance.Status.PRESENT).count(),
            "Absent": window.filter(status=TeacherAttendance.Status.ABSENT).count(),
            "Late": window.filter(status=TeacherAttendance.Status.LATE).count(),
            "On leave": window.filter(status=TeacherAttendance.Status.ON_LEAVE).count(),
        }
        attendance = {
            "labels": list(attendance_counts.keys()),
            "datasets": [
                {
                    "data": list(attendance_counts.values()),
                    "backgroundColor": ["#2dd4bf", "#ff6a88", "#9b6bff", "#f59e0b"],
                }
            ],
        }

        return JsonResponse(
            {
                "status": "success",
                "enrollment": enrollment,
                "feeCollection": fee_collection,
                "performance": performance,
                "attendance": attendance,
            }
        )
    except (DatabaseError, ValueError, TypeError, KeyError) as exc:
        log_view_exception(
            request,
            "observability.views.api_dashboard_charts: chart aggregation failed",
            extra={"error": str(exc)},
        )
        return JsonResponse({"status": "error", "error": str(exc)}, status=500)


def _region_for_school(school) -> tuple[str, str]:
    region_code = str(getattr(school, "default_region_id", "") or "UNASSIGNED")
    region_name = (
        str(
            getattr(getattr(school, "default_region", None), "name", "") or "Unassigned"
        )
        if region_code == "UNASSIGNED"
        else str(
            getattr(getattr(school, "default_region", None), "name", "") or region_code
        )
    )
    return region_code, region_name


def _get_region_bucket(
    region_metrics: dict[str, dict], region_code: str, region_name: str
) -> dict:
    bucket = region_metrics.get(region_code)
    if bucket is None:
        bucket = {
            "region_code": region_code,
            "region_name": region_name,
            "active_schools": 0,
            "webhook_total": 0,
            "webhook_delivered": 0,
            "webhook_dead_letter": 0,
            "webhook_inflight": 0,
            "delivery_latencies_ms": [],
            "delivery_latency_breaches": 0,
            "sync_conflicts_total_window": 0,
            "sync_conflicts_resolved_window": 0,
            "sync_conflicts_pending": 0,
        }
        region_metrics[region_code] = bucket
    return bucket


def _record_webhook_delivery(
    bucket: dict,
    *,
    status: str,
    start_at,
    end_at,
    webhook_latency_target_ms: float,
    delivered_states: set[str],
    dead_states: set[str],
    inflight_states: set[str],
):
    normalized_status = str(status or "")
    bucket["webhook_total"] += 1

    if normalized_status in delivered_states:
        bucket["webhook_delivered"] += 1
    elif normalized_status in dead_states:
        bucket["webhook_dead_letter"] += 1
    elif normalized_status in inflight_states:
        bucket["webhook_inflight"] += 1

    if (
        normalized_status in delivered_states
        and start_at
        and end_at
        and end_at >= start_at
    ):
        latency_ms = (end_at - start_at).total_seconds() * 1000.0
        bucket["delivery_latencies_ms"].append(latency_ms)
        if latency_ms > webhook_latency_target_ms:
            bucket["delivery_latency_breaches"] += 1


def _webhook_stack_summary() -> dict:
    from apps.events.legacy_bridge import legacy_webhook_sync_snapshot

    return legacy_webhook_sync_snapshot()


def _platform_incident_payload(incident) -> dict:
    return {
        "id": str(incident.id),
        "title": incident.title,
        "incident_type": incident.incident_type,
        "severity": incident.severity,
        "status": incident.status,
        "summary": incident.summary,
        "source_system": incident.source_system,
        "affected_school": getattr(
            getattr(incident, "affected_school", None), "name", None
        ),
        "affected_schema_name": incident.affected_schema_name,
        "detected_at": incident.detected_at.isoformat()
        if incident.detected_at
        else None,
        "acknowledged_at": incident.acknowledged_at.isoformat()
        if incident.acknowledged_at
        else None,
        "resolved_at": incident.resolved_at.isoformat()
        if incident.resolved_at
        else None,
        "created_by": getattr(getattr(incident, "created_by", None), "username", None),
        "acknowledged_by": getattr(
            getattr(incident, "acknowledged_by", None), "username", None
        ),
        "resolved_by": getattr(
            getattr(incident, "resolved_by", None), "username", None
        ),
        "details": incident.details or {},
        "updates_count": incident.updates.count(),
        "has_postmortem": _incident_has_postmortem(incident),
    }


def _incident_has_postmortem(incident) -> bool:
    from apps.observability.models_incident_timeline import incident_has_postmortem

    return incident_has_postmortem(incident)


@require_GET
@observability_auth_required
def platform_incidents_console(request):
    from apps.observability.models import PlatformIncident

    incidents = list(
        PlatformIncident.objects.select_related(
            "affected_school",
            "created_by",
            "acknowledged_by",
            "resolved_by",
        )[:50]
    )
    # Postmortem chip data: one query, then attribute for the template.
    from apps.observability.models_incident_timeline import IncidentUpdate

    postmortem_ids = set(
        IncidentUpdate.objects.filter(
            incident__in=[i.pk for i in incidents],
            kind=IncidentUpdate.Kind.POSTMORTEM,
        ).values_list("incident_id", flat=True)
    )
    for incident in incidents:
        incident.has_postmortem = incident.pk in postmortem_ids
    incident_counts = {
        row["status"]: row["total"]
        for row in PlatformIncident.objects.values("status").annotate(total=Count("id"))
    }
    context = {
        "incidents": incidents,
        "incident_counts": incident_counts,
        "webhook_stack": _webhook_stack_summary(),
    }
    return render(request, "observability/platform_incidents.html", context)


@require_GET
@observability_auth_required
def api_platform_incidents(request):
    from apps.observability.models import PlatformIncident

    status_filter = str(request.GET.get("status") or "").strip().lower()
    severity_filter = str(request.GET.get("severity") or "").strip().lower()
    try:
        limit = max(1, min(int(request.GET.get("limit", 50)), 200))
    except (TypeError, ValueError):
        limit = 50

    incidents = PlatformIncident.objects.select_related(
        "affected_school",
        "created_by",
        "acknowledged_by",
        "resolved_by",
    )
    if status_filter:
        incidents = incidents.filter(status=status_filter)
    if severity_filter:
        incidents = incidents.filter(severity=severity_filter)

    counts = {
        row["status"]: row["total"]
        for row in PlatformIncident.objects.values("status").annotate(total=Count("id"))
    }

    return JsonResponse(
        {
            "status": "success",
            "counts": counts,
            "incidents": [
                _platform_incident_payload(incident) for incident in incidents[:limit]
            ],
            "webhook_stack": _webhook_stack_summary(),
        }
    )


@require_POST
@observability_auth_required
def api_platform_incident_status(request, incident_id):
    from apps.observability.models import PlatformIncident

    try:
        incident = PlatformIncident.objects.select_related(
            "affected_school",
            "created_by",
            "acknowledged_by",
            "resolved_by",
        ).get(pk=incident_id)
    except PlatformIncident.DoesNotExist:
        return JsonResponse(
            {"status": "error", "error": "Incident not found."}, status=404
        )

    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}

    action = (
        str(payload.get("action") or request.POST.get("action") or "").strip().lower()
    )
    now = timezone.now()
    user = request.user if getattr(request.user, "is_authenticated", False) else None
    update_fields: list[str] = []

    if action == "acknowledge":
        if incident.status == PlatformIncident.Status.OPEN:
            incident.status = PlatformIncident.Status.ACKNOWLEDGED
            update_fields.append("status")
        if incident.acknowledged_at is None:
            incident.acknowledged_at = now
            update_fields.append("acknowledged_at")
        if user is not None and incident.acknowledged_by_id is None:
            incident.acknowledged_by = user
            update_fields.append("acknowledged_by")
    elif action == "mitigate":
        if incident.status != PlatformIncident.Status.MITIGATED:
            incident.status = PlatformIncident.Status.MITIGATED
            update_fields.append("status")
        if incident.acknowledged_at is None:
            incident.acknowledged_at = now
            update_fields.append("acknowledged_at")
        if user is not None and incident.acknowledged_by_id is None:
            incident.acknowledged_by = user
            update_fields.append("acknowledged_by")
    elif action == "resolve":
        if incident.status != PlatformIncident.Status.RESOLVED:
            incident.status = PlatformIncident.Status.RESOLVED
            update_fields.append("status")
        if incident.acknowledged_at is None:
            incident.acknowledged_at = now
            update_fields.append("acknowledged_at")
        if user is not None and incident.acknowledged_by_id is None:
            incident.acknowledged_by = user
            update_fields.append("acknowledged_by")
        incident.resolved_at = now
        incident.resolved_by = user
        update_fields.extend(["resolved_at", "resolved_by"])
    else:
        return JsonResponse(
            {"status": "error", "error": "Unsupported incident action."}, status=400
        )

    if update_fields:
        incident.save(update_fields=list(dict.fromkeys(update_fields + ["updated_at"])))
        # Timeline of record: every operator transition leaves a trail entry
        # (best-effort — a timeline failure never blocks incident handling).
        from apps.observability.models_incident_timeline import (
            IncidentUpdate,
            record_incident_update,
        )

        record_incident_update(
            incident,
            kind=IncidentUpdate.Kind.STATUS_CHANGE,
            body=f"Status → {incident.status} ({action})",
            user=user,
        )

    return JsonResponse(
        {"status": "success", "incident": _platform_incident_payload(incident)}
    )


@require_GET
@observability_auth_required
def api_platform_incident_timeline(request, incident_id):
    """Timeline of record for one incident (newest first)."""
    from apps.observability.models import PlatformIncident

    try:
        incident = PlatformIncident.objects.get(pk=incident_id)
    except PlatformIncident.DoesNotExist:
        return JsonResponse(
            {"status": "error", "error": "Incident not found."}, status=404
        )
    entries = [
        {
            "id": str(u.id),
            "kind": u.kind,
            "body": u.body,
            "created_by": getattr(u.created_by, "username", None),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in incident.updates.select_related("created_by")[:200]
    ]
    return JsonResponse(
        {
            "status": "success",
            "incident": _platform_incident_payload(incident),
            "timeline": entries,
        }
    )


@require_POST
@observability_auth_required
def api_platform_incident_update_add(request, incident_id):
    """Append an update / action item / postmortem to an incident.

    A ``postmortem`` entry is the artifact that closes the loop from
    "resolved" to "learned" — the console flags resolved incidents that
    still lack one.
    """
    from apps.observability.models import PlatformIncident
    from apps.observability.models_incident_timeline import IncidentUpdate

    try:
        incident = PlatformIncident.objects.get(pk=incident_id)
    except PlatformIncident.DoesNotExist:
        return JsonResponse(
            {"status": "error", "error": "Incident not found."}, status=404
        )
    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
    kind = str(payload.get("kind") or request.POST.get("kind") or "update").strip().lower()
    body = str(payload.get("body") or request.POST.get("body") or "").strip()
    valid_kinds = {choice.value for choice in IncidentUpdate.Kind}
    if kind not in valid_kinds:
        return JsonResponse(
            {"status": "error", "error": f"Unsupported kind: {kind}"}, status=400
        )
    if not body:
        return JsonResponse(
            {"status": "error", "error": "Update body required."}, status=400
        )
    user = request.user if getattr(request.user, "is_authenticated", False) else None
    entry = IncidentUpdate.objects.create(
        incident=incident,
        kind=kind,
        body=body[:4000],  # magic-number-allow: incident-note-body-cap-chars
        created_by=user,
    )
    return JsonResponse(
        {
            "status": "success",
            "entry": {
                "id": str(entry.id),
                "kind": entry.kind,
                "created_at": entry.created_at.isoformat(),
            },
            "incident": _platform_incident_payload(incident),
        }
    )


@require_GET
@observability_auth_required
def api_operational_slo_dashboard(request):
    """Regional go-live SLO dashboard (SEC-608)."""
    from apps.events.models import WebhookDelivery as CanonicalWebhookDelivery
    from apps.schools.models import School
    from apps.siteconfig.models import (
        SyncConflict,
        WebhookDelivery as LegacyWebhookDelivery,
    )

    try:
        raw_hours = int(request.GET.get("hours", 24))
    except (TypeError, ValueError):
        raw_hours = 24
    window_hours = max(1, min(raw_hours, 24 * 30))

    now = timezone.now()
    window_start = now - timedelta(hours=window_hours)
    webhook_success_target = float(
        getattr(settings, "WEBHOOK_SUCCESS_SLO_PERCENT", 99.0)
    )
    webhook_latency_target_ms = float(
        getattr(settings, "WEBHOOK_P95_LATENCY_SLO_MS", 15000.0)
    )
    pending_conflict_target = int(
        getattr(settings, "SYNC_CONFLICT_PENDING_SLO_MAX", 10)
    )

    region_metrics: dict[str, dict] = {}
    schools = list(
        School.objects.filter(is_active=True)
        .select_related("default_region")
        .only("id", "default_region_id", "default_region__name")
    )
    school_region_lookup: dict[str, tuple[str, str]] = {}
    for school in schools:
        region_code, region_name = _region_for_school(school)
        school_region_lookup[str(school.id)] = (region_code, region_name)
        _get_region_bucket(region_metrics, region_code, region_name)[
            "active_schools"
        ] += 1

    legacy_deliveries = (
        LegacyWebhookDelivery.objects.filter(
            created_at__gte=window_start, subscription__is_active=True
        )
        .select_related("subscription__school__default_region")
        .only(
            "status",
            "created_at",
            "delivered_at",
            "last_attempt_at",
            "subscription__school__default_region_id",
            "subscription__school__default_region__name",
        )
    )
    for delivery in legacy_deliveries:
        school = getattr(getattr(delivery, "subscription", None), "school", None)
        region_code, region_name = _region_for_school(school)
        bucket = _get_region_bucket(region_metrics, region_code, region_name)
        _record_webhook_delivery(
            bucket,
            status=getattr(delivery, "status", ""),
            start_at=getattr(delivery, "created_at", None),
            end_at=getattr(delivery, "delivered_at", None)
            or getattr(delivery, "last_attempt_at", None),
            webhook_latency_target_ms=webhook_latency_target_ms,
            delivered_states={"DELIVERED"},
            dead_states={"DEAD_LETTER"},
            inflight_states={"PENDING", "RETRYING"},
        )

    canonical_deliveries = (
        CanonicalWebhookDelivery.objects.filter(created_at__gte=window_start)
        .select_related("subscription", "domain_event")
        .only(
            "status",
            "created_at",
            "delivered_at",
            "attempted_at",
            "subscription__school_id",
            "domain_event__school_id",
        )
    )
    for delivery in canonical_deliveries:
        subscription = getattr(delivery, "subscription", None)
        domain_event = getattr(delivery, "domain_event", None)
        school_id = getattr(subscription, "school_id", None) or getattr(
            domain_event, "school_id", None
        )
        region_code, region_name = school_region_lookup.get(
            str(school_id), ("UNASSIGNED", "Unassigned")
        )
        bucket = _get_region_bucket(region_metrics, region_code, region_name)
        _record_webhook_delivery(
            bucket,
            status=getattr(delivery, "status", ""),
            start_at=getattr(delivery, "created_at", None),
            end_at=getattr(delivery, "delivered_at", None)
            or getattr(delivery, "attempted_at", None),
            webhook_latency_target_ms=webhook_latency_target_ms,
            delivered_states={CanonicalWebhookDelivery.Status.DELIVERED},
            dead_states={CanonicalWebhookDelivery.Status.FAILED},
            inflight_states={
                CanonicalWebhookDelivery.Status.PENDING,
                CanonicalWebhookDelivery.Status.SENT,
            },
        )

    conflict_window = (
        # tenant-isolation-allow: SLO dashboard regional rollup across tenants (reviewed 2026-05-14)
        SyncConflict.objects.filter(created_at__gte=window_start)
        .select_related("school__default_region")
        .only("status", "school__default_region_id", "school__default_region__name")
    )
    for conflict in conflict_window:
        school = getattr(conflict, "school", None)
        region_code, region_name = _region_for_school(school)
        bucket = _get_region_bucket(region_metrics, region_code, region_name)
        bucket["sync_conflicts_total_window"] += 1
        if str(getattr(conflict, "status", "")) != "PENDING":
            bucket["sync_conflicts_resolved_window"] += 1

    pending_conflicts = (
        # tenant-isolation-allow: SLO dashboard regional rollup across tenants (reviewed 2026-05-14)
        SyncConflict.objects.filter(status=SyncConflict.Status.PENDING)
        .select_related("school__default_region")
        .only("school__default_region_id", "school__default_region__name")
    )
    for conflict in pending_conflicts:
        school = getattr(conflict, "school", None)
        region_code, region_name = _region_for_school(school)
        bucket = _get_region_bucket(region_metrics, region_code, region_name)
        bucket["sync_conflicts_pending"] += 1

    region_rows: list[dict] = []
    summary = {
        "regions": 0,
        "healthy_regions": 0,
        "warning_regions": 0,
        "critical_regions": 0,
        "active_schools": len(schools),
    }

    for region_code in sorted(region_metrics.keys()):
        bucket = region_metrics[region_code]
        webhook_total = int(bucket["webhook_total"])
        webhook_delivered = int(bucket["webhook_delivered"])
        webhook_success_rate = _percent(
            webhook_delivered, webhook_total, fallback=100.0
        )
        webhook_error_rate = round(max(0.0, 100.0 - webhook_success_rate), 2)
        allowed_error_rate = round(max(0.0, 100.0 - webhook_success_target), 2)
        error_budget_remaining = round(
            max(0.0, allowed_error_rate - webhook_error_rate), 2
        )
        error_budget_burn = round(max(0.0, webhook_error_rate - allowed_error_rate), 2)

        latencies = [float(value) for value in bucket["delivery_latencies_ms"]]
        p95_latency_ms = _p95(latencies)
        latency_breach_rate = _percent(
            int(bucket["delivery_latency_breaches"]),
            len(latencies),
            fallback=0.0,
        )

        sync_total_window = int(bucket["sync_conflicts_total_window"])
        sync_resolved_window = int(bucket["sync_conflicts_resolved_window"])
        sync_resolution_rate = _percent(
            sync_resolved_window, sync_total_window, fallback=100.0
        )
        sync_pending = int(bucket["sync_conflicts_pending"])

        status = "healthy"
        if webhook_success_rate < max(
            0.0, webhook_success_target - 2.0
        ) or sync_pending > (pending_conflict_target * 2):
            status = "critical"
        elif (
            webhook_success_rate < webhook_success_target
            or latency_breach_rate > 5.0
            or sync_pending > pending_conflict_target
        ):
            status = "warning"

        if status == "healthy":
            summary["healthy_regions"] += 1
        elif status == "warning":
            summary["warning_regions"] += 1
        else:
            summary["critical_regions"] += 1

        region_rows.append(
            {
                "region_code": bucket["region_code"],
                "region_name": bucket["region_name"],
                "status": status,
                "active_schools": int(bucket["active_schools"]),
                "webhook": {
                    "total": webhook_total,
                    "delivered": webhook_delivered,
                    "dead_letter": int(bucket["webhook_dead_letter"]),
                    "inflight": int(bucket["webhook_inflight"]),
                    "success_rate_percent": webhook_success_rate,
                    "p95_latency_ms": p95_latency_ms,
                    "latency_breach_rate_percent": latency_breach_rate,
                },
                "error_budget": {
                    "target_success_percent": webhook_success_target,
                    "allowed_error_rate_percent": allowed_error_rate,
                    "actual_error_rate_percent": webhook_error_rate,
                    "remaining_percent": error_budget_remaining,
                    "burn_percent": error_budget_burn,
                },
                "sync_conflicts": {
                    "pending": sync_pending,
                    "pending_target_max": pending_conflict_target,
                    "total_window": sync_total_window,
                    "resolved_window": sync_resolved_window,
                    "resolution_rate_percent": sync_resolution_rate,
                },
            }
        )

    summary["regions"] = len(region_rows)

    data = {
        "generated_at": now.isoformat(),
        "window_hours": window_hours,
        "window_start": window_start.isoformat(),
        "slo_targets": {
            "webhook_success_percent": webhook_success_target,
            "webhook_p95_latency_ms": webhook_latency_target_ms,
            "pending_sync_conflicts_max": pending_conflict_target,
        },
        "summary": summary,
        "regions": region_rows,
        "webhook_stack": _webhook_stack_summary(),
    }
    if request.GET.get("format") == "html" or (
        request.META.get("HTTP_ACCEPT") or ""
    ).strip().split(",")[0].strip().startswith("text/html"):
        try:
            data["dashboard_url"] = reverse("super:dashboard")
        except NoReverseMatch:
            data["dashboard_url"] = "/super/"
        return render(request, "observability/slo_dashboard.html", data)
    return JsonResponse({"status": "success", **data})


# ============================================
# ADMIN DASHBOARD - Backend/System Management
# ============================================


@login_required
@user_passes_test(
    lambda u: u.is_staff or u.is_superuser or getattr(u, "role", None) == "ADMIN"
)
def admin_dashboard(request):
    """Legacy alias for the admin dashboard."""
    return redirect("admin:index")


# C3: Runtime observability — inspect effective runtime (resolver registry + sample runtime)
@login_required
@require_GET
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def runtime_inspect(request):
    """Admin tool: What's driving this? — effective runtime summary, resolver registry, and debug sources (plan C3 / metadata-driven observability)."""
    from apps.platform_runtime.resolver_registry import RESOLVER_ENTRY_POINTS

    rt = getattr(request, "tenant_runtime", None)
    route = getattr(rt, "route", None) if rt else None
    tenant_identity = getattr(rt, "tenant", None) if rt else None
    debug = getattr(rt, "debug", None) if rt else None
    payload = {
        "resolvers": [{"name": n, "location": loc} for n, loc in RESOLVER_ENTRY_POINTS],
        "tenant_runtime_present": rt is not None,
        "surface": getattr(route, "surface", None) if route else None,
        "identity_slug": getattr(tenant_identity, "slug", None)
        if tenant_identity
        else None,
    }
    if debug is not None:
        payload["resolved_sources"] = {
            "runtime_version": getattr(debug, "runtime_version", None),
            "source_blueprint_id": getattr(debug, "source_blueprint_id", None),
            "source_policy_bundle_id": getattr(debug, "source_policy_bundle_id", None),
            "applied_overrides": list(getattr(debug, "applied_overrides", []) or []),
            "compilation_trace": list(getattr(debug, "compilation_trace", []) or []),
            "compilation_timestamp": getattr(debug, "compilation_timestamp", None),
            "warnings": list(getattr(debug, "warnings", []) or []),
        }
    return JsonResponse(payload)


@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def communication_delivery_health(request):
    """Operator diagnostic: notification delivery-channel readiness (LOW-9).

    Surfaces whether email / SMS / browser web push (VAPID) / native push are
    configured on this deployment, plus active subscriber/device counts. Booleans
    and counts ONLY — never any key material. Staff/superuser only. This closes
    the web-push *visibility* gap; delivery itself is already wired into the
    dispatch router (native + web push, each failure-isolated).
    """
    from apps.communication.delivery_health import collect_delivery_health

    return JsonResponse(collect_delivery_health())
