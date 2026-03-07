from django.core.management.base import BaseCommand

from apps.events.legacy_bridge import retire_legacy_webhook_subscriptions


class Command(BaseCommand):
    help = "Sync legacy siteconfig webhook subscriptions into apps.events and retire the legacy active subscriptions."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview changes without updating legacy rows.")

    def handle(self, *args, **options):
        summary = retire_legacy_webhook_subscriptions(dry_run=bool(options.get("dry_run")))
        self.stdout.write(
            self.style.SUCCESS(
                "created={created} updated={updated} unchanged={unchanged} retired_active_subscriptions={retired_active_subscriptions}".format(
                    **summary
                )
            )
        )
