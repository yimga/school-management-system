"""
Employer portal: limited login for employers to view apprentice progress and confirm on-site hours.
"""

from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.http import HttpRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.effective_access import role_access
from apps.people.models import ApprenticePlacement
from apps.platform_runtime.structured_logging import (
    log_exception_with_context,
    log_view_exception,
)

# Typed exceptions for §2.4 broad-except replacement (allowlist 0).
_EMPLOYER_HOURS_PARSE_ERRORS = (InvalidOperation, ValueError, TypeError)
_EMPLOYER_TRANSCRIPT_CONTEXT_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    ObjectDoesNotExist,
    DatabaseError,
)


def _is_employer(request) -> bool:
    if not request.user.is_authenticated:
        return False
    return role_access(request.user, "EMPLOYER")


@login_required
@require_http_methods(["GET"])
def employer_dashboard(request: HttpRequest):
    """List apprentice placements for this employer (view progress, confirm hours)."""
    if not _is_employer(request):
        return HttpResponseForbidden("Employer access only.")
    placements = (
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        ApprenticePlacement.objects.filter(employer=request.user)
        .select_related("school", "student")
        .order_by("-updated_at")
    )
    if request.headers.get("Accept", "").find("application/json") >= 0:
        return JsonResponse(
            {
                "placements": [
                    {
                        "id": p.id,
                        "student_name": p.student.get_full_name()
                        if p.student_id
                        else "",
                        "school_name": p.school.name if p.school_id else "",
                        "confirmed_hours": str(p.confirmed_hours),
                        "last_confirmed_at": p.last_confirmed_at.isoformat()
                        if p.last_confirmed_at
                        else None,
                    }
                    for p in placements
                ],
            }
        )
    return render(request, "people/employer_dashboard.html", {"placements": placements})


@login_required
@require_http_methods(["GET", "POST"])
def employer_confirm_hours(request: HttpRequest, placement_id: int):
    """Confirm on-site hours for an apprentice placement (employer only)."""
    if not _is_employer(request):
        return HttpResponseForbidden("Employer access only.")
    placement = get_object_or_404(
        ApprenticePlacement, pk=placement_id, employer=request.user
    )
    if request.method == "POST":
        try:
            hours = Decimal(request.POST.get("hours", "0").strip() or "0")
        except _EMPLOYER_HOURS_PARSE_ERRORS:
            log_exception_with_context(
                "employer_confirm_hours: failed to parse hours",
                school_id=placement.school_id,
                extra={"placement_id": placement_id},
            )
            hours = Decimal("0")
        if hours > 0:
            placement.confirmed_hours += hours
            from django.utils import timezone

            placement.last_confirmed_at = timezone.now()
            placement.save(
                update_fields=["confirmed_hours", "last_confirmed_at", "updated_at"]
            )
        if request.headers.get("Accept", "").find("application/json") >= 0:
            return JsonResponse(
                {"ok": True, "confirmed_hours": str(placement.confirmed_hours)}
            )
        return redirect("portal:employer_dashboard")
    return render(
        request, "people/employer_confirm_hours.html", {"placement": placement}
    )


@login_required
@require_http_methods(["GET"])
def employer_student_transcript(request: HttpRequest, placement_id: int):
    """Download or view transcript for an apprentice (employer only). Uses dual_transcript context when student has transcript_track=DUAL."""
    if not _is_employer(request):
        return HttpResponseForbidden("Employer access only.")
    placement = get_object_or_404(
        ApprenticePlacement, pk=placement_id, employer=request.user
    )
    student = placement.student
    from apps.academics.services import get_active_year_and_term
    from apps.reports.services import annual_report_context

    active_year, _ = get_active_year_and_term(school=getattr(request, "school", None))
    year = active_year or (
        student.academic_year if getattr(student, "academic_year_id", None) else None
    )
    if not year:
        return JsonResponse({"error": "No academic year for transcript."}, status=400)
    try:
        context = annual_report_context(student, year)
    except _EMPLOYER_TRANSCRIPT_CONTEXT_ERRORS as exc:
        log_view_exception(
            request,
            "employer_student_transcript: annual_report_context failed",
            extra={
                "placement_id": placement_id,
                "student_id": getattr(student, "id", None),
            },
        )
        return JsonResponse({"error": str(exc)}, status=500)
    if request.headers.get("Accept", "").find("application/json") >= 0:
        return JsonResponse(
            {
                "student": student.get_full_name(),
                "year": year.name,
                "dual_transcript": context.get("dual_transcript", False),
                "transcript_track": context.get("transcript_track", "ACADEMIC"),
            }
        )
    from django.shortcuts import render as django_render

    return django_render(
        request,
        "people/employer_transcript.html",
        {"placement": placement, "student": student, "year": year, "context": context},
    )
