"""
Tenant schema provisioning: check existence and create schema (PostgreSQL).
§2.4 schema existence delegates to django-tenants; local DDL remains only for CREATE SCHEMA.
"""

from __future__ import annotations

from django.db import connection


def schema_exists(schema_name: str) -> bool:
    """Return True if the PostgreSQL schema exists. No-op on non-PostgreSQL (returns False)."""
    if not (schema_name or "").strip():
        return False
    if connection.vendor != "postgresql":
        return False
    from django_tenants.utils import schema_exists as tenant_schema_exists

    return bool(
        tenant_schema_exists(schema_name.strip(), database=connection.alias)
    )


def create_schema_if_not_exists(schema_name: str) -> None:
    """Create a missing tenant schema via django-tenants. No-op on non-PostgreSQL."""
    if not (schema_name or "").strip():
        return
    if connection.vendor != "postgresql":
        return

    from apps.customers.models import Client

    client = Client.objects.filter(schema_name=schema_name.strip()).first()
    if client is None:
        return
    client.create_schema(check_if_exists=True, verbosity=0)
