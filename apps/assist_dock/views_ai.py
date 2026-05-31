"""v4.00.94 Wave D — AI action + insights endpoints.

  POST /assist-dock/ai/<action_id>/    → run action through services.ai_helpers
  GET  /assist-dock/insights.json      → list current proactive insights
  POST /assist-dock/insights/clear/    → dismiss one insight by id
  GET  /assist-dock/ai/actions.json    → list registered actions (jsonable)

All endpoints are authenticated and CSRF-protected (Django default).
Per-request payloads are length-capped so a malicious client can't fan
out unbounded gateway calls.
"""

from __future__ import annotations

import json
import logging

from services.http_auth_guards import login_required_api as login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_safe

from .ai_actions import (
    actions_as_jsonable,
    all_actions,
    invoke_action,
)
from .insights import clear_insight, insight_as_jsonable, list_insights

logger = logging.getLogger(__name__)

# Cap body payload size so a runaway page_excerpt can't OOM the worker.
_MAX_BODY_BYTES = 8 * 1024


@login_required
@require_safe
def list_ai_actions(request):
    """Return all registered actions (label / icon / description / order)."""
    return JsonResponse({"actions": actions_as_jsonable(all_actions())})


@login_required
@require_http_methods(["POST"])
@csrf_protect
def invoke_ai_action_view(request, action_id):
    """Run a registered action and return its envelope as JSON.

    Body shape (all optional):

      {
        "page_path": "/portal/dashboard/",
        "page_excerpt": "Up to 2000 chars of context...",
        "user_query": "Why is this fee marked overdue?"
      }
    """
    raw = request.body or b""
    if len(raw) > _MAX_BODY_BYTES:
        return HttpResponseBadRequest("payload too large")
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("bad json")
    if not isinstance(body, dict):
        return HttpResponseBadRequest("body must be object")
    payload = invoke_action(
        action_id=action_id,
        request=request,
        page_path=str(body.get("page_path") or "")[:512],
        page_excerpt=str(body.get("page_excerpt") or "")[:2000],
        user_query=str(body.get("user_query") or "")[:512],
    )
    status = 200 if payload.get("ok") else 503
    return JsonResponse(payload, status=status)


@login_required
@require_safe
def list_insights_view(request):
    """Return the user's pending insights (optionally filtered by ?page=...)."""
    user_id = getattr(request.user, "pk", None)
    if not user_id:
        return JsonResponse({"insights": []})
    page = (request.GET.get("page") or "")[:256]
    items = list_insights(user_id, page_path=page)
    return JsonResponse({"insights": [insight_as_jsonable(i) for i in items]})


@login_required
@require_http_methods(["POST"])
@csrf_protect
def clear_insight_view(request):
    """Dismiss an insight by id. Body: ``{"insight_id": "..."}``."""
    raw = request.body or b""
    if len(raw) > 1024:
        return HttpResponseBadRequest("payload too large")
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("bad json")
    if not isinstance(body, dict):
        return HttpResponseBadRequest("body must be object")
    insight_id = str(body.get("insight_id") or "")[:128]
    if not insight_id:
        return HttpResponseBadRequest("insight_id required")
    user_id = getattr(request.user, "pk", None)
    if not user_id:
        return HttpResponseBadRequest("anonymous")
    removed = clear_insight(user_id, insight_id)
    return JsonResponse({"removed": bool(removed)})
