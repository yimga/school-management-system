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


_CONNECTION_SCHOOL_ID_BY_SCHEMA: dict[str, str | None] = {}


def forget_connection_school_cache(schema_name: str | None = None) -> None:
    """Drop the memoised schema->school_id mapping (all schemas when None)."""
    if schema_name is None:
        _CONNECTION_SCHOOL_ID_BY_SCHEMA.clear()
    else:
        _CONNECTION_SCHOOL_ID_BY_SCHEMA.pop(schema_name, None)


def resolve_connection_school_id():
    """PK of the School the CURRENT DB connection is scoped to, or None.

    In schema-per-tenant mode a schema IS a school (``customers.Client`` holds a
    OneToOne to ``schools.School``), so the connection itself is authoritative
    even when the row being saved carries a NULL ``school`` FK — which happens
    routinely, because schema isolation makes the redundant per-row FK easy to
    omit (seeders and bulk writers both do).

    That NULL is not cosmetic: callers that resolve tenant policy from a row's
    ``school`` (grading scale, attendance ownership) silently fall back to a
    platform-neutral default when it is missing — e.g. a /20 Cameroon school
    resolves to a 100-point scale and accepts a mark of 25.

    ``connection.tenant`` is NOT enough on its own: ``schema_context()`` installs
    a ``FakeTenant`` carrying only ``schema_name``, so the mapping is resolved
    from ``customers.Client`` and memoised per schema — a per-row query would be
    a real cost on bulk paths like roll-call.

    Returns None (never raises) on the public schema, under RLS/shared-table
    mode, and on non-PostgreSQL connections, where no single school is implied.
    """
    schema_name = (getattr(connection, "schema_name", "") or "").strip()
    if not schema_name or schema_name == "public":
        return None
    if schema_name in _CONNECTION_SCHOOL_ID_BY_SCHEMA:
        return _CONNECTION_SCHOOL_ID_BY_SCHEMA[schema_name]

    school_id = None
    tenant = getattr(connection, "tenant", None)
    # A real Client instance already carries the FK; a FakeTenant does not.
    school_id = getattr(tenant, "school_id", None)
    if school_id is None:
        try:
            from django.apps import apps as django_apps

            client_model = django_apps.get_model("customers", "Client")
            school_id = (
                client_model.objects.filter(schema_name=schema_name)
                .values_list("school_id", flat=True)
                .first()
            )
        except (
            DatabaseError,
            OperationalError,
            ProgrammingError,
            LookupError,
            AttributeError,
            ValueError,
        ):
            school_id = None

    _CONNECTION_SCHOOL_ID_BY_SCHEMA[schema_name] = school_id
    return school_id


def resolve_connection_school():
    """The School the CURRENT DB connection is scoped to, or None.

    Object form of :func:`resolve_connection_school_id` — use the id-only helper
    on hot write paths that just need the FK.
    """
    school_id = resolve_connection_school_id()
    if school_id is None:
        return None
    try:
        from django.apps import apps as django_apps

        school_model = django_apps.get_model("schools", "School")
        return school_model.objects.filter(pk=school_id).first()
    except (
        DatabaseError,
        OperationalError,
        ProgrammingError,
        LookupError,
        AttributeError,
        ValueError,
    ):
        return None


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
