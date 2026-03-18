"""
Tenant-scoped health metrics: PG catalog queries for table sizes and schema stats.
§2.4 raw_sql_replacement_targets: all health raw SQL lives here; health_utils delegates.
Staff/control-plane only; tenant scoping via schema_name.
"""

import logging

from django.db import connection
from django.db.utils import DatabaseError, OperationalError, ProgrammingError

logger = logging.getLogger(__name__)


def get_top_tables_by_size(
    limit: int = 10, schema_name: str | None = None
) -> list[dict]:
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
        cursor.execute(
            """
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
            """,
            [limit],
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def check_table_exists(qualified_table: str) -> bool:
    """
    Return True if the given qualified table (e.g. 'public.schools_school' or 'tenant_schema.people_studentprofile')
    exists in the current database. Uses PostgreSQL to_regclass(); no-op on non-PostgreSQL (returns False).
    """
    if connection.vendor != "postgresql":
        return False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s)", [qualified_table])
            row = cursor.fetchone()
            return bool(row and row[0])
    except (OperationalError, ProgrammingError, DatabaseError):
        return False


def count_table_rows(schema: str, table: str) -> int:
    """
    Return row count for the given schema.table. Identifiers are quoted for safety.
    Returns -1 on error (e.g. permissions, RLS). No-op on non-PostgreSQL (returns 0).
    """
    if connection.vendor != "postgresql":
        return 0
    try:
        quoted_schema = connection.ops.quote_name(schema)
        quoted_table = connection.ops.quote_name(table)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {quoted_schema}.{quoted_table}")
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
    except (OperationalError, ProgrammingError, DatabaseError) as e:
        logger.debug(
            "health_repository.count_table_rows failed for %s.%s: %s", schema, table, e
        )
        return -1


def get_global_health_stats() -> list[dict]:
    """
    Per-schema storage (for multi-schema). Single-schema: one row for public.
    Returns list of dicts: schema_name, pretty_size, raw_size, table_count.
    No-op on non-PostgreSQL backends (returns []).
    """
    if connection.vendor != "postgresql":
        return []
    with connection.cursor() as cursor:
        cursor.execute(
            """
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
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
