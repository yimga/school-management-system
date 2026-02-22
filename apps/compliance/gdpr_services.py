"""GDPR services: Right to Erasure (Art.17) and Data Portability (Art.20)."""

from __future__ import annotations

import csv
import io
import logging
from typing import Any
from uuid import uuid4

from django.apps import apps
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_model(app_label: str, model_name: str):
    try:
        return apps.get_model(app_label, model_name)
    except Exception:
        return None


def _anonymized_username(user_id: int) -> str:
    suffix = uuid4().hex[:10]
    return f"deleted_user_{user_id}_{suffix}"[:150]


def _anonymized_email(user_id: int) -> str:
    suffix = uuid4().hex[:10]
    return f"deleted+{user_id}_{suffix}@invalid.local"


def _log_compliance_event(*, school_id: Any, student_id: Any, action: str, detail: str, user_id: int | None = None) -> None:
    try:
        School = _get_model("schools", "School")
        ComplianceAuditLog = _get_model("compliance", "ComplianceAuditLog")
        User = _get_model("accounts", "User")
        if not School or not ComplianceAuditLog:
            return
        school = School.objects.filter(pk=school_id).select_related("default_region").first()
        if not school or not getattr(school, "default_region", None):
            return
        actor = User.objects.filter(pk=user_id).first() if user_id else None
        ComplianceAuditLog.objects.create(
            region=school.default_region,
            action_type="policy_enforced",
            description=detail,
            details={"school_id": str(school_id), "student_id": str(student_id), "gdpr_action": action},
            user=actor,
            severity="high",
        )
    except Exception:
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
        return {"ok": False, "error": "Student not found", "school_id": school_id, "student_id": student_id}

    attendance_count = Attendance.objects.filter(student_id=student_id).count() if Attendance else 0
    incident_count = Incident.objects.filter(student_id=student_id).count() if Incident else 0
    evaluation_count = Evaluation.objects.filter(student_id=student_id).count() if Evaluation else 0
    guardian_count = StudentGuardian.objects.filter(student_id=student_id).count() if StudentGuardian else 0

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
            except Exception:
                logger.debug("Could not delete student profile photo for student_id=%s", student_id)
            student.profile_photo = None

        custom = dict(getattr(student, "custom_attributes", {}) or {})
        custom["gdpr"] = {
            "scrubbed_at": scrubbed_at.isoformat(),
            "action": "art17_erasure_anonymization",
        }

        student.first_name = "Deleted"
        student.last_name = f"Student-{student.pk}"
        student.student_code = f"GDPR-{student.pk}-{token[:6]}"[:50]
        if getattr(student, "admission_number", None):
            student.admission_number = f"GDPR-{student.pk}-{token}"[:64]
        student.parent_phone = ""
        student.place_of_birth = ""
        student.referral_code = f"GDPR-{token[:6]}"
        student.custom_attributes = custom
        student.is_active = False
        if hasattr(student, "deleted_at"):
            student.deleted_at = scrubbed_at
        if hasattr(student, "status"):
            try:
                student.status = student.Status.ALUMNI
            except Exception:
                pass
        student.save()

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
            )

        if Attendance:
            Attendance.objects.filter(student_id=student_id).update(remarks="")
        if Incident:
            Incident.objects.filter(student_id=student_id).update(description="Redacted under GDPR Art. 17")
        if Evaluation:
            Evaluation.objects.filter(student_id=student_id).update(remarks="")

        if Applicant and old_email:
            Applicant.objects.filter(school_id=school_id, email__iexact=old_email).update(
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
        "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else None,
        "status": student.status,
        "joined_date": student.joined_date.isoformat() if student.joined_date else None,
        "classroom_id": student.classroom_id,
        "specialty_id": student.specialty_id,
        "academic_year_id": student.academic_year_id,
        "is_active": bool(student.is_active),
        "custom_attributes": dict(getattr(student, "custom_attributes", {}) or {}),
    }


def export_student_data_portability(school_id: int, student_id: int, format: str = "json") -> dict[str, Any] | None:
    """
    Data Portability (GDPR Art. 20).
    Caller must enforce MFA before calling.
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
        guardians = StudentGuardian.objects.filter(student_id=student_id).select_related("guardian_user")
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
                    "academic_year": getattr(getattr(ev, "academic_year", None), "name", ""),
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
        for row in Attendance.objects.filter(school_id=school_id, student_id=student_id).order_by("date"):
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
        for row in Incident.objects.filter(school_id=school_id, student_id=student_id).order_by("-date"):
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
        invoices = Invoice.objects.filter(school_id=school_id, student_id=student_id).order_by("-issued_date")
        for row in invoices:
            invoices_payload.append(
                {
                    "id": row.pk,
                    "reference": row.reference,
                    "status": row.status,
                    "issued_date": row.issued_date.isoformat() if row.issued_date else None,
                    "due_date": row.due_date.isoformat() if row.due_date else None,
                    "total_amount": row.total_amount,
                    "balance_amount": row.balance_amount,
                    "payment_code": row.payment_code,
                }
            )

    payments_payload: list[dict[str, Any]] = []
    if Payment:
        payments = Payment.objects.filter(school_id=school_id, student_id=student_id).order_by("-paid_at")
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

    payload: dict[str, Any] = {
        "export_format": fmt,
        "schema": "ceds-lite-v1",
        "generated_at": timezone.now().isoformat(),
        "school_id": school_id,
        "student_id": student_id,
        "student": _student_core_payload(student),
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
