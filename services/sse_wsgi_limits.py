"""WSGI-safe SSE connection duration caps (Render / Gunicorn).

Long ``while True`` SSE loops on sync/gthread workers block threads and can
starve ``/health/`` when Render's probe timeout is only 5 seconds.
"""

from __future__ import annotations

import os


def wsgi_sse_max_duration_seconds(
    *,
    env_key: str = "WORKFLOW_PROGRESS_SSE_MAX_SECONDS",
    default_seconds: float = 25.0,
    gunicorn_margin_seconds: float = 5.0,
    hard_cap_seconds: float = 60.0,
) -> float:
    """Seconds to hold one SSE connection before emitting a graceful close frame."""

    raw = (os.environ.get(env_key) or "").strip()
    if raw:
        try:
            return max(5.0, min(float(raw), hard_cap_seconds))
        except ValueError:
            pass
    gunicorn_raw = (os.environ.get("GUNICORN_TIMEOUT") or "").strip()
    if gunicorn_raw:
        try:
            worker_timeout = float(gunicorn_raw)
            return max(
                5.0,
                min(worker_timeout - gunicorn_margin_seconds, hard_cap_seconds),
            )
        except ValueError:
            pass
    return default_seconds
