"""
PostgreSQL RLS session GUCs: SET/RESET app.current_school_id and app.rls_bypass.
§2.4 raw_sql_replacement_targets: no ORM for session variables; consumed from rls_context.
"""

from __future__ import annotations

from django.db import connection


def set_current_school_id(school_id: str) -> None:
    """SET app.current_school_id = %s (parameterized). Caller enforces policy / normalization."""
    with connection.cursor() as cursor:
        cursor.execute("SET app.current_school_id = %s", [school_id])


def reset_current_school_id() -> None:
    """RESET app.current_school_id."""
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_school_id")


def set_rls_bypass_on() -> None:
    """SET app.rls_bypass = 'on'."""
    with connection.cursor() as cursor:
        cursor.execute("SET app.rls_bypass = 'on'")


def reset_rls_bypass_var() -> None:
    """RESET app.rls_bypass."""
    with connection.cursor() as cursor:
        cursor.execute("RESET app.rls_bypass")
