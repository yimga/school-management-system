"""Parent-facing GDPR data rights (portability + erasure requests)."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


def _parent_children(request, school):
    from apps.people.models import StudentGuardian, StudentProfile

    if school is None:
        return StudentProfile.objects.none()
    return (
        StudentProfile.objects.filter(
            school=school,
            pk__in=StudentGuardian.objects.filter(
                guardian_user=request.user,
                student__school=school,
            ).values_list("student_id", flat=True),
        )
        .select_related("user")
        .order_by("last_name", "first_name")
    )


def _pending_erase_requests(request, school):
    from apps.compliance.models import EraseRequest

    children = _parent_children(request, school)
    user_ids = [c.user_id for c in children if c.user_id]
    if not user_ids:
        return EraseRequest.objects.none()
    return EraseRequest.objects.filter(
        school=school,
        subject_user_id__in=user_ids,
        requested_by=request.user,
    ).order_by("-created_at")


@login_required
@require_http_methods(["GET", "POST"])
def parent_data_rights(request):
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseForbidden("School context required.")
    children = list(_parent_children(request, school))
    if not children:
        return render(
            request,
            "portal/parent_data_rights.html",
            {
                "school": school,
                "children": [],
                "erase_requests": [],
                "empty_guardian": True,
            },
        )

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        student_id_raw = (request.POST.get("student_id") or "").strip()
        try:
            student_id = int(student_id_raw)
        except (TypeError, ValueError):
            messages.error(request, "Select a valid student.")
            return redirect("portal:parent_data_rights")

        child = next((c for c in children if c.pk == student_id), None)
        if child is None:
            return HttpResponseForbidden("You may only access your linked children.")

        if action == "export":
            from apps.compliance.gdpr_services import export_student_data_portability

            export_format = (request.POST.get("format") or "json").strip().lower()
            if export_format not in {"json", "csv"}:
                export_format = "json"
            result = export_student_data_portability(
                school.id, child.pk, format=export_format
            )
            if not result:
                messages.error(request, "Export is not available for this student.")
                return redirect("portal:parent_data_rights")
            if export_format == "csv" and isinstance(result, dict):
                payload = result.get("csv") or result.get("data") or ""
                response = HttpResponse(payload, content_type="text/csv; charset=utf-8")
                response["Content-Disposition"] = (
                    f'attachment; filename="{school.slug}-student-{child.pk}.csv"'
                )
                return response
            body = json.dumps(result, indent=2, default=str)
            response = HttpResponse(body, content_type="application/json")
            response["Content-Disposition"] = (
                f'attachment; filename="{school.slug}-student-{child.pk}.json"'
            )
            return response

        if action == "erasure":
            if not child.user_id:
                messages.warning(
                    request,
                    "This student has no linked portal account; contact the school "
                    "office to process erasure manually.",
                )
                return redirect("portal:parent_data_rights")
            sla_days = int(getattr(settings, "COMPLIANCE_ERASURE_SLA_DAYS", 30))
            try:
                from apps.compliance.models import EraseRequest

                er = EraseRequest.objects.create(
                    school=school,
                    requested_by=request.user,
                    subject_user_id=child.user_id,
                    status=EraseRequest.Status.PENDING,
                    reason=f"Parent GDPR Art. 17 request (student_id={child.pk})",
                    due_at=timezone.now() + timedelta(days=sla_days),
                )
                messages.success(
                    request,
                    f"Erasure request submitted (reference #{er.pk}). "
                    f"Due within {sla_days} days.",
                )
            except Exception:
                logger.exception(
                    "parent_data_rights erasure create failed student_id=%s",
                    child.pk,
                )
                messages.error(request, "Could not submit erasure request. Try again.")
            return redirect("portal:parent_data_rights")

        messages.error(request, "Unknown action.")
        return redirect("portal:parent_data_rights")

    return render(
        request,
        "portal/parent_data_rights.html",
        {
            "school": school,
            "children": children,
            "erase_requests": list(_pending_erase_requests(request, school)[:20]),
            "sla_days": int(getattr(settings, "COMPLIANCE_ERASURE_SLA_DAYS", 30)),
            "empty_guardian": False,
        },
    )


@login_required
@require_http_methods(["GET"])
def api_parent_data_rights_status(request):
    school = getattr(request, "school", None)
    if school is None:
        return JsonResponse({"ok": False, "error": "no_school"}, status=403)
    children = _parent_children(request, school)
    return JsonResponse(
        {
            "ok": True,
            "child_count": children.count(),
            "pending_erasure_count": _pending_erase_requests(request, school)
            .filter(status="pending")
            .count(),
        }
    )
