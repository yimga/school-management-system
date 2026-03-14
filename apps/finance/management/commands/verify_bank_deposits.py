"""
Management command to verify receipt uploads against bank statements.

Usage:
    python manage.py verify_bank_deposits
    python manage.py verify_bank_deposits --auto-approve
    python manage.py verify_bank_deposits --account-id=1
"""

from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import DatabaseError, IntegrityError
from django.utils import timezone
from apps.finance.models import PaymentProofUpload, BankAccount, BankStatementEntry
from apps.finance.bank_verification import BankDepositVerifier
from apps.finance.services import create_payment_from_receipt
from apps.finance.receipt_verification import ReceiptVerificationService


class Command(BaseCommand):
    help = "Verify receipt uploads against bank statements and auto-approve if verified"
    
    def add_arguments(self, parser):
        parser.add_argument(
            "--auto-approve",
            action="store_true",
            help="Automatically approve and create payments for verified deposits"
        )
        parser.add_argument(
            "--account-id",
            type=int,
            help="Verify only for specific bank account"
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Days to search before/after receipt date (default: 7)"
        )
    
    def handle(self, *args, **options):
        auto_approve = options["auto_approve"]
        account_id = options.get("account_id")
        tolerance_days = options["days"]
        
        verifier = BankDepositVerifier()
        
        # Get pending receipt uploads that need bank verification
        receipt_uploads = PaymentProofUpload.objects.filter(
            status__in=[
                PaymentProofUpload.Status.PENDING,
                PaymentProofUpload.Status.DISCREPANCY
            ],
            bank_verified=False
        ).select_related("invoice", "uploaded_by")
        
        if account_id:
            # Filter by payment method matching account type
            account = BankAccount.objects.get(id=account_id)
            if account.account_type == BankAccount.AccountType.BANK:
                receipt_uploads = receipt_uploads.filter(payment_method="BANK")
            elif account.account_type == BankAccount.AccountType.MTN_MOMO:
                receipt_uploads = receipt_uploads.filter(payment_method="MTN_MOMO")
            elif account.account_type == BankAccount.AccountType.ORANGE_MONEY:
                receipt_uploads = receipt_uploads.filter(payment_method="ORANGE_MOMO")
        
        verified_count = 0
        not_found_count = 0
        error_count = 0
        
        for receipt_upload in receipt_uploads:
            try:
                # Get relevant bank accounts
                if receipt_upload.payment_method == "BANK":
                    accounts = BankAccount.objects.filter(
                        account_type=BankAccount.AccountType.BANK,
                        is_active=True
                    )
                elif receipt_upload.payment_method == "MTN_MOMO":
                    accounts = BankAccount.objects.filter(
                        account_type=BankAccount.AccountType.MTN_MOMO,
                        is_active=True
                    )
                elif receipt_upload.payment_method == "ORANGE_MOMO":
                    accounts = BankAccount.objects.filter(
                        account_type=BankAccount.AccountType.ORANGE_MONEY,
                        is_active=True
                    )
                else:
                    continue
                
                if account_id:
                    accounts = accounts.filter(id=account_id)
                
                if not accounts.exists():
                    self.stdout.write(
                        self.style.WARNING(
                            f"No active bank account found for {receipt_upload.payment_method}"
                        )
                    )
                    continue
                
                # Get bank statements for all relevant accounts
                all_statements = []
                for account in accounts:
                    statements = BankStatementEntry.objects.filter(
                        bank_account=account,
                        transaction_type__in=[
                            BankStatementEntry.TransactionType.DEPOSIT,
                            BankStatementEntry.TransactionType.TRANSFER_IN
                        ]
                    )
                    all_statements.extend(list(statements))
                
                # Verify deposit
                if receipt_upload.payment_method == "MTN_MOMO":
                    verification_result = verifier.verify_mtn_momo_deposit(
                        receipt_upload,
                        [s for s in all_statements if s.bank_account.account_type == BankAccount.AccountType.MTN_MOMO]
                    )
                elif receipt_upload.payment_method == "ORANGE_MOMO":
                    verification_result = verifier.verify_orange_money_deposit(
                        receipt_upload,
                        [s for s in all_statements if s.bank_account.account_type == BankAccount.AccountType.ORANGE_MONEY]
                    )
                else:
                    verification_result = verifier.verify_deposit(
                        receipt_upload,
                        all_statements,
                        tolerance_days=tolerance_days
                    )
                
                # Update receipt upload with verification result
                receipt_upload.bank_verified = verification_result["verified"]
                receipt_upload.bank_verification_date = timezone.now()
                receipt_upload.bank_verification_method = verification_result["match_method"]
                receipt_upload.bank_statement_entry = verification_result.get("matched_entry")
                receipt_upload.bank_verification_notes = "; ".join(verification_result.get("discrepancies", []))
                
                if verification_result["verified"]:
                    verified_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Verified: Receipt {receipt_upload.id} - "
                            f"Match: {verification_result['match_method']} "
                            f"(confidence: {verification_result['match_confidence']:.2f})"
                        )
                    )
                    
                    # Auto-approve if requested
                    if auto_approve and verification_result["match_confidence"] >= 0.9:
                        with transaction.atomic():
                            # Extract receipt data if not already done
                            if not receipt_upload.verification_data:
                                verification_service = ReceiptVerificationService()
                                receipt_data = verification_service.extract_receipt_data(receipt_upload.receipt_file)
                                receipt_upload.verification_data = receipt_data
                                if receipt_data.get("amount"):
                                    receipt_upload.uploaded_amount = receipt_data["amount"]
                            
                            # Create payment
                            receipt_data = receipt_upload.verification_data or {}
                            payment = create_payment_from_receipt(receipt_upload, receipt_data)
                            
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  → Payment {payment.id} created and applied"
                                )
                            )
                else:
                    not_found_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"✗ Not found: Receipt {receipt_upload.id} - "
                            f"{verification_result.get('discrepancies', ['No match'])[0]}"
                        )
                    )
                
                receipt_upload.save()
                
            except (ValidationError, DatabaseError, IntegrityError, ValueError, TypeError, AttributeError) as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"✗ Error verifying receipt {receipt_upload.id}: {str(e)}"
                    )
                )
        
        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(f"Verified: {verified_count}"))
        self.stdout.write(self.style.WARNING(f"Not found: {not_found_count}"))
        self.stdout.write(self.style.ERROR(f"Errors: {error_count}"))
        self.stdout.write("="*50)
