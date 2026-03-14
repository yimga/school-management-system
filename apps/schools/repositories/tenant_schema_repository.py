"""
Tenant schema DDL: drop schema (onboarding kill-switch).
§2.4 raw_sql_replacement_targets: single raw SQL for DROP SCHEMA lives here; onboarding_service delegates.
Use only on onboarding failure; staff/control-plane only.
"""
from django.db import connection


def drop_tenant_schema_if_exists(schema_name: str) -> None:
    """
    Drop a PostgreSQL schema if it exists (CASCADE). No-op if schema_name is empty or 'public'.
    Identifier is quoted for safety. Use only for onboarding kill-switch.
    """
    if not schema_name or schema_name == "public":
        return
    if connection.vendor != "postgresql":
        return
    quoted = connection.ops.quote_name(schema_name)
    with connection.cursor() as cursor:
        cursor.execute(f"DROP SCHEMA IF EXISTS {quoted} CASCADE;")
