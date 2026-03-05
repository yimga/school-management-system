"""
Context managers for RLS (single-schema mode): set session GUC for tenant or bypass.
Use in management commands or Celery tasks when tenant context is not set by middleware.
"""
from contextlib import contextmanager

from django.db import connection


@contextmanager
def rls_school(school_id):
    """
    Set app.current_school_id for the current DB session, then reset in finally.
    Use when running code that must see only one school's rows (e.g. RLS mode Celery task).
    school_id: UUID or int, will be cast to str.
    """
    if connection.vendor != "postgresql":
        yield
        return
    sid = str(school_id)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET app.current_school_id = %s", [sid])
        yield
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute("RESET app.current_school_id")
        except Exception:
            pass


@contextmanager
def rls_bypass():
    """
    Set app.rls_bypass = 'on' for the current DB session, then reset in finally.
    Use for management commands that need cross-tenant or unconstrained reads.
    """
    if connection.vendor != "postgresql":
        yield
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET app.rls_bypass = 'on'")
        yield
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute("RESET app.rls_bypass")
        except Exception:
            pass
