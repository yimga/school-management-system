from django.core.management.base import BaseCommand

from apps.events.legacy_bridge import sync_legacy_webhook_subscriptions


class Command(BaseCommand):
    help = "Sync legacy siteconfig webhook subscriptions into the canonical apps.events webhook stack."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the sync plan without writing canonical webhook subscriptions.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        result = sync_legacy_webhook_subscriptions(dry_run=dry_run)
        mode = "dry-run" if dry_run else "write"
        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"Legacy webhook sync ({mode}) complete. "
                    f"created={result['created']} updated={result['updated']} "
                    f"unchanged={result['unchanged']} legacy_groups={result['legacy_groups']} "
                    f"unsynced_legacy_groups={result['unsynced_legacy_groups']}"
                )
            )
        )
