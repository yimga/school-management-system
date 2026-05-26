"""Server-side apply for payroll / HR field_capture workflows (batch 1511)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.payroll.models_offline_capture import PayrollOfflineCaptureRecord

logger = logging.getLogger(__name__)
User = get_user_model()

PAYROLL_WORKFLOWS: frozenset[str] = frozenset(
    {
        "payroll_create_run",
        "payroll_leave_request",
    }
)


def _client_key(payload: dict[str, Any]) -> str:
    return str(
        payload.get("client_offline_id")
        or payload.get("idempotency_key")
        or "",
    )[:128]


def _record_capture(
    *,
    school_id: int,
    user_id: int,
    workflow: str,
    client_offline_id: str,
    status: str,
    fields: dict[str, Any],
    result_summary: dict[str, Any],
    payroll_run_id: int | None = None,
) -> PayrollOfflineCaptureRecord:
    key = (client_offline_id or "").strip()[:128]
    if key:
        existing = PayrollOfflineCaptureRecord.objects.filter(
            school_id=school_id,
            client_offline_id=key,
        ).first()
        if existing:
            return existing
    return PayrollOfflineCaptureRecord.objects.create(
        school_id=school_id,
        workflow=workflow,
        client_offline_id=key,
        status=status,
        source=PayrollOfflineCaptureRecord.Source.OFFLINE,
        fields_snapshot=fields,
        result_summary=result_summary,
        payroll_run_id=payroll_run_id,
        created_by_id=user_id,
    )


def apply_payroll_workflow(
    school_id: int,
    user_id: int,
    workflow: str,
    fields: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if workflow not in PAYROLL_WORKFLOWS:
        return None
    if workflow == "payroll_create_run":
        return _apply_create_run(school_id, user_id, fields, payload)
    if workflow == "payroll_leave_request":
        return _apply_leave_request(school_id, user_id, fields, payload)
    return None


def _active_profile():
    from apps.payroll.services import get_active_payroll_profile

    return get_active_payroll_profile()


def _apply_create_run(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.payroll.models import PayrollRun

    profile = _active_profile()
    if not profile:
        return {"ok": False, "error": "no_compliance_profile"}

    start_raw = fields.get("period_start") or fields.get("start")
    end_raw = fields.get("period_end") or fields.get("end")
    if not start_raw or not end_raw:
        return {"ok": False, "error": "missing_period_dates"}

    try:
        start_date = date.fromisoformat(str(start_raw)[:10])
        end_date = date.fromisoformat(str(end_raw)[:10])
    except ValueError:
        return {"ok": False, "error": "invalid_date_format"}

    if end_date < start_date:
        return {"ok": False, "error": "period_end_before_start"}

    duplicate = PayrollRun.objects.filter(
        profile=profile,
        period_start=start_date,
        period_end=end_date,
    ).first()
    if duplicate:
        capture = _record_capture(
            school_id=school_id,
            user_id=user_id,
            workflow="payroll_create_run",
            client_offline_id=_client_key(payload),
            status=PayrollOfflineCaptureRecord.Status.APPLIED,
            fields=fields,
            result_summary={"run_id": duplicate.pk, "idempotent": True},
            payroll_run_id=duplicate.pk,
        )
        return {
            "ok": True,
            "workflow_applied": "payroll_create_run",
            "capture_id": capture.pk,
            "run_id": duplicate.pk,
            "idempotent": True,
        }

    with transaction.atomic():
        run = PayrollRun.objects.create(
            profile=profile,
            period_start=start_date,
            period_end=end_date,
            created_by_id=user_id,
            status=PayrollRun.Status.DRAFT,
        )

    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="payroll_create_run",
        client_offline_id=_client_key(payload),
        status=PayrollOfflineCaptureRecord.Status.APPLIED,
        fields=fields,
        result_summary={"run_id": run.pk},
        payroll_run_id=run.pk,
    )
    return {
        "ok": True,
        "workflow_applied": "payroll_create_run",
        "capture_id": capture.pk,
        "run_id": run.pk,
    }


def _apply_leave_request(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.payroll.forms import LeaveRequestForm
    from apps.payroll.models import LeaveRequest, PayrollEmployee

    user = User.objects.filter(pk=user_id).first()
    if not user:
        return {"ok": False, "error": "user_not_found"}

    try:
        employee = user.payroll_profile
    except PayrollEmployee.DoesNotExist:
        return {"ok": False, "error": "no_payroll_profile"}

    form = LeaveRequestForm(data=fields)
    if not form.is_valid():
        return {"ok": False, "error": "validation", "details": dict(form.errors)}

    with transaction.atomic():
        leave = form.save(commit=False)
        leave.employee = employee
        leave.status = LeaveRequest.Status.PENDING
        leave.is_paid = leave.leave_type != LeaveRequest.LeaveType.UNPAID
        leave.save()

    capture = _record_capture(
        school_id=school_id,
        user_id=user_id,
        workflow="payroll_leave_request",
        client_offline_id=_client_key(payload),
        status=PayrollOfflineCaptureRecord.Status.APPLIED,
        fields=fields,
        result_summary={"leave_id": leave.pk},
    )
    return {
        "ok": True,
        "workflow_applied": "payroll_leave_request",
        "capture_id": capture.pk,
        "leave_id": leave.pk,
    }
