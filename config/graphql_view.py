"""
Part F Section 16.3: GraphQL gateway — minimal endpoint for API-first (GraphQL, webhook bus).
POST /graphql/ with JSON body { "query": "query { health }" } returns { "data": { "health": "ok" } }.
Extend with full schema (e.g. graphene-django) when needed.
"""
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET", "POST"])
@csrf_exempt
def graphql_gateway(request):
    if request.method == "GET":
        return JsonResponse({"data": {"health": "ok", "message": "GraphQL gateway (Part F 16.3). POST a query."}})
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"errors": [{"message": "Invalid JSON"}]}, status=400)
    query = (body.get("query") or "").strip()
    if not query:
        return JsonResponse({"errors": [{"message": "Missing query"}]}, status=400)
    # Minimal resolver: support query { health } and query { __typename }
    if "health" in query:
        return JsonResponse({"data": {"health": "ok"}})
    if "__typename" in query:
        return JsonResponse({"data": {"__typename": "Query"}})
    return JsonResponse({"data": {}, "errors": [{"message": "Unsupported query"}]}, status=200)
