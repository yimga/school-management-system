"""Django helper that wraps SSE generators with the per-worker concurrency cap.

Long-lived SSE streams each pin one gthread worker thread. ``guarded_sse_response``
only starts a stream when a concurrency slot is free (see
``services.sse_wsgi_limits.try_acquire_sse_slot``); otherwise it returns a tiny
200 event-stream that tells the client to back off and closes immediately, so
the worker thread is released at once instead of being held by another stream.
This keeps threads available for ``/health/`` and ordinary requests.
"""

from __future__ import annotations

from typing import AsyncIterator, Callable, Iterator

from django.http import StreamingHttpResponse

from services.sse_wsgi_limits import release_sse_slot, try_acquire_sse_slot


def _busy_frame(retry_ms: int) -> bytes:
    # Single frame: bump the client's EventSource reconnect delay, then end the
    # response so the worker thread/coroutine is freed immediately (no slot held).
    return (
        f"retry: {int(retry_ms)}\n"
        "event: busy\n"
        'data: {"reason": "sse_capacity"}\n\n'
    ).encode("utf-8")


def _busy_iter(retry_ms: int) -> Iterator[bytes]:
    yield _busy_frame(retry_ms)


def guarded_sse_response(
    stream_factory: Callable[[], Iterator[bytes]],
    *,
    content_type: str = "text/event-stream",
    busy_retry_ms: int = 30000,  # magic-number-allow: millisecond-timeout
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


def guarded_async_sse_response(
    async_stream_factory: Callable[[], AsyncIterator[bytes]],
    *,
    content_type: str = "text/event-stream",
    busy_retry_ms: int = 30000,
) -> StreamingHttpResponse:
    """Async (ASGI) counterpart of :func:`guarded_sse_response`.

    ``async_stream_factory`` is a zero-arg callable returning an async byte
    iterator. The concurrency slot is acquired non-blockingly and released in
    the async generator's ``finally`` when the connection closes. Under ASGI an
    open SSE stream is a coroutine, not a pinned worker thread.
    """

    if not try_acquire_sse_slot():

        async def _busy() -> AsyncIterator[bytes]:
            yield _busy_frame(busy_retry_ms)

        response = StreamingHttpResponse(_busy(), content_type=content_type)
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    async def _guarded() -> AsyncIterator[bytes]:
        try:
            async for chunk in async_stream_factory():
                yield chunk
        finally:
            release_sse_slot()

    response = StreamingHttpResponse(_guarded(), content_type=content_type)
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
