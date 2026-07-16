"""
Regional payment orchestration and dead-simple UX descriptors for guardians/cashiers.

Designed for low-literacy contexts: two choices (PRIMARY / BACKUP), obvious order.
"""

from __future__ import annotations

from typing import Any

from apps.finance.models import TenantPaymentPolicy


def build_simple_payment_flow(
    policy: TenantPaymentPolicy | None,
) -> dict[str, Any]:
    """
    Return steps and rail choices for UI — minimal branching ("usable by a 5-year-old").
    """
    steps = [
        {
            "step": 1,
            "title": "Pick how you pay",
            "subtitle": "Tap the big button your school uses first.",
        },
        {
            "step": 2,
            "title": "Pay",
            "subtitle": "Follow the short instructions on screen.",
        },
        {
            "step": 3,
            "title": "If internet dies",
            "subtitle": "Take one photo of your receipt. We finish when power returns.",
        },
    ]
    choices: list[dict[str, Any]] = []
    if policy and policy.region_profile:
        pr = policy.region_profile
        choices.append(
            {
                "role": "PRIMARY",
                "code": pr.primary_rail.code,
                "label": pr.primary_rail.label,
                "kind": pr.primary_rail.kind,
            }
        )
        choices.append(
            {
                "role": "BACKUP",
                "code": pr.backup_rail.code,
                "label": pr.backup_rail.label,
                "kind": pr.backup_rail.kind,
            }
        )
    return {
        "steps": steps,
        "choices": choices,
        "simplicity_big_buttons": getattr(policy, "simplicity_big_buttons", True)
        if policy
        else True,
        "allow_manual_offline_proof": getattr(policy, "allow_manual_offline_proof", True)
        if policy
        else True,
    }


def reconcile_offline_payment_intent(
    intent,
    *,
    reconciled_by,
):
    """
    Turn a queued offline intent into a completed Payment and refresh invoice balance/status.

    Caller must enforce RBAC (finance staff). Raises ValueError if already reconciled.
    """
    from django.db import transaction
    from django.utils import timezone

    from apps.finance.models import Invoice, OfflinePaymentIntent, Payment

    if intent.status != OfflinePaymentIntent.Status.QUEUED_REVIEW:
        raise ValueError("Only queued intents can be reconciled.")
    if intent.reconciled_payment_id:
        raise ValueError("Intent already linked to a payment.")

    inv: Invoice = intent.invoice
    currency = getattr(inv.profile, "currency_code", None) or "USD"

    with transaction.atomic():
        payment = Payment(
            invoice=inv,
            school=inv.school,
            student=inv.student,
            amount=intent.amount,
            method=intent.payment_method,
            reference=(intent.transaction_reference or "")[:80]
            or f"offline-intent-{intent.pk}",
            external_reference=(intent.transaction_reference or "")[:128],
            status="completed",
            created_by=reconciled_by,
            paid_at=timezone.now(),
            currency_code=currency,
            description=f"Offline queued payment (intent {intent.pk})",
        )
        payment.full_clean()
        payment.save()

        intent.reconciled_payment = payment
        intent.status = OfflinePaymentIntent.Status.RECONCILED
        intent.save(update_fields=["reconciled_payment", "status", "updated_at"])

        inv.reconcile_balance()
        current_balance = inv.computed_balance
        if current_balance <= 0:
            inv.status = Invoice.Status.PAID
        elif current_balance < inv.total_amount:
            inv.status = Invoice.Status.PARTIAL
        else:
            inv.status = Invoice.Status.ISSUED
        inv.balance_amount = current_balance
        inv.save(update_fields=["status", "balance_amount", "updated_at"])

        # Feed the fractional sub-ledger. A bursar-approved offline intent IS an
        # irregular partial payment over the counter — exactly what
        # FractionalPaymentLedger models. This is its only production producer:
        # without it the sub-ledger stays permanently EMPTY, so
        # enrollment_clearance_for_invoice() can never return True and
        # reports.student_has_financial_clearance() blocks a partial payer's
        # report card forever (the micro-finance "pay enough instalments -> see
        # results" loop was wired on the consumer side with nothing producing).
        # Kept inside this atomic block on purpose: the cash receipt and its
        # clearance line are one financial event and must commit together — a
        # swallowed ledger write would be a silent money-integrity bug.
        # Idempotent on the intent pk, so a retry/redelivery cannot double-post.
        # Invoice.school is nullable (platform/AP invoices carry no tenant) but
        # FractionalPaymentLedger.school is NOT NULL, and both clearance readers
        # are school-scoped — so a school-less row is unwritable AND could never
        # be read back. Tenant enrollment-clearance simply does not apply there.
        if inv.school_id is not None:
            from apps.finance.fractional_ledger_services import post_partial_payment
            from apps.finance.models_fractional_ledger import FractionalPaymentLedger

            post_partial_payment(
                school=inv.school,
                invoice=inv,
                amount=intent.amount,
                source=FractionalPaymentLedger.Source.CASH_COUNTER,
                idempotency_key=f"offline-intent-{intent.pk}",
                student=inv.student,
                note=f"Bursar-approved offline intent {intent.pk}",
            )

    return payment
