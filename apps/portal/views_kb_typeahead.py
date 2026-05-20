"""KB search typeahead JSON API (batch 1339)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.portal.help_governance import ai_help_enabled_for_request
from apps.portal.help_search_intelligence import kb_typeahead_suggestions


@login_required
@require_GET
def api_kb_typeahead(request):
    q = (request.GET.get("q") or "").strip()
    if not ai_help_enabled_for_request(request):
        return JsonResponse({"success": True, "suggestions": [], "disabled": True})
    suggestions = kb_typeahead_suggestions(request, q, limit=8)
    return JsonResponse({"success": True, "suggestions": suggestions, "query": q})
