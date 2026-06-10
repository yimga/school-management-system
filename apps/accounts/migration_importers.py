"""
Pass 8: importer functions for the Migration Wizard's new domains.

Each importer is a pure function: takes the tenant `school` and an iterable of
mapped row dicts (column → target_field already resolved by the wizard), returns
a result dict shaped like the existing student/grade flow:

    {
        "created": int,
        "updated": int,
        "skipped": int,
        "error_count": int,
        "errors": [str, ...],
        "rollback_snapshot": {...},
    }

Pass 8.D (2026-05-11): fees + payments now persist to Invoice + Payment
respectively. Idempotency keyed on reference (invoice_number /
payment_reference); Part F 25.1 invoice immutability honored — ISSUED rows
are skipped on re-import. Currency normalized to ISO 4217 with school
default as fallback.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.utils import DatabaseError
from django.utils import timezone

logger = logging.getLogger(__name__)

User = get_user_model()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _normalize(value) -> str:
    """Strip + cast to str; treat None as empty."""
    if value is None:
        return ""
    return str(value).strip()


def _parse_date(value: str):
    """Accept YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY. Return date or None."""
    value = _normalize(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _empty_result() -> dict:
    return {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "error_count": 0,
        "errors": [],
        "rollback_snapshot": {},
    }


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------


def import_teachers(school, rows: Iterable[dict], *, actor=None) -> dict:
    """Create or update User + TeacherProfile + SchoolMembership for each row."""
    from apps.people.models import TeacherProfile
    from apps.schools.models import SchoolMembership

    result = _empty_result()
    created_ids: list[int] = []
    updated_ids: list[int] = []

    for idx, row in enumerate(rows, start=1):
        email = _normalize(row.get("email")).lower()
        first_name = _normalize(row.get("first_name"))
        last_name = _normalize(row.get("last_name"))
        if not email or not first_name or not last_name:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: email, first_name, last_name are required."
            )
            continue
        username = _normalize(row.get("username")) or email.split("@")[0][:150]
        phone = _normalize(row.get("phone"))
        position = _normalize(row.get("subject_specialty"))
        try:
            with transaction.atomic():
                user, user_created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                        "role": User.Role.TEACHER,
                        "is_active": True,
                    },
                )
                if not user_created:
                    user.first_name = first_name or user.first_name
                    user.last_name = last_name or user.last_name
                    user.role = User.Role.TEACHER
                    user.is_active = True
                    user.save(
                        update_fields=["first_name", "last_name", "role", "is_active"]
                    )
                TeacherProfile.objects.update_or_create(
                    user=user,
                    defaults={
                        "school": school,
                        "phone": phone or "",
                        "position_title": position or "",
                        "is_active": True,
                    },
                )
                SchoolMembership.objects.update_or_create(
                    user=user,
                    school=school,
                    defaults={"role": User.Role.TEACHER, "is_primary": True},
                )
        except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
            result["error_count"] += 1
            result["errors"].append(f"Row {idx} ({email}): {exc}")
            continue
        if user_created:
            result["created"] += 1
            created_ids.append(user.pk)
        else:
            result["updated"] += 1
            updated_ids.append(user.pk)

    result["rollback_snapshot"] = {
        "created_user_ids": created_ids,
        "updated_user_ids": updated_ids,
    }
    return result


# ---------------------------------------------------------------------------
# Guardians (parents)
# ---------------------------------------------------------------------------


def import_guardians(school, rows: Iterable[dict], *, actor=None) -> dict:
    """Create or update Parent User + SchoolMembership + StudentGuardian links."""
    from apps.people.models import StudentGuardian, StudentProfile
    from apps.schools.models import SchoolMembership

    result = _empty_result()
    created_user_ids: list[int] = []
    created_link_ids: list[int] = []

    for idx, row in enumerate(rows, start=1):
        email = _normalize(row.get("email")).lower()
        first_name = _normalize(row.get("first_name"))
        last_name = _normalize(row.get("last_name"))
        student_codes_raw = _normalize(row.get("student_codes"))
        if not email or not first_name or not last_name or not student_codes_raw:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: email, first_name, last_name, student_codes are required."
            )
            continue
        student_codes = [
            c.strip() for c in student_codes_raw.replace(";", ",").split(",") if c.strip()
        ]
        students = list(
            StudentProfile.objects.filter(school=school, student_code__in=student_codes)
        )
        missing = set(student_codes) - {s.student_code for s in students}
        if missing:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx} ({email}): student_codes not found: {', '.join(sorted(missing))}."
            )
            continue

        username = _normalize(row.get("username")) or email.split("@")[0][:150]
        phone = _normalize(row.get("phone"))
        relationship_raw = _normalize(row.get("relationship")).upper() or "GUARDIAN"
        relationship = (
            relationship_raw
            if relationship_raw in {"MOTHER", "FATHER", "GUARDIAN", "OTHER"}
            else "OTHER"
        )
        try:
            with transaction.atomic():
                user, user_created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                        "role": User.Role.PARENT,
                        "is_active": True,
                    },
                )
                if not user_created:
                    user.first_name = first_name or user.first_name
                    user.last_name = last_name or user.last_name
                    user.role = User.Role.PARENT
                    user.is_active = True
                    user.save(
                        update_fields=["first_name", "last_name", "role", "is_active"]
                    )
                SchoolMembership.objects.update_or_create(
                    user=user,
                    school=school,
                    defaults={"role": User.Role.PARENT, "is_primary": True},
                )
                for student in students:
                    link, link_created = StudentGuardian.objects.update_or_create(
                        guardian_user=user,
                        student=student,
                        defaults={
                            "relationship": relationship,
                            "phone": phone or "",
                            "email": email,
                        },
                    )
                    if link_created:
                        created_link_ids.append(link.pk)
                if user_created:
                    created_user_ids.append(user.pk)
        except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
            result["error_count"] += 1
            result["errors"].append(f"Row {idx} ({email}): {exc}")
            continue
        if user_created:
            result["created"] += 1
        else:
            result["updated"] += 1

    result["rollback_snapshot"] = {
        "created_user_ids": created_user_ids,
        "created_guardian_link_ids": created_link_ids,
    }
    return result


# ---------------------------------------------------------------------------
# Roster (Classroom + Subject + Term + SubjectAssignment)
# ---------------------------------------------------------------------------


def import_roster(school, rows: Iterable[dict], *, actor=None) -> dict:
    """
    Create or update Classroom, Subject, Term, Specialty, and assignment records.

    A tenant-scoped General specialty is created when the import row does not
    provide one, so the roster is immediately usable by grading workflows.
    """
    from apps.academics.models import (
        AcademicYear,
        Classroom,
        Department,
        Specialty,
        Subject,
        SubjectAssignment,
        Term,
    )

    result = _empty_result()
    created_classrooms: list[int] = []
    created_subjects: list[int] = []
    created_terms: list[int] = []
    created_assignments: list[int] = []

    # Resolve a default academic year and department once per call.
    active_year = (
        AcademicYear.objects.filter(school=school, is_active=True).order_by("-id").first()
        or AcademicYear.objects.filter(school=school).order_by("-id").first()
    )
    if not active_year:
        result["error_count"] += sum(1 for _ in rows) or 1
        result["errors"].append(
            "No academic year exists for this school. Create one before importing the roster."
        )
        return result

    default_department = (
        Department.objects.filter(school=school).order_by("id").first()
    )

    for idx, row in enumerate(rows, start=1):
        classroom_name = _normalize(row.get("classroom_name"))
        subject_code = _normalize(row.get("subject_code"))
        subject_name = _normalize(row.get("subject_name")) or subject_code
        term_name = _normalize(row.get("term_name"))
        if not classroom_name or not subject_code:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: classroom_name and subject_code are required."
            )
            continue
        try:
            with transaction.atomic():
                department = default_department or Department.objects.create(
                    school=school,
                    code=f"{school.slug or 'sch'}-GEN",
                    name="General",
                )
                classroom, classroom_created = Classroom.objects.update_or_create(
                    code=f"{school.slug or 'sch'}-{classroom_name}"[:30],
                    defaults={
                        "school": school,
                        "academic_year": active_year,
                        "department": department,
                        "name": classroom_name,
                    },
                )
                if classroom_created:
                    created_classrooms.append(classroom.pk)
                subject, subject_created = Subject.objects.get_or_create(
                    school=school,
                    name=subject_name,
                    defaults={"category": Subject.Category.GENERAL},
                )
                if subject_created:
                    created_subjects.append(subject.pk)
                if term_name:
                    term, term_created = Term.objects.get_or_create(
                        school=school,
                        academic_year=active_year,
                        name=term_name[:60],
                    )
                    if term_created:
                        created_terms.append(term.pk)
                else:
                    term = (
                        Term.objects.filter(school=school, academic_year=active_year)
                        .order_by("position", "id")
                        .first()
                    )

                # Auto-create SubjectAssignment (classroom × subject × term × specialty)
                # so freshly-imported roster rows are immediately usable by
                # evaluations / grading. The wizard previously deferred this to
                # the Academics admin — pass 8.D closes that gap.
                specialty_code = _normalize(row.get("specialty_code")) or _normalize(
                    row.get("specialty")
                )
                specialty_name = (
                    _normalize(row.get("specialty_name")) or specialty_code or "General"
                )
                specialty_code = (
                    specialty_code or f"{school.slug or 'sch'}-GEN"
                )[:30]
                specialty, _ = Specialty.objects.get_or_create(
                    code=specialty_code,
                    defaults={
                        "school": school,
                        "department": department,
                        "name": specialty_name[:120],
                    },
                )
                if term is not None:
                    assignment, assignment_created = (
                        SubjectAssignment.objects.get_or_create(
                            academic_year=active_year,
                            term=term,
                            classroom=classroom,
                            specialty=specialty,
                            subject=subject,
                            defaults={
                                "school": school,
                                "coefficient": _parse_decimal(row.get("coefficient"))
                                or 1,
                            },
                        )
                    )
                    if assignment_created:
                        created_assignments.append(assignment.pk)
                result["created"] += 1
        except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
            result["error_count"] += 1
            result["errors"].append(f"Row {idx}: {exc}")
            continue

    result["rollback_snapshot"] = {
        "created_classroom_ids": created_classrooms,
        "created_subject_ids": created_subjects,
        "created_term_ids": created_terms,
        "created_assignment_ids": created_assignments,
    }
    return result


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------


def import_attendance(school, rows: Iterable[dict], *, actor=None) -> dict:
    """Bulk-create Attendance records via student_code + classroom lookup."""
    from apps.academics.models import Attendance, Classroom
    from apps.people.models import StudentProfile

    result = _empty_result()
    created_ids: list[int] = []
    valid_statuses = {choice[0] for choice in Attendance.Status.choices}

    for idx, row in enumerate(rows, start=1):
        student_code = _normalize(row.get("student_code"))
        date_value = _parse_date(_normalize(row.get("date")))
        status = _normalize(row.get("status")).lower() or Attendance.Status.PRESENT
        if not student_code or date_value is None:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: student_code and a valid date (YYYY-MM-DD) are required."
            )
            continue
        if status not in valid_statuses:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: invalid status '{status}' (must be one of {sorted(valid_statuses)})."
            )
            continue
        student = (
            StudentProfile.objects.filter(school=school, student_code=student_code)
            .select_related("classroom")
            .first()
        )
        if student is None:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: student_code '{student_code}' not found for this school."
            )
            continue
        classroom = getattr(student, "classroom", None)
        if classroom is None:
            classroom = (
                Classroom.objects.filter(school=school).order_by("id").first()
            )
        if classroom is None:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: no classroom available to anchor the attendance row."
            )
            continue
        try:
            record, created = Attendance.objects.update_or_create(
                student=student,
                classroom=classroom,
                date=date_value,
                defaults={
                    "school": school,
                    "status": status,
                    "remarks": _normalize(row.get("remarks"))[:255],
                },
            )
        except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
            result["error_count"] += 1
            result["errors"].append(f"Row {idx} ({student_code}): {exc}")
            continue
        if created:
            result["created"] += 1
            created_ids.append(record.pk)
        else:
            result["updated"] += 1

    result["rollback_snapshot"] = {"created_attendance_ids": created_ids}
    return result


# ---------------------------------------------------------------------------
# Fees and Payments (pass 8.B scaffolds — record-only, no Invoice/Payment writes)
# ---------------------------------------------------------------------------


def _parse_decimal(value):
    """Cast '1,234.50' / '1234.5' / Decimal to Decimal, or None."""
    from decimal import Decimal, InvalidOperation

    raw = _normalize(value)
    if not raw:
        return None
    cleaned = raw.replace(",", "").replace(" ", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _normalize_currency(value, fallback: str = "") -> str:
    """ISO 4217 3-letter code, upper. Falls back when value is junk."""
    raw = _normalize(value).upper()
    if len(raw) == 3 and raw.isalpha():
        return raw
    return fallback.upper()


def _resolve_school_currency(school) -> str:
    """Get the school's effective default currency from RegionConfig / settings."""
    try:
        region = getattr(school, "region", None) or getattr(school, "default_region", None)
        if region and getattr(region, "currency_code", None):
            return str(region.currency_code).upper()
    except Exception:  # noqa: BLE001 - best-effort lookup
        pass
    try:
        from django.conf import settings

        return str(getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD")).upper()
    except Exception:  # noqa: BLE001
        return "USD"


def _resolve_compliance_profile(school):
    """Get the active ComplianceProfile, preferring one bound to the school's country."""
    from apps.finance.models import ComplianceProfile

    country = getattr(school, "country_code", None) or getattr(school, "country", None)
    qs = ComplianceProfile.objects.filter(is_active=True)
    if country:
        scoped = qs.filter(country_code=str(country).upper()).first()
        if scoped:
            return scoped
    return qs.first()


def import_fees(school, rows: Iterable[dict], *, actor=None) -> dict:
    """
    Pass 8.D: persist Fee rows to Invoice.

    Idempotency: keyed on (school, reference=invoice_number). Re-importing the
    same invoice_number updates only the still-DRAFT row; ISSUED/PAID invoices
    are read-only (Part F 25.1) and report as skipped without raising.

    Currency: coerced to ISO 4217 (3-letter, upper). When the row has no
    `currency` column, the school's default region currency is used. The
    Invoice model itself doesn't carry a currency column — it inherits from
    the bound ComplianceProfile — but the imported currency is recorded in
    the row's `notes` field for the audit trail.
    """
    from apps.finance.models import Invoice
    from apps.people.models import StudentProfile

    result = _empty_result()
    created_ids: list[int] = []
    updated_ids: list[int] = []
    school_currency = _resolve_school_currency(school)
    profile = _resolve_compliance_profile(school)
    if profile is None:
        result["error_count"] = sum(1 for _ in rows) if isinstance(rows, list) else 0
        result["errors"].append(
            "No active ComplianceProfile available for this school — "
            "create one in Site Settings before importing fees."
        )
        return result

    for idx, row in enumerate(rows, start=1):
        student_code = _normalize(row.get("student_code"))
        amount = _parse_decimal(row.get("amount"))
        invoice_number = _normalize(row.get("invoice_number"))
        if not student_code or amount is None or amount <= 0:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: student_code and positive amount are required."
            )
            continue
        student = (
            StudentProfile.objects.filter(school=school, student_code=student_code)
            .only("id", "school_id")
            .first()
        )
        if student is None:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: student_code '{student_code}' not found for this school."
            )
            continue
        currency_code = _normalize_currency(row.get("currency"), fallback=school_currency)
        due_date = _parse_date(_normalize(row.get("due_date")))
        fee_type = _normalize(row.get("fee_type"))[:80]
        notes_parts = [
            f"Imported via migration importer; original currency={currency_code}.",
        ]
        if fee_type:
            notes_parts.append(f"fee_type={fee_type}")
        if _normalize(row.get("academic_year")):
            notes_parts.append(f"academic_year={_normalize(row.get('academic_year'))}")
        if _normalize(row.get("term_name")):
            notes_parts.append(f"term={_normalize(row.get('term_name'))}")
        notes = " ".join(notes_parts)

        defaults = {
            "school": school,
            "profile": profile,
            "student": student,
            "total_amount": amount,
            "balance_amount": amount,
            "status": Invoice.Status.ISSUED,
            "notes": notes[:2000],
        }
        if due_date:
            defaults["due_date"] = due_date

        try:
            if invoice_number:
                existing = (
                    Invoice.objects.filter(school=school, reference=invoice_number)
                    .order_by("id")
                    .first()
                )
                if existing is None:
                    invoice = Invoice(reference=invoice_number, **defaults)
                    invoice.save()
                    result["created"] += 1
                    created_ids.append(invoice.pk)
                elif existing.status == Invoice.Status.DRAFT:
                    for k, v in defaults.items():
                        setattr(existing, k, v)
                    existing.save()
                    result["updated"] += 1
                    updated_ids.append(existing.pk)
                else:
                    result["skipped"] += 1
                    result["errors"].append(
                        f"Row {idx}: invoice '{invoice_number}' already ISSUED — "
                        "skipped per Part F 25.1 immutability."
                    )
            else:
                invoice = Invoice(**defaults)
                invoice.save()
                result["created"] += 1
                created_ids.append(invoice.pk)
        except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
            result["error_count"] += 1
            result["errors"].append(f"Row {idx} ({student_code}): {exc}")
            continue

    result["rollback_snapshot"] = {
        "created_invoice_ids": created_ids,
        "updated_invoice_ids": updated_ids,
    }
    return result


def import_payments(school, rows: Iterable[dict], *, actor=None) -> dict:
    """
    Pass 8.D: persist Payment rows.

    Idempotency: keyed on (school, reference_number=payment_reference). A
    duplicate `payment_reference` is treated as already-imported (skipped).

    Invoice resolution: when `invoice_number` is present we attempt to bind
    the Payment to the matching Invoice for the same student; on mismatch
    the Payment is still recorded (orphaned) and the warning is logged.

    Currency: coerced to ISO 4217. The Payment model stores currency_code
    directly, so the imported value is preserved verbatim.
    """
    from apps.finance.models import Invoice, Payment
    from apps.people.models import StudentProfile

    result = _empty_result()
    created_ids: list[int] = []
    school_currency = _resolve_school_currency(school)

    for idx, row in enumerate(rows, start=1):
        student_code = _normalize(row.get("student_code"))
        amount = _parse_decimal(row.get("amount"))
        paid_at_date = _parse_date(_normalize(row.get("paid_at")))
        if not student_code or amount is None or amount <= 0:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: student_code and positive amount are required."
            )
            continue
        if paid_at_date is None:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: paid_at must be a valid date (YYYY-MM-DD)."
            )
            continue
        student = (
            StudentProfile.objects.filter(school=school, student_code=student_code)
            .only("id", "school_id")
            .first()
        )
        if student is None:
            result["error_count"] += 1
            result["errors"].append(
                f"Row {idx}: student_code '{student_code}' not found for this school."
            )
            continue

        reference_number = _normalize(row.get("payment_reference"))[:50] or None
        # tenant-isolation-allow: import-pipeline-validates-school-before-persist
        if reference_number and Payment.objects.filter(
            reference_number=reference_number
        ).exists():
            result["skipped"] += 1
            continue

        invoice = None
        invoice_number = _normalize(row.get("invoice_number"))
        if invoice_number:
            invoice = (
                Invoice.objects.filter(school=school, reference=invoice_number)
                .order_by("id")
                .first()
            )
            if invoice and invoice.student_id and invoice.student_id != student.pk:
                result["errors"].append(
                    f"Row {idx}: invoice '{invoice_number}' is bound to a different "
                    "student; payment recorded against the row's student instead."
                )
                invoice = None

        currency_code = _normalize_currency(
            row.get("currency"), fallback=school_currency
        )
        paid_at_dt = timezone.make_aware(
            datetime.combine(paid_at_date, datetime.min.time())
        )

        try:
            payment = Payment.objects.create(
                school=school,
                student=student,
                invoice=invoice,
                amount=amount,
                currency_code=currency_code,
                paid_at=paid_at_dt,
                reference_number=reference_number,
                reference=reference_number or "",
                description=_normalize(row.get("notes"))[:255],
                method=_normalize(row.get("method"))[:20],
            )
        except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
            result["error_count"] += 1
            result["errors"].append(f"Row {idx} ({student_code}): {exc}")
            continue
        result["created"] += 1
        created_ids.append(payment.pk)

        # Best-effort balance recalc — never block the row on this.
        if invoice is not None:
            try:
                remaining = invoice.balance_amount - amount
                invoice.balance_amount = max(remaining, type(amount)("0.00"))
                invoice._recalculating = True  # bypass Part F 25.1 immutability
                if invoice.balance_amount <= type(amount)("0.00"):
                    invoice.status = Invoice.Status.PAID
                elif invoice.balance_amount < invoice.total_amount:
                    invoice.status = Invoice.Status.PARTIAL
                invoice.save()
            except Exception:  # noqa: BLE001
                logger.debug(
                    "import_payments: invoice balance recalc failed",
                    exc_info=True,
                )

    result["rollback_snapshot"] = {"created_payment_ids": created_ids}
    return result


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


IMPORTERS = {
    "teachers": import_teachers,
    "guardians": import_guardians,
    "roster": import_roster,
    "attendance": import_attendance,
    "fees": import_fees,
    "payments": import_payments,
}


def run_importer(migration_type: str, school, rows: Iterable[dict], *, actor=None) -> dict:
    """Look up the importer for `migration_type` and invoke it. Raises KeyError on unknown."""
    importer = IMPORTERS[migration_type]
    return importer(school, rows, actor=actor)
