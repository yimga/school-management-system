"""
Phase 10 — 1.2: Backfill RuntimeDefaults.payload from SiteSettings.
Run after deploying RuntimeDefaults; get_effective_site_settings will prefer this
payload before falling back to legacy singleton fields.
"""
from django.core.management.base import BaseCommand

from apps.siteconfig.domain_ownership import OWNERSHIP_DOMAINS


class Command(BaseCommand):
    help = "Backfill platform_runtime.RuntimeDefaults from SiteSettings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner",
            action="append",
            choices=OWNERSHIP_DOMAINS,
            dest="owners",
            help="Limit the payload to one or more SiteSettings ownership domains.",
        )
        parser.add_argument(
            "--exclude-owner",
            action="append",
            choices=OWNERSHIP_DOMAINS,
            dest="exclude_owners",
            help="Exclude one or more SiteSettings ownership domains from the payload.",
        )

    def handle(self, *args, **options):
        from apps.platform_runtime.models import RuntimeDefaults
        from apps.siteconfig.models import SiteSettings

        owners = options.get("owners") or None
        exclude_owners = options.get("exclude_owners") or None
        site = SiteSettings.get_solo()
        obj, created = RuntimeDefaults.sync_from_site_settings(
            site,
            owners=owners,
            exclude_owners=exclude_owners,
        )
        payload = obj.payload or {}
        owner_note = []
        if owners:
            owner_note.append(f"owners={','.join(owners)}")
        if exclude_owners:
            owner_note.append(f"exclude={','.join(exclude_owners)}")
        suffix = f" ({'; '.join(owner_note)})" if owner_note else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"RuntimeDefaults id=1 {'created' if created else 'updated'} with {len(payload)} keys{suffix}."
            )
        )
