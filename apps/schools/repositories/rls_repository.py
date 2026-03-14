"""
RLS (Row-Level Security) read-only checks: tenant table RLS status from PG catalog.
§2.4 raw_sql_replacement_targets: single raw SQL for verify_tenant_rls lives here; command delegates.
PostgreSQL only; staff/control-plane use.
"""
from django.db import connection


def get_tenant_rls_status(table_names: list[str]) -> dict[str, bool]:
    """
    Return {relname: relrowsecurity} for the given table names in the public schema.
    Only tables that exist are included. No-op on non-PostgreSQL (returns {}).
    """
    if connection.vendor != "postgresql" or not table_names:
        return {}
    placeholders = ",".join(["%s"] * len(table_names))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            AND c.relname IN (%s)
            """ % placeholders,
            table_names,
        )
        return {row[0]: bool(row[1]) for row in cursor.fetchall()}
