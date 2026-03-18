"""
Context managers for RLS (single-schema mode): set session GUC for tenant or bypass.
Use in management commands or Celery tasks when tenant context is not set by middleware.

Single place for app.current_school_id SET/RESET so middleware and other callers
do not duplicate raw SQL (see RUNMYCAMPUS §2.4 raw SQL wrap).
"""

import logging
from contextlib import contextmanager

from django.db import connection
from django.db.utils import DatabaseError, OperationalError, ProgrammingError

logger = logging.getLogger(__name__)


def set_rls_school_id(school_id):
    """
    Set app.current_school_id for the current DB connection (e.g. in middleware).
    No-op when not PostgreSQL. Does not reset; caller must call reset_rls_school_id later.
    """
    if connection.vendor != "postgresql":
        return
    sid = str(school_id)
    with connection.cursor() as cursor:
        cursor.execute("SET app.current_school_id = %s", [sid])


def reset_rls_school_id():
    """
    Reset app.current_school_id for the current DB connection (e.g. in middleware response).
    No-op when not PostgreSQL.
    """
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_school_id")


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
        except (OperationalError, ProgrammingError, DatabaseError) as e:
            logger.debug("RLS reset app.current_school_id: %s", e)


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
        except (OperationalError, ProgrammingError, DatabaseError):
            pass
