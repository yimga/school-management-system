"""Server-Sent Events stream for bundle progress (v3.29).

Single endpoint:

    GET /api/v1/bundles/<pk>/events/stream/    (text/event-stream)

Streams ``MigrationProgressEvent`` rows for the bundle as they're
created. Frames follow the SSE spec::

    event: <kind>
    id: <event_pk>
    data: <json>

Heartbeat: a ``: ping\\n\\n`` comment line every 30s keeps proxies from
half-closing the socket. The stream closes gracefully after 60s so a
client connected to a Heroku-style ≤30-worker setup doesn't tie a worker
forever; clients should reconnect.

**Production note**: SSE under Django's sync request flow ties up a
worker for the connection's lifetime. Production deployments serving SSE
should run under ASGI/Daphne (or size Gunicorn worker count
appropriately).

Defense-in-depth: tenant scoping is enforced by ``BundleViewSet`` —
this stream is mounted as a ``@action`` so ``get_object`` runs the
queryset filter first.
"""

from __future__ import annotations

import json
import logging
import time

from django.conf import settings
from django.http import StreamingHttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.decorators import action

logger = logging.getLogger(__name__)


# Stream tuning knobs. Conservative defaults; operators with edge-proxy
# clean-up windows can tune these in a follow-up via RuntimeDefaults.
SSE_TICK_SECONDS = 1.0
SSE_HEARTBEAT_SECONDS = 30.0
SSE_MAX_DURATION_SECONDS = 60.0

# v3.33.0 — transport-mode SOT. Mirrors ``settings.MIGRATION_CLOUD_SSE_TRANSPORT``
# with a safe fallback default so test environments without the setting still
# resolve. See ``docs/SSE_DAPHNE_DEPLOYMENT.md`` for the runbook.
SSE_TRANSPORT_WSGI_FALLBACK = "wsgi-fallback"
SSE_TRANSPORT_ASGI_DAPHNE = "asgi-daphne"
SSE_TRANSPORT_DEFAULT = SSE_TRANSPORT_WSGI_FALLBACK


def _resolved_transport() -> str:
    """Return the configured transport mode, defaulting safely."""
    value = getattr(settings, "MIGRATION_CLOUD_SSE_TRANSPORT", None)
    if not value:
        return SSE_TRANSPORT_DEFAULT
    normalized = str(value).strip().lower()
    if normalized in (SSE_TRANSPORT_WSGI_FALLBACK, SSE_TRANSPORT_ASGI_DAPHNE):
        return normalized
    return SSE_TRANSPORT_DEFAULT


def _format_sse_frame(event_id, kind, payload) -> bytes:
    """Format one event as an SSE frame. Returns bytes for the wire."""
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    if kind:
        parts.append(f"event: {kind}")
    parts.append("data: " + json.dumps(payload, default=str))
    parts.append("")  # blank line terminates the frame
    return ("\n".join(parts) + "\n").encode("utf-8")


def _generate_snapshot(bundle):
    """Yield exactly one frame + stream-close sentinel and return.

    Used when ``MIGRATION_CLOUD_SSE_TRANSPORT == "wsgi-fallback"``: a
    sync Gunicorn worker can't safely hold a connection open for 60s
    without burning a whole worker per active SSE client. Instead we
    emit a single ``bundle.status`` snapshot, immediately follow with a
    ``stream.close`` sentinel carrying ``transport: "wsgi-fallback"``,
    and close the response. Clients can re-poll on a timer.
    """
    yield _format_sse_frame(
        event_id="init",
        kind="bundle.status",
        payload={
            "bundle_id": bundle.pk,
            "status": bundle.status,
            "updated_at": bundle.updated_at.isoformat() if bundle.updated_at else None,
            "transport": SSE_TRANSPORT_WSGI_FALLBACK,
        },
    )
    yield _format_sse_frame(
        event_id="close",
        kind="stream.close",
        payload={
            "reason": "wsgi-fallback-one-shot",
            "reconnect": True,
            "transport": SSE_TRANSPORT_WSGI_FALLBACK,
        },
    )


def _generate_stream(bundle):
    """Yield SSE frames for the bundle until max-duration elapses.

    Polls ``MigrationProgressEvent`` on a short tick. We open the
    connection with an initial bundle-status frame so clients see SOMETHING
    even on a quiet bundle. Heartbeat comment lines keep proxies happy.
    """
    from apps.migration_cloud.models import MigrationProgressEvent

    start = time.monotonic()
    last_heartbeat = start
    last_event_id = 0

    # Initial frame — current status snapshot.
    yield _format_sse_frame(
        event_id="init",
        kind="bundle.status",
        payload={
            "bundle_id": bundle.pk,
            "status": bundle.status,
            "updated_at": bundle.updated_at.isoformat() if bundle.updated_at else None,
        },
    )

    while True:
        now = time.monotonic()
        if now - start >= SSE_MAX_DURATION_SECONDS:
            # Graceful close — emit a sentinel and exit.
            yield _format_sse_frame(
                event_id="close",
                kind="stream.close",
                payload={"reason": "max-duration-reached", "reconnect": True},
            )
            return

        # tenant-isolation-allow: sse-events-stream-already-tenant-scoped-via-get-object
        new_events = (
            MigrationProgressEvent.objects
            .filter(bundle=bundle, pk__gt=last_event_id)
            .order_by("pk")[:100]
        )
        emitted_any = False
        for event in new_events:
            last_event_id = event.pk
            yield _format_sse_frame(
                event_id=event.pk,
                kind=event.kind,
                payload={
                    "id": event.pk,
                    "kind": event.kind,
                    "stage": event.stage,
                    "message": event.message,
                    "detail": event.detail,
                    "created_at": event.created_at.isoformat(),
                },
            )
            emitted_any = True

        if not emitted_any and (now - last_heartbeat) >= SSE_HEARTBEAT_SECONDS:
            yield b": ping\n\n"
            last_heartbeat = now

        time.sleep(SSE_TICK_SECONDS)


def events_stream_action_factory():
    """Return an ``@action`` method registering the SSE endpoint on a viewset."""

    @action(detail=True, methods=["get"], url_path="events/stream")
    @extend_schema(
        tags=["Migration Cloud"],
        summary="Stream bundle progress events as SSE",
        description=(
            "Returns ``text/event-stream``. Each event is a ``data: {json}`` "
            "frame; heartbeat ``: ping`` comment lines arrive every 30s "
            "while the bundle is quiet. The connection closes gracefully "
            "after 60s; clients should reconnect with EventSource's built-in "
            "retry semantics.\n\n"
            "**Production deployments** running Django under sync Gunicorn "
            "workers should size workers accordingly — each SSE connection "
            "ties up one worker. ASGI/Daphne is preferred for SSE-heavy "
            "tenants."
        ),
        responses={
            200: OpenApiResponse(
                description="text/event-stream of SSE frames",
            ),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Bundle not found"),
        },
    )
    def events_stream(self, request, pk=None):
        bundle = self.get_object()
        transport = _resolved_transport()
        # WSGI-safe mode: one-shot snapshot + close. Avoids tying a sync
        # worker to a 60-second long-poll. Operator promotes to
        # ``asgi-daphne`` once SSE-aware ASGI workers are deployed.
        if transport == SSE_TRANSPORT_WSGI_FALLBACK:
            generator = _generate_snapshot(bundle)
        else:
            generator = _generate_stream(bundle)
        response = StreamingHttpResponse(
            generator,
            content_type="text/event-stream",
        )
        # Disable buffering at edge proxies; CDNs / nginx need explicit hints.
        response["Cache-Control"] = "no-cache, no-transform"
        response["X-Accel-Buffering"] = "no"
        response["X-Migration-Cloud-SSE-Transport"] = transport
        logger.info(
            "migration_cloud_sse_stream_open bundle_id=%s user_id=%s transport=%s",
            bundle.pk, getattr(request.user, "pk", None), transport,
        )
        return response

    return events_stream
