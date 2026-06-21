"""Server-side realtime transport capability flags for browser clients.

WSGI (Gunicorn gthread) cannot upgrade WebSockets. SSE works on WSGI when
views use sync generators (see workflow_progress + assist_dock stream views).
ASGI (UvicornWorker) unlocks WebSocket WAL ingest via Django Channels.
"""

from __future__ import annotations

import os


def resolve_web_server_mode() -> str:
    """Return ``asgi`` or ``wsgi`` for the active web tier."""

    mode = (os.environ.get("WEB_SERVER_MODE") or "wsgi").strip().lower()
    if mode == "asgi":
        return "asgi"
    script = (os.environ.get("RMC_WEB_START_SCRIPT") or "").strip().lower()
    if "asgi" in script:
        return "asgi"
    return "wsgi"


def is_asgi_web_tier() -> bool:
    return resolve_web_server_mode() == "asgi"


def _env_truthy(key: str) -> bool | None:
    raw = (os.environ.get(key) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


def wal_stream_client_enabled() -> bool:
    """True only when ASGI is active AND the operator opted in."""

    explicit = _env_truthy("RMC_WAL_STREAM_ENABLED")
    if explicit is False:
        return False
    if not is_asgi_web_tier():
        return False
    return explicit is True


def sse_streams_client_enabled() -> bool:
    """SSE badge/workflow streams — supported on WSGI and ASGI."""

    explicit = _env_truthy("RMC_SSE_STREAMS_ENABLED")
    if explicit is False:
        return False
    return True


def resolve_realtime_client_config() -> dict[str, str | bool]:
    return {
        "webServerMode": resolve_web_server_mode(),
        "walStreamEnabled": wal_stream_client_enabled(),
        "sseStreamsEnabled": sse_streams_client_enabled(),
    }
