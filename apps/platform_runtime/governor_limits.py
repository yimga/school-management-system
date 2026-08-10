"""
Governor limits for multitenant platform protection (Path-to-10).
Define and expose limits for workflow volume, API throughput, dashboard refresh,
migration concurrency, dynamic field count, and pack complexity.
Enforcement can be phased; inspection always exposes current limits and usage.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.core.cache import cache
from django.db import DatabaseError
from django.utils import timezone

logger = logging.getLogger(__name__)

# Errors that must degrade a single persisted-usage read to 0 rather than blank
# the whole cockpit (missing app, absent table, transient DB/cache fault).
_PERSISTED_USAGE_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    DatabaseError,
    ConnectionError,
    OSError,
)

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


def workflow_run_limit_exceeded(
    tenant_id: Optional[str] = None, school_id: Optional[int] = None
) -> bool:
    """Return True when the tenant has exceeded the daily workflow run cap."""
    if not tenant_id and school_id is not None:
        tenant_id = str(school_id)
    if not tenant_id:
        return False
    try:
        date_str = timezone.now().strftime("%Y-%m-%d")
        key = _tenant_workflow_runs_key(tenant_id, date_str)
        count = int(cache.get(key, 0) or 0)
        return count >= WORKFLOW_RUNS_PER_DAY_PER_TENANT
    except (ValueError, TypeError, AttributeError, ConnectionError, OSError):
        return False


def record_workflow_run(
    tenant_id: Optional[str] = None, school_id: Optional[int] = None
) -> None:
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
    except (ValueError, TypeError, AttributeError, ConnectionError, OSError) as e:
        logger.debug("governor record_workflow_run skip: %s", e)


def record_dashboard_refresh(
    tenant_id: Optional[str] = None, school_id: Optional[int] = None
) -> None:
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
    except (ValueError, TypeError, AttributeError, ConnectionError, OSError) as e:
        logger.debug("governor record_dashboard_refresh skip: %s", e)


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


def _persisted_tenant_usage(school_id: Any) -> Dict[str, int]:
    """Read the three DB/ledger-backed usage counters from their AUTHORITATIVE
    sources rather than a parallel governor cache:

      * ``ai_invocations_today`` -> the billing ``UsageMeter`` daily rollup
        (``apps.billing.models_metering.snapshot``) — the same ledger the
        realtime meter and the AI-token flush task already write to.
      * ``dynamic_field_count`` -> active, tenant-scoped
        ``metadata.DynamicFieldDefinition`` rows.
      * ``active_migrations`` -> in-flight ``migration_cloud.MigrationBundle``
        applies (a bundle sits in ``APPLYING`` for the duration of its tenant
        apply — the best-available concurrency signal; there is no purpose-built
        concurrency counter to read).

    Each source is guarded independently so a missing app/table degrades THAT
    counter to 0 without blanking the cockpit. Returns zeros when the school
    cannot be resolved (e.g. the no-context inspector branches pass no school).
    """
    out = {"active_migrations": 0, "dynamic_field_count": 0, "ai_invocations_today": 0}
    if not school_id:
        return out
    try:
        from apps.schools.models import School

        school = School.objects.filter(pk=school_id).first()
    except _PERSISTED_USAGE_ERRORS as e:
        logger.debug("governor school resolve skip: %s", e)
        return out
    if school is None:
        return out
    try:
        from apps.billing.models_metering import snapshot

        out["ai_invocations_today"] = int(snapshot(school).get("ai_invocations", 0) or 0)
    except _PERSISTED_USAGE_ERRORS as e:
        logger.debug("governor ai_invocations read skip: %s", e)
    try:
        from apps.metadata.models import DynamicFieldDefinition

        out["dynamic_field_count"] = DynamicFieldDefinition.objects.filter(
            school=school, is_active=True
        ).count()
    except _PERSISTED_USAGE_ERRORS as e:
        logger.debug("governor dynamic_field_count read skip: %s", e)
    try:
        from apps.migration_cloud.models import BundleStatus, MigrationBundle

        out["active_migrations"] = MigrationBundle.objects.filter(
            school=school, status=BundleStatus.APPLYING
        ).count()
    except _PERSISTED_USAGE_ERRORS as e:
        logger.debug("governor active_migrations read skip: %s", e)
    return out


def get_governor_usage_for_tenant(
    tenant_id: Optional[str] = None,
    school_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Return current usage vs limits for a tenant. API requests per minute are
    wired to the tenant throttle cache; workflow/dashboard counters to the
    governor cache; and migration / dynamic-field / AI-invocation counters to
    their authoritative DB + billing-ledger sources (see
    ``_persisted_tenant_usage``).
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
        except (ImportError, AttributeError, TypeError, ValueError) as e:
            logger.debug("governor get_tenant_api_request_count skip: %s", e)
    tid = tenant_id or (str(school_id) if school_id else None)
    workflow_runs_today = 0
    dashboard_refreshes_last_hour = 0
    if tid:
        try:
            date_str = timezone.now().strftime("%Y-%m-%d")
            workflow_runs_today = (
                cache.get(_tenant_workflow_runs_key(tid, date_str), 0) or 0
            )
        except (TypeError, AttributeError, ConnectionError, OSError) as e:
            logger.debug("governor workflow_runs_today cache skip: %s", e)
        try:
            hour_str = timezone.now().strftime("%Y-%m-%d-%H")
            dashboard_refreshes_last_hour = (
                cache.get(_tenant_dashboard_refreshes_key(tid, hour_str), 0) or 0
            )
        except (TypeError, AttributeError, ConnectionError, OSError) as e:
            logger.debug("governor dashboard_refreshes cache skip: %s", e)
    persisted = _persisted_tenant_usage(school_id)
    usage = {
        "workflow_runs_today": workflow_runs_today,
        "api_requests_last_minute": api_requests_last_minute,
        "dashboard_refreshes_last_hour": dashboard_refreshes_last_hour,
        "active_migrations": persisted["active_migrations"],
        "dynamic_field_count": persisted["dynamic_field_count"],
        "ai_invocations_today": persisted["ai_invocations_today"],
    }
    status = {
        "workflow_runs_per_day": {
            "limit": limits["workflow_runs_per_day"],
            "used": usage["workflow_runs_today"],
            "enforced": True,
        },
        "api_requests_per_minute": {
            "limit": limits["api_requests_per_minute"],
            "used": usage["api_requests_last_minute"],
            "enforced": True,
        },
        "dashboard_refresh_per_hour": {
            "limit": limits["dashboard_refresh_per_hour"],
            "used": usage["dashboard_refreshes_last_hour"],
            "enforced": False,
        },
        "migration_concurrency": {
            "limit": limits["migration_concurrency"],
            "used": usage["active_migrations"],
            "enforced": False,
        },
        "dynamic_field_count_max": {
            "limit": limits["dynamic_field_count_max"],
            "used": usage["dynamic_field_count"],
            "enforced": False,
        },
        "ai_invocations_per_day": {
            "limit": limits["ai_invocations_per_day"],
            "used": usage["ai_invocations_today"],
            "enforced": False,
        },
    }
    note = (
        "API requests from throttle; workflow/dashboard from governor cache "
        "(record_workflow_run/record_dashboard_refresh); ai_invocations from the "
        "billing UsageMeter daily rollup; dynamic_field_count from active "
        "metadata.DynamicFieldDefinition rows; active_migrations from "
        "migration_cloud bundles in APPLYING."
    )
    return {
        "limits": limits,
        "usage": usage,
        "status": status,
        "tenant_id": tenant_id,
        "school_id": school_id,
        "note": note,
    }
