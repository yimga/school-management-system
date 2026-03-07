"""
Part F Section 16.3: GraphQL gateway — full schema via graphene-django.
POST /graphql/ with JSON body { "query": "query { health me { username } schoolCount }" }.
Uses config.schema (Query: health, me, schoolCount, schools).
"""
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from config.schema import schema


@require_http_methods(["GET", "POST"])
@csrf_exempt
def graphql_gateway(request):
    if request.method == "GET":
        return JsonResponse({
            "data": {
                "health": "ok",
                "message": "GraphQL gateway. POST a query. Supported: health, me { username email isStaff }, schoolCount, schools { id name slug } (staff only). Introspection enabled.",
            },
        })
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"errors": [{"message": "Invalid JSON"}]}, status=400)
    query = (body.get("query") or "").strip()
    if not query:
        return JsonResponse({"errors": [{"message": "Missing query"}]}, status=400)
    variables = body.get("variables") or {}
    operation_name = body.get("operationName")

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
