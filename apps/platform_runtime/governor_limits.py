"""
Governor limits for multitenant platform protection (Path-to-10).
Define and expose limits for workflow volume, API throughput, dashboard refresh,
migration concurrency, dynamic field count, and pack complexity.
Enforcement can be phased; inspection always exposes current limits and usage.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from django.core.cache import cache
from django.utils import timezone

# Limit definitions (platform-wide; tenant overrides via plan/entitlement later).
WORKFLOW_RUNS_PER_DAY_PER_TENANT = 10_000
API_REQUESTS_PER_MINUTE_PER_TENANT = 600
DASHBOARD_REFRESH_PER_HOUR_PER_TENANT = 120
MIGRATION_CONCURRENCY_PER_TENANT = 2
DYNAMIC_FIELD_COUNT_MAX_PER_TENANT = 500
PACK_COMPLEXITY_MAX_WORKFLOWS = 50
PACK_COMPLEXITY_MAX_DASHBOARD_WIDGETS = 80
AI_INVOCATIONS_PER_DAY_PER_TENANT = 1_000

LIMIT_KEYS = (
    "workflow_runs_per_day",
    "api_requests_per_minute",
    "dashboard_refresh_per_hour",
    "migration_concurrency",
    "dynamic_field_count_max",
    "pack_complexity_max_workflows",
    "pack_complexity_max_dashboard_widgets",
    "ai_invocations_per_day",
)


def _tenant_workflow_runs_key(tenant_id: str, date_str: str) -> str:
    return f"platform_runtime:governor:workflow_runs:{tenant_id}:{date_str}"


def _tenant_dashboard_refreshes_key(tenant_id: str, hour_str: str) -> str:
    return f"platform_runtime:governor:dashboard_refreshes:{tenant_id}:{hour_str}"


def record_workflow_run(tenant_id: Optional[str] = None, school_id: Optional[int] = None) -> None:
    """Increment workflow run count for governor limits. Call from workflow_engine.run_workflow."""
    if not tenant_id and school_id is not None:
        tenant_id = str(school_id)
    if not tenant_id:
        return
    try:
        date_str = timezone.now().strftime("%Y-%m-%d")
        key = _tenant_workflow_runs_key(tenant_id, date_str)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=86400 * 2)  # 2 days TTL
    except Exception:
        pass


def record_dashboard_refresh(tenant_id: Optional[str] = None, school_id: Optional[int] = None) -> None:
    """Increment dashboard refresh count for governor limits. Call from dashboard refresh endpoint or view."""
    if not tenant_id and school_id is not None:
        tenant_id = str(school_id)
    if not tenant_id:
        return
    try:
        hour_str = timezone.now().strftime("%Y-%m-%d-%H")
        key = _tenant_dashboard_refreshes_key(tenant_id, hour_str)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=7200)  # 2 hours
    except Exception:
        pass


def get_platform_governor_limits() -> Dict[str, Any]:
    """
    Return current platform governor limit definitions for operator visibility.
    Used by runtime inspector and control plane. Values are defaults; plan/entitlement
    can override per tenant (future).
    """
    return {
        "workflow_runs_per_day": WORKFLOW_RUNS_PER_DAY_PER_TENANT,
        "api_requests_per_minute": API_REQUESTS_PER_MINUTE_PER_TENANT,
        "dashboard_refresh_per_hour": DASHBOARD_REFRESH_PER_HOUR_PER_TENANT,
        "migration_concurrency": MIGRATION_CONCURRENCY_PER_TENANT,
        "dynamic_field_count_max": DYNAMIC_FIELD_COUNT_MAX_PER_TENANT,
        "pack_complexity_max_workflows": PACK_COMPLEXITY_MAX_WORKFLOWS,
        "pack_complexity_max_dashboard_widgets": PACK_COMPLEXITY_MAX_DASHBOARD_WIDGETS,
        "ai_invocations_per_day": AI_INVOCATIONS_PER_DAY_PER_TENANT,
    }


def get_governor_usage_for_tenant(
    tenant_id: Optional[str] = None,
    school_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Return current usage vs limits for a tenant. API requests per minute are
    wired to the tenant throttle cache; other counters remain placeholder until instrumented.
    """
    limits = get_platform_governor_limits()
    # API requests: read from rate_limit throttle cache when tenant/school is known.
    api_requests_last_minute = 0
    if tenant_id or school_id:
        try:
            from apps.api.rate_limit import get_tenant_api_request_count
            tid = tenant_id or (str(school_id) if school_id else None)
            if tid:
                api_requests_last_minute = get_tenant_api_request_count(tid)
        except Exception:
            pass
    tid = tenant_id or (str(school_id) if school_id else None)
    workflow_runs_today = 0
    dashboard_refreshes_last_hour = 0
    if tid:
        try:
            date_str = timezone.now().strftime("%Y-%m-%d")
            workflow_runs_today = cache.get(_tenant_workflow_runs_key(tid, date_str), 0) or 0
        except Exception:
            pass
        try:
            hour_str = timezone.now().strftime("%Y-%m-%d-%H")
            dashboard_refreshes_last_hour = cache.get(_tenant_dashboard_refreshes_key(tid, hour_str), 0) or 0
        except Exception:
            pass
    usage = {
        "workflow_runs_today": workflow_runs_today,
        "api_requests_last_minute": api_requests_last_minute,
        "dashboard_refreshes_last_hour": dashboard_refreshes_last_hour,
        "active_migrations": 0,
        "dynamic_field_count": 0,
        "ai_invocations_today": 0,
    }
    status = {
        "workflow_runs_per_day": {"limit": limits["workflow_runs_per_day"], "used": usage["workflow_runs_today"], "enforced": False},
        "api_requests_per_minute": {"limit": limits["api_requests_per_minute"], "used": usage["api_requests_last_minute"], "enforced": True},
        "dashboard_refresh_per_hour": {"limit": limits["dashboard_refresh_per_hour"], "used": usage["dashboard_refreshes_last_hour"], "enforced": False},
        "migration_concurrency": {"limit": limits["migration_concurrency"], "used": usage["active_migrations"], "enforced": False},
        "dynamic_field_count_max": {"limit": limits["dynamic_field_count_max"], "used": usage["dynamic_field_count"], "enforced": False},
        "ai_invocations_per_day": {"limit": limits["ai_invocations_per_day"], "used": usage["ai_invocations_today"], "enforced": False},
    }
    note = "API requests from throttle; workflow/dashboard from governor cache (record_workflow_run/record_dashboard_refresh)."
    return {
        "limits": limits,
        "usage": usage,
        "status": status,
        "tenant_id": tenant_id,
        "school_id": school_id,
        "note": note,
    }
