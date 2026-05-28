"""One-time migration: siteconfig.ProductFeedback → apps.feedback.FeatureRequest."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.feedback.legacy_product_feedback_migration import migrate_legacy_rows


class Command(BaseCommand):
    help = "Migrate legacy ProductFeedback rows into FeatureRequest (CEZGP P7c)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write rows (default is dry-run preview only).",
        )

    def handle(self, *args, **options):
        dry_run = not options["apply"]
        summary = migrate_legacy_rows(dry_run=dry_run)
        mode = "DRY-RUN" if dry_run else "APPLIED"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: scanned={summary.scanned} created={summary.created} "
                f"skipped_existing={summary.skipped_existing}"
            )
        )
