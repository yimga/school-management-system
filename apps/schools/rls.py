"""
RLS (Row-Level Security) helpers for single-schema multi-tenancy.
RLS is only applied when USE_DJANGO_TENANTS=False and the DB is PostgreSQL.
When USE_DJANGO_TENANTS=True, tenant isolation is via schema-per-tenant; RLS is not used.
"""


def should_apply_rls(connection):
    from django.conf import settings

    if getattr(settings, "USE_DJANGO_TENANTS", False):
        return False
    return connection.vendor == "postgresql"
