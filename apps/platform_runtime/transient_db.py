"""Detect transient PostgreSQL outages (recovery, SSL drop, connection reset)."""

from __future__ import annotations

from django.db import DatabaseError

_TRANSIENT_MARKERS = (
    "recovery mode",
    "connection failed",
    "unexpected eof",
    "ssl error",
    "could not connect",
    "connection refused",
    "too many connections",
    "server closed the connection",
    "connection is closed",
    "connection already closed",
    "terminating connection",
    "consuming input failed",
    "database system is not yet accepting",
)


def is_transient_database_error(exc: BaseException) -> bool:
    """True when the error is likely a short-lived Postgres/connection blip."""

    if not isinstance(exc, DatabaseError):
        return False
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


def reset_broken_database_state() -> None:
    """Clear broken atomic/rollback state and drop dead pooled connections."""
    from django.db import connection, transaction

    try:
        if connection.in_atomic_block:
            transaction.set_rollback(True)
        elif connection.needs_rollback:
            connection.rollback()
    except Exception:
        pass
    try:
        connection.close_if_unusable_or_obsolete()
    except Exception:
        pass


WORKFLOW_PROGRESS_PATH_PREFIX = "/platform-runtime/workflow-progress/"
CONTROL_PLANE_PATH_PREFIX = "/super/"


def is_workflow_progress_path(path: str) -> bool:
    return (path or "").startswith(WORKFLOW_PROGRESS_PATH_PREFIX)


def is_control_plane_path(path: str) -> bool:
    return (path or "").startswith(CONTROL_PLANE_PATH_PREFIX)


def request_wants_json(request) -> bool:
    path = getattr(request, "path", "") or ""
    accept = (request.META.get("HTTP_ACCEPT") or "").lower()
    if "application/json" in accept or "text/json" in accept:
        return True
    if path.startswith("/api/") or "/api/v1/" in path:
        return True
    xhr = (request.META.get("HTTP_X_REQUESTED_WITH") or "").lower()
    return xhr == "xmlhttprequest"
