"""GDPR services: Right to Erasure (Art.17) and Data Portability (Art.20).
§2.4: Typed exception tuples and log_exception_with_context for model lookup, audit log, and scrub paths.
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any
from uuid import uuid4

from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from apps.metadata.services import get_dynamic_field_map, set_dynamic_field_value
from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)

# §2.4: Typed tuples for GDPR service paths (no broad except).
_GDPR_GET_MODEL_ERRORS = (
    LookupError,
    ImportError,
    ValueError,
    AttributeError,
    TypeError,
)
_GDPR_AUDIT_LOG_ERRORS = (
    DatabaseError,
    IntegrityError,
    ValidationError,
    ObjectDoesNotExist,
    AttributeError,
    TypeError,
    ValueError,
)
_GDPR_FILE_DELETE_ERRORS = (
    OSError,
    PermissionError,
    ValueError,
    AttributeError,
    TypeError,
)
_GDPR_STATUS_ASSIGN_ERRORS = (AttributeError, ValueError, TypeError)


def _get_model(app_label: str, model_name: str):
    try:
        return apps.get_model(app_label, model_name)
    except _GDPR_GET_MODEL_ERRORS:
        return None


def _anonymized_username(user_id: int) -> str:
    suffix = uuid4().hex[:10]
    return f"deleted_user_{user_id}_{suffix}"[:150]


def _anonymized_email(user_id: int) -> str:
    suffix = uuid4().hex[:10]
    return f"deleted+{user_id}_{suffix}@invalid.local"


def _log_compliance_event(
    *,
    school_id: Any,
    student_id: Any,
    action: str,
    detail: str,
    user_id: int | None = None,
) -> None:
    try:
        School = _get_model("schools", "School")
        ComplianceAuditLog = _get_model("compliance", "ComplianceAuditLog")
        User = _get_model("accounts", "User")
        if not School or not ComplianceAuditLog:
            return
        school = (
            School.objects.filter(pk=school_id).select_related("default_region").first()
        )
        if not school or not getattr(school, "default_region", None):
            return
        actor = User.objects.filter(pk=user_id).first() if user_id else None
        ComplianceAuditLog.objects.create(
            region=school.default_region,
            action_type="policy_enforced",
            description=detail,
            details={
                "school_id": str(school_id),
                "student_id": str(student_id),
                "gdpr_action": action,
            },
            user=actor,
            severity="high",
        )
    except _GDPR_AUDIT_LOG_ERRORS:
        log_exception_with_context(
            "Failed to write ComplianceAuditLog for GDPR action",
            school_id=school_id,
            extra={"student_id": student_id, "gdpr_action": action},
        )
        logger.exception("Failed to write ComplianceAuditLog for GDPR action")


def gdpr_scrub_student(
    school_id: int,
    student_id: int,
    *,
    dry_run: bool = False,
    requested_by_user_id: int | None = None,
) -> dict[str, Any]:
    """
    Right to Erasure (GDPR Art. 17).

    Strategy:
    - keep referential integrity for academic/financial records,
    - anonymize direct PII on StudentProfile and linked student User,
    - redact ancillary PII-bearing fields on guardian and incident/attendance notes.
    """
    StudentProfile = _get_model("people", "StudentProfile")
    StudentGuardian = _get_model("people", "StudentGuardian")
    Attendance = _get_model("academics", "Attendance")
    Incident = _get_model("academics", "Incident")
    Evaluation = _get_model("evals", "Evaluation")
    Applicant = _get_model("people", "Applicant")

    if not StudentProfile:
        return {"ok": False, "error": "StudentProfile model unavailable"}

    student = (
        StudentProfile.objects.filter(school_id=school_id, pk=student_id)
        .select_related("user")
        .first()
    )
    if not student:
        return {
            "ok": False,
            "error": "Student not found",
            "school_id": school_id,
            "student_id": student_id,
        }

    attendance_count = (
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        Attendance.objects.filter(student_id=student_id).count() if Attendance else 0
    )
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    incident_count = (
        Incident.objects.filter(student_id=student_id).count() if Incident else 0
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    )
    evaluation_count = (
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        Evaluation.objects.filter(student_id=student_id).count() if Evaluation else 0
    )
    guardian_count = (
        StudentGuardian.objects.filter(student_id=student_id).count()
        if StudentGuardian
        else 0
    )

    summary = {
        "school_id": str(school_id),
        "student_id": str(student_id),
        "dry_run": dry_run,
        "would_anonymize": {
            "student_profile": True,
            "student_user": bool(getattr(student, "user_id", None)),
            "guardians": guardian_count,
            "attendance_notes": attendance_count,
            "incident_descriptions": incident_count,
            "evaluation_remarks": evaluation_count,
        },
        "would_wipe_media_prefix": f"tenants/{school_id}/students/{student_id}",
        "status": "planned" if dry_run else "executing",
    }
    if dry_run:
        return summary

    scrubbed_at = timezone.now()
    token = uuid4().hex[:12].upper()
    old_email = ""

    with transaction.atomic():
        user = getattr(student, "user", None)
        if user:
            old_email = (getattr(user, "email", "") or "").strip()
            # Preserve non-student shared identities by unlinking instead of mutating.
            if str(getattr(user, "role", "")) == "STUDENT":
                user.username = _anonymized_username(user.pk)
                user.email = _anonymized_email(user.pk)
                user.first_name = "Deleted"
                user.last_name = "User"
                user.is_active = False
                user.profile_photo = None
                user.set_unusable_password()
                user.save(
                    update_fields=[
                        "username",
                        "email",
                        "first_name",
                        "last_name",
                        "is_active",
                        "profile_photo",
                        "password",
                    ]
                )
            else:
                student.user = None

        if getattr(student, "profile_photo", None):
            try:
                student.profile_photo.delete(save=False)
            except _GDPR_FILE_DELETE_ERRORS:
                log_exception_with_context(
                    "Could not delete student profile photo during GDPR scrub",
                    school_id=school_id,
                    extra={"student_id": student_id},
                )
                logger.debug(
                    "Could not delete student profile photo for student_id=%s",
                    student_id,
                )
            student.profile_photo = None

        gdpr_marker = {
            "scrubbed_at": scrubbed_at.isoformat(),
            "action": "art17_erasure_anonymization",
        }
        set_dynamic_field_value(student, "gdpr", gdpr_marker, sync_legacy=True)

        student.first_name = "Deleted"
        student.last_name = f"Student-{student.pk}"
        student.student_code = f"GDPR-{student.pk}-{token[:6]}"[:50]
        if getattr(student, "admission_number", None):
            student.admission_number = f"GDPR-{student.pk}-{token}"[:64]
        student.parent_phone = ""
        student.place_of_birth = ""
        student.referral_code = f"GDPR-{token[:6]}"
        student.is_active = False
        if hasattr(student, "deleted_at"):
            student.deleted_at = scrubbed_at
        if hasattr(student, "status"):
            try:
                student.status = student.Status.ALUMNI
            except _GDPR_STATUS_ASSIGN_ERRORS:
                log_exception_with_context(
                    "Could not set student status to ALUMNI during GDPR scrub",
                    school_id=school_id,
                    extra={"student_id": student_id},
                )
        student.save()
        set_dynamic_field_value(
            student,
            "gdpr",
            gdpr_marker,
            sync_legacy=False,
            data_type="json",
            label="GDPR status",
        )

        if StudentGuardian:
            StudentGuardian.objects.filter(student_id=student_id).update(
                phone="",
                email="",
                whatsapp_number="",
                address="",
                receives_email=False,
                receives_sms=False,
                receives_whatsapp=False,
                can_view_finance=False,
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            )

        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        if Attendance:
            Attendance.objects.filter(student_id=student_id).update(remarks="")
        if Incident:
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            Incident.objects.filter(student_id=student_id).update(
                description="Redacted under GDPR Art. 17"
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            )
        if Evaluation:
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            Evaluation.objects.filter(student_id=student_id).update(remarks="")

        if Applicant and old_email:
            Applicant.objects.filter(
                school_id=school_id, email__iexact=old_email
            ).update(
                first_name="Deleted",
                last_name=f"Applicant-{student.pk}",
                email=_anonymized_email(student.pk),
                lead_source="gdpr_redacted",
            )

    _log_compliance_event(
        school_id=school_id,
        student_id=student_id,
        action="art17_erasure",
        detail=f"GDPR Art. 17 erasure/anonymization executed for student_id={student_id}",
        user_id=requested_by_user_id,
    )

    return {
        "ok": True,
        "school_id": str(school_id),
        "student_id": str(student_id),
        "dry_run": False,
        "status": "completed",
        "anonymized": {
            "student_profile": True,
            "student_user": bool(old_email or getattr(student, "user_id", None)),
            "guardians": guardian_count,
            "attendance_notes": attendance_count,
            "incident_descriptions": incident_count,
            "evaluation_remarks": evaluation_count,
        },
    }


def _student_core_payload(student) -> dict[str, Any]:
    return {
        "id": student.pk,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "student_code": student.student_code,
        "admission_number": student.admission_number,
        "gender": student.gender,
        "date_of_birth": student.date_of_birth.isoformat()
        if student.date_of_birth
        else None,
        "status": student.status,
        "joined_date": student.joined_date.isoformat() if student.joined_date else None,
        "classroom_id": student.classroom_id,
        "specialty_id": student.specialty_id,
        "academic_year_id": student.academic_year_id,
        "is_active": bool(student.is_active),
        "custom_attributes": get_dynamic_field_map(student),
    }


# --- Art.15/Art.20 export DLP redaction + audit (2026-06-10) ---
# Route every export section through the field-level DLP layer so third-party
# Personal Data the subject is not entitled to is masked per the sensitivity
# tiers in the field catalog (apps.policies.dlp.redact_record). redact_record
# degrades safely — an entity with no classified fields returns the record
# unchanged — so this strengthens automatically as the catalog grows and never
# weakens the prior (unredacted) behaviour. Each export section maps to a
# field-catalog entity code (apps.metadata EntityCatalogEntry.code).
_DSAR_EXPORT_REDACT_ERRORS = (
    DatabaseError,
    ObjectDoesNotExist,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
)


def _redact_export_rows(rows, *, entity, subject, school, school_id):
    """Apply field-level DLP redaction to a list of export record dicts.

    Fails open to the *unchanged* row on any policy/DB error — matching the
    pre-existing ``load_field_meta`` fail-open behaviour, with the operator's
    mandatory pre-delivery review (DSAR runbook §7) as the human backstop — so
    an Art.15/Art.20 export never crashes mid-assembly.
    """
    from apps.policies.dlp import redact_record

    out = []
    for row in rows:
        try:
            out.append(
                redact_record(
                    row,
                    entity=entity,
                    subject=subject,
                    school=school,
                    action="export",
                )
            )
        except _DSAR_EXPORT_REDACT_ERRORS as exc:
            log_exception_with_context(
                "DSAR export redaction failed; emitting unredacted row for operator review",
                school_id=school_id,
                extra={"entity": entity, "error": str(exc)},
            )
            out.append(row)
    return out


def _log_dsar_export(*, school_id, student_id, subject, sections):
    """Emit one PolicyDecisionLog row per Art.15/Art.20 export (never Personal Data)."""
    try:
        from apps.policies.pdp import PolicyDecisionLog

        PolicyDecisionLog.objects.create(  # tenant-isolation-allow: dsar-export-audit-log-explicit-school-id
            school_id=school_id,
            subject_id=str(subject.get("user_id") or student_id),
            subject_role=str(subject.get("role") or "student"),
            action="dsar_access_export",
            resource_type="people.StudentProfile",
            resource_id=str(student_id),
            effect="allow",
            decision_reason="art15-portability-export",
            context_snapshot={"sections": sorted(sections)},
        )
    except _GDPR_AUDIT_LOG_ERRORS as exc:
        log_exception_with_context(
            "DSAR export PolicyDecisionLog emission failed",
            school_id=school_id,
            extra={"student_id": student_id, "error": str(exc)},
        )


def export_student_data_portability(
    school_id: int, student_id: int, format: str = "json"
) -> dict[str, Any] | None:
    """
    Data Portability (GDPR Art. 20).
    Caller must enforce MFA before calling.

    Every section is routed through the field-level DLP layer
    (``apps.policies.dlp.redact_record``, ``action="export"``) so third-party
    Personal Data the subject is not entitled to is masked per the field
    catalog's sensitivity tiers, and one ``PolicyDecisionLog`` row is emitted
    per export for the audit trail.
    """
    fmt = (format or "json").strip().lower()

    StudentProfile = _get_model("people", "StudentProfile")
    StudentGuardian = _get_model("people", "StudentGuardian")
    Evaluation = _get_model("evals", "Evaluation")
    Attendance = _get_model("academics", "Attendance")
    Invoice = _get_model("finance", "Invoice")
    Payment = _get_model("finance", "Payment")
    Incident = _get_model("academics", "Incident")

    if not StudentProfile:
        return None

    student = (
        StudentProfile.objects.filter(school_id=school_id, pk=student_id)
        .select_related("school", "classroom", "specialty", "academic_year")
        .first()
    )
    if not student:
        return None

    guardians_payload: list[dict[str, Any]] = []
    if StudentGuardian:
        guardians = StudentGuardian.objects.filter(
            student_id=student_id
        ).select_related("guardian_user")
        for guardian in guardians:
            user = getattr(guardian, "guardian_user", None)
            guardians_payload.append(
                {
                    "id": guardian.pk,
                    "relationship": guardian.relationship,
                    "phone": guardian.phone,
                    "email": guardian.email,
                    "preferred_contact": guardian.preferred_contact,
                    "guardian_name": user.get_full_name() if user else "",
                }
            )

    evaluations_payload: list[dict[str, Any]] = []
    if Evaluation:
        evaluations = (
            Evaluation.objects.filter(school_id=school_id, student_id=student_id)
            .select_related("academic_year", "term", "subject_assignment__subject")
            .order_by("academic_year_id", "term_id", "subject_assignment_id")
        )
        for ev in evaluations:
            subject = getattr(getattr(ev, "subject_assignment", None), "subject", None)
            evaluations_payload.append(
                {
                    "id": ev.pk,
                    "academic_year": getattr(
                        getattr(ev, "academic_year", None), "name", ""
                    ),
                    "term": getattr(getattr(ev, "term", None), "name", ""),
                    "subject": getattr(subject, "name", ""),
                    "seq1_score": ev.seq1_score,
                    "seq2_score": ev.seq2_score,
                    "exam_score": ev.exam_score,
                    "mock_score": ev.mock_score,
                    "practical_score": ev.practical_score,
                    "remarks": ev.remarks,
                    "letter_grade": ev.letter_grade,
                }
            )

    attendance_payload: list[dict[str, Any]] = []
    if Attendance:
        for row in Attendance.objects.filter(
            school_id=school_id, student_id=student_id
        ).order_by("date"):
            attendance_payload.append(
                {
                    "id": row.pk,
                    "date": row.date.isoformat() if row.date else None,
                    "status": row.status,
                    "remarks": row.remarks,
                    "classroom_id": row.classroom_id,
                }
            )

    incidents_payload: list[dict[str, Any]] = []
    if Incident:
        for row in Incident.objects.filter(
            school_id=school_id, student_id=student_id
        ).order_by("-date"):
            incidents_payload.append(
                {
                    "id": row.pk,
                    "date": row.date.isoformat() if row.date else None,
                    "incident_type": row.incident_type,
                    "severity": row.severity,
                    "status": row.status,
                    "description": row.description,
                }
            )

    invoices_payload: list[dict[str, Any]] = []
    if Invoice:
        invoices = Invoice.objects.filter(
            school_id=school_id, student_id=student_id
        ).order_by("-issued_date")
        for row in invoices:
            invoices_payload.append(
                {
                    "id": row.pk,
                    "reference": row.reference,
                    "status": row.status,
                    "issued_date": row.issued_date.isoformat()
                    if row.issued_date
                    else None,
                    "due_date": row.due_date.isoformat() if row.due_date else None,
                    "total_amount": row.total_amount,
                    "balance_amount": row.balance_amount,
                    "payment_code": row.payment_code,
                }
            )

    payments_payload: list[dict[str, Any]] = []
    if Payment:
        payments = Payment.objects.filter(
            school_id=school_id, student_id=student_id
        ).order_by("-paid_at")
        for row in payments:
            payments_payload.append(
                {
                    "id": row.pk,
                    "amount": row.amount,
                    "currency_code": row.currency_code,
                    "method": row.method,
                    "status": row.status,
                    "reference": row.reference,
                    "external_reference": row.external_reference,
                    "paid_at": row.paid_at.isoformat() if row.paid_at else None,
                    "invoice_id": row.invoice_id,
                }
            )

    # Route every section through the field-level DLP layer (Art.15 third-party
    # PII masking) keyed by the data subject, then audit the export.
    subject = {"user_id": getattr(student, "user_id", None), "role": "student"}
    school = getattr(student, "school", None)
    _rk = {"subject": subject, "school": school, "school_id": school_id}
    student_core = _redact_export_rows(
        [_student_core_payload(student)], entity="student", **_rk
    )[0]
    guardians_payload = _redact_export_rows(guardians_payload, entity="person", **_rk)
    evaluations_payload = _redact_export_rows(evaluations_payload, entity="grade", **_rk)
    attendance_payload = _redact_export_rows(
        attendance_payload, entity="attendance", **_rk
    )
    incidents_payload = _redact_export_rows(incidents_payload, entity="incident", **_rk)
    invoices_payload = _redact_export_rows(invoices_payload, entity="invoice", **_rk)
    payments_payload = _redact_export_rows(payments_payload, entity="payment", **_rk)
    _log_dsar_export(
        school_id=school_id,
        student_id=student_id,
        subject=subject,
        sections=[
            "student",
            "guardians",
            "evaluations",
            "attendance",
            "incidents",
            "invoices",
            "payments",
        ],
    )

    payload: dict[str, Any] = {
        "export_format": fmt,
        "schema": "ceds-lite-v1",
        "generated_at": timezone.now().isoformat(),
        "school_id": school_id,
        "student_id": student_id,
        "student": student_core,
        "guardians": guardians_payload,
        "academics": {
            "evaluations": evaluations_payload,
            "attendance": attendance_payload,
            "incidents": incidents_payload,
        },
        "finance": {
            "invoices": invoices_payload,
            "payments": payments_payload,
        },
    }

    if fmt == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["section", "field", "value"])
        for key, value in payload["student"].items():
            writer.writerow(["student", key, value])
        for g in guardians_payload:
            writer.writerow(["guardians", "record", g])
        for row in evaluations_payload:
            writer.writerow(["evaluations", "record", row])
        for row in attendance_payload:
            writer.writerow(["attendance", "record", row])
        for row in incidents_payload:
            writer.writerow(["incidents", "record", row])
        for row in invoices_payload:
            writer.writerow(["invoices", "record", row])
        for row in payments_payload:
            writer.writerow(["payments", "record", row])
        return {
            "export_format": "csv",
            "filename": f"student_{student_id}_portability.csv",
            "content": stream.getvalue(),
            "status": "ok",
        }

    return payload


def fulfill_pending_erasure(
    erase_request_id: int,
    *,
    fulfilled_by_user_id: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Approve→fulfill an EraseRequest: run the GDPR scrub for the subject and
    advance the row to COMPLETED. Closes the gap where the admin action
    flipped status without actually erasing data.

    The function is the *only* sanctioned transition from APPROVED→COMPLETED
    for student subjects. Non-student subjects (teacher / parent / staff users)
    are not yet handled and return a structured "unsupported_subject_kind"
    response so callers can surface a clear message instead of silently
    no-oping.
    """
    EraseRequest = _get_model("compliance", "EraseRequest")
    StudentProfile = _get_model("people", "StudentProfile")
    if not EraseRequest or not StudentProfile:
        return {"ok": False, "error": "compliance models unavailable"}

    er = EraseRequest.objects.filter(pk=erase_request_id).select_related(  # tenant-isolation-allow: PK lookup, school checked via .school after fetch
        "subject_user", "school"
    ).first()
    if not er:
        return {"ok": False, "error": "EraseRequest not found"}

    if er.status not in {
        EraseRequest.Status.PENDING,
        EraseRequest.Status.APPROVED,
    }:
        return {
            "ok": False,
            "error": f"EraseRequest is in terminal state '{er.status}' — cannot fulfill.",
            "status": er.status,
        }

    student = StudentProfile.objects.filter(
        school_id=er.school_id, user_id=er.subject_user_id
    ).first()
    if not student:
        return {
            "ok": False,
            "error": "unsupported_subject_kind: only student subjects are currently supported.",
            "subject_user_id": er.subject_user_id,
        }

    result = gdpr_scrub_student(
        er.school_id,
        student.pk,
        dry_run=dry_run,
        requested_by_user_id=fulfilled_by_user_id,
    )
    if dry_run:
        return {"ok": True, "dry_run": True, "scrub_summary": result}
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error"), "scrub_summary": result}

    er.status = EraseRequest.Status.COMPLETED
    er.completed_at = timezone.now()
    er.save(update_fields=["status", "completed_at"])
    return {
        "ok": True,
        "erase_request_id": er.pk,
        "status": er.status,
        "scrub_summary": result,
    }
