"""
Management command to send deadline reminder notifications to teachers.
Uses SubjectAssignment.grading_deadline_at; teachers are resolved via TeacherAssignment.
When CELERY_BROKER_URL is set, enqueues the task; otherwise runs the logic inline.

Usage:
    python manage.py send_deadline_reminders
    python manage.py send_deadline_reminders --days 7,3,1
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.analytics.tasks import run_deadline_reminders, send_deadline_reminders_task


class Command(BaseCommand):
    help = "Send grading deadline reminders to teachers (SubjectAssignment.grading_deadline_at)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=str,
            default="7,3,1,0.5",
            help="Comma-separated days before deadline to send reminders",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print reminders without sending",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        days_str = options.get("days", "7,3,1,0.5")
        broker_url = getattr(settings, "CELERY_BROKER_URL", None) or ""

        if broker_url:
            send_deadline_reminders_task.delay(days_str=days_str, dry_run=dry_run)
            self.stdout.write(
                self.style.SUCCESS("Deadline reminders queued. Worker will process them.")
            )
            return

        result = run_deadline_reminders(days_str=days_str, dry_run=dry_run)
        if result.get("error"):
            self.stdout.write(self.style.ERROR(result["error"]))
            return
        sent = result.get("sent", 0)
        errors = result.get("errors", 0)
        self.stdout.write(
            self.style.SUCCESS(f"\nCommand completed. Sent {sent} reminders." + (f" Errors: {errors}." if errors else ""))
        )
