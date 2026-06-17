"""Regression seal: create_payment_from_receipt must be idempotent (double-credit guard).

Bug (2026-06-17 gap analysis): the function unconditionally created a Payment and applied
it, with no check of proof_upload.payment. Re-running on the same receipt (retry, or a
no-reference receipt re-processed) double-credited the invoice. Fix: if the proof already
links a payment, return it without creating a second.
"""
from unittest import mock

from django.test import TestCase

from apps.finance.services import create_payment_from_receipt


class ReceiptIdempotencySealTests(TestCase):
    # The function is @transaction.atomic, so entering it needs a DB connection even
    # though the idempotency guard returns before issuing any query.
    @mock.patch("apps.finance.services.apply_payment")
    @mock.patch("apps.finance.services.Payment")
    def test_already_settled_proof_returns_existing_payment(self, payment_model, apply):
        existing_payment = mock.Mock(name="existing_payment")
        proof = mock.Mock(payment_id=42, payment=existing_payment)

        result = create_payment_from_receipt(proof, {"amount": "100"})

        self.assertIs(result, existing_payment)
        self.assertFalse(
            payment_model.objects.create.called, "must not create a second Payment"
        )
        self.assertFalse(apply.called, "must not re-apply payment to the invoice")
