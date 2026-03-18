"""
Form draft API for Section 26.5: save/load draft for long tenant-facing forms.
GET: return draft data for form_key (JSON).
POST: save draft (body: JSON { "data": { ... } }).
DELETE: clear draft for form_key.
"""

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from .models import FormDraft

logger = logging.getLogger(__name__)


def _get_school(request):
    return getattr(request, "school", None)


@login_required
@require_http_methods(["GET", "POST", "DELETE"])
def form_draft_api(request, form_key: str):
    """
    GET: return { "data": {...}, "updated_at": "iso" } or 404.
    POST: body JSON { "data": {...} }; create or update draft; return 200.
    DELETE: remove draft for this form_key; return 204.
    """
    school = _get_school(request)
    if not school:
        return JsonResponse({"error": "School context required"}, status=400)

    if request.method == "GET":
        draft = FormDraft.objects.filter(
            school=school,
            user=request.user,
            form_key=form_key,
        ).first()
        if not draft:
            return JsonResponse({"error": "No draft"}, status=404)
        return JsonResponse(
            {
                "data": draft.data,
                "updated_at": draft.updated_at.isoformat()
                if draft.updated_at
                else None,
            }
        )

    if request.method == "DELETE":
        FormDraft.objects.filter(
            school=school,
            user=request.user,
            form_key=form_key,
        ).delete()
        return HttpResponse(status=204)

    # POST
    try:
        body = json.loads(request.body) if request.body else {}
        data = body.get("data")
        if data is None:
            return JsonResponse({"error": "Missing 'data' in body"}, status=400)
        if not isinstance(data, dict):
            return JsonResponse({"error": "'data' must be an object"}, status=400)
    except json.JSONDecodeError as e:
        return JsonResponse({"error": f"Invalid JSON: {e}"}, status=400)

    draft, _ = FormDraft.objects.update_or_create(
        school=school,
        user=request.user,
        form_key=form_key,
        defaults={"data": data},
    )
    return JsonResponse(
        {
            "ok": True,
            "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
        }
    )
