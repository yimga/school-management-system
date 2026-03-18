from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import DatabaseError, IntegrityError
from django.utils import timezone

from apps.finance.models import (
    BankAccount,
    BankStatementEntry,
    BankStatementUpload,
    Invoice,
    Payment,
    PaymentMethodCode,
    PaymentProofUpload,
    SuspensePayment,
    SuspensePaymentAllocation,
)
from apps.finance.services import apply_payment
from apps.platform_runtime.helpers import get_platform_defaults


@dataclass
class ParsedStatementRow:
    transaction_date: datetime.date
    amount: Decimal
    transaction_reference: str
    description: str
    transaction_type: str
    balance_after: Decimal | None = None
    payer_phone: str = ""
    payer_name: str = ""
    raw_payload: dict | None = None


class BankStatementImportService:
    """
    Imports bank statements (CSV/MT940), creates statement entries, and opens
    suspense items for unmatched deposits.
    """

    DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")
    CSV_DATE_KEYS = ("date", "transaction_date", "value_date")
    CSV_AMOUNT_KEYS = ("amount", "credit", "value")
    CSV_REFERENCE_KEYS = ("reference", "transaction_reference", "ref", "transaction_id")
    CSV_DESCRIPTION_KEYS = ("description", "narration", "details", "memo")
    CSV_TYPE_KEYS = ("type", "transaction_type", "dr_cr")
    CSV_BALANCE_KEYS = ("balance", "running_balance", "balance_after")

    def process_upload(self, upload: BankStatementUpload) -> dict:
        upload.status = BankStatementUpload.Status.PROCESSING
        upload.errors = []
        upload.save(update_fields=["status", "errors"])

        created_count = 0
        suspense_count = 0
        errors: list[str] = []
        parsed_rows = self._parse_statement_file(upload)

        for idx, row in enumerate(parsed_rows, start=1):
            try:
                entry, created = self._upsert_entry(upload.bank_account, row)
                if created:
                    created_count += 1
                if self._link_or_create_suspense(entry, row):
                    suspense_count += 1
            except (
                ValueError,
                TypeError,
                DatabaseError,
                IntegrityError,
                ValidationError,
            ) as exc:
                errors.append(f"Row {idx}: {exc}")

        upload.entries_imported = created_count
        upload.errors = errors
        upload.status = (
            BankStatementUpload.Status.FAILED
            if errors and not created_count
            else BankStatementUpload.Status.COMPLETED
        )
        upload.processed_at = timezone.now()
        upload.save(
            update_fields=[
                "entries_imported",
                "errors",
                "status",
                "processed_at",
            ]
        )
        return {
            "entries_created": created_count,
            "suspense_created": suspense_count,
            "errors": errors,
            "status": upload.status,
        }

    def _parse_statement_file(
        self, upload: BankStatementUpload
    ) -> list[ParsedStatementRow]:
        upload.statement_file.open("rb")
        raw = upload.statement_file.read()
        upload.statement_file.close()

        file_name = (upload.statement_file.name or "").lower()
        if file_name.endswith(".mt940") or b":61:" in raw:
            return list(self._parse_mt940(raw.decode("utf-8", errors="ignore")))

        # default to CSV
        text = raw.decode("utf-8-sig", errors="ignore")
        return list(self._parse_csv(text))

    def _parse_csv(self, text: str) -> Iterable[ParsedStatementRow]:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            if not row:
                continue
            date_str = self._pick(row, self.CSV_DATE_KEYS)
            amount_str = self._pick(row, self.CSV_AMOUNT_KEYS)
            if not date_str or not amount_str:
                continue

            amount = self._to_decimal(amount_str)
            txn_type = self._infer_transaction_type(
                amount, self._pick(row, self.CSV_TYPE_KEYS)
            )
            description = self._pick(row, self.CSV_DESCRIPTION_KEYS)
            reference = self._pick(row, self.CSV_REFERENCE_KEYS)
            balance_str = self._pick(row, self.CSV_BALANCE_KEYS)

            yield ParsedStatementRow(
                transaction_date=self._to_date(date_str),
                amount=amount,
                transaction_reference=reference[:100],
                description=description,
                transaction_type=txn_type,
                balance_after=self._to_decimal(balance_str) if balance_str else None,
                payer_phone=self._extract_phone(f"{reference} {description}"),
                payer_name=self._extract_payer_name(description),
                raw_payload=row,
            )

    def _parse_mt940(self, text: str) -> Iterable[ParsedStatementRow]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        current: ParsedStatementRow | None = None
        for line in lines:
            if line.startswith(":61:"):
                if current:
                    yield current
                current = self._parse_mt940_61(line)
            elif line.startswith(":86:") and current:
                extra = line[4:].strip()
                current.description = (current.description + " " + extra).strip()
                if not current.payer_phone:
                    current.payer_phone = self._extract_phone(extra)
                if not current.payer_name:
                    current.payer_name = self._extract_payer_name(extra)
        if current:
            yield current

    def _parse_mt940_61(self, line: str) -> ParsedStatementRow:
        payload = line[4:]
        # Example: 2402010201C15000,00NTRFNONREF//TX123
        date_token = payload[:6]
        value_date = datetime.strptime(date_token, "%y%m%d").date()
        remainder = payload[10:] if len(payload) > 10 else payload[6:]
        sign_char = "C"
        if remainder and remainder[0] in ("C", "D"):
            sign_char = remainder[0]
            remainder = remainder[1:]

        amount_match = re.match(r"([0-9,\.]+)", remainder)
        amount_str = amount_match.group(1) if amount_match else "0"
        amount = self._to_decimal(amount_str)
        if sign_char == "D":
            amount = -amount

        ref_match = re.search(r"//([A-Za-z0-9\-_]+)", payload)
        reference = ref_match.group(1) if ref_match else ""

        return ParsedStatementRow(
            transaction_date=value_date,
            amount=amount,
            transaction_reference=reference[:100],
            description="MT940 import",
            transaction_type=self._infer_transaction_type(amount, ""),
            raw_payload={"line": line},
        )

    def _upsert_entry(
        self,
        bank_account: BankAccount,
        row: ParsedStatementRow,
    ) -> tuple[BankStatementEntry, bool]:
        existing = BankStatementEntry.objects.filter(
            bank_account=bank_account,
            transaction_date=row.transaction_date,
            amount=row.amount,
            transaction_reference=row.transaction_reference,
        ).first()
        if existing:
            return existing, False

        entry = BankStatementEntry.objects.create(
            bank_account=bank_account,
            transaction_date=row.transaction_date,
            amount=row.amount,
            transaction_type=row.transaction_type,
            transaction_reference=row.transaction_reference,
            description=row.description,
            balance_after=row.balance_after,
            imported_from="Bank Statement Upload",
        )
        return entry, True

    def _link_or_create_suspense(
        self, entry: BankStatementEntry, row: ParsedStatementRow
    ) -> bool:
        if entry.transaction_type not in (
            BankStatementEntry.TransactionType.DEPOSIT,
            BankStatementEntry.TransactionType.TRANSFER_IN,
        ):
            return False

        proof = self._find_matching_receipt_proof(entry)
        if proof:
            entry.matched_receipt_upload = proof
            entry.is_verified = True
            entry.save(update_fields=["matched_receipt_upload", "is_verified"])
            return False

        # No receipt proof match -> open suspense queue item
        suggested_invoice = self._suggest_invoice(
            entry.transaction_reference, entry.description
        )
        suspense, created = SuspensePayment.objects.get_or_create(
            bank_statement_entry=entry,
            defaults={
                "amount": abs(entry.amount),
                "currency": entry.bank_account.currency
                or get_platform_defaults(use_db=False)["currency"],
                "transaction_reference": entry.transaction_reference,
                "payer_name": row.payer_name,
                "payer_phone": row.payer_phone,
                "description": entry.description,
                "raw_payload": row.raw_payload or {},
                "suggested_invoice": suggested_invoice,
                "suggested_student": getattr(suggested_invoice, "student", None),
            },
        )
        return created

    def _find_matching_receipt_proof(
        self, entry: BankStatementEntry
    ) -> PaymentProofUpload | None:
        ref = (entry.transaction_reference or "").strip()
        if ref:
            by_ref = (
                PaymentProofUpload.objects.filter(
                    transaction_reference__iexact=ref,
                    bank_verified=False,
                )
                .order_by("-created_at")
                .first()
            )
            if by_ref:
                return by_ref

        by_amount = (
            PaymentProofUpload.objects.filter(
                uploaded_amount=abs(entry.amount),
                bank_verified=False,
                created_at__date__gte=entry.transaction_date - timedelta(days=7),
                created_at__date__lte=entry.transaction_date + timedelta(days=7),
            )
            .order_by("-created_at")
            .first()
        )
        return by_amount

    def _suggest_invoice(self, reference: str, description: str) -> Invoice | None:
        ref = (reference or "").strip()
        desc = (description or "").strip()
        if ref:
            invoice = Invoice.objects.filter(payment_code__iexact=ref).first()
            if invoice:
                return invoice
            invoice = Invoice.objects.filter(reference__iexact=ref).first()
            if invoice:
                return invoice
        if desc:
            invoice = Invoice.objects.filter(payment_code__icontains=desc).first()
            if invoice:
                return invoice
        return None

    @transaction.atomic
    def claim_suspense_payment(
        self,
        suspense_payment: SuspensePayment,
        allocations: list[dict],
        claimed_by=None,
        notes: str = "",
    ) -> dict:
        if not allocations:
            raise ValueError("At least one allocation is required.")

        total = Decimal("0.00")
        parsed_allocations: list[tuple[Invoice, Decimal]] = []
        for row in allocations:
            invoice_id = int(row["invoice_id"])
            amount = self._to_decimal(row["amount"])
            if amount <= 0:
                continue
            invoice = Invoice.objects.select_related("student").get(pk=invoice_id)
            parsed_allocations.append((invoice, amount))
            total += amount

        if total <= 0:
            raise ValueError("Allocation total must be positive.")
        if total > suspense_payment.remaining_amount:
            raise ValueError("Allocation total exceeds suspense remaining amount.")

        method = self._payment_method_from_bank_account(suspense_payment)
        created_payments: list[Payment] = []

        for invoice, amount in parsed_allocations:
            payment = Payment.objects.create(
                invoice=invoice,
                student=invoice.student,
                amount=amount,
                method=method,
                reference=f"SUSP-{suspense_payment.pk}-{invoice.pk}",
                external_reference=suspense_payment.transaction_reference or "",
                paid_at=timezone.now(),
                status="completed",
                processed_by=claimed_by,
                description=f"Allocated from suspense payment #{suspense_payment.pk}",
            )
            apply_payment(payment)
            SuspensePaymentAllocation.objects.update_or_create(
                suspense_payment=suspense_payment,
                invoice=invoice,
                defaults={
                    "amount": amount,
                    "payment": payment,
                    "created_by": claimed_by,
                },
            )
            created_payments.append(payment)

        suspense_payment.claimed_by = claimed_by
        suspense_payment.claimed_at = suspense_payment.claimed_at or timezone.now()
        suspense_payment.notes = (suspense_payment.notes or "").strip()
        if notes:
            suspense_payment.notes = (suspense_payment.notes + "\n" + notes).strip()
        if parsed_allocations and not suspense_payment.claimed_student:
            suspense_payment.claimed_student = parsed_allocations[0][0].student

        if suspense_payment.remaining_amount <= Decimal("0.00"):
            suspense_payment.status = SuspensePayment.Status.RESOLVED
            suspense_payment.resolved_at = timezone.now()
            if suspense_payment.bank_statement_entry_id:
                suspense_payment.bank_statement_entry.is_verified = True
                suspense_payment.bank_statement_entry.save(
                    update_fields=["is_verified"]
                )
        else:
            suspense_payment.status = SuspensePayment.Status.PARTIAL
        suspense_payment.save()

        return {
            "suspense_payment_id": suspense_payment.pk,
            "status": suspense_payment.status,
            "allocated_total": str(total),
            "remaining": str(suspense_payment.remaining_amount),
            "payment_ids": [str(p.pk) for p in created_payments],
        }

    def _payment_method_from_bank_account(
        self, suspense_payment: SuspensePayment
    ) -> str:
        account_type = None
        if suspense_payment.bank_statement_entry_id:
            account_type = (
                suspense_payment.bank_statement_entry.bank_account.account_type
            )
        if account_type == BankAccount.AccountType.MTN_MOMO:
            return PaymentMethodCode.MTN_MOMO
        if account_type == BankAccount.AccountType.ORANGE_MONEY:
            return PaymentMethodCode.ORANGE_MOMO
        if account_type == BankAccount.AccountType.BANK:
            return PaymentMethodCode.BANK
        return PaymentMethodCode.OTHER

    def _pick(self, row: dict, keys: tuple[str, ...]) -> str:
        lowered = {str(k).strip().lower(): (v or "") for k, v in row.items()}
        for key in keys:
            value = lowered.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def _to_date(self, value: str):
        text = (value or "").strip()
        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Unsupported date format: '{value}'")

    def _to_decimal(self, value: str | Decimal) -> Decimal:
        if isinstance(value, Decimal):
            return value
        text = str(value or "").strip().replace(" ", "").replace(",", ".")
        try:
            return Decimal(text)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid amount '{value}'") from exc

    def _infer_transaction_type(self, amount: Decimal, raw_type: str) -> str:
        t = (raw_type or "").upper().strip()
        if t in {"CREDIT", "CR", "IN", "DEPOSIT"}:
            return BankStatementEntry.TransactionType.DEPOSIT
        if t in {"TRANSFER_IN"}:
            return BankStatementEntry.TransactionType.TRANSFER_IN
        if t in {"DEBIT", "DR", "OUT", "WITHDRAWAL"}:
            return BankStatementEntry.TransactionType.WITHDRAWAL
        if amount < 0:
            return BankStatementEntry.TransactionType.WITHDRAWAL
        return BankStatementEntry.TransactionType.DEPOSIT

    def _extract_phone(self, text: str) -> str:
        if not text:
            return ""
        match = re.search(r"(?:237)?([62]\d{8})", text.replace(" ", ""))
        return match.group(1) if match else ""

    def _extract_payer_name(self, text: str) -> str:
        if not text:
            return ""
        # Conservative extraction: keep first alpha sequence up to 60 chars.
        match = re.search(r"([A-Za-z][A-Za-z\s\.\-']{2,60})", text)
        return (match.group(1).strip() if match else "")[:120]
