"""
Short-TTL caches for the manager super dashboard (Render hot path).

POST /super/ and slow GET /super/ were starving single-worker Gunicorn health
checks. These caches trim repeated platform-wide aggregates on every refresh.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache
from django.db import DatabaseError

from apps.platform_runtime.transient_db import is_transient_database_error

logger = logging.getLogger(__name__)

_EMPTY_INCIDENT_BUNDLE: dict[str, Any] = {
    "platform_incidents": [],
    "incident_counts": {},
    "critical_incident_count": 0,
}

from apps.registries.models import (
    CountryRegistry,
    EducationLevelRegistry,
    EducationSystemTypeRegistry,
    SubdivisionRegistry,
)

from .super_dashboard_registry import FleetRegistryMetrics, compute_fleet_registry_metrics
from .super_views_command_center_data import build_command_center_data as _build_command_center_data

_COMMAND_CENTER_KEY = "rmc:super_dashboard:command_center:v1"
_PLATFORM_HEALTH_KEY = "rmc:super_dashboard:platform_health:v1"
_HEALTH_TABLES_KEY = "rmc:super_dashboard:health_tables:v1"
_REGISTRY_COUNTS_KEY = "rmc:super_dashboard:registry_counts:v1"
_INCIDENT_BUNDLE_KEY = "rmc:super_dashboard:incident_bundle:v1"
_WEBHOOK_STACK_KEY = "rmc:super_dashboard:webhook_stack:v1"
_COUNTRY_ROLLUP_KEY = "rmc:super_dashboard:country_rollup:v1"
_COMMAND_CENTER_TTL = 60
_PLATFORM_HEALTH_TTL = 30
_HEALTH_METADATA_TTL = 120
_REGISTRY_COUNTS_TTL = 120
_FLEET_METRICS_TTL = 60
_INCIDENT_BUNDLE_TTL = 30
_WEBHOOK_STACK_TTL = 45
_COUNTRY_ROLLUP_TTL = 60


def get_cached_command_center_data() -> dict:
    data = cache.get(_COMMAND_CENTER_KEY)
    if data is not None:
        return data
    data = _build_command_center_data()
    cache.set(_COMMAND_CENTER_KEY, data, _COMMAND_CENTER_TTL)
    return data


def get_cached_platform_health() -> dict:
    data = cache.get(_PLATFORM_HEALTH_KEY)
    if data is not None:
        return data
    from apps.observability.monitoring import SystemHealthMonitor

    try:
        data = SystemHealthMonitor.get_comprehensive_health()
    except Exception:
        data = {
            "overall_status": "warning",
            "cpu": {"usage_percent": 0.0, "threshold": 80.0, "status": "warning"},
            "memory": {
                "usage_percent": 0.0,
                "used_mb": 0.0,
                "threshold": 85.0,
                "status": "warning",
            },
            "disk": {
                "usage_percent": 0.0,
                "free_gb": 0.0,
                "threshold": 90.0,
                "status": "warning",
            },
            "database": {"status": "unhealthy", "response_time_ms": 0.0},
            "cache": {"status": "unhealthy", "type": "unknown"},
        }
    cache.set(_PLATFORM_HEALTH_KEY, data, _PLATFORM_HEALTH_TTL)
    return data


def get_cached_health_table_metadata() -> tuple[list, list]:
    cached = cache.get(_HEALTH_TABLES_KEY)
    if cached is not None:
        return cached
    top_tables: list = []
    schema_stats: list = []
    try:
        from .health_utils import get_global_health_stats, get_top_tables_by_size

        top_tables = get_top_tables_by_size(limit=10)
        schema_stats = get_global_health_stats()
    except Exception:
        pass
    payload = (top_tables, schema_stats)
    cache.set(_HEALTH_TABLES_KEY, payload, _HEALTH_METADATA_TTL)
    return payload


def get_cached_registry_counts() -> dict[str, int]:
    cached = cache.get(_REGISTRY_COUNTS_KEY)
    if cached is not None:
        return cached
    try:
        counts = {
            "countries": CountryRegistry.objects.filter(is_active=True).count(),
            "subdivisions": SubdivisionRegistry.objects.filter(is_active=True).count(),
            "education_levels": EducationLevelRegistry.objects.filter(is_active=True).count(),
            "education_system_types": EducationSystemTypeRegistry.objects.filter(
                is_active=True
            ).count(),
        }
    except DatabaseError as exc:
        if not is_transient_database_error(exc):
            raise
        logger.warning("super_dashboard_registry_counts_transient_db: %s", exc)
        counts = {
            "countries": 0,
            "subdivisions": 0,
            "education_levels": 0,
            "education_system_types": 0,
        }
    cache.set(_REGISTRY_COUNTS_KEY, counts, _REGISTRY_COUNTS_TTL)
    return counts


def get_cached_incident_bundle() -> dict[str, Any]:
    cached = cache.get(_INCIDENT_BUNDLE_KEY)
    if cached is not None:
        return cached
    from django.db.models import Count

    from apps.observability.models import PlatformIncident

    statuses = (
        PlatformIncident.Status.OPEN,
        PlatformIncident.Status.ACKNOWLEDGED,
        PlatformIncident.Status.MITIGATED,
    )
    try:
        incidents = list(
            PlatformIncident.objects.select_related("affected_school")
            .filter(status__in=statuses)
            .order_by("-detected_at", "-created_at")[:12]
            .values(
                "id",
                "title",
                "incident_type",
                "severity",
                "status",
                "affected_school_id",
                "affected_school__name",
            )
        )
        for row in incidents:
            row["affected_school_name"] = row.pop("affected_school__name", "")

        counts = {
            row["status"]: row["total"]
            for row in PlatformIncident.objects.values("status").annotate(total=Count("id"))
        }
        critical_count = PlatformIncident.objects.filter(
            status__in=statuses,
            severity__in=[
                PlatformIncident.Severity.CRITICAL,
                PlatformIncident.Severity.HIGH,
            ],
        ).count()
        payload = {
            "platform_incidents": incidents,
            "incident_counts": counts,
            "critical_incident_count": critical_count,
        }
    except DatabaseError as exc:
        if not is_transient_database_error(exc):
            raise
        logger.warning("super_dashboard_incident_bundle_transient_db: %s", exc)
        payload = dict(_EMPTY_INCIDENT_BUNDLE)
    cache.set(_INCIDENT_BUNDLE_KEY, payload, _INCIDENT_BUNDLE_TTL)
    return payload


def get_cached_legacy_webhook_stack() -> dict[str, Any]:
    cached = cache.get(_WEBHOOK_STACK_KEY)
    if cached is not None:
        return cached
    from apps.events.legacy_bridge import legacy_webhook_sync_snapshot

    payload = legacy_webhook_sync_snapshot()
    cache.set(_WEBHOOK_STACK_KEY, payload, _WEBHOOK_STACK_TTL)
    return payload


def get_cached_country_rollup() -> list[dict[str, Any]]:
    cached = cache.get(_COUNTRY_ROLLUP_KEY)
    if cached is not None:
        return cached
    from django.db.models import Count

    from apps.schools.models import School

    try:
        payload = list(
            School.objects.exclude(country_code="")
            .values("country_code")
            .annotate(
                school_count=Count("id"),
                student_count=Count("student_profiles", distinct=True),
            )
            .order_by("-school_count", "country_code")[:12]
        )
    except DatabaseError as exc:
        if not is_transient_database_error(exc):
            raise
        logger.warning("super_dashboard_country_rollup_transient_db: %s", exc)
        payload = []
    cache.set(_COUNTRY_ROLLUP_KEY, payload, _COUNTRY_ROLLUP_TTL)
    return payload


def _fleet_metrics_cache_key(
    incident_school_ids: set[Any], churn_risk_school_ids: set[Any]
) -> str:
    parts = tuple(
        sorted(str(pk) for pk in incident_school_ids)
        + sorted(str(pk) for pk in churn_risk_school_ids)
    )
    return f"rmc:super_dashboard:fleet_metrics:v1:{hash(parts)}"


def get_cached_fleet_registry_metrics(
    *,
    incident_school_ids: set[Any],
    churn_risk_school_ids: set[Any],
) -> FleetRegistryMetrics:
    key = _fleet_metrics_cache_key(incident_school_ids, churn_risk_school_ids)
    cached = cache.get(key)
    if cached is not None:
        return cached
    metrics = compute_fleet_registry_metrics(
        incident_school_ids=incident_school_ids,
        churn_risk_school_ids=churn_risk_school_ids,
    )
    cache.set(key, metrics, _FLEET_METRICS_TTL)
    return metrics
