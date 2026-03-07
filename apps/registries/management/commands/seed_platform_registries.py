from django.core.management.base import BaseCommand

from apps.registries.services import ensure_registry_baseline


class Command(BaseCommand):
    help = "Seed platform registries for countries, subdivisions, education levels, and education system types."

    def handle(self, *args, **options):
        ensure_registry_baseline()
        self.stdout.write(self.style.SUCCESS("Platform registries seeded."))
