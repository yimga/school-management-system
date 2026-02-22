"""
Financial Aid & Scholarships: eligibility check, simulate and execute disbursement.
Uses nuance engine (JSON-Logic) for eligibility; audit log on every balance change.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.people.models import StudentProfile
from apps.siteconfig.nuance_engine import _safe_eval, HOOK_REGISTRY, _scrub_context, DEFAULT_ALLOWED_KEYS

from .models import (
    AwardSource,
    Scholarship,
    FinancialAidApplication,
    AidAuditLog,
    Invoice,
    InvoiceLine,
    Payment,
)


def _student_context(student: StudentProfile) -> dict[str, Any]:
    """Build context for eligibility: gpa, sibling_count, student_tags, custom_attributes, etc."""
    tags = list(student.tags.values_list("name", flat=True)) if hasattr(student, "tags") else []
    sibling_count = 0
    try:
        from apps.people.models import StudentGuardian
        guardian_ids = list(student.guardian_links.values_list("guardian_user_id", flat=True))
        if guardian_ids:
            same_guardian = StudentGuardian.objects.filter(guardian_user_id__in=guardian_ids).values_list("student_id", flat=True).distinct()
            sibling_count = max(0, len(set(same_guardian)) - 1)
    except Exception:
        pass
    custom = getattr(student, "custom_attributes", None) or {}
    gpa = custom.get("gpa")
    if gpa is None and hasattr(student, "gpa"):
        gpa = getattr(student, "gpa", None)
    attendance_rate = custom.get("attendance_rate")
    fee_status = custom.get("fee_status", "unknown")
    return {
        "gpa": float(gpa) if gpa is not None else None,
        "sibling_count": sibling_count,
        "student_tags": tags,
        "custom_attributes": custom,
        "attendance_rate": float(attendance_rate) if attendance_rate is not None else None,
        "fee_status": fee_status,
    }


def check_eligibility(student: StudentProfile, scholarship: Scholarship) -> tuple[bool, str]:
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
    try:
        result = _safe_eval(criteria, scrubbed)
    except Exception:
        return False, "Eligibility rule evaluation failed."
    if result is True:
        return True, ""
    if result is False:
        return False, "Does not meet eligibility criteria."
    return False, str(result) if result is not None else "Eligibility check returned no result."


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
    scholarship = Scholarship.objects.filter(school_id=school_id, pk=scholarship_id).first()
    if not scholarship:
        return {"error": "Scholarship not found", "total_amount": 0, "per_student": [], "insufficient_funds": True}
    source = scholarship.source
    students = list(
        StudentProfile.objects.filter(school_id=school_id, pk__in=student_ids).select_related("school")
    )
    per_student = []
    total = Decimal("0.00")
    amount_per = scholarship.award_amount
    for student in students:
        eligible, reason = check_eligibility(student, scholarship)
        per_student.append({
            "student_id": student.pk,
            "student_name": getattr(student, "user", None) and getattr(student.user, "get_full_name", lambda: str(student))() or str(student),
            "eligible": eligible,
            "reason": reason,
            "amount": amount_per if eligible else Decimal("0.00"),
        })
        if eligible:
            total += amount_per
    insufficient = source.remaining_funds < total
    return {
        "total_amount": total,
        "per_student": per_student,
        "insufficient_funds": insufficient,
        "source_remaining": source.remaining_funds,
        "scholarship_title": scholarship.title,
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
    app = FinancialAidApplication.objects.select_related("student", "scholarship", "scholarship__source").filter(
        school_id=school_id,
        pk=application_id,
    ).first()
    if not app:
        return {"ok": False, "error": "Application not found"}
    if app.status == FinancialAidApplication.Status.DISBURSED:
        return {"ok": False, "error": "Already disbursed"}
    if app.status not in (FinancialAidApplication.Status.APPROVED, FinancialAidApplication.Status.UNDER_REVIEW):
        return {"ok": False, "error": f"Invalid status for disbursement: {app.status}"}
    amount = app.amount_approved or app.scholarship.award_amount
    source = app.scholarship.source
    if source.remaining_funds < amount:
        return {"ok": False, "error": f"Insufficient funds: {source.remaining_funds} < {amount}"}

    with transaction.atomic():
        source.remaining_funds -= amount
        source.save(update_fields=["remaining_funds", "updated_at"])
        AidAuditLog.objects.create(
            school_id=school_id,
            source=source,
            action="disbursement",
            amount=-amount,
            balance_after=source.remaining_funds,
            reason=f"Disbursement for application {app_id}",
            application=app,
            created_by_id=user_id,
        )
        app.status = FinancialAidApplication.Status.DISBURSED
        app.disbursed_at = timezone.now()
        app.save(update_fields=["status", "disbursed_at", "updated_at"])
        # Create credit on student's invoice or a payment-type record
        invoice = Invoice.objects.filter(
            school_id=school_id,
            student=app.student,
            status__in=(Invoice.Status.ISSUED, Invoice.Status.PARTIAL, Invoice.Status.PAID),
        ).order_by("-issued_date").first()
        if invoice:
            InvoiceLine.objects.create(
                invoice=invoice,
                description=f"Scholarship: {app.scholarship.title}",
                quantity=Decimal("1"),
                unit_price=-amount,
                amount=-amount,
                fee_item=None,
            )
            invoice.total_amount = (invoice.total_amount or Decimal("0")) - amount
            invoice.save(update_fields=["total_amount", "updated_at"])
        else:
            Payment.objects.create(
                school_id=school_id,
                student=app.student,
                amount=amount,
                currency_code=getattr(app.scholarship.source, "currency", "USD"),
                purpose="tuition",
                description=f"Scholarship disbursement: {app.scholarship.title}",
                status="completed",
                paid_at=timezone.now(),
                completed_at=timezone.now(),
                created_by_id=user_id,
            )
    return {"ok": True, "application_id": app_id, "amount": amount}


def get_endowment_health_report(school_id: Any) -> list[dict]:
    """
    Phase 2: For each AwardSource, sum committed (APPROVED/UNDER_REVIEW not disbursed) vs remaining_funds.
    Returns list of {name, total_budget, remaining_funds, committed, net_liquidity, status}.
    """
    from django.db.models import Sum
    sources = AwardSource.objects.filter(school_id=school_id, is_active=True)
    result = []
    for src in sources:
        committed = (
            FinancialAidApplication.objects.filter(
                scholarship__source=src,
                status__in=(
                    FinancialAidApplication.Status.APPROVED,
                    FinancialAidApplication.Status.UNDER_REVIEW,
                ),
            ).aggregate(s=Sum("amount_approved"))["s"] or Decimal("0.00")
        )
        committed = committed or Decimal("0.00")
        if not isinstance(committed, Decimal):
            committed = Decimal(str(committed))
        net = src.remaining_funds - committed
        status = "HEALTHY" if net >= Decimal("0") else "CRITICAL"
        result.append({
            "id": src.pk,
            "name": src.name,
            "total_budget": src.total_budget,
            "remaining_funds": src.remaining_funds,
            "committed": committed,
            "net_liquidity": net,
            "status": status,
            "currency": src.currency,
        })
    return result


def net_price_estimate(school_id: Any, context: dict) -> dict:
    """
    Phase 7: Net Price Calculator — estimate aid and out-of-pocket from income, family size, etc.
    Uses nuance hook tuition_calc / fee_discount if available; otherwise returns list price.
    """
    from apps.siteconfig.nuance_engine import apply_nuance
    tuition = context.get("tuition") or context.get("fee") or 0
    try:
        tuition = float(tuition)
    except (TypeError, ValueError):
        tuition = 0
    school = None
    try:
        from apps.schools.models import School
        school = School.objects.filter(pk=school_id).first()
    except Exception:
        pass
    if school:
        discounted = apply_nuance(school, "tuition_calc", {**context, "fee": tuition})
        if discounted is not None:
            try:
                tuition = float(discounted)
            except (TypeError, ValueError):
                pass
    return {
        "estimated_tuition": tuition,
        "estimated_aid": max(0, (context.get("list_price") or tuition) - tuition),
        "out_of_pocket": tuition,
        "currency": context.get("currency", "USD"),
    }
