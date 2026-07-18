"""Record a payment received against a platform invoice via a local rail / reconciliation.

Producer for ``apps.billing.services.record_platform_invoice_payment`` (Phase 2: localized,
Stripe-free platform collection). This is how the platform books a subscription payment
from a school in a market Stripe never reaches — an operator (or a local-PSP webhook /
reconciliation script) records the mobile-money / bank-transfer receipt here.

Safe by default: prints a preview and requires ``--apply`` to post the credit and settle.

Usage:
  python manage.py record_platform_payment --invoice INV-2026-000123 --amount 32.00 \\
      --method mtn_momo --reference MP240718.1234.ABCD --apply
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from apps.billing.models import PlatformInvoice
from apps.billing.services import (
    platform_account_balance,
    record_platform_invoice_payment,
)


class Command(BaseCommand):
    help = (
        "Record a payment received against a platform invoice "
        "(local rail / manual reconciliation)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--invoice", required=True, help="PlatformInvoice number, e.g. INV-2026-000123"
        )
        parser.add_argument(
            "--amount",
            required=True,
            help="Amount received (decimal). Use the invoice total to settle in full.",
        )
        parser.add_argument(
            "--method",
            required=True,
            help="Rail: mtn_momo, orange_money, bank_transfer, manual, ...",
        )
        parser.add_argument(
            "--reference",
            default="",
            help="External transaction reference (used for idempotency).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually post the credit + settle. Without it, preview only.",
        )

    def handle(self, *args, **opts):
        try:
            invoice = PlatformInvoice.objects.select_related(
                "billing_account", "school"
            ).get(number=opts["invoice"])
        except PlatformInvoice.DoesNotExist as exc:
            raise CommandError(
                f"No platform invoice with number {opts['invoice']!r}"
            ) from exc

        try:
            amount = Decimal(str(opts["amount"]))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise CommandError(f"Invalid --amount {opts['amount']!r}") from exc
        if amount <= 0:
            raise CommandError("--amount must be positive")

        balance_before = platform_account_balance(invoice.billing_account)
        self.stdout.write(
            f"Invoice {invoice.number}: total={invoice.total} {invoice.currency_code} "
            f"status={invoice.status} account_balance={balance_before}"
        )
        self.stdout.write(
            f"Would record: {amount} via {opts['method']} "
            f"(ref={opts['reference'] or '<auto>'})"
        )

        if not opts["apply"]:
            self.stdout.write(
                self.style.WARNING("PREVIEW only. Re-run with --apply to record.")
            )
            return

        record_platform_invoice_payment(
            invoice,
            amount=amount,
            method=opts["method"],
            external_reference=opts["reference"],
        )
        invoice.refresh_from_db()
        balance_after = platform_account_balance(invoice.billing_account)
        self.stdout.write(
            self.style.SUCCESS(
                f"Recorded. Invoice status={invoice.status}, "
                f"account_balance={balance_after}"
            )
        )
