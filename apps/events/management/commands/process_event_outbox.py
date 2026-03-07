"""
Process pending domain events from the outbox. Run via cron or Celery beat.
Usage: python manage.py process_event_outbox [--batch 100]
"""
from django.core.management.base import BaseCommand
from apps.events.tasks import process_outbox_batch


class Command(BaseCommand):
    help = "Process pending domain events from the outbox."

    def add_arguments(self, parser):
        parser.add_argument("--batch", type=int, default=100, help="Max events to process per run")

    def handle(self, *args, **options):
        batch = options["batch"]
        n = process_outbox_batch(batch_size=batch)
        self.stdout.write(self.style.SUCCESS(f"Processed {n} event(s)."))
