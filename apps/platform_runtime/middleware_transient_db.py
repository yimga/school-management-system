"""Return 503 (not 500) during transient Postgres outages."""

from __future__ import annotations

import json
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin

from apps.platform_runtime.transient_db import (
    is_control_plane_path,
    is_transient_database_error,
    is_workflow_progress_path,
    request_wants_json,
    reset_broken_database_state,
)

logger = logging.getLogger(__name__)

_RETRY_AFTER_SECONDS = 30
_UNAVAILABLE_MESSAGE = (
    "The database is temporarily unavailable. Please wait a moment and try again."
)


class TransientDatabaseUnavailableMiddleware(MiddlewareMixin):
    """Map short-lived Postgres failures to a retryable 503 across operator and marketing surfaces."""

    def process_exception(self, request, exception):
        if not is_transient_database_error(exception):
            return None

        reset_broken_database_state()
        path = getattr(request, "path", "") or ""
        logger.warning(
            "transient_db_unavailable path=%s error=%s",
            path,
            str(exception)[:200],
        )

        payload = {
            "error": "database_unavailable",
            "retryable": True,
            "detail": _UNAVAILABLE_MESSAGE,
        }

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

        template = (
            "errors/503_control_plane.html"
            if is_control_plane_path(path)
            else "errors/503.html"
        )
        response = render(
            request,
            template,
            {"message": _UNAVAILABLE_MESSAGE},
            status=503,
        )
        response["Retry-After"] = str(_RETRY_AFTER_SECONDS)
        return response
