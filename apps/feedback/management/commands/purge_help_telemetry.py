"""
Purge aged help telemetry (deflection + search logs + AI reviews) — batch 1345.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Delete help telemetry rows older than help_telemetry_retention_days."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", default=True)
        parser.add_argument("--apply", action="store_true", help="Actually delete rows.")
        parser.add_argument("--days", type=int, default=0, help="Override retention days.")

    def handle(self, *args, **options):
        from apps.feedback.models import (
            HelpSearchQueryLog,
            SupportAIInteractionReview,
            SupportDeflectionEvent,
        )
        from apps.portal.help_governance import help_telemetry_retention_days

        days = int(options.get("days") or 0) or help_telemetry_retention_days()
        cutoff = timezone.now() - timedelta(days=days)
        dry = not options.get("apply", False)
        models = (
            ("SupportDeflectionEvent", SupportDeflectionEvent),
            ("HelpSearchQueryLog", HelpSearchQueryLog),
            ("SupportAIInteractionReview", SupportAIInteractionReview),
        )
        total = 0
        for label, model in models:
            # tenant-isolation-allow: retention purge across all schools by design
            qs = model.objects.filter(created_at__lt=cutoff)
            count = qs.count()
            total += count
            if dry:
                self.stdout.write(f"{label}: would delete {count}")
            else:
                deleted, _ = qs.delete()
                self.stdout.write(f"{label}: deleted {deleted}")
        suffix = " (dry-run)" if dry else ""
        self.stdout.write(self.style.SUCCESS(f"purge_help_telemetry complete: {total}{suffix}"))
