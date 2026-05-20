"""Tenant feature-flagged school help AI surface (/school/help/ai/)."""

from __future__ import annotations

from django.http import HttpResponseForbidden
from django.views.decorators.http import require_GET

from apps.platform_runtime.helpers import get_effective_flags
from apps.siteconfig.views_ai_center import ai_center


@require_GET
def school_help_ai(request):
    flags = get_effective_flags(request)
    if not flags.get("enable_ai_center_help", True):
        return HttpResponseForbidden("AI help is not enabled for this school.")
    return ai_center(request)
