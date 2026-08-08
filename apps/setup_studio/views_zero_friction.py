"""Setup Studio 50X zero-friction JSON endpoints (tenant-scoped)."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from apps.setup_studio.zero_friction import (
    apply_recommended_setup,
    get_zero_friction_payload,
    what_is_blocking_launch,
)


def _school_from_request(request):
    school = getattr(request, "school", None)
    if school is None and hasattr(request, "user"):
        from apps.schools.models import SchoolMembership

        mem = (
            SchoolMembership.objects.filter(  # tenant-isolation-allow: primary-membership-resolves-tenant-context
                user=request.user,
                is_primary=True,
            )
            .select_related("school")
            .first()
        )
        if mem:
            school = mem.school
    return school


@login_required
@require_GET
def api_blockers(request):
    school = _school_from_request(request)
    if not school:
        return JsonResponse({"ok": False, "error": "school_required"}, status=400)
    return JsonResponse({"ok": True, **what_is_blocking_launch(school)})


@login_required
@require_GET
def api_zero_friction_payload(request):
    school = _school_from_request(request)
    if not school:
        return JsonResponse({"ok": False, "error": "school_required"}, status=400)
    return JsonResponse({"ok": True, "payload": get_zero_friction_payload(school)})


@login_required
@require_POST
def api_recommended_setup(request):
    school = _school_from_request(request)
    if not school:
        return JsonResponse({"ok": False, "error": "school_required"}, status=400)
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeError, json.JSONDecodeError):
        body = {}
    actor_id = getattr(request.user, "pk", None)
    result = apply_recommended_setup(school, actor_id=actor_id)
    auto_fix = body.get("auto_fix") or request.POST.get("auto_fix")
    if str(auto_fix).lower() in {"1", "true", "on", "yes"}:
        # "Fix automatically" must actually PERFORM safe setup (seed/align
        # registries, attach the default plan, create a starter academic year),
        # not merely recompute the score. The report lists what was fixed and
        # what still needs a human decision (blueprint choice, roster import).
        from apps.setup_studio.auto_repair import auto_repair_setup

        result["auto_repair"] = auto_repair_setup(school, actor_id=actor_id)
        # Re-read the recommendation after repair so the payload reflects the
        # new, higher health score and cleared blockers.
        result.update(apply_recommended_setup(school, actor_id=actor_id))
    return JsonResponse(result)
