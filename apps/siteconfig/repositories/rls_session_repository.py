"""
PostgreSQL RLS session GUC read for tenant-scoped cache keys (read-only).
§2.4 raw_sql_replacement_targets: current_setting('app.current_school_id', true) has no ORM equivalent.
"""

from __future__ import annotations

from django.db import DatabaseError, connection

_OPTIONAL_ERRORS = (
    AttributeError,
    DatabaseError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def fetch_current_school_id_setting_value() -> object | None:
    """
    Return the raw session value for app.current_school_id, or None when unset/unavailable.

    Policy (django-tenants mode, non-PostgreSQL) belongs in callers; this function only issues
    the retained SELECT.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.current_school_id', true)")
            row = cursor.fetchone()
        if not row:
            return None
        return row[0]
    except _OPTIONAL_ERRORS:
        return None
