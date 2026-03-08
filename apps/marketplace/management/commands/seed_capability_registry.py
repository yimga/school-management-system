"""
Seed CapabilityRegistry with standard capability codes from the manifest schema.
Run: python manage.py seed_capability_registry
Idempotent: creates only missing codes; use --reset to clear and re-seed (optional).
"""
from django.core.management.base import BaseCommand

from apps.marketplace.models import CapabilityRegistry


# Standard codes per category (code, name, description)
DEFAULT_CAPABILITIES = [
    (CapabilityRegistry.Category.DASHBOARD_WIDGET, "dashboard_widget", "Dashboard widget", "Widget shown on school dashboard"),
    (CapabilityRegistry.Category.WORKFLOW_ACTION, "workflow_action", "Workflow action", "Action available in workflow automation"),
    (CapabilityRegistry.Category.WORKFLOW_CONDITION, "workflow_condition", "Workflow condition", "Condition in workflow automation"),
    (CapabilityRegistry.Category.INTEGRATION_ADAPTER, "integration_adapter", "Integration adapter", "External integration adapter"),
]


class Command(BaseCommand):
    help = "Seed CapabilityRegistry with standard capability codes (dashboard_widget, workflow_action, etc.)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all registry entries and re-seed (default: only add missing).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing.",
        )

    def handle(self, *args, **options):
        reset = options["reset"]
        dry_run = options["dry_run"]
        if reset and not dry_run:
            deleted, _ = CapabilityRegistry.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} capability registry entries."))
        created = 0
        for category, code, name, description in DEFAULT_CAPABILITIES:
            if dry_run:
                if reset or not CapabilityRegistry.objects.filter(code=code).exists():
                    self.stdout.write(f"Would create: {code} ({category})")
                    created += 1
                continue
            _, was_created = CapabilityRegistry.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "category": category,
                    "description": description,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"Created: {code}"))
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry run: would create {created} entries."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done. Created {created} capability registry entries."))
