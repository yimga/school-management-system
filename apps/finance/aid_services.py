"""
Financial Aid & Scholarships: eligibility check, simulate and execute disbursement.
Uses nuance engine (JSON-Logic) for eligibility; audit log on every balance change.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.metadata.services import get_dynamic_field_map, get_dynamic_field_value
from apps.people.models import StudentProfile
from apps.siteconfig.nuance_engine import (
    DEFAULT_ALLOWED_KEYS,
    HOOK_REGISTRY,
    _scrub_context,
    evaluate_json_logic,
)

from .models import (
    AwardSource,
    Scholarship,
    FinancialAidApplication,
    AidAuditLog,
    Invoice,
    InvoiceLine,
    Payment,
)
from .services import recalculate_invoice, post_scholarship_disbursement_to_ledger


def _resolve_aid_currency(explicit=None, *, school=None, school_id=None) -> str:
    """Local-first ISO 4217 currency for aid / scholarship money.

    Precedence: an explicit per-row value -> the school's ``resolve_currency()``
    cascade -> ``PLATFORM_DEFAULT_CURRENCY``. Never a hardcoded ``"USD"`` tenant
    lock: a non-USD school's scholarship disbursement / net-price estimate must
    carry the school's real currency. Degrade-safe — any lookup failure falls
    through to the platform default.
    """
    from django.conf import settings

    val = str(explicit).strip() if explicit else ""
    if val:
        return val.upper()
    if school is None and school_id:
        try:
            from apps.schools.models import School

            school = School.objects.filter(pk=school_id).first()
        except Exception:  # noqa: BLE001 — currency resolution must never break disbursement
            school = None
    if school is not None:
        try:
            code = (school.resolve_currency() or "").strip()
            if code:
                return code.upper()
        except Exception:  # noqa: BLE001
            pass
    return (getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD") or "USD").upper()


def _student_context(student: StudentProfile) -> dict[str, Any]:
    """Build context for eligibility: gpa, sibling_count, student_tags, custom_attributes, etc."""
    tags = (
        list(student.tags.values_list("name", flat=True))
        if hasattr(student, "tags")
        else []
    )
    sibling_count = 0
    try:
        from apps.people.models import StudentGuardian

        guardian_ids = list(
            student.guardian_links.values_list("guardian_user_id", flat=True)
        )
        if guardian_ids:
            same_guardian = (
                StudentGuardian.objects.filter(guardian_user_id__in=guardian_ids)  # tenant-isolation-allow: bounded to an explicit guardian id set from one student's links (reviewed 2026-09-03)
                .values_list("student_id", flat=True)
                .distinct()
            )
            sibling_count = max(0, len(set(same_guardian)) - 1)
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        logging.getLogger(__name__).debug("_student_context sibling_count skip: %s", e)
    custom = get_dynamic_field_map(student)
    gpa = get_dynamic_field_value(student, "gpa", default=getattr(student, "gpa", None))
    if gpa is None and hasattr(student, "gpa"):
        gpa = getattr(student, "gpa", None)
    attendance_rate = get_dynamic_field_value(
        student, "attendance_rate", default=custom.get("attendance_rate")
    )
    fee_status = get_dynamic_field_value(
        student, "fee_status", default=custom.get("fee_status", "unknown")
    )
    return {
        "gpa": float(gpa) if gpa is not None else None,
        "sibling_count": sibling_count,
        "student_tags": tags,
        "custom_attributes": custom,
        "attendance_rate": float(attendance_rate)
        if attendance_rate is not None
        else None,
        "fee_status": fee_status,
    }


def _restricted_purpose_error(source: AwardSource, scholarship: Scholarship) -> str | None:
    """
    Return an error string if a restricted source rejects this scholarship's purpose,
    else None. A non-restricted source (or one with no declared purpose) never blocks.
    """
    if not getattr(source, "is_restricted", False):
        return None
    required = (getattr(source, "restricted_purpose", "") or "").strip()
    if not required:
        return None
    actual = (getattr(scholarship, "purpose", "") or "").strip()
    if actual.casefold() == required.casefold():
        return None
    return (
        f"Restricted fund '{source.name}' permits only purpose '{required}'; "
        f"scholarship purpose is '{actual or 'unset'}'."
    )


def check_eligibility(
    student: StudentProfile, scholarship: Scholarship
) -> tuple[bool, str]:
    """
    Run scholarship.eligibility_criteria (JSON-Logic) against student context.
    Returns (True, "") if eligible, (False, reason) otherwise.
    """
    context = _student_context(student)
    criteria = scholarship.eligibility_criteria
    if not criteria:
        return True, ""
    allowed = set(HOOK_REGISTRY.get("scholarship_eligibility", DEFAULT_ALLOWED_KEYS))
    scrubbed = _scrub_context(context, allowed)
    result = evaluate_json_logic(criteria, scrubbed)
    if result is None and criteria:
        return False, "Eligibility rule evaluation failed or timed out."
    if result is True:
        return True, ""
    if result is False:
        return False, "Does not meet eligibility criteria."
    return False, str(
        result
    ) if result is not None else "Eligibility check returned no result."


def simulate_bulk_disbursement(
    scholarship_id: int,
    student_ids: list[int],
    *,
    school_id: Any,
) -> dict[str, Any]:
    """
    Simulate disbursing to given students. Returns summary: total_amount, per_student, insufficient_funds.
    Does not modify DB.
    """
    scholarship = Scholarship.objects.filter(
        school_id=school_id, pk=scholarship_id
    ).first()
    if not scholarship:
        return {
            "error": "Scholarship not found",
            "total_amount": 0,
            "per_student": [],
            "insufficient_funds": True,
        }
    source = scholarship.source
    students = list(
        StudentProfile.objects.filter(
            school_id=school_id, pk__in=student_ids
        ).select_related("school")
    )
    per_student = []
    total = Decimal("0.00")
    amount_per = scholarship.award_amount
    for student in students:
        eligible, reason = check_eligibility(student, scholarship)
        per_student.append(
            {
                "student_id": student.pk,
                "student_name": getattr(student, "user", None)
                and getattr(student.user, "get_full_name", lambda: str(student))()
                or str(student),
                "eligible": eligible,
                "reason": reason,
                "amount": amount_per if eligible else Decimal("0.00"),
            }
        )
        if eligible:
            total += amount_per
    insufficient = source.remaining_funds < total
    return {
        "total_amount": total,
        "per_student": per_student,
        "insufficient_funds": insufficient,
        "source_remaining": source.remaining_funds,
        "scholarship_title": scholarship.title,
        "restriction_error": _restricted_purpose_error(source, scholarship),
    }


def execute_disbursement(
    application_id: int,
    *,
    school_id: Any,
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    In a transaction: decrement source.remaining_funds, set Application to DISBURSED,
    create Invoice line (credit) or Payment record, write AidAuditLog.
    """
    app = (
        FinancialAidApplication.objects.select_related(
            "student", "scholarship", "scholarship__source"
        )
        .filter(
            school_id=school_id,
            pk=application_id,
        )
        .first()
    )
    if not app:
        return {"ok": False, "error": "Application not found"}
    if app.status == FinancialAidApplication.Status.DISBURSED:
        return {"ok": False, "error": "Already disbursed"}
    if app.status not in (
        FinancialAidApplication.Status.APPROVED,
        FinancialAidApplication.Status.UNDER_REVIEW,
    ):
        return {"ok": False, "error": f"Invalid status for disbursement: {app.status}"}
    amount = app.amount_approved or app.scholarship.award_amount
    source = app.scholarship.source
    purpose_error = _restricted_purpose_error(source, app.scholarship)
    if purpose_error:
        return {"ok": False, "error": purpose_error}
    if source.remaining_funds < amount:
        return {
            "ok": False,
            "error": f"Insufficient funds: {source.remaining_funds} < {amount}",
        }

    with transaction.atomic():
        source.remaining_funds -= amount
        source.save(update_fields=["remaining_funds", "updated_at"])
        AidAuditLog.objects.create(
            school_id=school_id,
            source=source,
            action="disbursement",
            amount=-amount,
            balance_after=source.remaining_funds,
            reason=f"Disbursement for application {app.pk}",
            application=app,
            created_by_id=user_id,
        )
        app.status = FinancialAidApplication.Status.DISBURSED
        app.disbursed_at = timezone.now()
        app.save(update_fields=["status", "disbursed_at", "updated_at"])
        # Create credit on student's invoice or a payment-type record
        invoice = (
            Invoice.objects.filter(
                school_id=school_id,
                student=app.student,
                status__in=(
                    Invoice.Status.ISSUED,
                    Invoice.Status.PARTIAL,
                    Invoice.Status.PAID,
                ),
            )
            .order_by("-issued_date")
            .first()
        )
        created_payment = None
        if invoice:
            InvoiceLine.objects.create(
                invoice=invoice,
                description=f"Scholarship: {app.scholarship.title}",
                quantity=Decimal("1"),
                unit_price=-amount,
                amount=-amount,
                fee_item=None,
            )
            recalculate_invoice(invoice)
        else:
            created_payment = Payment.objects.create(
                school_id=school_id,
                student=app.student,
                amount=amount,
                currency_code=_resolve_aid_currency(
                    getattr(app.scholarship.source, "currency", None),
                    school_id=school_id,
                ),
                purpose="tuition",
                description=f"Scholarship disbursement: {app.scholarship.title}",
                method="BANK",
                status="completed",
                paid_at=timezone.now(),
                completed_at=timezone.now(),
                created_by_id=user_id,
            )
        post_scholarship_disbursement_to_ledger(
            application=app,
            amount=amount,
            invoice=invoice,
            payment=created_payment,
        )
        try:
            from apps.events.webhooks import enqueue_webhook_event

            enqueue_webhook_event(
                school=app.student.school,
                event_type="finance.aid_disbursed",
                event_id=f"aid-disbursed-{app.pk}",
                data={
                    "application_id": app.pk,
                    "student_id": app.student_id,
                    "scholarship_id": app.scholarship_id,
                    "source_id": source.pk,
                    "amount": str(amount),
                    "currency": source.currency,
                    "invoice_id": getattr(invoice, "pk", None),
                    "payment_id": getattr(created_payment, "pk", None),
                },
            )
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            ConnectionError,
            OSError,
        ) as e:
            logging.getLogger(__name__).debug(
                "disbursement webhook enqueue skip: %s", e
            )
    return {"ok": True, "application_id": app.pk, "amount": amount}


def credit_award_source(
    *,
    school_id: Any,
    source_id: Any,
    amount: Decimal,
    currency: str | None = None,
    reason: str = "",
    user_id: int | None = None,
    method: str = "",
) -> dict[str, Any]:
    """
    Inflow side of the aid loop: credit a donation INTO an AwardSource fund.

    Mirrors execute_disbursement's outflow — bumps remaining_funds (and total_budget,
    so committed-vs-remaining health stays consistent) and writes an AidAuditLog
    action='donation'. Tenant-scoped by school_id; refuses currency mismatch so a
    USD gift never silently inflates an EUR fund.
    """
    if amount is None:
        return {"ok": False, "error": "Amount is required"}
    if not isinstance(amount, Decimal):
        try:
            amount = Decimal(str(amount))
        except (ArithmeticError, TypeError, ValueError):
            return {"ok": False, "error": "Amount is not a valid number"}
    if amount <= 0:
        return {"ok": False, "error": "Amount must be positive"}
    source = AwardSource.objects.filter(school_id=school_id, pk=source_id).first()
    if not source:
        return {"ok": False, "error": "Award source not found"}
    if currency and source.currency and currency.upper() != source.currency.upper():
        return {
            "ok": False,
            "error": f"Currency mismatch: gift {currency} vs fund {source.currency}",
        }
    with transaction.atomic():
        source.remaining_funds += amount
        source.total_budget += amount
        source.save(update_fields=["remaining_funds", "total_budget", "updated_at"])
        audit = AidAuditLog.objects.create(
            school_id=school_id,
            source=source,
            action="donation",
            amount=amount,
            balance_after=source.remaining_funds,
            reason=(reason or "Donation")[:255],
            created_by_id=user_id,
        )
        # Post the INFLOW to the GL so it mirrors disbursement (which posts the
        # outflow) — double-entry symmetry. No-op when no compliance profile.
        from .services import post_donation_to_ledger

        post_donation_to_ledger(
            school=source.school,
            amount=amount,
            reference_id=audit.pk,
            memo=(reason or "Donation")[:255],
            method=method or "",
        )
    return {
        "ok": True,
        "source_id": source.pk,
        "amount": amount,
        "balance_after": source.remaining_funds,
    }


def get_endowment_health_report(school_id: Any, *, years_ahead: int = 4) -> list[dict]:
    """
    Phase 2: For each AwardSource, sum committed (APPROVED/UNDER_REVIEW not disbursed) vs remaining_funds.
    Returns list of {name, total_budget, remaining_funds, committed, net_liquidity, status}.
    """
    from django.db.models import Sum

    years_ahead = max(1, min(int(years_ahead), 6))
    sources = AwardSource.objects.filter(school_id=school_id, is_active=True)
    result = []
    trailing_window_start = timezone.now() - timedelta(days=365)  # magic-number-allow: retention-window-days
    for src in sources:
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        committed = FinancialAidApplication.objects.filter(
            scholarship__source=src,
            status__in=(
                FinancialAidApplication.Status.APPROVED,
                FinancialAidApplication.Status.UNDER_REVIEW,
            ),
        ).aggregate(s=Sum("amount_approved"))["s"] or Decimal("0.00")
        committed = committed or Decimal("0.00")
        if not isinstance(committed, Decimal):
            committed = Decimal(str(committed))

        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        # Use trailing 12-month disbursement activity as a conservative annual burn estimate.
        burn_aggregate = AidAuditLog.objects.filter(
            source=src,
            action="disbursement",
            created_at__gte=trailing_window_start,
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
        annual_burn_estimate = abs(Decimal(str(burn_aggregate)))

        net = src.remaining_funds - committed
        status = "HEALTHY" if net >= Decimal("0") else "CRITICAL"
        projections = []
        projected = net
        for year in range(1, years_ahead + 1):
            projected = projected - annual_burn_estimate
            projections.append(
                {
                    "year_offset": year,
                    "projected_net_liquidity": projected,
                    "status": "HEALTHY" if projected >= Decimal("0") else "CRITICAL",
                }
            )
        result.append(
            {
                "id": src.pk,
                "name": src.name,
                "total_budget": src.total_budget,
                "remaining_funds": src.remaining_funds,
                "committed": committed,
                "net_liquidity": net,
                "status": status,
                "currency": src.currency,
                "annual_burn_estimate": annual_burn_estimate,
                "projections": projections,
            }
        )
    return result


def net_price_estimate(school_id: Any, context: dict) -> dict:
    """
    Phase 7: Net Price Calculator — estimate aid and out-of-pocket from income, family size, etc.
    Uses nuance hook tuition_calc / fee_discount if available; otherwise returns list price.
    """
    from apps.siteconfig.nuance_engine import apply_nuance

    tuition = context.get("tuition") or context.get("fee") or 0
    try:
        tuition = float(tuition)  # money-float-allow: scalar-coerce-input (net-price estimator)
    except (TypeError, ValueError):
        tuition = 0
    school = None
    try:
        from apps.schools.models import School

        school = School.objects.filter(pk=school_id).first()
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        logging.getLogger(__name__).debug(
            "net_price_estimate School lookup skip: %s", e
        )
    if school:
        discounted = apply_nuance(school, "tuition_calc", {**context, "fee": tuition})
        if discounted is not None:
            try:
                tuition = float(discounted)  # money-float-allow: scalar-coerce-input (nuance-engine result)
            except (TypeError, ValueError):
                pass
    return {
        "estimated_tuition": tuition,
        "estimated_aid": max(0, (context.get("list_price") or tuition) - tuition),
        "out_of_pocket": tuition,
        "currency": _resolve_aid_currency(context.get("currency"), school=school),
    }
