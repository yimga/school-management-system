"""
Read-only, tenant-safe summary of active PlatformIncident rows.

Fleet-wide incidents: generic copy only (no titles). School-scoped incidents: titles
visible to that tenant only. Minimizes accidental leakage of internal operator wording
on global incidents.
"""

from __future__ import annotations

from typing import Any

from django.core.cache import cache

_SOFT = (
    AttributeError,
    ImportError,
    LookupError,
    TypeError,
    ValueError,
)
try:
    from django.db import DatabaseError, OperationalError
except ImportError:
    DatabaseError = Exception  # type: ignore[misc, assignment]
    OperationalError = Exception  # type: ignore[misc, assignment]

_DB_SOFT = (DatabaseError, OperationalError) + _SOFT

# Bumped on every PlatformIncident write so all per-school cache keys miss (fleet affects every tenant).
STRIP_CACHE_VER_KEY = "obs:tenant_status_strip:ver"


def _strip_cache_generation() -> int:
    try:
        v = cache.get(STRIP_CACHE_VER_KEY)
        return int(v) if v is not None else 0
    except _SOFT:
        return 0


def _active_statuses():
    from apps.observability.models import PlatformIncident

    return (
        PlatformIncident.Status.OPEN,
        PlatformIncident.Status.ACKNOWLEDGED,
        PlatformIncident.Status.MITIGATED,
    )


def _fleet_types():
    from apps.observability.models import PlatformIncident

    return (
        PlatformIncident.IncidentType.AVAILABILITY,
        PlatformIncident.IncidentType.PERFORMANCE,
    )


def compute_platform_status_strip_bundle(school_id: Any) -> dict[str, Any]:
    """
    Return a template-friendly dict. Cached briefly to avoid per-request table scans.
    Cache keys include a generation counter invalidated on PlatformIncident saves/deletes.
    """
    gen = _strip_cache_generation()
    cache_key = f"obs:tenant_status_strip:b2:{gen}:{school_id or 'none'}"
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    except _SOFT:
        pass

    bundle: dict[str, Any] = {
        "show": False,
        "fleet_generic": False,
        "tenant_items": [],
    }
    try:
        from apps.observability.models import PlatformIncident

        active = _active_statuses()
        fleet_types = _fleet_types()
        bundle["fleet_generic"] = PlatformIncident.objects.filter(
            status__in=active,
            affected_school__isnull=True,
            incident_type__in=fleet_types,
        ).exists()
        if school_id is not None:
            bundle["tenant_items"] = list(
                PlatformIncident.objects.filter(
                    status__in=active,
                    affected_school_id=school_id,
                ).values("title", "severity", "status")[:5]
            )
        bundle["show"] = bool(bundle["fleet_generic"] or bundle["tenant_items"])
    except _DB_SOFT:
        bundle = {
            "show": False,
            "fleet_generic": False,
            "tenant_items": [],
        }

    try:
        cache.set(cache_key, bundle, 60)
    except _SOFT:
        pass
    return bundle


def invalidate_platform_status_strip_cache(school_id: Any = None) -> None:  # noqa: ARG001
    """
    Invalidate all tenant status strip bundles. Increments a global generation counter
    so every cached key misses (required when fleet-wide incidents change).

    ``school_id`` is reserved for future targeted invalidation; currently unused.
    """
    try:
        v = cache.get(STRIP_CACHE_VER_KEY)
        n = 0 if v is None else int(v)
        cache.set(STRIP_CACHE_VER_KEY, n + 1, timeout=None)
    except _SOFT:
        pass
