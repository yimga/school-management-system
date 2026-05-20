"""JSON API for support deflection before ticket submit."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.portal.support_deflection import find_deflection_candidates, record_deflection_event


@login_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def api_support_deflection(request):
    """
    Return high-confidence KB matches for pre-ticket deflection.
    GET/POST: q, subject, description (combined into query text).
    """
    if request.method == "POST" and request.body:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            body = {}
    else:
        body = request.GET
    parts = [
        body.get("q") or body.get("query") or "",
        body.get("subject") or "",
        body.get("description") or body.get("message") or "",
    ]
    query_text = " ".join(p for p in parts if p).strip()
    bundle = find_deflection_candidates(request, query_text=query_text)
    if bundle.get("blocking"):
        record_deflection_event(
            request,
            query_text=query_text,
            articles=bundle.get("articles") or [],
            outcome="suggested",
            surface=(body.get("surface") or "support_ticket")[:64],
        )
    return JsonResponse({"success": True, **bundle})


@login_required
@csrf_protect
@require_http_methods(["POST"])
def api_support_deflection_ack(request):
    """User dismissed deflection or opened an article — telemetry only."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "invalid json"}, status=400)
    outcome = (body.get("outcome") or "dismissed")[:32]
    query_text = (body.get("query") or "")[:2000]
    articles = body.get("articles") if isinstance(body.get("articles"), list) else []
    record_deflection_event(
        request,
        query_text=query_text,
        articles=articles,
        outcome=outcome,
        surface=(body.get("surface") or "support_ticket")[:64],
    )
    return JsonResponse({"success": True})
