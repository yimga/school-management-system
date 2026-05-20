"""
Ensure DRAFT KB articles exist for guided-journey slug map (batch 1354).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.portal.help_guided_journeys import JOURNEY_BY_PREFIX
from apps.portal.models_kb import HelpAudience, KBArticle, KBCategory


class Command(BaseCommand):
    help = "Create DRAFT operator KB stubs for journey slugs missing from the corpus."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write rows (default dry-run).")

    def handle(self, *args, **options):
        apply = bool(options.get("apply"))
        category = KBCategory.objects.filter(is_active=True).order_by("display_order").first()
        if category is None:
            self.stderr.write("No KBCategory — create one first.")
            return
        slugs: set[str] = set()
        for rows in JOURNEY_BY_PREFIX.values():
            slugs.update(rows)
        created = 0
        for slug in sorted(slugs):
            if KBArticle.objects.filter(slug=slug, school__isnull=True).exists():
                continue
            title = slug.replace("-", " ").title()
            if apply:
                KBArticle.objects.create(
                    title=title,
                    slug=slug,
                    category=category,
                    summary=f"Journey stub for {slug} — expand before publish.",
                    content=f"# {title}\n\nDraft journey placeholder (batch 1354 seed).",
                    status="DRAFT",
                    help_audience=HelpAudience.BOTH,
                )
            created += 1
            self.stdout.write(f"{'create' if apply else 'would create'}: {slug}")
        self.stdout.write(self.style.SUCCESS(f"seed_help_journey_slugs: {created} stub(s)"))
