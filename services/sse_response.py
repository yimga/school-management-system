"""Django helper that wraps SSE generators with the per-worker concurrency cap.

Long-lived SSE streams each pin one gthread worker thread. ``guarded_sse_response``
only starts a stream when a concurrency slot is free (see
``services.sse_wsgi_limits.try_acquire_sse_slot``); otherwise it returns a tiny
200 event-stream that tells the client to back off and closes immediately, so
the worker thread is released at once instead of being held by another stream.
This keeps threads available for ``/health/`` and ordinary requests.
"""

from __future__ import annotations

from typing import Callable, Iterator

from django.http import StreamingHttpResponse

from services.sse_wsgi_limits import release_sse_slot, try_acquire_sse_slot


def _busy_iter(retry_ms: int) -> Iterator[bytes]:
    # Single frame: bump the client's EventSource reconnect delay, then end the
    # response so the worker thread is freed immediately (no slot consumed).
    yield (
        f"retry: {int(retry_ms)}\n"
        "event: busy\n"
        'data: {"reason": "sse_capacity"}\n\n'
    ).encode("utf-8")


def guarded_sse_response(
    stream_factory: Callable[[], Iterator[bytes]],
    *,
    content_type: str = "text/event-stream",
    busy_retry_ms: int = 30000,
) -> StreamingHttpResponse:
    """Return an SSE response only if a concurrency slot is available.

    ``stream_factory`` is a zero-arg callable returning the SSE byte generator.
    When the per-worker cap is reached, the client receives a graceful busy frame
    (with a longer ``retry``) instead of a pinned thread.
    """

    if not try_acquire_sse_slot():
        response = StreamingHttpResponse(
            _busy_iter(busy_retry_ms), content_type=content_type
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _guarded() -> Iterator[bytes]:
        try:
            yield from stream_factory()
        finally:
            release_sse_slot()

    response = StreamingHttpResponse(_guarded(), content_type=content_type)
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
