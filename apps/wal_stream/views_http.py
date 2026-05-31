"""HTTP fallback for /ws/wal/ when the request is not upgraded to WebSocket."""

from __future__ import annotations

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET", "HEAD", "POST"])
def wal_websocket_http_stub(request):
    """
    WSGI cannot serve Channels WebSockets. Without this view, unmatched /ws/wal/
    requests fall through manager middleware and return 302 to login.
    """

    if not getattr(request.user, "is_authenticated", False):
        return HttpResponse(status=401)
    return JsonResponse(
        {
            "error": "websocket_requires_asgi",
            "detail": "WAL ingest requires ASGI (Daphne) with Channels routing.",
        },
        status=426,
    )
