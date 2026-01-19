from __future__ import annotations

from django.core.management import BaseCommand, call_command
from django.utils import timezone


class Command(BaseCommand):
    help = "Run the Phase 7 QA/automation checklist."

    def handle(self, *args, **options):
        start = timezone.now()
        self.stdout.write("Running Phase 7 checks...")
        call_command("check")
        call_command("test")
        call_command("run_attendance_cycle")
        call_command("run_payroll_cycle")
        call_command("run_payment_reminders")
        end = timezone.now()
        self.stdout.write(self.style.SUCCESS(f"Phase 7 checks completed in {end-start}."))
