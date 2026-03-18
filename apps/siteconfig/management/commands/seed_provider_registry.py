"""
Platform bootstrap: Seed platform-level provider registry (Integration with school=None)
so Manager/API Center can show viable provider types: payment, email, SMS, document AI,
identity provider, storage provider. Idempotent (update_or_create by slug).
Run: python manage.py seed_provider_registry
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.siteconfig.models import Integration


# Official starter provider registry (audit pack: payment, email, SMS, document AI, identity, storage)
# school=None => platform-level template; schools clone or reference these when enabling.
PROVIDER_REGISTRY = [
    {
        "slug": "provider-registry-payment",
        "name": "Payment provider",
        "provider": "payments",
        "category": "PAYMENT",
    },
    {
        "slug": "provider-registry-email",
        "name": "Email provider",
        "provider": "email",
        "category": "MESSAGING",
    },
    {
        "slug": "provider-registry-sms",
        "name": "SMS provider",
        "provider": "sms",
        "category": "MESSAGING",
    },
    {
        "slug": "provider-registry-document-ai",
        "name": "Document AI provider",
        "provider": "analytics",
        "category": "AI",
    },
    {
        "slug": "provider-registry-identity",
        "name": "Identity provider",
        "provider": "other",
        "category": "SIS",
    },
    {
        "slug": "provider-registry-storage",
        "name": "Storage provider",
        "provider": "other",
        "category": "OTHER",
    },
]


class Command(BaseCommand):
    help = (
        "Seed platform-level provider registry (Integration templates with school=None) "
        "so payment, email, SMS, document AI, identity, storage show as viable providers. Idempotent."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created/updated without writing.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write("Dry run: no changes will be written.")

        created = 0
        for row in PROVIDER_REGISTRY:
            slug = row["slug"]
            if dry_run:
                if not Integration.objects.filter(slug=slug).exists():
                    self.stdout.write(
                        f"Would create provider registry entry: {row['name']} ({slug})"
                    )
                    created += 1
                continue
            _, was_created = Integration.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": row["name"],
                    "provider": row["provider"],
                    "category": row.get("category", "OTHER"),
                    "school": None,
                    "enabled": False,
                    "config": {},
                },
            )
            if was_created:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Provider registry: {len(PROVIDER_REGISTRY)} entries ensured ({created} created)."
            )
        )
