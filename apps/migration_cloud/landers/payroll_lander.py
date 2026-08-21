"""Payroll lander — preserves canonical payroll rows as custom records.

Canonical row shape::

    {
        "staff_external_id":  "T-1029",
        "pay_period":         "2025-09",       # YYYY-MM
        "gross_amount":       3850.00,
        "net_amount":         3215.00,
        "currency":           "USD",
        "issued_date":        "2025-09-30",
        "reference":          "PS-2025-09-T1029",  # optional natural key
    }

Design note: the platform's first-class ``apps.payroll.Payslip`` requires a
``payroll_run``→PayrollRun FK and an ``employee``→PayrollEmployee FK (a distinct
model from ``people.TeacherProfile``). A data migration can't manufacture payroll
RUNS or PayrollEmployee records without inventing HR/ledger infrastructure, so
rather than force-fit (which ValueError/IntegrityError-quarantined every row) we
PRESERVE each payslip row losslessly as a ``DynamicFieldValue`` custom record
keyed to a stable (staff, pay_period) identity. Money stays as the source string
(never coerced to float) so no ledger value is corrupted. Re-runs update the same
record; distinct pay periods stay distinct.
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    persist_dfv_extras,
    record_row_error,
)
from .base import Lander, LanderContext, LanderResult, register
from .reason_codes import LANDER_ERROR, MISSING_REQUIRED


class PayrollLander(Lander):
    domain = "payroll"
    # Persists the ENTIRE row (every non-empty key) to DynamicFieldValue, so it
    # already captures all custom_fields.*/_unmapped.* residuals itself.
    sweeps_custom_columns = True

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        result = LanderResult()
        for row in canonical_rows:
            external_id = (row.get("staff_external_id") or row.get("external_id") or "").strip()
            # Schools that kept payroll by name rather than by employee number
            # had every row rejected. The name is a perfectly good identity for
            # a record keyed on (person, pay period) -- it just was not accepted.
            staff_name = " ".join(
                str(
                    row.get("staff_name")
                    or row.get("employee_name")
                    or row.get("full_name")
                    or row.get("name")
                    or ""
                ).split()
            )
            if not external_id and not staff_name:
                record_row_error(
                    result,
                    row,
                    "payroll: this row does not say which staff member it "
                    "belongs to. Add an employee id column or a staff name column.",
                    reason_code=MISSING_REQUIRED,
                )
                continue
            identity = external_id or staff_name
            reference = (row.get("reference") or "").strip()
            pay_period = (row.get("pay_period") or "").strip()
            # Stable per-record identity → re-runs update the same custom record.
            record_key = (reference or f"{identity}:{pay_period or 'na'}")[:64]
            record = {k: str(v) for k, v in row.items() if v not in (None, "")}

            if ctx.dry_run:
                result.created += 1
                continue
            try:
                persist_dfv_extras(
                    ctx=ctx,
                    entity_type="payroll",
                    entity_id=record_key,
                    extras={"record": record},
                    result=result,
                )
                result.created += 1
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"payroll preserve failed for {external_id} {pay_period}: "
                    f"{type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result


register("payroll", PayrollLander())
