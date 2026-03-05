"""
Process pending webhook deliveries (POST to subscription URLs with retries and signing).
Usage: python manage.py process_webhook_deliveries [--batch 50]
"""
from django.core.management.base import BaseCommand
from apps.events.tasks import process_webhook_deliveries_batch


class Command(BaseCommand):
    help = "Process pending webhook deliveries."

    def add_arguments(self, parser):
        parser.add_argument("--batch", type=int, default=50, help="Max deliveries to process per run")

    def handle(self, *args, **options):
        n = process_webhook_deliveries_batch(batch_size=options["batch"])
        self.stdout.write(self.style.SUCCESS(f"Processed {n} webhook delivery attempt(s)."))
