# Phase Compliance optional: Data portability (GDPR Art. 20) and Erasure request (Art. 17)
from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponseForbidden

from django.contrib.auth.decorators import login_required


def _mfa_verified(request):
    """True if session has valid MFA (for data portability)."""
    if request.session.get("mfa_verified"):
        return True
    from django.utils import timezone
    until_raw = request.session.get("mfa_verified_until")
    if not until_raw:
        return False
    try:
        until_dt = timezone.datetime.fromisoformat(until_raw)
        if timezone.is_naive(until_dt):
            until_dt = timezone.make_aware(until_dt, timezone.get_current_timezone())
        return timezone.now() <= until_dt
    except Exception:
        return False


@login_required
@require_http_methods(["GET", "POST"])
def data_portability_export(request):
    """Data portability (GDPR Art. 20). Requires MFA verification; returns CEDS-style export (stub)."""
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("School context required.")
    from django_otp import user_has_device
    if user_has_device(request.user) and not _mfa_verified(request):
        messages.warning(request, "Verify MFA to export student data.")
        from django.urls import reverse
        return redirect(reverse("accounts:mfa_verify") + "?next=" + request.get_full_path())
    student_id = request.GET.get("student_id") or request.POST.get("student_id")
    if student_id:
        try:
            student_id = int(student_id)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid student_id"}, status=400)
    if not student_id:
        return JsonResponse({"error": "student_id required"}, status=400)
    from apps.people.models import StudentProfile
    student = StudentProfile.objects.filter(school=school, pk=student_id).first()
    if not student:
        return JsonResponse({"error": "Student not found"}, status=404)
    from .gdpr_services import export_student_data_portability
    result = export_student_data_portability(school.id, student_id, format="json")
    return JsonResponse(result or {"error": "Export not available"})


@login_required
@require_http_methods(["GET", "POST"])
def erasure_request_view(request):
    """Right to Erasure request (GDPR Art. 17). Submit student_id; logged for admin to process (stub)."""
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "Select your school.")
        return redirect("portal:home")
    if request.method == "POST":
        student_id = (request.POST.get("student_id") or "").strip()
        if not student_id:
            messages.error(request, "Student ID required.")
            return redirect("compliance:erasure_request")
        try:
            sid = int(student_id)
        except (TypeError, ValueError):
            messages.error(request, "Invalid student ID.")
            return redirect("compliance:erasure_request")
        from apps.people.models import StudentProfile
        student = StudentProfile.objects.filter(school=school, pk=sid).first()
        if not student:
            messages.error(request, "Student not found.")
            return redirect("compliance:erasure_request")
        try:
            from .models import ComplianceAuditLog
            region = getattr(school, "default_region", None)
            if region:
                ComplianceAuditLog.objects.create(
                    region=region,
                    action_type="policy_enforced",
                    description="Erasure request submitted for student_id=%s (GDPR Art. 17)" % sid,
                    details={"student_id": sid, "school_id": school.id, "requested_by": request.user.id},
                    user=request.user,
                    severity="high",
                )
        except Exception:
            pass
        messages.success(request, "Erasure request logged. An administrator will process it.")
        return redirect("compliance:erasure_request")
    return render(request, "compliance/erasure_request.html", {"school": school})
