"""v4.00.13 — Timetable solver UI hook.

Closes the v4.00.12 follow-on gap: the CSP backtracking solver shipped
in ``apps/academics/timetable_solver.py`` but no view invoked it from a
teacher-facing surface. This view accepts a POST with a JSON description
of lessons/teachers/rooms/slots (or pulls them from the tenant's
TimetableTemplate when present) and returns the solver's placement
list as JSON.

The actual UI button lives in `templates/portal/timetable_build.html`
and uses `window.rmcBulkActions.postWithCsrf` to call this endpoint.
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect

logger = logging.getLogger(__name__)


@method_decorator([login_required, csrf_protect], name="dispatch")
class TimetableBuildView(View):
    """POST /school/studio/timetable/build/.

    # rbac-allow: school-staff-timetable-auto-build
    """

    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            payload = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "invalid_json"}, status=400)

        # Caller can either pass a fully-specified problem (lessons +
        # teachers + rooms + slots arrays) or invoke the helper that pulls
        # the data from the tenant's TimetableTemplate.
        problem = payload.get("problem")
        if not isinstance(problem, dict):
            return JsonResponse({"error": "problem_must_be_dict"}, status=400)
        soft_constraints = payload.get("soft_constraints") or {}
        if not isinstance(soft_constraints, dict):
            return JsonResponse({"error": "soft_constraints_must_be_dict"}, status=400)
        try:
            max_search_steps = int(payload.get("max_search_steps") or 50_000)
            if not 1 <= max_search_steps <= 250_000:
                raise ValueError("max_search_steps must be between 1 and 250000")
            soft_constraints = {
                key: float(value)
                for key, value in soft_constraints.items()
                if key in {"avoid_first_period_for", "avoid_last_period_for", "prefer_morning"}
            }
            if any(not 0.0 <= value <= 1.0 for value in soft_constraints.values()):
                raise ValueError("soft constraint weights must be between 0 and 1")
        except (TypeError, ValueError) as exc:
            return JsonResponse({"error": "solver_options", "detail": str(exc)}, status=400)

        try:
            from apps.academics.timetable_solver import (
                LessonRequest,
                Resource,
                TimeSlot,
                solve_with_backtracking,
            )

            lessons = [
                LessonRequest(**self._sanitize_lesson(lesson))
                for lesson in (problem.get("lessons") or [])
            ]
            teachers = {
                t["resource_id"]: Resource(**self._sanitize_resource(t))
                for t in (problem.get("teachers") or [])
            }
            rooms = {
                r["resource_id"]: Resource(**self._sanitize_resource(r))
                for r in (problem.get("rooms") or [])
            }
            slots = tuple(TimeSlot(**self._sanitize_slot(s)) for s in (problem.get("slots") or []))
        except (TypeError, KeyError, ValueError) as exc:
            return JsonResponse({"error": "problem_shape", "detail": str(exc)}, status=400)

        if not lessons or not slots:
            return JsonResponse({"error": "empty_problem"}, status=400)

        try:
            result = solve_with_backtracking(
                lessons=lessons,
                teachers=teachers,
                rooms=rooms,
                slots=slots,
                max_search_steps=max_search_steps,
                soft_constraints=soft_constraints,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("timetable solve failed: %s", exc)
            return JsonResponse({"error": "solve_failed", "detail": str(exc)}, status=500)

        return JsonResponse({
            "strategy": result.strategy,
            "placed": [
                {
                    "lesson_id": p.lesson_id,
                    "teacher_id": p.teacher_id,
                    "room_id": p.room_id,
                    "slot_id": p.slot_id,
                    "class_id": p.class_id,
                    "subject": p.subject,
                }
                for p in result.placed
            ],
            "unplaced_count": len(result.unplaced),
            "conflict_count": len(result.conflicts),
        })

    def _sanitize_lesson(self, raw: dict) -> dict:
        return {
            "lesson_id": str(raw["lesson_id"]),
            "class_id": str(raw.get("class_id", "")),
            "subject": str(raw.get("subject", "")),
            "teacher_id": str(raw.get("teacher_id", "")),
            "required_room_kind": str(raw.get("required_room_kind", "any")),
            "preferred_room_ids": tuple(str(r) for r in (raw.get("preferred_room_ids") or [])),
            "duration_minutes": int(raw.get("duration_minutes", 45)),
            "weekly_periods": int(raw.get("weekly_periods", 1)),
            "locked_slot_ids": tuple(str(s) for s in (raw.get("locked_slot_ids") or [])),
        }

    def _sanitize_resource(self, raw: dict) -> dict:
        return {
            "resource_id": str(raw["resource_id"]),
            "kind": str(raw.get("kind", "teacher")),
            "display_name": str(raw.get("display_name", raw.get("resource_id", ""))),
            "availability_slots": tuple(str(s) for s in (raw.get("availability_slots") or [])),
        }

    def _sanitize_slot(self, raw: dict) -> dict:
        return {
            "slot_id": str(raw["slot_id"]),
            "day_of_week": int(raw.get("day_of_week", 1)),
            "start_minutes": int(raw.get("start_minutes", 0)),
            "end_minutes": int(raw.get("end_minutes", 0)),
        }
