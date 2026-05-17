"""Small cache-backed throttling helpers for unauthenticated and per-tenant API surfaces."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.db.utils import DatabaseError

logger = logging.getLogger(__name__)

# Plan I: per-tenant API quotas (default requests per window when tenant is set)
API_TENANT_RATE_LIMIT_KEY = "api_tenant"
DEFAULT_TENANT_MAX_PER_MINUTE = getattr(
    settings, "API_TENANT_MAX_REQUESTS_PER_MINUTE", 600
)
DEFAULT_TENANT_WINDOW_SECONDS = 60


def client_ip(request) -> str:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.META.get("REMOTE_ADDR") or "unknown").strip()


def _throttle(key: str, max_count: int, window_seconds: int) -> tuple[bool, int]:
    """Shared fixed-window throttle logic. Returns (allowed, retry_after_seconds)."""
    try:
        if cache.add(key, 1, timeout=window_seconds):
            return True, 0
        try:
            count = int(cache.incr(key))
        except (TypeError, ValueError, AttributeError):
            count = int(cache.get(key, 0) or 0) + 1
            cache.set(key, count, timeout=window_seconds)
        if count > int(max_count):
            return False, int(window_seconds)
        return True, 0
    except (TypeError, ValueError, AttributeError) as e:
        logger.debug("Rate-limit cache unavailable for key=%s: %s", key, e)
        return True, 0


def throttle_ip_request(
    request,
    *,
    scope: str,
    max_count: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """
    Fixed-window per-IP throttling.

    Returns:
      (allowed, retry_after_seconds)
    """
    ip = client_ip(request)
    key = f"rate_limit:{scope}:{ip}"
    return _throttle(key, max_count, window_seconds)


def _check_tenant_quota_limit(
    school, limit_type: str = "api_calls"
) -> tuple[bool, int]:
    """
    If school has TenantQuotaLimit for limit_type, check TenantApiUsage for current period.
    Returns (allowed, retry_after_seconds). Caches result 60s per school to avoid DB on every request.
    """
    if not school or not getattr(school, "pk", None):
        return True, 0
    cache_key = f"quota_check:{school.pk}:{limit_type}"
    cached = cache.get(cache_key)
    if cached is not None:
        if cached is True:
            return True, 0
        if isinstance(cached, dict):
            return cached.get("allowed", True), cached.get("retry", 0)
    try:
        from django.utils import timezone
        from django.db.models import Sum
        from apps.schools.models import TenantQuotaLimit, TenantApiUsage

        limit_row = (
            TenantQuotaLimit.objects.filter(
                school_id=school.pk, limit_type=limit_type, is_active=True
            )
            .values("limit_value", "period_days")
            .first()
        )
        if not limit_row:
            cache.set(cache_key, True, timeout=60)
            return True, 0
        limit_value = int(limit_row["limit_value"])
        period_days = limit_row.get("period_days")
        today = timezone.now().date()
        if period_days:
            from datetime import timedelta

            period_start = today - timedelta(days=period_days)
            usage = TenantApiUsage.objects.filter(
                school_id=school.pk,
                limit_type=limit_type,
                period_date__gte=period_start,
                period_date__lte=today,
            ).aggregate(total=Sum("request_count"))
        else:
            usage = TenantApiUsage.objects.filter(
                school_id=school.pk,
                limit_type=limit_type,
                period_date=today,
            ).aggregate(total=Sum("request_count"))
        total = int(usage.get("total") or 0)
        allowed = total < limit_value
        retry = 60 if period_days else 60
        cache.set(cache_key, {"allowed": allowed, "retry": retry}, timeout=60)
        return allowed, retry if not allowed else 0
    except (ImportError, AttributeError, TypeError, ValueError, DatabaseError) as e:
        logger.debug("_check_tenant_quota_limit failed: %s", e, exc_info=True)
        return True, 0


def _get_apicenter_quota_for_school(
    school, quota_type: str = "requests_per_minute"
) -> tuple[int | None, int | None]:
    """
    8.1: If APIQuota exists for this school (or platform-wide) for quota_type, return (limit_value, window_seconds).
    Otherwise (None, None).
    """
    try:
        from apps.apicenter.models import APIQuota

        if school and getattr(school, "pk", None):
            row = (
                APIQuota.objects.filter(
                    quota_type=quota_type, school_id=school.pk
                ).first()
                or APIQuota.objects.filter(
                    quota_type=quota_type, school__isnull=True
                ).first()
            )
        else:
            row = APIQuota.objects.filter(
                quota_type=quota_type, school__isnull=True
            ).first()
        if not row:
            return None, None
        limit = int(row.limit_value) if row.limit_value else None
        if quota_type == "requests_per_minute":
            window = (int(row.period_minutes or 1) * 60) if limit else None
        elif quota_type == "requests_per_day":
            window = 86400
        else:
            window = 60
        return limit, window
    except (ImportError, AttributeError, TypeError, ValueError, DatabaseError) as e:
        logger.debug("_get_apicenter_quota_for_school failed: %s", e, exc_info=True)
        return None, None


def throttle_tenant_request(
    request,
    *,
    scope: str = API_TENANT_RATE_LIMIT_KEY,
    max_count: int | None = None,
    window_seconds: int | None = None,
) -> tuple[bool, int]:
    """
    Plan I: Per-tenant API rate limit. Use when request.school is set (e.g. after TenantMiddleware).
    Also enforces TenantQuotaLimit (e.g. api_calls per month) when set for the school.
    8.1: When APIQuota (requests_per_minute) exists for the school, uses that limit; otherwise settings default.
    Returns (allowed, retry_after_seconds).
    """
    school = getattr(request, "school", None)
    if not school:
        return True, 0
    tenant_id = str(getattr(school, "pk", ""))
    if not tenant_id:
        return True, 0
    # Optional: enforce stored quota limit (api_calls or api_calls_per_month)
    quota_allowed, quota_retry = _check_tenant_quota_limit(
        school, limit_type="api_calls"
    )
    if not quota_allowed:
        return False, quota_retry
    # 8.1: Prefer APIQuota (apicenter) when set for this school
    apicenter_limit, apicenter_window = _get_apicenter_quota_for_school(
        school, "requests_per_minute"
    )
    if apicenter_limit is not None and apicenter_window is not None:
        max_count = apicenter_limit
        window_seconds = apicenter_window
    else:
        max_count = (
            max_count if max_count is not None else DEFAULT_TENANT_MAX_PER_MINUTE
        )
        window_seconds = (
            window_seconds
            if window_seconds is not None
            else DEFAULT_TENANT_WINDOW_SECONDS
        )
    key = f"rate_limit:{scope}:tenant:{tenant_id}"
    allowed, retry = _throttle(key, max_count, window_seconds)
    if allowed:
        record_tenant_api_usage(school)
    return allowed, retry


def get_tenant_api_request_count(tenant_id: str | int) -> int:
    """
    Return current per-minute request count for the tenant (from throttle cache).
    Used by governor limits / runtime inspector. Returns 0 if no key or cache unavailable.
    """
    if not tenant_id:
        return 0
    key = f"rate_limit:{API_TENANT_RATE_LIMIT_KEY}:tenant:{tenant_id}"
    try:
        val = cache.get(key)
        return int(val) if val is not None else 0
    except (TypeError, ValueError, AttributeError):
        return 0


def record_tenant_api_usage(school, limit_type: str = "api_calls"):
    """
    Record one API request for the tenant (for billing/usage dashboard).
    Throttled to ~1 write per 6 seconds per school to avoid DB load.
    """
    if not school or not getattr(school, "pk", None):
        return
    try:
        cache_key = f"usage_record:{school.pk}:{limit_type}"
        if cache.get(cache_key):
            return
        cache.set(cache_key, 1, timeout=6)
        from django.utils import timezone
        from django.db.models import F
        from apps.schools.models import TenantApiUsage

        today = timezone.now().date()
        obj, _ = TenantApiUsage.objects.get_or_create(
            school_id=school.pk,
            period_date=today,
            limit_type=limit_type,
            defaults={"request_count": 0},
        )
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        TenantApiUsage.objects.filter(pk=obj.pk).update(
            request_count=F("request_count") + 1
        )
    except (ImportError, AttributeError, TypeError, ValueError, DatabaseError) as e:
        logger.debug("record_tenant_api_usage failed: %s", e, exc_info=True)
