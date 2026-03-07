"""
AI narrative feedback: list draft narratives and approve (teacher-approved parent message).
"""
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.communication.models import NarrativeFeedback
from apps.communication.narrative_feedback import approve_narrative, mark_narrative_sent
from apps.schools.mixins import get_current_school


def _can_approve_narrative(request) -> bool:
    """Teachers and staff can approve narratives for their school."""
    if not request.user.is_authenticated:
        return False
    if request.user.is_staff or request.user.is_superuser:
        return True
    role = (getattr(request.user, "role", "") or "").upper()
    return role in ("ADMIN", "TEACHER", "LEADERSHIP", "PRINCIPAL")


@login_required
@require_http_methods(["GET"])
def narrative_list(request: HttpRequest):
    """List narrative feedbacks (drafts first) for current school."""
    if not _can_approve_narrative(request):
        return HttpResponseForbidden("Not allowed.")
    school = get_current_school(request)
    if not school:
        return HttpResponseForbidden("No school context.")
    qs = NarrativeFeedback.objects.filter(school=school).select_related("student", "achievement_event").order_by("-created_at")
    drafts = list(qs.filter(status=NarrativeFeedback.Status.DRAFT)[:50])
    if request.headers.get("Accept", "").find("application/json") >= 0:
        return JsonResponse({
            "drafts": [
                {
                    "id": n.id,
                    "student_id": n.student_id,
                    "student_name": n.student.get_full_name() if n.student_id else "",
                    "message_text": n.message_text,
                    "event_type": n.achievement_event.event_type if n.achievement_event_id else "",
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                }
                for n in drafts
            ],
        })
    return render(request, "communication/narrative_list.html", {"drafts": drafts, "school": school})


@login_required
@require_http_methods(["GET", "POST"])
def narrative_approve(request: HttpRequest, narrative_id: int):
    """Approve a draft narrative (and optionally mark as sent)."""
    if not _can_approve_narrative(request):
        return HttpResponseForbidden("Not allowed.")
    school = get_current_school(request)
    if not school:
        return HttpResponseForbidden("No school context.")
    narrative = get_object_or_404(NarrativeFeedback, pk=narrative_id, school=school)
    if narrative.status != NarrativeFeedback.Status.DRAFT:
        if request.headers.get("Accept", "").find("application/json") >= 0:
            return JsonResponse({"error": "Already approved or sent."}, status=400)
        return redirect("communication:narrative_list")

    if request.method == "POST":
        approve_narrative(narrative, approved_by=request.user)
        if request.POST.get("mark_sent"):
            mark_narrative_sent(narrative)
        if request.headers.get("Accept", "").find("application/json") >= 0:
            narrative.refresh_from_db()
            return JsonResponse({"ok": True, "status": narrative.status})
        return redirect("communication:narrative_list")

    return render(request, "communication/narrative_approve.html", {"narrative": narrative})
