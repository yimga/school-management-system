# Phase Compliance optional: Data portability (GDPR Art. 20) and Erasure request (Art. 17)
import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.platform_runtime.structured_logging import log_view_exception

logger = logging.getLogger(__name__)

# §2.4: Typed tuples for GDPR views (no broad except).
_GDPR_MFA_VERIFY_PARSE_ERRORS = (ValueError, TypeError, AttributeError)
_GDPR_VIEW_AUDIT_LOG_ERRORS = (
    DatabaseError,
    IntegrityError,
    ValidationError,
    TypeError,
    ValueError,
    AttributeError,
)


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
    except _GDPR_MFA_VERIFY_PARSE_ERRORS:
        logger.debug("_mfa_verified: invalid mfa_verified_until session value")
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

        return redirect(
            reverse("accounts:mfa_verify") + "?next=" + request.get_full_path()
        )
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

    export_format = (
        (request.GET.get("format") or request.POST.get("format") or "json")
        .strip()
        .lower()
    )
    if export_format not in {"json", "csv"}:
        return JsonResponse({"error": "format must be json or csv"}, status=400)
    result = export_student_data_portability(
        school.id, student_id, format=export_format
    )
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
                description="GDPR Art. 20 portability export generated for student_id=%s"
                % student_id,
                details={
                    "student_id": student_id,
                    "school_id": school.id,
                    "requested_by": request.user.id,
                    "format": export_format,
                },
                user=request.user,
                severity="high",
            )
    except _GDPR_VIEW_AUDIT_LOG_ERRORS:
        log_view_exception(
            request,
            "GDPR portability audit log create failed",
            extra={"student_id": student_id, "format": export_format},
        )
    return JsonResponse(result)


@login_required
@require_http_methods(["GET", "POST"])
def erasure_request_view(request):
    """Right to Erasure request (GDPR Art. 17) for student / staff / guardian."""
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "Select your school.")
        return redirect("portal:home")
    if request.method == "POST":
        from datetime import timedelta

        from django.conf import settings
        from django.utils import timezone

        from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile

        from .models import EraseRequest

        subject_kind = (request.POST.get("subject_kind") or "student").strip().lower()
        if subject_kind not in {"student", "staff", "guardian"}:
            messages.error(request, "Invalid subject kind.")
            return redirect("compliance:erasure_request")

        execute_now = (request.POST.get("execute_now") or "").strip() in {
            "1",
            "true",
            "on",
            "yes",
        }
        dry_run = (request.POST.get("dry_run") or "").strip() in {
            "1",
            "true",
            "on",
            "yes",
        }

        subject_user_id = None
        reason_tag = subject_kind
        student_pk = None

        if subject_kind == "student":
            student_id = (request.POST.get("student_id") or "").strip()
            if not student_id:
                messages.error(request, "Student ID required.")
                return redirect("compliance:erasure_request")
            try:
                sid = int(student_id)
            except (TypeError, ValueError):
                messages.error(request, "Invalid student ID.")
                return redirect("compliance:erasure_request")
            student = StudentProfile.objects.filter(school=school, pk=sid).first()
            if not student:
                messages.error(request, "Student not found.")
                return redirect("compliance:erasure_request")
            student_pk = sid
            subject_user_id = student.user_id
            reason_tag = "student_id=%s" % sid
        elif subject_kind == "staff":
            raw = (request.POST.get("staff_user_id") or "").strip()
            if not raw:
                messages.error(request, "Staff user ID required.")
                return redirect("compliance:erasure_request")
            try:
                uid = int(raw)
            except (TypeError, ValueError):
                messages.error(request, "Invalid staff user ID.")
                return redirect("compliance:erasure_request")
            if not TeacherProfile.objects.filter(school=school, user_id=uid).exists():
                messages.error(request, "Staff member not found in this school.")
                return redirect("compliance:erasure_request")
            subject_user_id = uid
            reason_tag = "staff_user_id=%s" % uid
        else:
            raw = (request.POST.get("guardian_user_id") or "").strip()
            if not raw:
                messages.error(request, "Guardian user ID required.")
                return redirect("compliance:erasure_request")
            try:
                uid = int(raw)
            except (TypeError, ValueError):
                messages.error(request, "Invalid guardian user ID.")
                return redirect("compliance:erasure_request")
            if not StudentGuardian.objects.filter(
                guardian_user_id=uid, student__school=school
            ).exists():
                messages.error(request, "Guardian not found in this school.")
                return redirect("compliance:erasure_request")
            subject_user_id = uid
            reason_tag = "guardian_user_id=%s" % uid

        if execute_now:
            if not (request.user.is_staff or request.user.is_superuser):
                messages.error(request, "Only staff users can execute erasure now.")
                return redirect("compliance:erasure_request")
            if subject_kind == "student":
                from .gdpr_services import gdpr_scrub_student

                result = gdpr_scrub_student(
                    school.id,
                    student_pk,
                    dry_run=dry_run,
                    requested_by_user_id=request.user.id,
                )
            else:
                from .dsar_subjects import scrub_user_subject

                result = scrub_user_subject(
                    school.id,
                    subject_user_id,
                    dry_run=dry_run,
                    requested_by_user_id=request.user.id,
                )
            if result.get("ok") or result.get("dry_run"):
                if dry_run:
                    messages.success(
                        request,
                        "GDPR erasure dry-run completed: %s"
                        % result.get("would_anonymize", result),
                    )
                else:
                    messages.success(request, "GDPR erasure/anonymization completed.")
            else:
                messages.error(
                    request, result.get("error") or "Failed to process erasure."
                )
            return redirect("compliance:erasure_request")

        erase_request_id = None
        sla_days = int(getattr(settings, "COMPLIANCE_ERASURE_SLA_DAYS", 30))
        if subject_user_id:
            try:
                er = EraseRequest.objects.create(
                    school=school,
                    requested_by=request.user,
                    subject_user_id=subject_user_id,
                    status=EraseRequest.Status.PENDING,
                    reason="GDPR Art. 17 erasure request (%s)" % reason_tag,
                    due_at=timezone.now() + timedelta(days=sla_days),
                )
                erase_request_id = er.pk
            except _GDPR_VIEW_AUDIT_LOG_ERRORS:
                log_view_exception(
                    request,
                    "GDPR EraseRequest create failed",
                    extra={"subject_kind": subject_kind, "reason_tag": reason_tag},
                )
        try:
            from .models import ComplianceAuditLog

            region = getattr(school, "default_region", None)
            if region:
                ComplianceAuditLog.objects.create(
                    region=region,
                    action_type="policy_enforced",
                    description="Erasure request submitted for %s (GDPR Art. 17)"
                    % reason_tag,
                    details={
                        "subject_kind": subject_kind,
                        "reason_tag": reason_tag,
                        "school_id": school.id,
                        "requested_by": request.user.id,
                        "erase_request_id": erase_request_id,
                        "subject_user_id": subject_user_id,
                    },
                    user=request.user,
                    severity="high",
                )
        except _GDPR_VIEW_AUDIT_LOG_ERRORS:
            log_view_exception(
                request,
                "GDPR erasure request audit log create failed",
                extra={"subject_kind": subject_kind},
            )
        if erase_request_id:
            messages.success(
                request,
                "Erasure request created and queued for processing (due within %s days)."
                % sla_days,
            )
        elif subject_kind == "student":
            messages.success(
                request,
                "Erasure request logged. This student has no linked account, so an "
                "administrator will process it manually.",
            )
        else:
            messages.error(
                request,
                "Could not queue erasure — subject has no processable user account.",
            )
        return redirect("compliance:erasure_request")
    return render(request, "compliance/erasure_request.html", {"school": school})
