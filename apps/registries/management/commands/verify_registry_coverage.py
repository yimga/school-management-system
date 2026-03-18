from django.core.management.base import BaseCommand, CommandError

from apps.registries.models import CountryRegistry
from apps.registries.services import ensure_country_registry_seed


class Command(BaseCommand):
    help = "Fail when registry coverage drops below the required country threshold."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minimum-countries",
            type=int,
            default=195,
            help="Minimum number of active country registry rows required.",
        )

    def handle(self, *args, **options):
        ensure_country_registry_seed()
        minimum = int(options["minimum_countries"])
        count = CountryRegistry.objects.filter(is_active=True).count()
        if count < minimum:
            raise CommandError(
                f"Country registry coverage too low: {count} < {minimum}"
            )
        self.stdout.write(self.style.SUCCESS(f"Country registry coverage OK: {count}"))
