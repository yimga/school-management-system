"""``manage.py sync_roster`` — pull a Clever/ClassLink district roster into a school (F5c).

Usage:
    python manage.py sync_roster --school <slug> --provider clever [--dry-run] [--limit 200]
    python manage.py sync_roster --school <slug> --provider classlink

Credentials are read from the school's District-interop ServiceIntegration
(``native_clever_bearer`` / ``native_classlink_bearer`` / ``native_classlink_base_url``),
which the tenant admin sets under the District interop screen. Live pulls require
a certified Clever/ClassLink district token (partner onboarding); without one the
command exits with a clear message rather than doing anything.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.interop.roster_sync import (
    RosterSyncError,
    classlink_fetch_pages,
    clever_fetch_pages,
    record_sync_state,
    resolve_roster_bearer,
    sync_roster_for_school,
)
from apps.schools.models import School


class Command(BaseCommand):
    help = "Pull a Clever/ClassLink district roster into a school (User + membership + StudentProfile)."

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="School slug or subdomain.")
        parser.add_argument(
            "--provider", required=True, choices=["clever", "classlink"],
            help="Roster source.",
        )
        parser.add_argument("--limit", type=int, default=100, help="Page size for the pull.")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Fetch + map + count, but write nothing.",
        )

    def handle(self, *args, **options):
        slug = (options["school"] or "").strip()
        school = School.objects.filter(Q(slug=slug) | Q(subdomain=slug)).first()
        if not school:
            raise CommandError(f"No school found for '{slug}' (slug or subdomain).")

        provider = options["provider"]
        bearer, base_url, integration = resolve_roster_bearer(school, provider)
        if not bearer:
            raise CommandError(
                f"No {provider} district bearer stored for '{school.slug}'. "
                f"Connect it under District interop first. Live pulls require a "
                f"certified {provider} district token (partner onboarding)."
            )

        if provider == "clever":
            fetch = clever_fetch_pages(bearer, limit=options["limit"])
        else:
            fetch = classlink_fetch_pages(bearer, base_url, limit=options["limit"])

        try:
            stats = sync_roster_for_school(
                school, provider=provider, fetch_pages=fetch, dry_run=options["dry_run"]
            )
        except RosterSyncError as exc:
            raise CommandError(f"Roster pull failed: {exc}")

        if integration is not None and not options["dry_run"]:
            record_sync_state(integration, stats)

        self.stdout.write(
            self.style.SUCCESS(
                f"Roster sync '{school.slug}' [{provider}]: "
                f"seen={stats['seen']} created={stats['created']} "
                f"updated={stats['updated']} students={stats['students']} "
                f"skipped={stats['skipped']} dry_run={stats['dry_run']}"
            )
        )
