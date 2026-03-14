# Phase Compliance optional: Data portability (GDPR Art. 20) and Erasure request (Art. 17)
from django.contrib import messages
from django.shortcuts import redirect, render
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
    """Data portability (GDPR Art. 20). Requires MFA verification and returns export payload."""
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
    export_format = (request.GET.get("format") or request.POST.get("format") or "json").strip().lower()
    if export_format not in {"json", "csv"}:
        return JsonResponse({"error": "format must be json or csv"}, status=400)
    result = export_student_data_portability(school.id, student_id, format=export_format)
    if not result:
        return JsonResponse({"error": "Export not available"}, status=404)
    # Log successful portability action for regional compliance traceability.
    try:
        from .models import ComplianceAuditLog
        region = getattr(school, "default_region", None)
        if region:
            ComplianceAuditLog.objects.create(
                region=region,
                action_type="policy_enforced",
                description="GDPR Art. 20 portability export generated for student_id=%s" % student_id,
                details={
                    "student_id": student_id,
                    "school_id": school.id,
                    "requested_by": request.user.id,
                    "format": export_format,
                },
                user=request.user,
                severity="high",
            )
    except Exception:
        pass
    return JsonResponse(result)


@login_required
@require_http_methods(["GET", "POST"])
def erasure_request_view(request):
    """Right to Erasure request (GDPR Art. 17)."""
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
        execute_now = (request.POST.get("execute_now") or "").strip() in {"1", "true", "on", "yes"}
        dry_run = (request.POST.get("dry_run") or "").strip() in {"1", "true", "on", "yes"}

        if execute_now:
            if not (request.user.is_staff or request.user.is_superuser):
                messages.error(request, "Only staff users can execute erasure now.")
                return redirect("compliance:erasure_request")
            from .gdpr_services import gdpr_scrub_student
            result = gdpr_scrub_student(
                school.id,
                sid,
                dry_run=dry_run,
                requested_by_user_id=request.user.id,
            )
            if result.get("ok") or result.get("dry_run"):
                if dry_run:
                    messages.success(
                        request,
                        "GDPR erasure dry-run completed: %s" % result.get("would_anonymize", {}),
                    )
                else:
                    messages.success(request, "GDPR erasure/anonymization completed.")
            else:
                messages.error(request, result.get("error") or "Failed to process erasure.")
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
