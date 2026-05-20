"""Archive published KB articles with sustained negative helpfulness (batch 1356)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.portal.kb_archive import archive_kb_articles, stale_kb_archive_candidates


class Command(BaseCommand):
    help = "Archive stale or unhelpful KB articles (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Persist ARCHIVED status")
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--min-votes", type=int, default=5)

    def handle(self, *args, **options):
        candidates = stale_kb_archive_candidates(
            min_votes=options["min_votes"],
            limit=options["limit"],
        )
        result = archive_kb_articles(candidates, dry_run=not options["apply"])
        self.stdout.write(
            self.style.SUCCESS(
                f"archive_stale_kb_articles: {result} ({len(candidates)} candidates)"
            )
        )
