"""Fractional / partial payment sub-ledger for irregular cash and mobile-money posts."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone


class FractionalPaymentLedger(models.Model):
    """Append-only partial payment lines against an invoice (Decimal precision)."""

    class Source(models.TextChoices):
        CASH_COUNTER = "cash_counter", "Cash over counter"
        GATEWAY = "gateway", "Payment gateway"
        WALLET = "wallet", "Parent wallet"
        ADJUSTMENT = "adjustment", "Manual adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="fractional_payment_ledger_rows",
    )
    invoice = models.ForeignKey(
        "finance.Invoice",
        on_delete=models.CASCADE,
        related_name="fractional_ledger_rows",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fractional_ledger_rows",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    tax_component = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=(
            "Portion of `amount` attributable to tax, snapshotted at post time by "
            "proportional allocation (amount x invoice-tax-fraction). Enables "
            "cash-basis VAT-collected remittance reporting from irregular partial "
            "posts. Purely informational: never affects amount / running / balance."
        ),
    )
    currency_code = models.CharField(max_length=3, default="USD")
    running_paid_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Cumulative paid on invoice after this row posts.",
    )
    invoice_balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Remaining invoice balance after this row.",
    )
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.CASH_COUNTER)
    idempotency_key = models.CharField(max_length=128, blank=True, default="", db_index=True)
    enrollment_clearance_met = models.BooleanField(
        default=False,
        help_text="True when cumulative paid meets tenant enrollment clearance threshold.",
    )
    note = models.CharField(max_length=255, blank=True, default="")
    posted_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["posted_at", "created_at"]
        indexes = [
            models.Index(fields=["school", "invoice", "-posted_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_fractional_ledger_school_idempotency",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.invoice_id} +{self.amount} ({self.source})"
