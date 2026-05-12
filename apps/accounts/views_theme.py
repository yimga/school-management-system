"""
Theme system v2 (2026-05-12): server-side persistence of the user's tri-mode
theme preference. The browser writes localStorage for instant first-paint;
this endpoint syncs to DashboardUserPreference.theme_preference (the canonical
field the context processor reads) so the choice survives device changes and
SSR can paint the correct theme before paint.

POST /api/preferences/theme/
  body: { "theme": "light" | "dark" | "system" }
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)
VALID_THEMES = {"light", "dark", "system"}


@require_http_methods(["POST"])
@csrf_protect
@login_required
def set_theme_preference(request: HttpRequest) -> JsonResponse:
    try:
        body = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    theme = (body.get("theme") or "").strip().lower()
    if theme not in VALID_THEMES:
        return JsonResponse(
            {"success": False, "error": f"theme must be one of {sorted(VALID_THEMES)}"},
            status=400,
        )

    try:
        # DashboardUserPreference is the canonical source that the siteconfig
        # context processor reads to emit USER_THEME_PREFERENCE on every request.
        from apps.siteconfig.models_dashboard import DashboardUserPreference

        pref, _created = DashboardUserPreference.objects.get_or_create(user=request.user)
        pref.theme_preference = theme
        pref.save(update_fields=["theme_preference"] if hasattr(pref, "save") else None)
    except (DatabaseError, AttributeError, ImportError) as exc:
        logger.warning("Failed to persist theme preference: %s", exc)
        return JsonResponse({"success": False, "error": "Persistence failed"}, status=503)

    return JsonResponse({"success": True, "theme": theme})
