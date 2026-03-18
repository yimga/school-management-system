"""
Tenant schema provisioning: check existence and create schema (PostgreSQL).
§2.4 raw_sql_replacement_targets: single place for ensure_tenant_schemas command; staff/operational only.
"""

from __future__ import annotations

from django.db import connection


def schema_exists(schema_name: str) -> bool:
    """Return True if the PostgreSQL schema exists. No-op on non-PostgreSQL (returns False)."""
    if not (schema_name or "").strip():
        return False
    if connection.vendor != "postgresql":
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            [schema_name.strip()],
        )
        return cursor.fetchone() is not None


def create_schema_if_not_exists(schema_name: str) -> None:
    """Create the PostgreSQL schema if it does not exist. Uses quoted identifier. No-op on non-PostgreSQL."""
    if not (schema_name or "").strip():
        return
    if connection.vendor != "postgresql":
        return
    quoted = connection.ops.quote_name(schema_name.strip())
    with connection.cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS %s" % quoted)
