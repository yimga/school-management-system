"""
Part F Section 16.3: GraphQL gateway — full schema via graphene-django.
POST /graphql/ with JSON body { "query": "query { health me { username } schoolCount }" }.
Uses config.schema (Query: health, me, schoolCount, schools).
"""

import json
import logging
import re

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.api.rate_limit import throttle_ip_request
from config.schema import schema

logger = logging.getLogger(__name__)

_INTROSPECTION_RE = re.compile(r"\b__schema\b|\b__type\b|IntrospectionQuery", re.I)


def _introspection_allowed() -> bool:
    explicit = getattr(settings, "GRAPHQL_INTROSPECTION_ENABLED", None)
    if explicit is not None:
        return bool(explicit)
    return bool(getattr(settings, "DEBUG", False))


@require_http_methods(["GET", "POST"])
@csrf_exempt
def graphql_gateway(request):
    if request.method == "GET":
        allowed, retry_after = throttle_ip_request(
            request,
            scope="graphql_gateway_get",
            max_count=60,
            window_seconds=60,
        )
        if not allowed:
            return JsonResponse(
                {"errors": [{"message": "Request limit exceeded. Retry later."}]},
                status=429,
                headers={"Retry-After": str(retry_after)},
            )
        return JsonResponse(
            {
                "data": {
                    "health": "ok",
                    "message": "GraphQL gateway. POST a query. Supported: health, me { username email isStaff }, schoolCount, schools { id name slug } (staff only). Introspection enabled.",
                },
            }
        )
    allowed, retry_after = throttle_ip_request(
        request,
        scope="graphql_gateway_post",
        max_count=120,
        window_seconds=60,
    )
    if not allowed:
        return JsonResponse(
            {"errors": [{"message": "Request limit exceeded. Retry later."}]},
            status=429,
            headers={"Retry-After": str(retry_after)},
        )
    content_type = (
        (
            (request.content_type or request.META.get("CONTENT_TYPE") or "").split(
                ";", 1
            )[0]
        )
        .strip()
        .lower()
    )
    if request.body and content_type != "application/json":
        return JsonResponse(
            {"errors": [{"message": "Content-Type must be application/json"}]},
            status=415,
        )
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"errors": [{"message": "Invalid JSON"}]}, status=400)
    if not isinstance(body, dict):
        return JsonResponse(
            {"errors": [{"message": "JSON object required"}]}, status=400
        )
    query = (body.get("query") or "").strip()
    if not query:
        return JsonResponse({"errors": [{"message": "Missing query"}]}, status=400)
    if not _introspection_allowed() and _INTROSPECTION_RE.search(query):
        return JsonResponse(
            {"errors": [{"message": "GraphQL introspection is disabled"}]},
            status=403,
        )
    variables = body.get("variables") or {}
    if not isinstance(variables, dict):
        return JsonResponse(
            {"errors": [{"message": "variables must be a JSON object"}]}, status=400
        )
    operation_name = body.get("operationName")
    if operation_name is not None and not isinstance(operation_name, str):
        return JsonResponse(
            {"errors": [{"message": "operationName must be a string"}]}, status=400
        )

    # Audit log for public_endpoint_audit §2.4 (no PII; operation + auth only)
    is_authenticated = getattr(request, "user", None) and getattr(
        request.user, "is_authenticated", False
    )
    logger.info(
        "graphql_gateway_post op=%s authenticated=%s",
        operation_name or "(anonymous)",
        is_authenticated,
        extra={"scope": "graphql_gateway_post"},
    )

    result = schema.execute(
        query,
        context=request,
        variable_values=variables,
        operation_name=operation_name,
    )
    payload = {}
    if result.data is not None:
        payload["data"] = result.data
    if result.errors:
        payload["errors"] = [{"message": str(e)} for e in result.errors]
    if not payload:
        payload = {"data": None, "errors": [{"message": "Unknown error"}]}
    status = 200
    if result.errors and result.data is None:
        status = 200
    return JsonResponse(payload, status=status)
