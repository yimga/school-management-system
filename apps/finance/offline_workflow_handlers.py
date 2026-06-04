"""
Server-side apply for finance field_capture workflows (batch 1511).

Mirrors live Django form paths with idempotent FinanceOfflineCaptureRecord rows.
"""

from __future__ import annotations

import json
import logging
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.finance.models_offline_capture import FinanceOfflineCaptureRecord

logger = logging.getLogger(__name__)
User = get_user_model()

FINANCE_WORKFLOWS: frozenset[str] = frozenset(
    {
        "finance_cash_closure",
        "finance_suspense_claim",
        "finance_access_bulk",
        "finance_access_request",
        "finance_generate_fees",
        "finance_split_allocation",
        "finance_report_request",
        "finance_requests_inbox",
        "finance_permission_to_pay_open",
        "finance_permission_to_pay_approve",
        "finance_invoice_detail",
        "finance_scan_teller",
    }
)


def _client_key(payload: dict[str, Any]) -> str:
    return str(
        payload.get("client_offline_id")
        or payload.get("idempotency_key")
        or "",
    )[:128]


def _existing_capture(
    school_id: int, client_offline_id: str
) -> FinanceOfflineCaptureRecord | None:
    key = (client_offline_id or "").strip()
    if not key:
        return None
    return FinanceOfflineCaptureRecord.objects.filter(
        school_id=school_id,
        client_offline_id=key,
    ).first()


def _record_capture(
    *,
    school_id: int,
    user_id: int,
    workflow: str,
    client_offline_id: str,
    status: str,
    fields: dict[str, Any],
    result_summary: dict[str, Any],
    profile_id: int | None = None,
    error_message: str = "",
) -> FinanceOfflineCaptureRecord:
    key = (client_offline_id or "").strip()[:128]
    existing = _existing_capture(school_id, key) if key else None
    if existing:
        return existing
    return FinanceOfflineCaptureRecord.objects.create(
        school_id=school_id,
        workflow=workflow,
        client_offline_id=key,
        status=status,
        source=FinanceOfflineCaptureRecord.Source.OFFLINE,
        fields_snapshot=fields,
        result_summary=result_summary,
        error_message=error_message[:500],
        profile_id=profile_id,
        created_by_id=user_id,
    )


def _profile_for_school(school_id: int):
    from apps.finance.models import ComplianceProfile
    from apps.schools.models import School
    from apps.siteconfig.config_service import get_effective_site_settings

    school = School.objects.filter(pk=school_id).first()
    site = get_effective_site_settings(school=school) if school else None
    profile = getattr(site, "compliance_profile", None) if site else None
    if profile is not None:
        return profile
    return ComplianceProfile.objects.filter(is_active=True).first()


def apply_finance_workflow(
    school_id: int,
    user_id: int,
    workflow: str,
    fields: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if workflow not in FINANCE_WORKFLOWS:
        return None
    handlers = {
        "finance_cash_closure": _apply_cash_closure,
        "finance_suspense_claim": _apply_suspense_claim,
        "finance_access_bulk": _apply_access_bulk,
        "finance_access_request": _apply_access_request,
        "finance_generate_fees": _apply_generate_fees_pending,
        "finance_split_allocation": _apply_split_allocation,
        "finance_report_request": _apply_report_request,
        "finance_requests_inbox": _apply_requests_inbox,
        "finance_permission_to_pay_open": _apply_permission_to_pay_open,
        "finance_permission_to_pay_approve": _apply_permission_to_pay_approve,
        "finance_invoice_detail": _apply_invoice_detail_note,
        "finance_scan_teller": _apply_scan_teller_pending,
    }
    handler = handlers.get(workflow)
    if not handler:
        return None
    return handler(school_id, user_id, fields, payload)


def _apply_cash_closure(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.finance.forms import CashOfficeClosureForm
    from apps.finance.models import CashOfficeClosure, Payment, PaymentMethodCode

    profile = _profile_for_school(school_id)
    if not profile:
        return {"ok": False, "error": "no_compliance_profile"}

    form = CashOfficeClosureForm(data=fields, profile=profile)
    if not form.is_valid():
        return {"ok": False, "error": "validation", "details": dict(form.errors)}

    closure_date = form.cleaned_data["closure_date"]
    # tenant-isolation-allow: finance-payment-scoped-via-invoice-compliance-profile-school
    cash_collected = Payment.objects.filter(
        invoice__profile=profile,
        invoice__school_id=school_id,
        method=PaymentMethodCode.CASH,
        status="completed",
        paid_at__date=closure_date,
    ).aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"] or Decimal(
        "0.00"
    )

    with transaction.atomic():
        closure, _created = CashOfficeClosure.objects.get_or_create(
            profile=profile,
            closure_date=closure_date,
        )
        closure.opening_cash = form.cleaned_data["opening_cash"]
        closure.cash_collected = cash_collected
        closure.deposited_to_bank = form.cleaned_data["deposited_to_bank"]
        closure.cash_on_hand = form.cleaned_data["cash_on_hand"]
        closure.bank_account = form.cleaned_data["bank_account"]
        closure.deposit_reference = form.cleaned_data["deposit_reference"]
        closure.notes = form.cleaned_data["notes"]
        closure.status = CashOfficeClosure.Status.CLOSED
        closure.closed_by_id = user_id
        closure.save()

    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="finance_cash_closure",
        client_offline_id=_client_key(payload),
        status=FinanceOfflineCaptureRecord.Status.APPLIED,
        fields=fields,
        result_summary={
            "closure_id": closure.pk,
            "closure_date": closure_date.isoformat(),
            "discrepancy": str(closure.discrepancy),
        },
        profile_id=profile.pk,
    )
    return {
        "ok": True,
        "workflow_applied": "finance_cash_closure",
        "capture_id": capture.pk,
        "closure_id": closure.pk,
    }


def _apply_suspense_claim(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.finance.bank_statement_import import BankStatementImportService
    from apps.finance.models import SuspensePayment

    try:
        suspense_id = int(fields.get("suspense_id") or fields.get("suspense_payment_id"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "missing_suspense_id"}

    raw_allocations = fields.get("allocations") or ""
    if isinstance(raw_allocations, (list, dict)):
        allocations = raw_allocations
    else:
        try:
            allocations = json.loads(str(raw_allocations))
        except json.JSONDecodeError:
            return {"ok": False, "error": "invalid_allocations_json"}

    suspense = SuspensePayment.objects.filter(pk=suspense_id).first()
    if not suspense:
        return {"ok": False, "error": "suspense_not_found"}

    user = User.objects.filter(pk=user_id).first()
    if not user:
        return {"ok": False, "error": "user_not_found"}

    try:
        result = BankStatementImportService().claim_suspense_payment(
            suspense_payment=suspense,
            allocations=allocations,
            claimed_by=user,
            notes=str(fields.get("notes") or "")[:500],
        )
    except Exception as exc:  # noqa: BLE001 — surface to offline conflict UI
        logger.warning("offline finance_suspense_claim failed: %s", exc)
        return {"ok": False, "error": str(exc)}

    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="finance_suspense_claim",
        client_offline_id=_client_key(payload),
        status=FinanceOfflineCaptureRecord.Status.APPLIED,
        fields=fields,
        result_summary={"suspense_id": suspense_id, **result},
    )
    return {
        "ok": True,
        "workflow_applied": "finance_suspense_claim",
        "capture_id": capture.pk,
        "suspense_id": suspense_id,
    }


def _apply_access_bulk(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.people.models import StudentGuardian

    guardians = StudentGuardian.objects.filter(student__school_id=school_id)
    year = (fields.get("year") or "").strip()
    classroom = (fields.get("classroom") or "").strip()
    if year.isdigit():
        guardians = guardians.filter(student__academic_year_id=int(year))
    if classroom.isdigit():
        guardians = guardians.filter(student__classroom_id=int(classroom))

    pending_qs = guardians.filter(can_view_finance=False)
    with transaction.atomic():
        granted = pending_qs.update(can_view_finance=True)

    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="finance_access_bulk",
        client_offline_id=_client_key(payload),
        status=FinanceOfflineCaptureRecord.Status.APPLIED,
        fields=fields,
        result_summary={"granted": granted},
    )
    return {
        "ok": True,
        "workflow_applied": "finance_access_bulk",
        "capture_id": capture.pk,
        "granted": granted,
    }


def _apply_access_request(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.requests.services import create_access_request
    from apps.schools.models import School

    user = User.objects.filter(pk=user_id).first()
    if not user:
        return {"ok": False, "error": "user_not_found"}

    school = School.objects.filter(pk=school_id).first()
    intent = (fields.get("intent") or "request_finance_access").strip()
    student_ids = fields.get("student_ids") or fields.get("student_id")
    if isinstance(student_ids, str) and student_ids.isdigit():
        student_ids = [int(student_ids)]
    elif isinstance(student_ids, int):
        student_ids = [student_ids]
    elif not isinstance(student_ids, list):
        student_ids = []

    access_request = create_access_request(
        request_type="FINANCE_ACCESS",
        requester=user,
        title="Finance access request (offline sync)",
        summary=intent,
        details={
            "intent": intent,
            "student_ids": student_ids,
            "offline": True,
        },
        school=school,
        status="PENDING" if "request" in intent else "APPROVED",
    )

    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="finance_access_request",
        client_offline_id=_client_key(payload),
        status=FinanceOfflineCaptureRecord.Status.APPLIED,
        fields=fields,
        result_summary={"access_request_id": access_request.pk},
    )
    return {
        "ok": True,
        "workflow_applied": "finance_access_request",
        "capture_id": capture.pk,
        "access_request_id": access_request.pk,
    }


def _apply_generate_fees_pending(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="finance_generate_fees",
        client_offline_id=_client_key(payload),
        status=FinanceOfflineCaptureRecord.Status.PENDING_REVIEW,
        fields=fields,
        result_summary={"queued": True, "reason": "batch_job_requires_online_operator"},
        profile_id=getattr(_profile_for_school(school_id), "pk", None),
    )
    return {
        "ok": True,
        "workflow_applied": "finance_generate_fees",
        "capture_id": capture.pk,
        "pending_review": True,
    }


def _apply_report_request(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.finance.forms import ReportRequestForm
    from apps.finance.models import Notification

    form = ReportRequestForm(data=fields)
    if not form.is_valid():
        return {"ok": False, "error": "validation", "details": dict(form.errors)}

    report = form.save(commit=False)
    report.requested_by_id = user_id
    report.save()
    Notification.objects.create(
        title="Report request received (offline sync)",
        message=f"Report {report.get_report_type_display()} queued from offline capture.",
        severity=Notification.Severity.INFO,
        recipient_id=user_id,
        created_by_id=user_id,
    )
    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="finance_report_request",
        client_offline_id=_client_key(payload),
        status=FinanceOfflineCaptureRecord.Status.APPLIED,
        fields=fields,
        result_summary={"report_request_id": report.pk},
    )
    return {
        "ok": True,
        "workflow_applied": "finance_report_request",
        "capture_id": capture.pk,
        "report_request_id": report.pk,
    }


def _apply_requests_inbox(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.finance.models import Notification

    raw_ids = fields.get("notification_ids") or fields.get("mark_read_ids") or []
    if isinstance(raw_ids, str):
        raw_ids = [x.strip() for x in raw_ids.split(",") if x.strip()]
    ids = []
    for item in raw_ids:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    updated = 0
    if ids:
        updated = Notification.objects.filter(
            pk__in=ids,
            recipient_id=user_id,
        ).update(is_read=True)

    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="finance_requests_inbox",
        client_offline_id=_client_key(payload),
        status=FinanceOfflineCaptureRecord.Status.APPLIED,
        fields=fields,
        result_summary={"marked_read": updated},
    )
    return {
        "ok": True,
        "workflow_applied": "finance_requests_inbox",
        "capture_id": capture.pk,
        "marked_read": updated,
    }


def _apply_permission_to_pay_open(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.finance.forms_permission_to_pay import OpenPermissionToPayForm
    from apps.finance.permission_to_pay import PermissionToPayError, open_request

    form = OpenPermissionToPayForm(data=fields)
    if not form.is_valid():
        return {"ok": False, "error": "validation", "details": dict(form.errors)}

    cleaned = form.cleaned_data
    try:
        req = open_request(
            tenant_id=str(school_id),
            student_id=cleaned["student_id"],
            event_code=cleaned["event_code"],
            amount=cleaned["amount"],
            currency=cleaned["currency"],
            guardian_threshold=cleaned["guardian_threshold"],
        )
    except PermissionToPayError as exc:
        return {"ok": False, "error": str(exc)}

    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="finance_permission_to_pay_open",
        client_offline_id=_client_key(payload),
        status=FinanceOfflineCaptureRecord.Status.APPLIED,
        fields=fields,
        result_summary={
            "request_id": req.request_id,
            "state": req.state,
            "requires_guardian_approval": req.requires_guardian_approval,
        },
    )
    return {
        "ok": True,
        "workflow_applied": "finance_permission_to_pay_open",
        "capture_id": capture.pk,
        "request_id": req.request_id,
    }


def _apply_permission_to_pay_approve(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.finance.forms_permission_to_pay import RecordGuardianApprovalForm
    from apps.finance.permission_to_pay import (
        PermissionToPayError,
        open_request,
        record_guardian_approval,
    )

    form = RecordGuardianApprovalForm(data=fields)
    if not form.is_valid():
        return {"ok": False, "error": "validation", "details": dict(form.errors)}

    request_id = (fields.get("request_id") or "").strip()
    if not request_id:
        return {"ok": False, "error": "missing_request_id"}

    prior = FinanceOfflineCaptureRecord.objects.filter(
        school_id=school_id,
        workflow="finance_permission_to_pay_open",
        result_summary__request_id=request_id,
    ).first()
    if not prior:
        return {"ok": False, "error": "open_request_not_found", "request_id": request_id}
    snap = prior.fields_snapshot or {}
    try:
        base = open_request(
            tenant_id=str(school_id),
            student_id=str(snap.get("student_id", "")),
            event_code=str(snap.get("event_code", "")),
            amount=Decimal(str(snap.get("amount", "0"))),
            currency=str(snap.get("currency", "USD")),
            guardian_threshold=Decimal(str(snap.get("guardian_threshold", "0"))),
        )
        base.request_id = request_id
    except (PermissionToPayError, InvalidOperation) as exc:
        return {"ok": False, "error": str(exc)}

    cleaned = form.cleaned_data
    try:
        updated = record_guardian_approval(
            base,
            guardian_id=cleaned["guardian_id"],
            approved_at_iso=cleaned["approved_at_iso"],
            method=cleaned["method"],
        )
    except PermissionToPayError as exc:
        return {"ok": False, "error": str(exc)}

    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="finance_permission_to_pay_approve",
        client_offline_id=_client_key(payload),
        status=FinanceOfflineCaptureRecord.Status.APPLIED,
        fields=fields,
        result_summary={"request_id": updated.request_id, "state": updated.state},
    )
    return {
        "ok": True,
        "workflow_applied": "finance_permission_to_pay_approve",
        "capture_id": capture.pk,
        "request_id": updated.request_id,
    }


def _apply_invoice_detail_note(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="finance_invoice_detail",
        client_offline_id=_client_key(payload),
        status=FinanceOfflineCaptureRecord.Status.APPLIED,
        fields=fields,
        result_summary={"invoice_id": fields.get("invoice_id")},
    )
    return {
        "ok": True,
        "workflow_applied": "finance_invoice_detail",
        "capture_id": capture.pk,
    }


def _apply_scan_teller_pending(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="finance_scan_teller",
        client_offline_id=_client_key(payload),
        status=FinanceOfflineCaptureRecord.Status.PENDING_REVIEW,
        fields=fields,
        result_summary={"queued": True, "reason": "ocr_requires_online_runtime"},
    )
    return {
        "ok": True,
        "workflow_applied": "finance_scan_teller",
        "capture_id": capture.pk,
        "pending_review": True,
    }


def _apply_split_allocation(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.academics.models import AcademicYear
    from apps.finance.forms import SplitAllocationForm
    from apps.finance.models import Invoice, InvoiceLine, Payment
    from apps.finance.services import apply_payment, assign_invoice_payer_shares, split_amount_equally
    from apps.people.models import StudentGuardian, StudentProfile

    profile = _profile_for_school(school_id)
    if not profile:
        return {"ok": False, "error": "no_compliance_profile"}

    # Idempotency P0: short-circuit BEFORE any money side effect. Previously the
    # invoice + payment were created first and the capture recorded afterward, so
    # a WAL/queue retry or two-device replay created a SECOND invoice + payment.
    client_key = _client_key(payload)
    existing = _existing_capture(school_id, client_key)
    if existing:
        return {
            "ok": True,
            "dedup": True,
            "workflow_applied": "finance_split_allocation",
            "capture_id": existing.pk,
            **(existing.result_summary or {}),
        }

    # tenant-isolation-allow: split-allocation-active-year-scoped-to-school-tenant
    active_year = AcademicYear.objects.filter(
        school_id=school_id,
        is_active=True,
    ).order_by("-start_date").first()
    if not active_year:
        return {"ok": False, "error": "no_active_academic_year"}

    students = StudentProfile.objects.filter(
        academic_year=active_year, school_id=school_id
    )
    student_id = fields.get("student")
    guardians = StudentGuardian.objects.none()
    if student_id and str(student_id).isdigit():
        guardians = StudentGuardian.objects.filter(
            student_id=int(student_id),
            student__academic_year=active_year,
            can_view_finance=True,
            guardian_user__is_active=True,
        )

    form = SplitAllocationForm(
        data=fields,
        student_queryset=students,
        guardian_queryset=guardians,
    )
    if not form.is_valid():
        return {"ok": False, "error": "validation", "details": dict(form.errors)}

    student = form.cleaned_data["student"]
    total_amount = form.cleaned_data["total_amount"]
    method = form.cleaned_data["method"]
    split_mode = (form.cleaned_data.get("split_mode") or "none").strip().lower()
    allocations = form.get_allocations()
    today = timezone.now().date()
    short_id = uuid.uuid4().hex[:8].upper()
    reference = f"SPLIT-OFF-{student.id}-{today.isoformat()}-{short_id}"
    payer_allocations = []
    if split_mode == "custom":
        payer_allocations = form.get_payer_allocations()
    elif split_mode == "equal":
        student_guardians = list(
            StudentGuardian.objects.filter(
                student=student,
                can_view_finance=True,
                guardian_user__is_active=True,
            ).select_related("guardian_user")
        )
        equal_parts = split_amount_equally(total_amount, len(student_guardians))
        payer_allocations = list(zip(student_guardians, equal_parts))

    from django.db import IntegrityError

    try:
        with transaction.atomic():
            # Create the capture FIRST inside the same transaction. The partial
            # unique constraint on (school, client_offline_id) makes a concurrent
            # replay raise IntegrityError here and roll the whole block back, so
            # the invoice + payment below can never be created twice for one key.
            capture = FinanceOfflineCaptureRecord.objects.create(
                school_id=school_id,
                workflow="finance_split_allocation",
                client_offline_id=client_key,
                status=FinanceOfflineCaptureRecord.Status.APPLIED,
                source=FinanceOfflineCaptureRecord.Source.OFFLINE,
                fields_snapshot=fields,
                result_summary={},
                profile_id=profile.pk,
                created_by_id=user_id,
            )
            invoice = Invoice.objects.create(
                profile=profile,
                academic_year=active_year,
                student=student,
                school_id=school_id,
                reference=reference,
                invoice_type=Invoice.InvoiceType.AR,
                issued_date=today,
                due_date=today,
                status=Invoice.Status.ISSUED,
                total_amount=total_amount,
                created_by_id=user_id,
            )
            for desc, amount in allocations:
                InvoiceLine.objects.create(
                    invoice=invoice,
                    description=desc,
                    quantity=Decimal("1.00"),
                    unit_price=amount,
                    amount=amount,
                )
            if payer_allocations:
                assign_invoice_payer_shares(invoice, payer_allocations, due_date=today)
            payment = Payment.objects.create(
                invoice=invoice,
                student=student,
                amount=total_amount,
                method=method,
                paid_at=timezone.now(),
                created_by_id=user_id,
            )
            apply_payment(payment)
            capture.result_summary = {"invoice_id": invoice.pk, "payment_id": str(payment.pk)}
            capture.save(update_fields=["result_summary"])
    except IntegrityError:
        # A concurrent replay won the unique-constraint race and already did the
        # work — return its result instead of double-charging.
        existing = _existing_capture(school_id, client_key)
        if existing:
            return {
                "ok": True,
                "dedup": True,
                "workflow_applied": "finance_split_allocation",
                "capture_id": existing.pk,
                **(existing.result_summary or {}),
            }
        raise
    return {
        "ok": True,
        "workflow_applied": "finance_split_allocation",
        "capture_id": capture.pk,
        "invoice_id": invoice.pk,
    }
