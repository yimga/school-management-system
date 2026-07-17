"""
Pass 12: RFC 7807 problem+json exception handler for DRF.

Standard envelope (https://datatracker.ietf.org/doc/html/rfc7807):

    {
        "type":      "https://docs.runmycampus.com/errors/<slug>",
        "title":     "<short, human-readable summary>",
        "status":    <http status int>,
        "detail":    "<longer, human-readable explanation>",
        "instance":  "<request path>",
        "errors":    [ ... field-level details when applicable ... ]
    }

Configured via REST_FRAMEWORK["EXCEPTION_HANDLER"] in config/settings.py.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

_ERROR_DOC_BASE = "https://docs.runmycampus.com/errors/"
PROBLEM_CONTENT_TYPE = "application/problem+json"


def _slug_for(status_code: int) -> str:
    return {
        400: "validation",
        401: "unauthorized",
        403: "forbidden",
        404: "not-found",
        405: "method-not-allowed",
        409: "conflict",
        410: "gone",
        415: "unsupported-media-type",
        422: "unprocessable-entity",
        429: "rate-limited",
        500: "internal",
        502: "bad-gateway",
        503: "unavailable",
        504: "timeout",
    }.get(int(status_code), "unknown")


def _title_for(status_code: int) -> str:
    return {
        400: "Validation failed",
        401: "Authentication required",
        403: "Permission denied",
        404: "Resource not found",
        405: "Method not allowed",
        409: "Conflict",
        415: "Unsupported media type",
        422: "Unprocessable entity",
        429: "Too many requests",
        500: "Internal server error",
        502: "Bad gateway",
        503: "Service unavailable",
        504: "Upstream timeout",
    }.get(int(status_code), "Error")


def _detail_string(data: Any) -> str:
    """Coerce DRF's varied error payloads to a single user-facing string."""
    if isinstance(data, str):
        return data
    if isinstance(data, list) and data:
        return _detail_string(data[0])
    if isinstance(data, dict):
        if "detail" in data:
            return _detail_string(data["detail"])
        if data:
            first_key = next(iter(data))
            return _detail_string(data[first_key])
    return ""


def _coerce_field_errors(data: Any) -> list:
    """When the original DRF payload is a dict of field → [errors], flatten it."""
    if isinstance(data, dict):
        out = []
        for field, value in data.items():
            if field == "detail":
                continue
            if isinstance(value, list):
                out.extend({"field": field, "message": str(v)} for v in value)
            else:
                out.append({"field": field, "message": str(value)})
        return out
    if isinstance(data, list):
        return [{"message": str(item)} for item in data if not isinstance(item, str)]
    return []


def rfc7807_exception_handler(exc, context):
    """Wrap the DRF default handler with an RFC 7807 envelope."""
    response = drf_default_handler(exc, context)
    if response is None:
        # DRF's default handler maps only APIException, Http404 and DRF's
        # PermissionDenied, so a model save()/full_clean() that raises Django's own
        # ValidationError (e.g. a plan usage cap in apps/schools/plan_limits.py) would
        # otherwise fall through here to a 500. It is a client input error — surface it
        # as a 400 in the same envelope rather than a server error + Sentry capture.
        if isinstance(exc, DjangoValidationError):
            request = context.get("request") if isinstance(context, dict) else None
            instance = getattr(request, "path", "") if request is not None else ""
            error_messages = list(getattr(exc, "messages", []) or [])
            envelope = {
                "type": f"{_ERROR_DOC_BASE}{_slug_for(400)}",
                "title": _title_for(400),
                "status": 400,
                "detail": error_messages[0] if error_messages else _title_for(400),
                "instance": instance,
            }
            if len(error_messages) > 1:
                envelope["errors"] = [{"message": m} for m in error_messages]
            new_response = Response(envelope, status=400)
            new_response["Content-Type"] = PROBLEM_CONTENT_TYPE
            return new_response
        # Any other non-DRF exception — let Django handle it (500 page / Sentry capture).
        return None

    request = context.get("request") if isinstance(context, dict) else None
    instance = getattr(request, "path", "") if request is not None else ""
    status_code = response.status_code

    detail = _detail_string(response.data)
    errors = _coerce_field_errors(response.data)

    envelope = {
        "type": f"{_ERROR_DOC_BASE}{_slug_for(status_code)}",
        "title": _title_for(status_code),
        "status": status_code,
        "detail": detail or _title_for(status_code),
        "instance": instance,
    }
    if errors:
        envelope["errors"] = errors

    new_response = Response(envelope, status=status_code)
    new_response["Content-Type"] = PROBLEM_CONTENT_TYPE
    return new_response
