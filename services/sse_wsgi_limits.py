"""WSGI-safe SSE connection duration caps (Render / Gunicorn).

Long ``while True`` SSE loops on sync/gthread workers block threads and can
starve ``/health/`` when Render's probe timeout is only 5 seconds.
"""

from __future__ import annotations

import os
import threading


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


# ---------------------------------------------------------------------------
# Concurrency cap — keep SSE streams from starving /health/ and normal traffic.
#
# Each long-lived SSE connection pins one gthread worker thread for its whole
# lifetime. With ``GUNICORN_THREADS=4`` and two persistent EventSource streams
# per browser tab (workflow-progress + assist-dock), a couple of open tabs can
# occupy every thread, leaving none for Render's /health/ probe (5s timeout) —
# the instance is then restarted, 502s trigger a reconnect storm, and the loop
# repeats. This bounded semaphore reserves threads so SSE can never consume the
# whole pool. Excess stream requests get a cheap, instantly-closed response so
# they release the thread immediately instead of blocking.
# ---------------------------------------------------------------------------

_sse_semaphore_lock = threading.Lock()
_sse_semaphore: threading.BoundedSemaphore | None = None
_sse_semaphore_capacity: int | None = None


def sse_stream_capacity(
    *,
    env_key: str = "SSE_MAX_CONCURRENT_STREAMS",
    thread_reserve_env: str = "SSE_THREAD_RESERVE",
    default_reserve: int = 2,
) -> int:
    """Max SSE streams a single worker process may hold open at once.

    Explicit ``SSE_MAX_CONCURRENT_STREAMS`` wins. Otherwise derive it from the
    gthread thread count minus a reserve (default 2) so ``/health/`` and normal
    requests always have a free thread. Never returns less than 1.
    """

    raw = (os.environ.get(env_key) or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    threads_raw = (os.environ.get("GUNICORN_THREADS") or "").strip()
    try:
        threads = int(threads_raw) if threads_raw else 4
    except ValueError:
        threads = 4
    reserve_raw = (os.environ.get(thread_reserve_env) or "").strip()
    try:
        reserve = int(reserve_raw) if reserve_raw else default_reserve
    except ValueError:
        reserve = default_reserve
    return max(1, threads - reserve)


def _get_sse_semaphore() -> threading.BoundedSemaphore:
    global _sse_semaphore, _sse_semaphore_capacity
    if _sse_semaphore is None:
        with _sse_semaphore_lock:
            if _sse_semaphore is None:
                _sse_semaphore_capacity = sse_stream_capacity()
                _sse_semaphore = threading.BoundedSemaphore(_sse_semaphore_capacity)
    return _sse_semaphore


def try_acquire_sse_slot() -> bool:
    """Non-blocking acquire of one SSE slot. False when the cap is reached."""

    return _get_sse_semaphore().acquire(blocking=False)


def release_sse_slot() -> None:
    """Release a slot acquired by :func:`try_acquire_sse_slot` (over-release safe)."""

    try:
        _get_sse_semaphore().release()
    except ValueError:
        # BoundedSemaphore raises if released more times than acquired; ignore
        # so a double-release in a generator's finally can never crash a worker.
        pass
