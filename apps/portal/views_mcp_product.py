"""HTTP JSON surface for product MCP scaffold (batch 1395)."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from services.ai.mcp_product_server import invoke_tool, list_tools, mcp_enabled


@require_http_methods(["GET"])
@login_required
def api_mcp_list_tools(request):
    if not mcp_enabled():
        return JsonResponse(
            {
                "success": False,
                "error": "RMC_PRODUCT_MCP_ENABLED is off — enable when external MCP client is ready.",
                "lane": "external",
            },
            status=503,
        )
    return JsonResponse({"success": True, "tools": list_tools()})


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_mcp_invoke_tool(request):
    if not mcp_enabled():
        return JsonResponse(
            {
                "success": False,
                "error": "RMC_PRODUCT_MCP_ENABLED is off",
                "lane": "external",
            },
            status=503,
        )
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"success": False, "error": "invalid json"}, status=400)
    name = (body.get("name") or body.get("tool") or "").strip()
    if not name:
        return JsonResponse({"success": False, "error": "name required"}, status=400)
    args = body.get("arguments") if isinstance(body.get("arguments"), dict) else {}
    result = invoke_tool(
        name,
        args,
        user=request.user,
        school=getattr(request, "school", None),
    )
    return JsonResponse({"success": bool(result.get("ok")), "result": result})
