"""Detect transient PostgreSQL outages (recovery, SSL drop, connection reset)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse

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

_RETRY_AFTER_SECONDS = 30
_UNAVAILABLE_MESSAGE = (
    "The database is temporarily unavailable. Please wait a moment and try again."
)

_DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / "debug-a48ae2.log"


def _agent_debug_log(
    location: str,
    message: str,
    data: dict,
    hypothesis_id: str,
    *,
    run_id: str = "pre-fix",
) -> None:
    # #region agent log
    payload = {
        "sessionId": "a48ae2",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except OSError:
        pass
    # #endregion


def _message_matches_transient_markers(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


def _single_exception_is_transient(exc: BaseException) -> bool:
    if isinstance(exc, DatabaseError) and _message_matches_transient_markers(exc):
        return True
    try:
        from psycopg import Error as PsycopgError

        if isinstance(exc, PsycopgError) and _message_matches_transient_markers(exc):
            return True
    except ImportError:
        pass
    return False


def is_transient_database_error(exc: BaseException) -> bool:
    """True when the error is likely a short-lived Postgres/connection blip."""

    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if _single_exception_is_transient(current):
            # #region agent log
            _agent_debug_log(
                "transient_db.py:is_transient_database_error",
                "transient db error detected",
                {
                    "exc_type": type(current).__name__,
                    "message": str(current)[:160],
                    "root_type": type(exc).__name__,
                },
                "H3",
            )
            # #endregion
            return True
        current = current.__cause__ or current.__context__
    return False


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


def _minimal_503_html(*, control_plane: bool) -> str:
    title = (
        "Manager temporarily unavailable"
        if control_plane
        else "Service temporarily unavailable"
    )
    heading = (
        "Platform maintenance in progress."
        if control_plane
        else "We'll be right back."
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="{_RETRY_AFTER_SECONDS}">
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #111827; background: #f8fafc; }}
    main {{ max-width: 36rem; margin: 4rem auto; padding: 2rem; background: #fff; border-radius: 12px; box-shadow: 0 8px 24px rgba(15,23,42,.08); }}
    h1 {{ font-size: 1.5rem; margin: 0 0 1rem; }}
    p {{ line-height: 1.5; margin: 0 0 1.5rem; }}
    button {{ font: inherit; padding: .65rem 1rem; border-radius: 8px; border: 0; background: #4f46e5; color: #fff; cursor: pointer; }}
  </style>
</head>
<body>
  <main>
    <div aria-hidden="true" style="font-size:3rem;font-weight:700;opacity:.2;">503</div>
    <h1>{heading}</h1>
    <p>{_UNAVAILABLE_MESSAGE}</p>
    <button type="button" onclick="window.location.reload()">Try again</button>
  </main>
</body>
</html>"""


def build_transient_db_unavailable_response(request, *, source: str = "middleware"):
    """Return a retryable 503 without touching the database or context processors."""

    path = getattr(request, "path", "") or ""
    payload = {
        "error": "database_unavailable",
        "retryable": True,
        "detail": _UNAVAILABLE_MESSAGE,
    }

    # #region agent log
    _agent_debug_log(
        "transient_db.py:build_transient_db_unavailable_response",
        "building db-free 503",
        {"path": path, "source": source, "wants_json": request_wants_json(request)},
        "H4",
    )
    # #endregion

    if is_workflow_progress_path(path):
        wants_sse = "stream" in path or "text/event-stream" in (
            request.META.get("HTTP_ACCEPT") or ""
        ).lower()
        if wants_sse:
            body = (
                f"retry: {_RETRY_AFTER_SECONDS * 1000}\n"
                f"event: unavailable\n"
                f"data: {json.dumps(payload)}\n\n"
            )
            response = HttpResponse(
                body,
                status=503,
                content_type="text/event-stream; charset=utf-8",
            )
            response["Retry-After"] = str(_RETRY_AFTER_SECONDS)
            return response

    if request_wants_json(request):
        response = JsonResponse(payload, status=503)
        response["Retry-After"] = str(_RETRY_AFTER_SECONDS)
        return response

    response = HttpResponse(
        _minimal_503_html(control_plane=is_control_plane_path(path)),
        status=503,
        content_type="text/html; charset=utf-8",
    )
    response["Retry-After"] = str(_RETRY_AFTER_SECONDS)
    return response
