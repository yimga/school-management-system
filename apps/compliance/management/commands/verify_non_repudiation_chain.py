"""Verify the platform-wide non-repudiation hash chain (Wave E).

    python manage.py verify_non_repudiation_chain [--school <id>]

Exit 0 = chain intact; exit 1 = tamper/break detected.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.compliance.non_repudiation import verify_chain


class Command(BaseCommand):
    help = "Verify the per-school non-repudiation action-log hash chain + signatures."

    def add_arguments(self, parser):
        parser.add_argument("--school", default=None, help="School id (omit for platform-level chain).")

    def handle(self, *args, **options):
        result = verify_chain(school_id=options.get("school"))
        if result["ok"]:
            self.stdout.write(self.style.SUCCESS(f"chain OK ({result['checked']} entries)"))
            return
        raise CommandError(
            f"chain BROKEN at sequence {result.get('broken_at')}: {result.get('reason')}"
        )
