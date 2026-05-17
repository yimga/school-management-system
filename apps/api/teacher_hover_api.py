"""
Cross-module teacher hover context (academics ↔ operations): workload + primary room.
"""

import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@method_decorator(login_required, name="dispatch")
@method_decorator(require_http_methods(["GET"]), name="dispatch")
class TeacherHoverContextView(View):
    """
    GET ?teacher_id=N — active assignment count + sample classroom (HR/ops context for academic UIs).
    """

    def get(self, request):
        school = getattr(request, "school", None)
        if not school:
            return JsonResponse({"error": "no_school"}, status=400)
        try:
            tid = int(request.GET.get("teacher_id") or 0)
        except (TypeError, ValueError):
            return JsonResponse({"error": "bad_id"}, status=400)
        if tid < 1:
            return JsonResponse({"error": "bad_id"}, status=400)

        try:
            from apps.people.models import TeacherProfile

            tp = TeacherProfile.objects.filter(pk=tid, school_id=school.id).first()
            if not tp:
                return JsonResponse({"error": "not_found"}, status=404)

            from apps.evals.models import TeacherAssignment

            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            qs = TeacherAssignment.objects.filter(
                teacher_id=tid, is_active=True
            ).select_related("subject_assignment__classroom")
            n = qs.count()
            first = qs.first()
            room = "—"
            if first and getattr(first, "subject_assignment", None):
                sa = first.subject_assignment
                cr = getattr(sa, "classroom", None)
                if cr:
                    room = getattr(cr, "name", "") or getattr(cr, "code", "") or "—"

            return JsonResponse(
                {
                    "teacher_id": tid,
                    "active_assignments": n,
                    "primary_room": room,
                    "workload_summary": f"{n} active class assignment(s)",
                }
            )
        except Exception as e:
            logger.debug("teacher_hover: %s", e)
            return JsonResponse({"error": "server"}, status=500)
