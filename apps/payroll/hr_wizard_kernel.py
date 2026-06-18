"""Human-capital wizard → tenant labor / tax / absence policy (school.settings)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hr_blob(school: Any | None) -> dict[str, Any]:
    if school is None:
        return {}
    return dict((getattr(school, "settings", None) or {}).get("hr") or {})


def _save_hr(school: Any | None, blob: dict[str, Any]) -> None:
    if school is None:
        return
    blob["updated_at"] = _utc_now()
    settings = dict(getattr(school, "settings", None) or {})
    settings["hr"] = blob
    school.settings = settings
    school.save(update_fields=["settings"])


def _dec(val: Any) -> Decimal | None:
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def apply_labor_contract_profile(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    profile = {
        k: payload.get(k)
        for k in (
            "max_weekly_hours",
            "overtime_threshold_hours",
            "overtime_multiplier",
            "standard_paid_leave_days",
            "sick_leave_days",
        )
        if payload.get(k) is not None
    }
    blob = _hr_blob(school)
    blob["labor_contract"] = profile
    _save_hr(school, blob)
    return {"ok": True, "labor_contract": profile}


def apply_regional_tax_blueprint(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    enabled = payload.get("value")
    if enabled is None:
        enabled = payload.get("enabled", True)
    blob = _hr_blob(school)
    blob["tax_blueprint_enabled"] = bool(enabled)
    _save_hr(school, blob)
    return {"ok": True, "tax_blueprint_enabled": blob["tax_blueprint_enabled"]}


def apply_absence_logic(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    absence = {
        k: payload.get(k)
        for k in (
            "emergency_absence_cutoff_time",
            "auto_broadcast_to_subs",
            "require_principal_approval",
        )
        if k in payload
    }
    blob = _hr_blob(school)
    blob["absence"] = absence
    _save_hr(school, blob)
    return {"ok": True, "absence": absence}


def apply_staff_schedule_preferences(
    *,
    school: Any | None,
    actor_user_id: int | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Per-staff hours from staff_onboarding wizard (PayrollEmployee + contract stub)."""
    from django.utils import timezone as dj_tz

    if school is None or not actor_user_id:
        return {"ok": False, "error": "missing_inputs"}

    hours = _dec(payload.get("standard_hours_per_week"))
    break_mins = payload.get("preferred_break_minutes")

    from apps.accounts.models import User
    from apps.payroll.models import EmploymentContract, PayrollEmployee

    try:
        user = User.objects.get(pk=actor_user_id)
    except User.DoesNotExist:
        return {"ok": False, "error": "user_not_found"}

    employee, _ = PayrollEmployee.objects.get_or_create(user=user)
    if payload.get("employee_id") and not employee.employee_code:
        employee.employee_code = str(payload["employee_id"])[:50]
        employee.save(update_fields=["employee_code"])

    contract = (
        employee.contracts.filter(is_active=True).order_by("-start_date").first()
    )
    today = dj_tz.now().date()
    if contract is None:
        contract = EmploymentContract.objects.create(
            employee=employee,
            start_date=today,
            pay_type=employee.pay_type,
            hours_per_week=hours or Decimal("40"),
            is_active=True,
        )
    elif hours is not None:
        contract.hours_per_week = hours
        contract.save(update_fields=["hours_per_week"])

    blob = _hr_blob(school)
    staff_bucket = dict(blob.get("staff_onboarding") or {})
    staff_bucket[str(actor_user_id)] = {
        "standard_hours_per_week": str(hours) if hours is not None else None,
        "preferred_break_minutes": break_mins,
        "updated_at": _utc_now(),
    }
    blob["staff_onboarding"] = staff_bucket
    _save_hr(school, blob)
    return {"ok": True, "employee_id": employee.pk, "contract_id": contract.pk}
