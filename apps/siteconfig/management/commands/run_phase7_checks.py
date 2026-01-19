from __future__ import annotations

from django.core.management import BaseCommand, call_command, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Run the Phase 7 QA/automation checklist."

    def add_arguments(self, parser):
        parser.add_argument(
            "--require-automation",
            action="store_true",
            help="Fail if optional automation commands (attendance/payroll/reminders) are missing.",
        )

    def handle(self, *args, **options):
        start = timezone.now()
        self.stdout.write("Running Phase 7 checks...")
        call_command("check")
        call_command("test")

        optional_commands = ["run_attendance_cycle", "run_payroll_cycle", "run_payment_reminders"]
        for cmd in optional_commands:
            try:
                call_command(cmd)
            except CommandError:
                msg = f"Skipped missing command: {cmd}"
                if options.get("require_automation"):
                    raise
                self.stdout.write(self.style.WARNING(msg))

        end = timezone.now()
        self.stdout.write(self.style.SUCCESS(f"Phase 7 checks completed in {end-start}."))
