"""Finance lander — persists canonical invoice rows into ``apps.finance.Invoice``.

Completeness fix (2026-07-11): the old lander wrote the money into ``amount``
(the field is ``total_amount``), never set the REQUIRED PROTECT ``profile``
(ComplianceProfile) FK, assigned the raw ``currency`` STRING to a
``CurrencyRegistry`` FK, and mapped ``issue_date``/``description`` to fields that
don't exist (``issued_date``/``notes``). Every invoice therefore failed
``Invoice.full_clean()`` (``total_amount`` stayed ``0.00`` and tripped
``MinValueValidator(0.01)``) or raised on the missing ``profile`` — so every
finance row quarantined and the invoiced amount silently vanished. The student
lookup was also unscoped (cross-school attach on single-schema).

Canonical row shape (source field names)::

    {
        "student_external_id": "PS-1029",
        "reference": "INV-2025-0001",
        "amount": "1250.00",           # → Invoice.total_amount
        "currency": "USD",             # display-only; resolved by the app, not stored as a string
        "due_date": "2025-09-30",
        "issue_date": "2025-09-01",    # → Invoice.issued_date
        "description": "Tuition Q1"    # → Invoice.notes
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
    resolve_student,
    student_lookup_field,
    upsert_with_conflict_detection,
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
            from apps.finance.provisioning_seed import ensure_tenant_compliance_profile
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
        # ``Invoice.profile`` is a REQUIRED PROTECT FK; resolve (or create) the
        # tenant schema's active ComplianceProfile once for the whole batch.
        profile = None
        if "profile" in invoice_fields:
            try:
                profile = ensure_tenant_compliance_profile(ctx.school)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"finance: could not resolve compliance profile: {type(exc).__name__}")

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
            if "profile" in invoice_fields and profile is None:
                result.quarantined += 1
                result.errors.append(
                    f"finance: no compliance profile available for invoice {reference}"
                )
                continue
            student = resolve_student(
                ctx=ctx,
                student_model=StudentProfile,
                lookup_field=student_lookup,
                external_id=external_id,
            )
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"finance: no student with {student_lookup}={external_id!r}"
                )
                continue

            defaults: dict[str, Any] = {
                "total_amount": amount,
                "due_date": coerce_date(row.get("due_date")),
                "issued_date": coerce_date(row.get("issue_date")),
                "notes": (row.get("description") or ""),
            }
            defaults = filter_to_model_fields(defaults, Invoice)
            # Re-attach FKs the empty/None filter drops or that must always be set.
            defaults["total_amount"] = amount
            if "student" in invoice_fields:
                defaults["student"] = student
            if "profile" in invoice_fields and profile is not None:
                defaults["profile"] = profile

            if ctx.dry_run:
                if ref_field:
                    exists = self._scoped(Invoice, ref_field, reference, ctx).exists()
                    if exists:
                        result.updated += 1
                    else:
                        result.created += 1
                else:
                    result.created += 1
                continue
            try:
                if ref_field:
                    # Scope the idempotency lookup to the school so two schools'
                    # invoices sharing a source reference never collide/overwrite.
                    lookup: dict[str, Any] = {ref_field: reference}
                    if "school" in invoice_fields and ctx.school is not None:
                        lookup["school"] = ctx.school
                    obj, created, preserved = upsert_with_conflict_detection(
                        ctx=ctx, domain="finance", model=Invoice,
                        lookup=lookup, defaults=defaults,
                        legacy_id=reference,
                    )
                    if preserved:
                        # Operator resolved this invoice conflict as PRESERVE —
                        # keep the tenant's existing amounts, don't overwrite.
                        result.skipped += 1
                        record_id_mapping(
                            ctx=ctx, legacy_id=reference,
                            canonical_obj=obj, domain="finance",
                        )
                        continue
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

    @staticmethod
    def _scoped(Invoice, ref_field, reference, ctx):
        qs = Invoice.objects.filter(**{ref_field: reference})  # tenant-isolation-allow: scoped-below-by-school-when-present / schema-context-isolates
        if "school" in model_field_names(Invoice) and ctx.school is not None:
            qs = qs.filter(school=ctx.school)
        return qs


register("finance", FinanceLander())
