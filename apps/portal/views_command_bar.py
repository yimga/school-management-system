"""
Permission-aware universal command bar API (Cmd+K backend).
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.portal.views_ai_gateway import _actor_roles, _gateway_rate_limit, _school_id
from services.ai.command_bar import search_command_bar

logger = logging.getLogger(__name__)

_GATEWAY_VIEW_ERRORS = (
    AttributeError,
    ImportError,
    TypeError,
    ValueError,
    OSError,
    RuntimeError,
    KeyError,
)


@require_http_methods(["GET", "POST"])
@csrf_protect
@login_required
def api_command_bar_search(request):
    """
    GET/POST q=...&active_url=...
    Returns topology matches + optional engine-room doc snippet.
    """
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        if request.method == "POST":
            body = json.loads(request.body) if request.body else {}
        else:
            body = request.GET
        query = (body.get("q") or body.get("query") or "").strip()[:500]
        from apps.portal.ai_surface_context import build_ai_surface_context

        surface = build_ai_surface_context(request)
        active_url = (
            (body.get("active_url") or body.get("path") or surface.get("current_path") or "")
            .strip()[:500]
        )
        if not query:
            return JsonResponse({"success": False, "error": "q required"}, status=400)

        user = request.user
        school = getattr(request, "school", None)
        include_ai = str(body.get("include_ai", "0")).lower() in ("1", "true", "yes")
        payload = search_command_bar(
            user,
            query,
            active_url=active_url,
            school=school,
            actor_roles=_actor_roles(request),
            actor_is_staff=bool(getattr(user, "is_staff", False)),
            actor_is_superuser=bool(getattr(user, "is_superuser", False)),
            include_ai_snippet=include_ai,
        )
        return JsonResponse(
            {
                "success": True,
                "query": query,
                "active_url": active_url,
                "school_id": _school_id(request),
                **payload,
            }
        )
    except _GATEWAY_VIEW_ERRORS as exc:
        logger.warning("command bar search failed: %s", exc)
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)
