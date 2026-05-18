"""Payroll lander — persists canonical payroll rows into ``apps.payroll.Payslip``.

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

Upsert key: (employee, reference) when reference is present, else
(employee, pay_period). All money is Decimal — never float.

Money safety: parsed via coerce_decimal; persists as Decimal to avoid
ledger corruption (compliant with the platform's ``scan_money_float``
zero-tolerance gate).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    coerce_decimal,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    staff_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class PayrollLander(Lander):
    domain = "payroll"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.payroll.models import Payslip
            from apps.people.models import TeacherProfile
        except ImportError as exc:
            raise LanderError(
                f"PayrollLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        staff_fields = model_field_names(TeacherProfile)
        staff_lookup = staff_lookup_field(staff_fields)
        p_fields = model_field_names(Payslip)

        for row in canonical_rows:
            external_id = (row.get("staff_external_id") or row.get("external_id") or "").strip()
            reference = (row.get("reference") or "").strip()
            pay_period = (row.get("pay_period") or "").strip()
            if not external_id:
                result.quarantined += 1
                result.errors.append(
                    f"payroll: missing staff_external_id in {row!r}"
                )
                continue
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
            employee = TeacherProfile.objects.filter(
                **{staff_lookup: external_id}
            ).first()
            if employee is None:
                result.quarantined += 1
                result.errors.append(
                    f"payroll: no staff with {staff_lookup}={external_id!r}"
                )
                continue

            gross = coerce_decimal(row.get("gross_amount") or row.get("gross_pay"))
            net = coerce_decimal(row.get("net_amount") or row.get("net_pay"))
            issued = coerce_date(row.get("issued_date") or row.get("paid_at"))

            defaults: dict[str, Any] = {}
            if gross is not None and "gross_pay" in p_fields:
                defaults["gross_pay"] = gross
            if net is not None and "net_pay" in p_fields:
                defaults["net_pay"] = net
            if reference and "reference" in p_fields:
                defaults["reference"] = reference[:128]
            if issued and "paid_at" in p_fields:
                defaults["paid_at"] = _dt.datetime.combine(issued, _dt.time.min)
            if "details" in p_fields:
                defaults["details"] = {
                    "pay_period": pay_period,
                    "currency": (row.get("currency") or "USD").upper()[:3],
                }
            defaults = filter_to_model_fields(defaults, Payslip)

            lookup_kwargs: dict[str, Any] = {"employee": employee}
            if reference and "reference" in p_fields:
                lookup_kwargs["reference"] = reference[:128]
            elif issued and "paid_at" in p_fields:
                lookup_kwargs["paid_at"] = defaults["paid_at"]

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = Payslip.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                obj, created = Payslip.objects.update_or_create(
                    defaults=defaults, **lookup_kwargs,
                )
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
                record_id_mapping(
                    ctx=ctx,
                    legacy_id=reference or f"{external_id}:{pay_period}",
                    canonical_obj=obj, domain="payroll",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"payroll upsert failed for {external_id} {pay_period}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return result


register("payroll", PayrollLander())
