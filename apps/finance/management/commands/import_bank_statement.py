from __future__ import annotations

from pathlib import Path

from django.core.files.base import File
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from apps.accounts.models import User
from apps.finance.bank_statement_import import BankStatementImportService
from apps.finance.models import BankAccount, BankStatementUpload


class Command(BaseCommand):
    help = "Import bank statements (CSV/MT940), create entries, and queue unmatched deposits in suspense."

    def add_arguments(self, parser):
        parser.add_argument("--upload-id", type=int, help="Process an existing BankStatementUpload by id.")
        parser.add_argument("--account-id", type=int, help="BankAccount id (required when creating upload).")
        parser.add_argument("--file", type=str, help="Statement file path (.csv or .mt940).")
        parser.add_argument("--start", type=str, help="Statement period start date (YYYY-MM-DD).")
        parser.add_argument("--end", type=str, help="Statement period end date (YYYY-MM-DD).")
        parser.add_argument("--username", type=str, help="User who uploaded/imported the statement.")

    def handle(self, *args, **options):
        service = BankStatementImportService()
        upload_id = options.get("upload_id")

        if upload_id:
            upload = BankStatementUpload.objects.filter(pk=upload_id).first()
            if not upload:
                raise CommandError(f"BankStatementUpload {upload_id} not found.")
            summary = service.process_upload(upload)
            self._print_summary(upload, summary)
            return

        account_id = options.get("account_id")
        file_path = options.get("file")
        start = options.get("start")
        end = options.get("end")
        username = options.get("username")

        if not account_id or not file_path or not start or not end:
            raise CommandError("For new imports use --account-id, --file, --start, and --end.")

        account = BankAccount.objects.filter(pk=account_id).first()
        if not account:
            raise CommandError(f"BankAccount {account_id} not found.")

        start_date = parse_date(start)
        end_date = parse_date(end)
        if not start_date or not end_date:
            raise CommandError("Invalid period dates. Use YYYY-MM-DD for --start and --end.")
        if end_date < start_date:
            raise CommandError("--end must be greater than or equal to --start.")

        source = Path(file_path)
        if not source.exists():
            raise CommandError(f"Statement file not found: {file_path}")

        user = None
        if username:
            user = User.objects.filter(username=username).first()
            if not user:
                raise CommandError(f"User '{username}' not found.")

        upload = BankStatementUpload.objects.create(
            bank_account=account,
            statement_period_start=start_date,
            statement_period_end=end_date,
            uploaded_by=user,
            status=BankStatementUpload.Status.PENDING,
        )
        with source.open("rb") as fh:
            upload.statement_file.save(source.name, File(fh), save=True)

        summary = service.process_upload(upload)
        self._print_summary(upload, summary)

    def _print_summary(self, upload: BankStatementUpload, summary: dict) -> None:
        self.stdout.write(self.style.SUCCESS(f"Upload {upload.id} processed with status {summary['status']}."))
        self.stdout.write(f"Entries created: {summary['entries_created']}")
        self.stdout.write(f"Suspense created: {summary['suspense_created']}")
        if summary["errors"]:
            self.stdout.write(self.style.WARNING("Errors:"))
            for err in summary["errors"]:
                self.stdout.write(f"- {err}")
