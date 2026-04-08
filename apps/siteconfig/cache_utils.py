"""
World Engine: tenant-scoped cache key prefix to prevent cross-tenant leakage.
Prepend this to any cache key that stores tenant-specific data when using shared Redis.
Redis-backed tenant resolution: when cache backend is Redis, tenant resolution
(schema/domain -> school id) can be cached to avoid DB on every request.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Optional

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, connection


OPTIONAL_CACHE_ERRORS = (
    AttributeError,
    DatabaseError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)

_MAX_CACHE_SCHOOL_ID_LEN = 128
# Align with PostgreSQL / django-tenants schema naming for tenant: cache prefixes.
_PG_TENANT_SCHEMA_CACHE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_MAX_TENANT_RESOLUTION_LOOKUP_LEN = 512
_MAX_TENANT_CACHE_BASE_KEY_LEN = 512
_INVALID_TENANT_CACHE_BASE_FALLBACK = "_"

_CACHE_SEGMENT_BINARY_TYPES = (bytes, bytearray, memoryview)


def _normalize_tenant_schema_name_cache(value: object) -> str | None:
    """Return a safe tenant schema segment for cache keys, or None if malformed."""
    if isinstance(value, bool):
        return None
    if isinstance(value, Mapping):
        return None
    if isinstance(value, _CACHE_SEGMENT_BINARY_TYPES):
        return None
    raw = str(value).strip() if value is not None else ""
    if not raw or not _PG_TENANT_SCHEMA_CACHE_RE.fullmatch(raw):
        return None
    return raw


def _normalize_tenant_resolution_lookup_key(key: object) -> str | None:
    """Return a safe Redis lookup key for tenant resolution cache, or None if malformed."""
    if not isinstance(key, str):
        return None
    normalized = key.strip()
    if not normalized or len(normalized) > _MAX_TENANT_RESOLUTION_LOOKUP_LEN:
        return None
    if "\x00" in normalized or "\n" in normalized or "\r" in normalized:
        return None
    return normalized


def _normalize_tenant_cache_base_key(key: object) -> str:
    """
    Return a safe suffix for tenant_cache_key, or a stable fallback when malformed.
    """
    if not isinstance(key, str):
        return _INVALID_TENANT_CACHE_BASE_FALLBACK
    s = key.strip()
    if (
        not s
        or len(s) > _MAX_TENANT_CACHE_BASE_KEY_LEN
        or "\x00" in s
        or "\n" in s
        or "\r" in s
    ):
        return _INVALID_TENANT_CACHE_BASE_FALLBACK
    return s


def _normalize_school_id(value: object) -> str | None:
    """
    Normalize a school id for cache prefixes (request.school or RLS GUC via current_setting).
    Rejects bool, collections.abc.Mapping, binary buffers, and pathological shapes so malformed
    session vars cannot widen cache key structure.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, Mapping):
        return None
    if isinstance(value, _CACHE_SEGMENT_BINARY_TYPES):
        return None
    normalized = str(value).strip() if value is not None else ""
    if not normalized or normalized.lower() in {"none", "null"}:
        return None
    if len(normalized) > _MAX_CACHE_SCHOOL_ID_LEN:
        return None
    if any(ch.isspace() for ch in normalized):
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in normalized):
        return None
    return normalized


def _current_rls_school_id() -> str | None:
    """
    Return the active RLS school id for the current DB session when available.

    This prevents background jobs and helper code from collapsing to the shared
    "public" cache namespace when they are already running inside a tenant RLS
    context.
    """
    try:
        if getattr(settings, "USE_DJANGO_TENANTS", False):
            return None
        if connection.vendor != "postgresql":
            return None
        # §2.4 raw_sql_replacement_targets: RLS session var only; no ORM equivalent; keep in this module.
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.current_school_id', true)")
            row = cursor.fetchone()
        return _normalize_school_id(row[0] if row else None)
    except OPTIONAL_CACHE_ERRORS:
        return None


def get_tenant_cache_prefix(request=None) -> str:
    """
    Return a string to prepend to tenant-scoped cache keys (e.g. schema name or school id).
    Use for evals, dashboard widgets, portal, reports, compliance, backend status fragment.
    """
    try:
        tenant = getattr(connection, "tenant", None)
        if tenant is not None:
            schema = _normalize_tenant_schema_name_cache(
                getattr(tenant, "schema_name", None)
            )
            if schema:
                return f"tenant:{schema}"
    except OPTIONAL_CACHE_ERRORS:
        pass
    current_school_id = _current_rls_school_id()
    if current_school_id:
        return f"school:{current_school_id}"
    if request is not None:
        school = getattr(request, "school", None)
        if school is not None:
            school_id = _normalize_school_id(getattr(school, "id", None))
            if school_id:
                return f"school:{school_id}"
    return "public"


def tenant_cache_key(base_key: str, request=None) -> str:
    """Return base_key prefixed with tenant/school identifier for tenant-scoped caches."""
    prefix = get_tenant_cache_prefix(request)
    safe = _normalize_tenant_cache_base_key(base_key)
    return f"{prefix}:{safe}"


# Redis-backed tenant resolution (RUNMYCAMPUS_ROADMAP_TASKS)
TENANT_RESOLUTION_CACHE_PREFIX = "tenant_resolution"
TENANT_RESOLUTION_TIMEOUT = 300  # 5 minutes


def get_tenant_cached(lookup_key: str) -> Optional[Any]:
    """
    Return cached tenant payload for lookup_key (e.g. schema_name or domain).
    Use when cache backend is Redis for fast tenant resolution without DB hit.
    Returns None if not cached or cache unavailable.
    """
    safe_key = _normalize_tenant_resolution_lookup_key(lookup_key)
    if not safe_key:
        return None
    key = f"{TENANT_RESOLUTION_CACHE_PREFIX}:{safe_key}"
    try:
        return cache.get(key)
    except OPTIONAL_CACHE_ERRORS:
        return None


def set_tenant_cached(
    lookup_key: str, payload: Any, timeout: int = TENANT_RESOLUTION_TIMEOUT
) -> None:
    """
    Cache tenant payload for lookup_key. Use after resolving tenant from DB
    so subsequent requests can use get_tenant_cached(lookup_key) without DB.
    """
    safe_key = _normalize_tenant_resolution_lookup_key(lookup_key)
    if not safe_key:
        return
    key = f"{TENANT_RESOLUTION_CACHE_PREFIX}:{safe_key}"
    try:
        cache.set(key, payload, timeout=timeout)
    except OPTIONAL_CACHE_ERRORS:
        pass
