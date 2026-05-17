"""Finance lander — persists canonical invoice rows into ``apps.finance.Invoice``.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "reference": "INV-2025-0001",
        "amount": "1250.00",
        "currency": "USD",
        "due_date": "2025-09-30",
        "issue_date": "2025-09-01",
        "description": "Tuition Q1 2025-26"
    }
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    coerce_decimal,
    detect_and_register_assets,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class FinanceLander(Lander):
    domain = "finance"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.finance.models import Invoice
            from apps.people.models import StudentProfile
        except ImportError as exc:
            raise LanderError(
                f"FinanceLander could not import Invoice / StudentProfile: {exc!s}"
            ) from exc

        result = LanderResult()
        invoice_fields = model_field_names(Invoice)
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)
        ref_field = "reference" if "reference" in invoice_fields else (
            "payment_code" if "payment_code" in invoice_fields else None
        )

        for row in canonical_rows:
            external_id = (row.get("student_external_id") or "").strip()
            reference = (row.get("reference") or row.get("invoice_reference") or "").strip()
            amount = coerce_decimal(row.get("amount"))
            if not external_id or not reference or amount is None:
                result.quarantined += 1
                result.errors.append(
                    f"finance: missing student/reference/amount in {row!r}"
                )
                continue
            student = StudentProfile.objects.filter(  # tenant-isolation-allow: lander runs inside schema_context(bundle.schema_name)
                **{student_lookup: external_id}
            ).first()
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"finance: no student with {student_lookup}={external_id!r}"
                )
                continue

            defaults: dict[str, Any] = {
                "amount": amount,
                "currency": (row.get("currency") or "USD").strip()[:3].upper(),
                "due_date": coerce_date(row.get("due_date")),
                "issue_date": coerce_date(row.get("issue_date")),
                "description": (row.get("description") or "")[:255],
                "student": student,
            }
            defaults = filter_to_model_fields(defaults, Invoice)
            # Restore the student FK (filter_to_model_fields drops empty/None).
            defaults["student"] = student

            if ctx.dry_run:
                if ref_field:
                    exists = Invoice.objects.filter(**{ref_field: reference}).exists()  # tenant-isolation-allow: lander runs inside schema_context(bundle.schema_name)
                    if exists:
                        result.updated += 1
                    else:
                        result.created += 1
                else:
                    result.created += 1
                continue
            try:
                if ref_field:
                    obj, created = Invoice.objects.update_or_create(
                        **{ref_field: reference}, defaults=defaults,
                    )
                else:
                    obj = Invoice.objects.create(**defaults)
                    created = True
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                record_id_mapping(
                    ctx=ctx, legacy_id=reference,
                    canonical_obj=obj, domain="finance",
                )
                detect_and_register_assets(
                    ctx=ctx, legacy_id=reference, entity_kind="invoice", row=row,
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"finance upsert failed for {reference}: {type(exc).__name__}: {exc}"
                )
        return result


register("finance", FinanceLander())
