"""
Tenant schema provisioning: check existence and create schema (PostgreSQL).
§2.4 schema existence delegates to django-tenants; local DDL remains only for CREATE SCHEMA.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from django.db import connection


_BINARY_BUFFER_TYPES = (bytes, bytearray, memoryview)
_PG_SCHEMA_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _normalize_schema_name(schema_name: object) -> str | None:
    if isinstance(schema_name, Mapping):
        return None
    if isinstance(schema_name, bool):
        return None
    if isinstance(schema_name, _BINARY_BUFFER_TYPES):
        return None
    if not isinstance(schema_name, str):
        return None
    try:
        normalized = schema_name.strip()
    except Exception:
        return None
    if not normalized:
        return None
    if not _PG_SCHEMA_NAME_RE.fullmatch(normalized):
        return None
    return normalized


def schema_exists(schema_name: str) -> bool:
    """Return True if the PostgreSQL schema exists. No-op on non-PostgreSQL (returns False)."""
    normalized = _normalize_schema_name(schema_name)
    if normalized is None:
        return False
    if connection.vendor != "postgresql":
        return False
    from django_tenants.utils import schema_exists as tenant_schema_exists

    exists = tenant_schema_exists(normalized, database=connection.alias)
    try:
        return bool(exists)
    except Exception:
        return False


def create_schema_if_not_exists(schema_name: str) -> None:
    """Create a missing tenant schema via django-tenants. No-op on non-PostgreSQL."""
    normalized = _normalize_schema_name(schema_name)
    if normalized is None:
        return
    if connection.vendor != "postgresql":
        return

    from apps.customers.models import Client

    # tenant-isolation-allow: provisioning-time lookup by schema_name (no tenant context yet; reviewed 2026-05-14)
    client = Client.objects.filter(schema_name=normalized).first()
    if client is None:
        return
    client.create_schema(check_if_exists=True, verbosity=0)
