"""
RLS (Row-Level Security) read-only checks: tenant table RLS status from PG catalog.
§2.4 raw_sql_replacement_targets: single raw SQL for verify_tenant_rls lives here; command delegates.
PostgreSQL only; staff/control-plane use.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from django.conf import settings
from django.db import connection

# Unquoted relname pattern for Django-style public-schema tables (max PG identifier length 63).
_PG_RLS_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

# Upper bound on relnames passed to the retained IN (...) catalog query (admin/ops; matches health LIMIT spirit).
_RLS_STATUS_MAX_TABLE_NAMES = 500


def get_tenant_rls_status(table_names: list[str]) -> dict[str, bool]:
    """
    Return {relname: relrowsecurity} for the given table names in the public schema.
    table_names must be a list or other non-mapping iterable of strings (collections.abc.Mapping,
    including dict and types.MappingProxyType, is rejected so accidental mapping objects cannot be
    interpreted as a relname sequence).     Not bool (Python bool is not iterable for this API).
    Non-iterable table_names (e.g. int) or values that fail while constructing an iterator
    return {} without SQL. Not a bare str/bytes/bytearray/memoryview, which would iterate
    by character or yield integer code units. Only tables that exist are included. Duplicate
    relnames are collapsed to the first occurrence. At most _RLS_STATUS_MAX_TABLE_NAMES (500)
    valid identifiers are queried (first in iteration order after deduplication), and
    iteration stops once that cap is reached. Iterator-consumption failures also return {}
    without SQL. Result-row normalization failures after the catalog query also return {}.
    No-op on non-PostgreSQL (returns {}).
    """
    if connection.vendor != "postgresql" or getattr(
        settings, "USE_DJANGO_TENANTS", False
    ):
        return {}
    if isinstance(table_names, Mapping):
        return {}
    if isinstance(table_names, bool):
        return {}
    if isinstance(table_names, (str, bytes, bytearray, memoryview)):
        return {}
    try:
        name_iter = iter(table_names)
    except Exception:
        return {}
    normalized_table_names: list[str] = []
    seen: set[str] = set()
    try:
        for name in name_iter:
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
            if len(normalized_table_names) >= _RLS_STATUS_MAX_TABLE_NAMES:
                break
    except Exception:
        return {}
    if not normalized_table_names:
        return {}
    placeholders = ",".join(["%s"] * len(normalized_table_names))
    try:
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
            try:
                return {row[0]: bool(row[1]) for row in cursor.fetchall()}
            except Exception:
                return {}
    except Exception:
        return {}
