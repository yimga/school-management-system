"""DSAR coverage for the non-student data-subject types the platform holds PII for.

Most DSAR implementations ship for "student" only and silently miss the other
people whose Personal Data sits in the tenant: teachers / staff, parents /
guardians, and admissions applicants. ``apps.compliance.gdpr_services`` already
covers the **student** subject (export + Art.17 scrub). This module closes the
remaining gaps with the SAME shape — structured machine-readable export and
in-place anonymization (never a hard delete that would break FK referential
integrity), tenant-scoped on ``school=`` so one tenant's DSAR can never read or
erase another tenant's PII, and a best-effort ``ComplianceAuditLog`` write on
every export and erase.

Subject types covered here:

* **Teacher / staff** — any ``User`` linked to a ``people.TeacherProfile`` in the
  tenant. PII lives on the ``User`` (name/email/username/photo) and the
  ``TeacherProfile`` (staff_id, phone, position_title, pay_grade, paystub_notes).
* **Parent / guardian** — any ``User`` linked to a tenant student via
  ``people.StudentGuardian``. PII lives on the ``User`` and the contact columns
  of every ``StudentGuardian`` row in this tenant (phone/email/whatsapp/address).
* **Applicant** — ``people.Applicant`` rows (admissions funnel leads). PII lives
  directly on the row (first/last name, email).

Retention gate: erasure of a teacher/staff subject is blocked while a financial
retention obligation applies (an unpaid Accounts-Payable invoice — e.g. unpaid
salary/stipend), and a parent/guardian erasure is blocked while a student they
are financially responsible for has an unpaid invoice. This mirrors DSAR_RUNBOOK
§9 ("Confirm controller has assessed there is no legal obligation to retain ...
financial-records retention"). The gate is overridable by the operator/controller
via ``force=True`` once they have assessed there is no retention obligation.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import FieldError
from django.db import transaction
from django.utils import timezone

from apps.platform_runtime.structured_logging import log_exception_with_context

from apps.compliance.gdpr_services import (
    _GDPR_FILE_DELETE_ERRORS,
    _anonymized_email,
    _anonymized_username,
    _get_model,
    _log_compliance_event,
)

logger = logging.getLogger(__name__)

# Subject-kind discriminators surfaced to callers.
SUBJECT_STUDENT = "student"
SUBJECT_STAFF = "staff"
SUBJECT_GUARDIAN = "guardian"
SUBJECT_APPLICANT = "applicant"
SUBJECT_UNKNOWN = "unknown"


def resolve_subject_kind(school_id: int, user_id: int) -> str:
    """Classify a ``User`` within a tenant into a DSAR subject kind.

    Tenant-scoped: every lookup is filtered by ``school_id`` so a User who is a
    student in tenant A is NOT seen as a subject in tenant B. Precedence:
    student > staff > guardian (a person can hold more than one relationship; the
    student path is the most complete eraser, so it wins).
    """
    StudentProfile = _get_model("people", "StudentProfile")
    TeacherProfile = _get_model("people", "TeacherProfile")
    StudentGuardian = _get_model("people", "StudentGuardian")

    if StudentProfile and StudentProfile.objects.filter(
        school_id=school_id, user_id=user_id
    ).exists():
        return SUBJECT_STUDENT
    if TeacherProfile and TeacherProfile.objects.filter(
        school_id=school_id, user_id=user_id
    ).exists():
        return SUBJECT_STAFF
    if StudentGuardian and StudentGuardian.objects.filter(
        guardian_user_id=user_id, student__school_id=school_id
    ).exists():
        return SUBJECT_GUARDIAN
    return SUBJECT_UNKNOWN


# --- Retention-hold gating (DSAR_RUNBOOK §9) ----------------------------------

def _staff_retention_hold(school_id: int, user_id: int) -> dict[str, Any] | None:
    """Return a hold descriptor if a staff subject has an unsettled payroll/AP obligation.

    An Accounts-Payable invoice that is not yet PAID/VOID represents money the
    school still owes (or is reconciling) for this staff member — a financial
    record the controller must retain until settled. We resolve the staff
    member's ``Counterparty`` (if any) and look for open AP invoices.
    """
    Invoice = _get_model("finance", "Invoice")
    if not Invoice:
        return None
    open_states = {"DRAFT", "ISSUED", "PARTIAL", "OVERDUE"}
    # AP invoices tied to this user as the counterparty's linked user. We match
    # conservatively on a counterparty whose linked user is this staff member;
    # a finance schema without that relation degrades to "no hold" (fail-open to
    # erasure is the safe DSAR default — the operator's §9 review is the backstop).
    try:
        open_ap = Invoice.objects.filter(
            school_id=school_id,
            invoice_type="AP",
            counterparty__user_id=user_id,
            status__in=open_states,
        ).exists()
    except FieldError:
        return None
    if open_ap:
        return {
            "kind": "financial_records",
            "basis": "Open Accounts-Payable invoice (unsettled payroll/stipend) for staff subject",
        }
    return None


def _guardian_retention_hold(school_id: int, user_id: int) -> dict[str, Any] | None:
    """Return a hold descriptor if a guardian is financially responsible for an unpaid invoice.

    A parent/guardian is the bill-payer for their students; an unpaid student
    invoice is a financial record the controller must retain until settled.
    """
    Invoice = _get_model("finance", "Invoice")
    StudentGuardian = _get_model("people", "StudentGuardian")
    if not Invoice or not StudentGuardian:
        return None
    student_ids = list(
        StudentGuardian.objects.filter(
            guardian_user_id=user_id, student__school_id=school_id
        ).values_list("student_id", flat=True)
    )
    if not student_ids:
        return None
    open_states = {"DRAFT", "ISSUED", "PARTIAL", "OVERDUE"}
    open_inv = Invoice.objects.filter(
        school_id=school_id,
        student_id__in=student_ids,
        status__in=open_states,
    ).exists()
    if open_inv:
        return {
            "kind": "financial_records",
            "basis": "Unpaid student invoice the guardian is financially responsible for",
        }
    return None


# --- User core anonymization (shared by staff + guardian) ---------------------

def _redact_counterparty_pii(school_id: int, user_id: int) -> int:
    """Redact the contact PII on any finance ``Counterparty`` linked to this user.

    A Counterparty mirrors a staff member / guardian's name + email + phone +
    address into the finance ledger. We null the contact columns (keep the row so
    the ledger's FKs stay intact) and return the number of rows redacted.
    """
    Counterparty = _get_model("finance", "Counterparty")
    if not Counterparty:
        return 0
    try:
        qs = Counterparty.objects.filter(school_id=school_id, user_id=user_id)
    except FieldError:
        # finance.Counterparty has no school_id in some schemas; fall back to
        # user-scoped (still tenant-correct because user→tenant is 1:1 here).
        qs = Counterparty.objects.filter(user_id=user_id)
    return qs.update(name="Redacted", email="", phone="", address="")


def _anonymize_user_core(user) -> bool:
    """Anonymize the direct PII on a ``User`` in place. Returns True if mutated.

    Never deletes the row (the User OneToOne/FK to TeacherProfile / guardian
    links is CASCADE — a hard delete would cascade-destroy linked records and
    break referential integrity / the audit trail). Anonymizes name, email,
    username, photo and disables login.
    """
    if not user:
        return False
    user.username = _anonymized_username(user.pk)
    user.email = _anonymized_email(user.pk)
    user.first_name = "Deleted"
    user.last_name = "User"
    user.is_active = False
    if getattr(user, "profile_photo", None):
        try:
            user.profile_photo.delete(save=False)
        except _GDPR_FILE_DELETE_ERRORS:
            log_exception_with_context(
                "Could not delete user profile photo during GDPR scrub",
                extra={"user_id": user.pk},
            )
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
    return True


# --- Teacher / staff subject ---------------------------------------------------

def export_staff_data(school_id: int, user_id: int) -> dict[str, Any] | None:
    """Right of access / portability (Art.15/20) for a teacher/staff subject.

    Tenant-scoped on ``school_id``. Returns the PII the subject can request:
    the linked ``User`` identity + the ``TeacherProfile`` columns.
    """
    TeacherProfile = _get_model("people", "TeacherProfile")
    if not TeacherProfile:
        return None
    teacher = (
        TeacherProfile.objects.filter(school_id=school_id, user_id=user_id)
        .select_related("user", "department")
        .first()
    )
    if not teacher:
        return None
    user = getattr(teacher, "user", None)
    payload = {
        "export_format": "json",
        "schema": "dsar-staff-v1",
        "subject_kind": SUBJECT_STAFF,
        "generated_at": timezone.now().isoformat(),
        "school_id": school_id,
        "user_id": user_id,
        "user": {
            "id": getattr(user, "id", None),
            "username": getattr(user, "username", ""),
            "email": getattr(user, "email", ""),
            "first_name": getattr(user, "first_name", ""),
            "last_name": getattr(user, "last_name", ""),
            "role": str(getattr(user, "role", "")),
        }
        if user
        else None,
        "teacher_profile": {
            "id": teacher.pk,
            "staff_id": teacher.staff_id,
            "phone": teacher.phone,
            "position_title": teacher.position_title,
            "pay_grade": teacher.pay_grade,
            "paystub_notes": teacher.paystub_notes,
            "department": getattr(teacher.department, "name", "")
            if teacher.department_id
            else "",
            "is_active": bool(teacher.is_active),
        },
    }
    _log_compliance_event(
        school_id=school_id,
        student_id=user_id,
        action="art15_export_staff",
        detail=f"DSAR access/portability export generated for staff user_id={user_id}",
    )
    return payload


def gdpr_scrub_staff(
    school_id: int,
    user_id: int,
    *,
    dry_run: bool = False,
    requested_by_user_id: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Right to erasure (Art.17) for a teacher/staff subject — anonymize in place.

    Tenant-scoped. Blocks while a financial retention obligation applies unless
    ``force=True`` (operator/controller assessed no obligation). Never hard-deletes.
    """
    TeacherProfile = _get_model("people", "TeacherProfile")
    if not TeacherProfile:
        return {"ok": False, "error": "TeacherProfile model unavailable"}
    teacher = (
        TeacherProfile.objects.filter(school_id=school_id, user_id=user_id)
        .select_related("user")
        .first()
    )
    if not teacher:
        return {
            "ok": False,
            "error": "Staff subject not found",
            "school_id": school_id,
            "user_id": user_id,
        }

    hold = None if force else _staff_retention_hold(school_id, user_id)
    if hold:
        return {
            "ok": False,
            "error": "retention_hold",
            "retention_hold": hold,
            "school_id": school_id,
            "user_id": user_id,
        }

    summary = {
        "school_id": str(school_id),
        "user_id": str(user_id),
        "subject_kind": SUBJECT_STAFF,
        "dry_run": dry_run,
        "would_anonymize": {"user": bool(teacher.user_id), "teacher_profile": True},
        "status": "planned" if dry_run else "executing",
    }
    if dry_run:
        return summary

    with transaction.atomic():
        _anonymize_user_core(getattr(teacher, "user", None))
        if getattr(teacher, "profile_photo", None):
            try:
                teacher.profile_photo.delete(save=False)
            except _GDPR_FILE_DELETE_ERRORS:
                log_exception_with_context(
                    "Could not delete teacher profile photo during GDPR scrub",
                    school_id=school_id,
                    extra={"user_id": user_id},
                )
            teacher.profile_photo = None
        teacher.staff_id = ""
        teacher.phone = ""
        teacher.position_title = ""
        teacher.pay_grade = ""
        teacher.paystub_notes = ""
        teacher.is_active = False
        teacher.save(
            update_fields=[
                "staff_id",
                "phone",
                "position_title",
                "pay_grade",
                "paystub_notes",
                "is_active",
                "profile_photo",
            ]
        )
        _redact_counterparty_pii(school_id, user_id)
        BadgeScanEvent = _get_model("people", "BadgeScanEvent")
        if BadgeScanEvent:
            # Strip identifier telemetry on this staff member's badge/ID scans.
            # tenant-isolation-allow: user_id is globally unique + resolved within this school above
            BadgeScanEvent.objects.filter(user_id=user_id).update(
                ip_address=None, user_agent="", notes=""
            )

    _log_compliance_event(
        school_id=school_id,
        student_id=user_id,
        action="art17_erasure_staff",
        detail=f"GDPR Art.17 erasure/anonymization executed for staff user_id={user_id}",
        user_id=requested_by_user_id,
    )
    return {
        "ok": True,
        "school_id": str(school_id),
        "user_id": str(user_id),
        "subject_kind": SUBJECT_STAFF,
        "dry_run": False,
        "status": "completed",
        "anonymized": {"user": bool(teacher.user_id), "teacher_profile": True},
    }


# --- Parent / guardian subject -------------------------------------------------

def export_guardian_data(school_id: int, user_id: int) -> dict[str, Any] | None:
    """Right of access / portability (Art.15/20) for a parent/guardian subject.

    Tenant-scoped. Returns the linked ``User`` identity + every ``StudentGuardian``
    row's contact PII in this tenant (the guardian links to the tenant's students).
    """
    StudentGuardian = _get_model("people", "StudentGuardian")
    User = _get_model("accounts", "User")
    if not StudentGuardian or not User:
        return None
    links = list(
        StudentGuardian.objects.filter(
            guardian_user_id=user_id, student__school_id=school_id
        ).select_related("student")
    )
    if not links:
        return None
    user = User.objects.filter(pk=user_id).first()
    links_payload = [
        {
            "id": link.pk,
            "student_id": link.student_id,
            "relationship": link.relationship,
            "phone": link.phone,
            "email": link.email,
            "whatsapp_number": link.whatsapp_number,
            "address": link.address,
            "preferred_contact": link.preferred_contact,
        }
        for link in links
    ]
    payload = {
        "export_format": "json",
        "schema": "dsar-guardian-v1",
        "subject_kind": SUBJECT_GUARDIAN,
        "generated_at": timezone.now().isoformat(),
        "school_id": school_id,
        "user_id": user_id,
        "user": {
            "id": getattr(user, "id", None),
            "username": getattr(user, "username", ""),
            "email": getattr(user, "email", ""),
            "first_name": getattr(user, "first_name", ""),
            "last_name": getattr(user, "last_name", ""),
            "role": str(getattr(user, "role", "")),
        }
        if user
        else None,
        "guardian_links": links_payload,
    }
    _log_compliance_event(
        school_id=school_id,
        student_id=user_id,
        action="art15_export_guardian",
        detail=f"DSAR access/portability export generated for guardian user_id={user_id}",
    )
    return payload


def gdpr_scrub_guardian(
    school_id: int,
    user_id: int,
    *,
    dry_run: bool = False,
    requested_by_user_id: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Right to erasure (Art.17) for a parent/guardian subject — anonymize in place.

    Tenant-scoped. Redacts contact PII on every ``StudentGuardian`` row in this
    tenant for this guardian. Anonymizes the linked ``User`` ONLY if the user has
    no other (student/staff) relationship in this tenant — a shared identity is
    preserved by redacting links only. Blocks on financial retention unless forced.
    """
    StudentGuardian = _get_model("people", "StudentGuardian")
    if not StudentGuardian:
        return {"ok": False, "error": "StudentGuardian model unavailable"}
    links = StudentGuardian.objects.filter(
        guardian_user_id=user_id, student__school_id=school_id
    )
    link_count = links.count()
    if not link_count:
        return {
            "ok": False,
            "error": "Guardian subject not found",
            "school_id": school_id,
            "user_id": user_id,
        }

    hold = None if force else _guardian_retention_hold(school_id, user_id)
    if hold:
        return {
            "ok": False,
            "error": "retention_hold",
            "retention_hold": hold,
            "school_id": school_id,
            "user_id": user_id,
        }

    # Only anonymize the shared User identity when this person is solely a
    # guardian in this tenant (not also a student/staff subject).
    other_kind = resolve_subject_kind(school_id, user_id)
    anonymize_user = other_kind == SUBJECT_GUARDIAN

    summary = {
        "school_id": str(school_id),
        "user_id": str(user_id),
        "subject_kind": SUBJECT_GUARDIAN,
        "dry_run": dry_run,
        "would_anonymize": {"guardian_links": link_count, "user": anonymize_user},
        "status": "planned" if dry_run else "executing",
    }
    if dry_run:
        return summary

    with transaction.atomic():
        links.update(
            phone="",
            email="",
            whatsapp_number="",
            address="",
            receives_email=False,
            receives_sms=False,
            receives_whatsapp=False,
            can_view_finance=False,
        )
        if anonymize_user:
            User = _get_model("accounts", "User")
            user = User.objects.filter(pk=user_id).first() if User else None
            _anonymize_user_core(user)
            _redact_counterparty_pii(school_id, user_id)

    _log_compliance_event(
        school_id=school_id,
        student_id=user_id,
        action="art17_erasure_guardian",
        detail=f"GDPR Art.17 erasure/anonymization executed for guardian user_id={user_id}",
        user_id=requested_by_user_id,
    )
    return {
        "ok": True,
        "school_id": str(school_id),
        "user_id": str(user_id),
        "subject_kind": SUBJECT_GUARDIAN,
        "dry_run": False,
        "status": "completed",
        "anonymized": {"guardian_links": link_count, "user": anonymize_user},
    }


# --- Applicant subject ---------------------------------------------------------

def export_applicant_data(school_id: int, applicant_id: int) -> dict[str, Any] | None:
    """Right of access / portability (Art.15/20) for an admissions applicant.

    Tenant-scoped on ``school_id``. Returns the PII held on the ``Applicant`` row.
    """
    Applicant = _get_model("people", "Applicant")
    if not Applicant:
        return None
    applicant = Applicant.objects.filter(school_id=school_id, pk=applicant_id).first()
    if not applicant:
        return None
    payload = {
        "export_format": "json",
        "schema": "dsar-applicant-v1",
        "subject_kind": SUBJECT_APPLICANT,
        "generated_at": timezone.now().isoformat(),
        "school_id": school_id,
        "applicant_id": applicant_id,
        "applicant": {
            "id": applicant.pk,
            "first_name": applicant.first_name,
            "last_name": applicant.last_name,
            "email": applicant.email,
            "lead_source": applicant.lead_source,
            "stage": applicant.stage,
            "exam_marker": applicant.exam_marker,
        },
    }
    _log_compliance_event(
        school_id=school_id,
        student_id=applicant_id,
        action="art15_export_applicant",
        detail=f"DSAR access/portability export generated for applicant_id={applicant_id}",
    )
    return payload


def gdpr_scrub_applicant(
    school_id: int,
    applicant_id: int,
    *,
    dry_run: bool = False,
    requested_by_user_id: int | None = None,
) -> dict[str, Any]:
    """Right to erasure (Art.17) for an admissions applicant — anonymize in place.

    Tenant-scoped. An applicant carries no financial obligation (no enrollment
    yet), so no retention gate applies. Never hard-deletes (an ENROLLED applicant
    may anchor a StudentProfile referral chain); the name/email are redacted.
    """
    Applicant = _get_model("people", "Applicant")
    if not Applicant:
        return {"ok": False, "error": "Applicant model unavailable"}
    applicant = Applicant.objects.filter(school_id=school_id, pk=applicant_id).first()
    if not applicant:
        return {
            "ok": False,
            "error": "Applicant subject not found",
            "school_id": school_id,
            "applicant_id": applicant_id,
        }

    summary = {
        "school_id": str(school_id),
        "applicant_id": str(applicant_id),
        "subject_kind": SUBJECT_APPLICANT,
        "dry_run": dry_run,
        "would_anonymize": {"applicant": True},
        "status": "planned" if dry_run else "executing",
    }
    if dry_run:
        return summary

    with transaction.atomic():
        applicant.first_name = "Deleted"
        applicant.last_name = f"Applicant-{applicant.pk}"
        applicant.email = _anonymized_email(applicant.pk)
        applicant.lead_source = "gdpr_redacted"
        applicant.exam_marker = ""
        applicant.extra_data = {}
        applicant.save(
            update_fields=[
                "first_name",
                "last_name",
                "email",
                "lead_source",
                "exam_marker",
                "extra_data",
            ]
        )

    _log_compliance_event(
        school_id=school_id,
        student_id=applicant_id,
        action="art17_erasure_applicant",
        detail=f"GDPR Art.17 erasure/anonymization executed for applicant_id={applicant_id}",
        user_id=requested_by_user_id,
    )
    return {
        "ok": True,
        "school_id": str(school_id),
        "applicant_id": str(applicant_id),
        "subject_kind": SUBJECT_APPLICANT,
        "dry_run": False,
        "status": "completed",
        "anonymized": {"applicant": True},
    }


# --- Unified dispatch for User-keyed EraseRequest subjects ---------------------

def scrub_user_subject(
    school_id: int,
    user_id: int,
    *,
    dry_run: bool = False,
    requested_by_user_id: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Dispatch a User-keyed erasure to the correct subject handler.

    Resolves the subject kind within the tenant and routes student → the
    canonical ``gdpr_scrub_student`` (via StudentProfile.id), staff →
    ``gdpr_scrub_staff``, guardian → ``gdpr_scrub_guardian``. Returns a
    structured ``unsupported_subject_kind`` only when the User has NO PII
    relationship in this tenant — every real subject type is now covered.
    """
    kind = resolve_subject_kind(school_id, user_id)
    if kind == SUBJECT_STUDENT:
        from apps.compliance.gdpr_services import gdpr_scrub_student

        StudentProfile = _get_model("people", "StudentProfile")
        student = (
            StudentProfile.objects.filter(school_id=school_id, user_id=user_id)
            .only("id")
            .first()
            if StudentProfile
            else None
        )
        if not student:
            return {"ok": False, "error": "unsupported_subject_kind", "user_id": user_id}
        return gdpr_scrub_student(
            school_id,
            student.id,
            dry_run=dry_run,
            requested_by_user_id=requested_by_user_id,
        )
    if kind == SUBJECT_STAFF:
        return gdpr_scrub_staff(
            school_id,
            user_id,
            dry_run=dry_run,
            requested_by_user_id=requested_by_user_id,
            force=force,
        )
    if kind == SUBJECT_GUARDIAN:
        return gdpr_scrub_guardian(
            school_id,
            user_id,
            dry_run=dry_run,
            requested_by_user_id=requested_by_user_id,
            force=force,
        )
    return {
        "ok": False,
        "error": "unsupported_subject_kind: user has no PII relationship in this tenant.",
        "user_id": user_id,
        "subject_kind": kind,
    }
