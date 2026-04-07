"""
Tenant-scoped health metrics: PG catalog queries for table sizes and schema stats.
§2.4 raw_sql_replacement_targets: all health raw SQL lives here; health_utils delegates.
Staff/control-plane only; tenant scoping via schema_name.
"""

from __future__ import annotations

import logging
import re

from django.db import connection
from django.db.utils import DatabaseError, OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

# PostgreSQL unqualified identifier (max 63): pg_stat_user_tables.schemaname filters and COUNT relnames.
_PG_HEALTH_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

# Upper bound for LIMIT on pg_stat_user_tables scan (admin/ops UI); avoids pathological row fetch cost.
_HEALTH_TOP_TABLES_MAX_LIMIT = 500
# Upper bound for schema groups returned by get_global_health_stats (super dashboard); avoids huge GROUP BY result sets.
_HEALTH_GLOBAL_SCHEMA_STATS_MAX_LIMIT = 500

# Reject buffer types callers might pass instead of str/int (explicit; avoids relying on coercion exceptions).
_BINARY_BUFFER_TYPES = (bytes, bytearray, memoryview)


def _normalize_identifier(value: str, *, field_name: str) -> str:
    """Strip and validate a single identifier segment; raises ValueError on invalid input."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must not be a boolean.")
    if isinstance(value, _BINARY_BUFFER_TYPES):
        raise ValueError(
            f"{field_name} must not be bytes, bytearray, or memoryview."
        )
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        raise ValueError(f"{field_name} must be a non-blank string.")
    return normalized


def _normalize_unqualified_identifier(value: str, *, field_name: str) -> str:
    normalized = _normalize_identifier(value, field_name=field_name)
    if "." in normalized:
        raise ValueError(f"{field_name} must be unqualified.")
    return normalized


def get_top_tables_by_size(
    limit: int = 10, schema_name: str | None = None
) -> list[dict]:
    """
    Return largest tables by total size (data + indexes).
    When schema_name is provided, scope results to that schema without mutating
    the shared connection search_path.
    Returns list of dicts: schema_name, table_name, total_pretty, raw_size, row_count (if available).
    No-op on non-PostgreSQL backends (returns []).
    limit must not be bool or a binary buffer (bool would coerce to 0/1; bytes, bytearray, and memoryview are not limits);
    otherwise it is coerced to int, must be positive, and is capped at 500
    (_HEALTH_TOP_TABLES_MAX_LIMIT) before the query runs.
    When schema_name is provided it is normalized with _normalize_unqualified_identifier (bool, buffers,
    blank, and qualified names rejected) and must match the health identifier pattern or the call returns [].
    """
    if connection.vendor != "postgresql":
        return []
    if isinstance(limit, bool):
        return []
    if isinstance(limit, _BINARY_BUFFER_TYPES):
        return []
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return []
    if limit <= 0:
        return []
    if limit > _HEALTH_TOP_TABLES_MAX_LIMIT:
        limit = _HEALTH_TOP_TABLES_MAX_LIMIT
    if schema_name is not None:
        try:
            schema_norm = _normalize_unqualified_identifier(
                schema_name, field_name="schema_name"
            )
        except ValueError:
            return []
        if not _PG_HEALTH_IDENTIFIER_RE.fullmatch(schema_norm):
            return []
        schema_name = schema_norm
    with connection.cursor() as cursor:
        params: list[object] = []
        schema_filter_sql = ""
        if schema_name:
            schema_filter_sql = "AND schemaname = %s"
            params.append(schema_name)
        params.append(limit)
        cursor.execute(
            f"""
            SELECT
                schemaname AS schema_name,
                relname AS table_name,
                pg_size_pretty(pg_total_relation_size(relid)) AS total_pretty,
                pg_total_relation_size(relid) AS raw_size,
                n_live_tup AS row_count
            FROM pg_catalog.pg_stat_user_tables
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
              {schema_filter_sql}
            ORDER BY pg_total_relation_size(relid) DESC
            LIMIT %s;
            """,
            params,
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def check_table_exists(qualified_table: str) -> bool:
    """
    Return True if the given qualified table (e.g. 'public.schools_school' or 'tenant_schema.people_studentprofile')
    exists in the current database. Uses Django introspection against the active search_path;
    schema and table segments (when present) must each be a PostgreSQL identifier (ASCII letters,
    digits, underscore; max 63 characters) before introspection runs.
    bool and binary buffer values are rejected via _normalize_identifier (same as schema/table segments in count_table_rows).
    no-op on non-PostgreSQL (returns False).
    """
    if connection.vendor != "postgresql":
        return False
    try:
        normalized_qualified_table = _normalize_identifier(
            qualified_table, field_name="qualified_table"
        )
        schema_name = None
        table_name = normalized_qualified_table
        if "." in normalized_qualified_table:
            schema_name, table_name = normalized_qualified_table.split(".", 1)
            schema_name = _normalize_unqualified_identifier(
                schema_name, field_name="schema"
            )
            table_name = _normalize_unqualified_identifier(
                table_name, field_name="table"
            )
            current_schema = getattr(connection, "schema_name", None)
            if schema_name not in {"public", current_schema}:
                return False
        else:
            table_name = _normalize_unqualified_identifier(
                table_name, field_name="table"
            )
        if schema_name is not None and not _PG_HEALTH_IDENTIFIER_RE.fullmatch(
            schema_name
        ):
            return False
        if not _PG_HEALTH_IDENTIFIER_RE.fullmatch(table_name):
            return False
        return table_name in set(connection.introspection.table_names())
    except (OperationalError, ProgrammingError, DatabaseError, ValueError):
        return False


def count_table_rows(schema: str, table: str) -> int:
    """
    Return row count for the given schema.table. Identifiers are quoted for safety.
    Schema and table must each be a single PostgreSQL identifier (ASCII letters, digits,
    underscore; max 63 characters) after strip — otherwise returns -1 without SQL.
    bool and binary buffer values are rejected via _normalize_identifier on schema and table (no SQL).
    Returns -1 on error (e.g. permissions, RLS). No-op on non-PostgreSQL (returns 0).
    """
    if connection.vendor != "postgresql":
        return 0
    try:
        schema_norm = _normalize_unqualified_identifier(schema, field_name="schema")
        table_norm = _normalize_unqualified_identifier(table, field_name="table")
        if not _PG_HEALTH_IDENTIFIER_RE.fullmatch(schema_norm):
            raise ValueError("schema must be a PostgreSQL identifier.")
        if not _PG_HEALTH_IDENTIFIER_RE.fullmatch(table_norm):
            raise ValueError("table must be a PostgreSQL identifier.")
        quoted_schema = connection.ops.quote_name(schema_norm)
        quoted_table = connection.ops.quote_name(table_norm)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {quoted_schema}.{quoted_table}")
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
    except (OperationalError, ProgrammingError, DatabaseError, ValueError) as e:
        logger.debug(
            "health_repository.count_table_rows failed for %s.%s: %s", schema, table, e
        )
        return -1


def get_global_health_stats() -> list[dict]:
    """
    Per-schema storage (for multi-schema). Single-schema: one row for public.
    Returns list of dicts: schema_name, pretty_size, raw_size, table_count.
    Result rows are capped at _HEALTH_GLOBAL_SCHEMA_STATS_MAX_LIMIT (500), largest schemas first.
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
            ORDER BY raw_size DESC
            LIMIT %s;
            """,
            [_HEALTH_GLOBAL_SCHEMA_STATS_MAX_LIMIT],
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
