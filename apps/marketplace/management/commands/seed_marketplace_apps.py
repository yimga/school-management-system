"""
Platform bootstrap: Seed first-party Marketplace apps and approved listings so the
Manager App catalog shows installable apps. Idempotent (update_or_create by slug).
Run: python manage.py seed_marketplace_apps
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.marketplace.models import (
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
)


# First-party apps to show in App catalog (installable after seed)
FIRST_PARTY_APPS = [
    {
        "slug": "advanced-analytics-pack",
        "name": "Advanced Analytics Pack",
        "description": "First-party analytics and reporting enhancements for dashboards and exports.",
        "version": "1.0",
        "manifest": {"scopes": [], "widgets": []},
    },
    {
        "slug": "migration-connector-pack",
        "name": "Migration Connector Pack",
        "description": "First-party migration and import connectors for CSV/XLSX and legacy data.",
        "version": "1.0",
        "manifest": {"scopes": ["migration_import"], "widgets": []},
    },
    {
        "slug": "premium-communication-pack",
        "name": "Premium Communication Pack",
        "description": "First-party communication and announcement enhancements.",
        "version": "1.0",
        "manifest": {"scopes": ["communication"], "widgets": []},
    },
    {
        "slug": "transport-bus-tracker",
        "name": "Transport / Bus Tracker",
        "description": "First-party transport and bus tracking module.",
        "version": "1.0",
        "manifest": {"scopes": ["transport"], "widgets": []},
    },
]


class Command(BaseCommand):
    help = "Seed first-party Marketplace apps and approved listings so App catalog is not empty. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write("Dry run: no changes will be written.")

        # Publisher for first-party apps
        publisher, pub_created = PublisherOrganization.objects.get_or_create(
            slug="runmycampus-first-party",
            defaults={
                "name": "RunMyCampus First-Party",
                "legal_name": "RunMyCampus First-Party",
                "verification_status": PublisherOrganization.VerificationStatus.VERIFIED,
            },
        )
        if pub_created and not dry_run:
            self.stdout.write(self.style.SUCCESS("Created publisher: RunMyCampus First-Party."))
        elif dry_run and not PublisherOrganization.objects.filter(slug="runmycampus-first-party").exists():
            self.stdout.write("Would create publisher: RunMyCampus First-Party.")

        created_apps = 0
        created_listings = 0
        for app_def in FIRST_PARTY_APPS:
            slug = app_def["slug"]
            if dry_run:
                if not MarketplaceApp.objects.filter(slug=slug).exists():
                    self.stdout.write(f"Would create app: {app_def['name']} ({slug})")
                    created_apps += 1
                app = MarketplaceApp.objects.filter(slug=slug).first()
                if app and not getattr(app, "listing", None):
                    self.stdout.write(f"Would create approved listing for: {slug}")
                    created_listings += 1
                continue

            app, app_created = MarketplaceApp.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": app_def["name"],
                    "description": app_def.get("description", ""),
                    "kind": MarketplaceApp.AppKind.FIRST_PARTY,
                    "version": app_def.get("version", "1.0"),
                    "manifest": app_def.get("manifest", {}),
                    "is_active": True,
                    "publisher": publisher,
                },
            )
            if app_created:
                created_apps += 1

            listing, list_created = MarketplaceListing.objects.get_or_create(
                app=app,
                defaults={
                    "publisher": publisher,
                    "short_description": (app.description or "")[:255],
                    "status": MarketplaceListing.Status.APPROVED,
                    "security_review_status": MarketplaceListing.ReviewStatus.NOT_REQUIRED,
                    "certification_status": MarketplaceListing.ReviewStatus.NOT_REQUIRED,
                    "kill_switch_active": False,
                    "approved_at": timezone.now(),
                },
            )
            if not list_created and listing.status != MarketplaceListing.Status.APPROVED:
                listing.status = MarketplaceListing.Status.APPROVED
                listing.kill_switch_active = False
                listing.save(update_fields=["status", "kill_switch_active", "updated_at"])
                created_listings += 1
            elif list_created:
                created_listings += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Marketplace apps: {len(FIRST_PARTY_APPS)} ensured ({created_apps} created). "
                f"Listings approved: {created_listings}."
            )
        )
