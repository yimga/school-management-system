from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.finance.bank_statement_import import BankStatementImportService
from apps.finance.models import SuspensePayment


class Command(BaseCommand):
    help = (
        "Claim and allocate a suspense payment to one or more invoices.\n"
        'Example --allocations \'[{"invoice_id":12,"amount":"10000"},{"invoice_id":13,"amount":"5000"}]\''
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--suspense-id", type=int, required=True, help="SuspensePayment id."
        )
        parser.add_argument(
            "--allocations",
            type=str,
            required=True,
            help="JSON list of allocation objects with invoice_id and amount.",
        )
        parser.add_argument("--username", type=str, help="User performing the claim.")
        parser.add_argument(
            "--notes", type=str, default="", help="Optional audit note."
        )

    def handle(self, *args, **options):
        suspense = SuspensePayment.objects.filter(pk=options["suspense_id"]).first()
        if not suspense:
            raise CommandError(f"SuspensePayment {options['suspense_id']} not found.")

        try:
            allocations = json.loads(options["allocations"])
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid allocations JSON: {exc}") from exc
        if not isinstance(allocations, list):
            raise CommandError("--allocations must decode to a JSON list.")

        user = None
        username = options.get("username")
        if username:
            user = User.objects.filter(username=username).first()
            if not user:
                raise CommandError(f"User '{username}' not found.")

        service = BankStatementImportService()
        result = service.claim_suspense_payment(
            suspense_payment=suspense,
            allocations=allocations,
            claimed_by=user,
            notes=options.get("notes", ""),
        )
        self.stdout.write(
            self.style.SUCCESS(f"Suspense {suspense.pk} updated: {result['status']}")
        )
        self.stdout.write(f"Allocated total: {result['allocated_total']}")
        self.stdout.write(f"Remaining: {result['remaining']}")
        self.stdout.write(f"Payments: {', '.join(result['payment_ids'])}")
