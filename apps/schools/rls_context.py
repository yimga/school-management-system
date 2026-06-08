"""
Context managers for RLS (single-schema mode): set session GUC for tenant or bypass.
Use in management commands or Celery tasks when tenant context is not set by middleware.

Single place for app.current_school_id SET/RESET so middleware and other callers
do not duplicate raw SQL (see RUNMYCAMPUS §2.4 raw SQL wrap).
"""

import logging
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from uuid import UUID

from django.conf import settings
from django.db import connection
from django.db.utils import DatabaseError, OperationalError, ProgrammingError

from apps.schools.repositories.rls_context_repository import (
    reset_current_school_id,
    reset_rls_bypass_var,
    set_current_school_id,
    set_rls_bypass_on,
)

logger = logging.getLogger(__name__)

_MAX_RLS_SCHOOL_ID_LEN = 128

_RLS_SCHOOL_ID_BINARY_TYPES = (bytes, bytearray, memoryview)


def _normalize_rls_school_id(school_id) -> str:
    if isinstance(school_id, Mapping):
        raise ValueError("set_rls_school_id school_id must not be a mapping.")
    if isinstance(school_id, bool):
        raise ValueError("set_rls_school_id school_id must not be a boolean.")
    if isinstance(school_id, _RLS_SCHOOL_ID_BINARY_TYPES):
        raise ValueError(
            "set_rls_school_id school_id must not be bytes, bytearray, or memoryview."
        )
    if isinstance(school_id, Iterable) and not isinstance(school_id, str):
        raise ValueError(
            "set_rls_school_id school_id must not be a non-string iterable."
        )
    if school_id is None:
        sid = ""
    elif isinstance(school_id, str):
        sid = school_id.strip()
    elif isinstance(school_id, (int, UUID)):
        sid = str(school_id)
    else:
        raise ValueError(
            "set_rls_school_id school_id must be a string, integer, or UUID."
        )
    if not sid or sid.lower() in {"none", "null"}:
        raise ValueError("set_rls_school_id requires a non-blank school_id.")
    if len(sid) > _MAX_RLS_SCHOOL_ID_LEN:
        raise ValueError("set_rls_school_id school_id exceeds maximum length.")
    if any(ch.isspace() for ch in sid):
        raise ValueError("set_rls_school_id school_id must not contain whitespace.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in sid):
        raise ValueError("set_rls_school_id school_id contains disallowed characters.")
    return sid


def _should_manage_rls_session_vars() -> bool:
    return connection.vendor == "postgresql" and not getattr(
        settings, "USE_DJANGO_TENANTS", False
    )


def set_rls_school_id(school_id):
    """
    Set app.current_school_id for the current DB connection (e.g. in middleware).
    No-op when not PostgreSQL. Does not reset; caller must call reset_rls_school_id later.
    school_id must not be collections.abc.Mapping, bool, a non-string iterable, or a binary
    buffer (bytes/bytearray/memoryview); use str/int/UUID-like values.
    """
    if not _should_manage_rls_session_vars():
        return
    sid = _normalize_rls_school_id(school_id)
    set_current_school_id(sid)


def reset_rls_school_id():
    """
    Reset app.current_school_id for the current DB connection (e.g. in middleware response).
    No-op when not PostgreSQL.
    """
    if not _should_manage_rls_session_vars():
        return
    reset_current_school_id()


def set_rls_bypass():
    """Set app.rls_bypass for the current DB connection. No-op when not PostgreSQL."""
    if not _should_manage_rls_session_vars():
        return
    set_rls_bypass_on()


def reset_rls_bypass():
    """Reset app.rls_bypass for the current DB connection. No-op when not PostgreSQL."""
    if not _should_manage_rls_session_vars():
        return
    reset_rls_bypass_var()


def quarantine_rls_connection(reason: str) -> None:
    """Close a connection whose tenant session state could not be reset."""
    logger.error("Closing DB connection after RLS cleanup failure: %s", reason)
    connection.close()


@contextmanager
def rls_school(school_id):
    """
    Set app.current_school_id for the current DB session, then reset in finally.
    Use when running code that must see only one school's rows (e.g. RLS mode Celery task).
    school_id: UUID or int, will be cast to str.
    """
    if not _should_manage_rls_session_vars():
        yield
        return
    try:
        set_rls_school_id(school_id)
        yield
    finally:
        try:
            reset_rls_school_id()
        except (OperationalError, ProgrammingError, DatabaseError) as e:
            logger.debug("RLS reset app.current_school_id: %s", e)
            quarantine_rls_connection(str(e))


@contextmanager
def rls_bypass():
    """
    Set app.rls_bypass = 'on' for the current DB session, then reset in finally.
    Use for management commands that need cross-tenant or unconstrained reads.
    """
    if not _should_manage_rls_session_vars():
        yield
        return
    try:
        set_rls_bypass()
        yield
    finally:
        try:
            reset_rls_bypass()
        except (OperationalError, ProgrammingError, DatabaseError) as e:
            logger.debug("RLS reset app.rls_bypass: %s", e)
            quarantine_rls_connection(str(e))
