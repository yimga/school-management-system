"""
RLS (Row-Level Security) read-only checks: tenant table RLS status from PG catalog.
§2.4 raw_sql_replacement_targets: single raw SQL for verify_tenant_rls lives here; command delegates.
PostgreSQL only; staff/control-plane use.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.db import connection

# Unquoted relname pattern for Django-style public-schema tables (max PG identifier length 63).
_PG_RLS_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

# Upper bound on relnames passed to the retained IN (...) catalog query (admin/ops; matches health LIMIT spirit).
_RLS_STATUS_MAX_TABLE_NAMES = 500


def get_tenant_rls_status(table_names: list[str]) -> dict[str, bool]:
    """
    Return {relname: relrowsecurity} for the given table names in the public schema.
    table_names must be a list or other non-dict iterable of strings (dict is rejected so accidental
    mapping objects cannot be interpreted as a relname sequence). Not a bare str/bytes/bytearray/memoryview, which would
    iterate by character or yield integer code units. Only tables that exist are included. Duplicate relnames are collapsed to
    the first occurrence. At most _RLS_STATUS_MAX_TABLE_NAMES (500) valid identifiers are
    queried (first in iteration order after deduplication). No-op on non-PostgreSQL (returns {}).
    """
    if connection.vendor != "postgresql" or getattr(
        settings, "USE_DJANGO_TENANTS", False
    ):
        return {}
    if isinstance(table_names, dict):
        return {}
    if isinstance(table_names, (str, bytes, bytearray, memoryview)) or not table_names:
        return {}
    normalized_table_names: list[str] = []
    seen: set[str] = set()
    for name in table_names:
        if not isinstance(name, str):
            continue
        n = name.strip()
        if not n or "." in n:
            continue
        if not _PG_RLS_TABLE_NAME_RE.fullmatch(n):
            continue
        if n in seen:
            continue
        seen.add(n)
        normalized_table_names.append(n)
    if not normalized_table_names:
        return {}
    if len(normalized_table_names) > _RLS_STATUS_MAX_TABLE_NAMES:
        normalized_table_names = normalized_table_names[:_RLS_STATUS_MAX_TABLE_NAMES]
    placeholders = ",".join(["%s"] * len(normalized_table_names))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            AND c.relname IN (%s)
            """
            % placeholders,
            normalized_table_names,
        )
        return {row[0]: bool(row[1]) for row in cursor.fetchall()}
