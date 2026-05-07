from django.core.management.base import BaseCommand

from apps.platform_runtime.governance_queue import process_due_configuration_changes


class Command(BaseCommand):
    help = "Process due approved configuration change requests."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        result = process_due_configuration_changes(limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {result['processed']} due configuration change request(s)."
            )
        )
