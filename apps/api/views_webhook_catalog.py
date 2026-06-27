"""
Pass 12: public webhook event-type catalog.

GET /api/v1/webhooks/event-types/ returns a JSON list of every event that
RunMyCampus can deliver to a tenant webhook subscription, with payload
schemas. The source of truth is apps.events.catalog.EVENT_CATALOG so this
endpoint never goes out of date.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.throttling import (
    ApiPublicReadThrottle,
    ApiReadThrottle,
    ApiSoftWarnHeaderMixin,
)


@extend_schema(
    tags=["Webhooks"],
    summary="List webhook event types",
    description=(
        "Returns every event RunMyCampus can deliver to a webhook subscription, "
        "plus the payload schema (required + optional keys), description, retry "
        "policy, and schema version. Public — no authentication required. Stable "
        "URL — safe to cache for 5 minutes."
    ),
    auth=[],
    responses={200: dict},
)
class WebhookEventTypesView(ApiSoftWarnHeaderMixin, APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    # Anonymous callers limited per-IP; authenticated callers per-user.
    throttle_classes = [ApiPublicReadThrottle, ApiReadThrottle]

    def get(self, request):
        try:
            from apps.events.catalog import EVENT_CATALOG
        except ImportError:
            return Response({"events": [], "count": 0})

        events = []
        for event_type, schema in sorted(EVENT_CATALOG.items()):
            payload = {
                "event_type": event_type,
                "description": schema.get("description", ""),
                "schema_version": schema.get("schema_version", "1.0"),
                "retry_policy": schema.get("retry_policy", "default"),
                "payload": {
                    "required": list(schema.get("payload_required_keys", ()) or ()),
                    "optional": list(schema.get("payload_optional_keys", ()) or ()),
                },
            }
            events.append(payload)

        response = Response(
            {
                "events": events,
                "count": len(events),
                "doc_url": "https://docs.runmycampus.com/webhooks/",
            }
        )
        response["Cache-Control"] = "public, max-age=300"
        return response
