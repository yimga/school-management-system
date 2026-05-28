"""Bulk POST endpoints for backend people list surfaces."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.people.bulk_student_actions import bulk_set_student_status, parse_student_id_list


def _parse_json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


@require_http_methods(["POST"])
@login_required
@permission_required("people.change_studentprofile", raise_exception=True)
def backend_student_bulk_status(request):
    payload = _parse_json_body(request)
    status = str(payload.get("status") or request.POST.get("status") or "").strip()
    student_ids = parse_student_id_list(payload.get("ids") or request.POST.getlist("ids"))

    school = getattr(request, "school", None)
    try:
        outcome = bulk_set_student_status(
            student_ids=student_ids, status=status, school=school
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    status_code = 200 if outcome.get("ok") else 422
    return JsonResponse(outcome, status=status_code)
