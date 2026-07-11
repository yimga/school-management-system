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

from ._helpers import persist_dfv_extras
from .base import Lander, LanderContext, LanderResult, register


class PayrollLander(Lander):
    domain = "payroll"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        result = LanderResult()
        for row in canonical_rows:
            external_id = (row.get("staff_external_id") or row.get("external_id") or "").strip()
            if not external_id:
                result.quarantined += 1
                result.errors.append(
                    f"payroll: missing staff_external_id in {row!r}"
                )
                continue
            reference = (row.get("reference") or "").strip()
            pay_period = (row.get("pay_period") or "").strip()
            # Stable per-record identity → re-runs update the same custom record.
            record_key = (reference or f"{external_id}:{pay_period or 'na'}")[:64]
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
                result.quarantined += 1
                result.errors.append(
                    f"payroll preserve failed for {external_id} {pay_period}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return result


register("payroll", PayrollLander())
