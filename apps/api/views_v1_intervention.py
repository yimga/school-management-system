"""
API v1 intervention endpoints (2.1 giant-file decomposition).
Red flags, risk calculation, action center, roadmap. Re-exported from views_v1 for urls_v1.
"""
from __future__ import annotations

import json
import logging

from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_http_methods

from apps.api.views_v1 import _backend_flag_enabled, _get_school_from_request

logger = logging.getLogger(__name__)


class InterventionRedFlagsView(View):
    """GET /api/v1/intervention/red-flags - At-risk students (score > 80)."""

    def get(self, request):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            from apps.analytics.models import RiskFactor
            threshold = int(request.GET.get("threshold", 80))
            qs = RiskFactor.objects.filter(school=school, score__gte=threshold).select_related("student", "student__user").order_by("-score")[:200]
            items = [{"student_id": r.student_id, "score": r.score, "reason_summary": r.reason_summary, "band": r.band, "computed_at": r.computed_at.isoformat() if r.computed_at else None} for r in qs]
            return JsonResponse({"count": len(items), "threshold": threshold, "students": items})
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            logger.exception("intervention/red-flags")
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(require_http_methods(["POST"]), name="dispatch")
class InterventionCalculateRiskView(View):
    """POST /api/v1/intervention/calculate-risk - Trigger risk score calculation (background)."""

    def post(self, request):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            from apps.analytics.tasks import compute_risk_factors_task
            result = compute_risk_factors_task.apply_async(kwargs={"school_id": str(school.id)})
            return JsonResponse({"ok": True, "job_id": result.id, "message": "Risk calculation started."}, status=202)
        except (AttributeError, DatabaseError, ImportError, OSError, RuntimeError, TypeError, ValueError) as e:
            msg = getattr(e, "message", str(e))
            return JsonResponse({"error": msg}, status=500)


class InterventionActionCenterView(View):
    """GET /api/v1/intervention/action-center - List interventions for Action Center (approve/dismiss)."""

    def get(self, request):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        from apps.analytics.models import InterventionLog, RiskFactor, get_risk_band_for_school
        status_filter = (request.GET.get("status") or "ONGOING").strip().upper()
        if status_filter == "ALL":
            qs = InterventionLog.objects.filter(school=school)
        else:
            qs = InterventionLog.objects.filter(school=school, status=status_filter)
        qs = qs.select_related("student", "student__user").order_by("-created_at")[:100]
        items = []
        for log in qs:
            risk = RiskFactor.objects.filter(school=school, student=log.student).order_by("-computed_at").first()
            risk_band = get_risk_band_for_school(risk.score, school) if risk else None
            items.append({
                "id": log.id,
                "student_id": log.student_id,
                "trigger_reason": log.trigger_reason,
                "action_taken": log.action_taken,
                "status": log.status,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "draft_email_subject": log.draft_email_subject or "",
                "draft_email_body": (log.draft_email_body or "")[:500],
                "meeting_link": log.meeting_link or "",
                "risk_score": float(risk.score) if risk else None,
                "risk_band": risk_band,
            })
        return JsonResponse({"count": len(items), "interventions": items})


@method_decorator(require_http_methods(["PATCH"]), name="dispatch")
class InterventionActionCenterDetailView(View):
    """PATCH /api/v1/intervention/action-center/<id> - Dismiss or resolve an intervention."""

    def patch(self, request, id):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            data = {}
        from apps.analytics.models import InterventionLog
        log = get_object_or_404(InterventionLog, pk=id, school=school)
        action = (data.get("action") or "dismiss").strip().lower()
        if action == "dismiss":
            log.status = InterventionLog.Status.DISMISSED
            log.dismissed_at = timezone.now()
            log.dismissed_by = request.user
        elif action == "resolve":
            log.status = InterventionLog.Status.RESOLVED
            log.resolved_at = timezone.now()
        else:
            return JsonResponse({"error": "action must be dismiss or resolve"}, status=400)
        log.save(update_fields=["status", "dismissed_at", "dismissed_by", "resolved_at"])
        return JsonResponse({"ok": True, "id": log.id, "status": log.status})


@method_decorator(require_http_methods(["POST"]), name="dispatch")
class InterventionGenerateRoadmapView(View):
    """POST /api/v1/intervention/generate-roadmap - Generate recovery roadmap for student (LLM)."""

    def post(self, request):
        if not _backend_flag_enabled("enable_intervention_llm_roadmap", request=request):
            return JsonResponse({"error": "Intervention roadmap is not enabled."}, status=404)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        student_id = data.get("student_id")
        if not student_id:
            return JsonResponse({"error": "student_id required"}, status=400)
        try:
            from apps.analytics.models import RiskFactor
            from apps.people.models import StudentProfile
            student = StudentProfile.objects.get(id=student_id, school=school)
            risk = RiskFactor.objects.filter(school=school, student=student).order_by("-computed_at").first()
            summary = risk.reason_summary if risk else "No risk data"
            roadmap = {"student_id": student_id, "summary": summary, "suggestions": ["Schedule 1-on-1 with teacher", "Assign remedial module"], "status": "draft"}
            return JsonResponse(roadmap, status=200)
        except StudentProfile.DoesNotExist:
            return JsonResponse({"error": "Student not found"}, status=404)
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            logger.exception("intervention/generate-roadmap")
            return JsonResponse({"error": str(e)}, status=500)
