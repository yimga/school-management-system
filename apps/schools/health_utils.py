"""
Section 8.7–8.8: Health check and resource hogs (PG metadata).
Single-schema: report table sizes. With django-tenants: per-schema sizes.
Refs: Dataedo — list largest tables; PostgreSQL pg_stat_user_tables, pg_total_relation_size.
"""
from django.db import connection


def get_top_tables_by_size(limit=10, schema_name=None):
    """
    Return largest tables by total size (data + indexes). Single-schema: schema_name ignored or 'public'.
    Returns list of dicts: schema_name, table_name, total_pretty, raw_size, row_count (if available).
    No-op on non-PostgreSQL backends (returns []).
    """
    if connection.vendor != "postgresql":
        return []
    with connection.cursor() as cursor:
        if schema_name:
            cursor.execute("SET search_path TO %s", [schema_name])
        query = """
            SELECT
                schemaname AS schema_name,
                relname AS table_name,
                pg_size_pretty(pg_total_relation_size(relid)) AS total_pretty,
                pg_total_relation_size(relid) AS raw_size,
                n_live_tup AS row_count
            FROM pg_catalog.pg_stat_user_tables
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY pg_total_relation_size(relid) DESC
            LIMIT %s;
        """
        cursor.execute(query, [limit])
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_global_health_stats():
    """
    Section 8.7: Per-schema storage (for multi-schema). Single-schema: one row for public.
    Returns list of dicts: schema_name, pretty_size, raw_size, table_count.
    No-op on non-PostgreSQL backends (returns []).
    """
    if connection.vendor != "postgresql":
        return []
    with connection.cursor() as cursor:
        query = """
            SELECT
                n.nspname AS schema_name,
                pg_size_pretty(SUM(pg_total_relation_size(c.oid))) AS pretty_size,
                COALESCE(SUM(pg_total_relation_size(c.oid)), 0)::bigint AS raw_size,
                COUNT(c.oid) AS table_count
            FROM pg_class c
            LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
              AND c.relkind = 'r'
            GROUP BY n.nspname
            ORDER BY raw_size DESC;
        """
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
