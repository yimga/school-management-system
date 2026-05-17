"""Field / feature explainer API for rmc_info_tag."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .ui_field_help import get_ui_field_help


@login_required
@require_GET
def tour_info_tag_api(request):
    """
    GET ?entity=invoice&field=status  OR  ?feature=finance.access
    Returns { title, body } for Bootstrap popovers.
    """
    entity = (request.GET.get("entity") or "").strip()
    field = (request.GET.get("field") or "").strip()
    feature = (request.GET.get("feature") or "").strip()
    payload = get_ui_field_help(entity, field, feature=feature)
    if not payload.get("title") and not payload.get("body"):
        return JsonResponse({"ok": False, "title": "", "body": ""}, status=404)
    return JsonResponse({"ok": True, **payload})
