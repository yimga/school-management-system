"""
Phase 10 — 1.2: Backfill RuntimeDefaults.payload from the siteconfig tenant settings row.
Run after deploying RuntimeDefaults; get_effective_site_settings will prefer this
payload before falling back to legacy singleton fields.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.platform_runtime.runtime_sync_owner_filters import (
    RUNTIME_SYNC_OWNER_CHOICES,
    normalize_runtime_sync_owner_filters,
)


class Command(BaseCommand):
    help = "Backfill platform_runtime.RuntimeDefaults from the siteconfig settings row."

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner",
            action="append",
            choices=RUNTIME_SYNC_OWNER_CHOICES,
            dest="owners",
            help="Limit the payload to one or more siteconfig ownership domains.",
        )
        parser.add_argument(
            "--exclude-owner",
            action="append",
            choices=RUNTIME_SYNC_OWNER_CHOICES,
            dest="exclude_owners",
            help="Exclude one or more siteconfig ownership domains from the payload.",
        )

    def handle(self, *args, **options):
        from apps.platform_runtime.models import RuntimeDefaults
        from apps.platform_runtime.helpers import get_platform_site_settings_record

        owners, exclude_owners = normalize_owner_filters(
            options.get("owners"),
            options.get("exclude_owners"),
        )
        # Platform backfill: use helper so get_solo() stays only in platform_runtime/helpers (allowlist shrink per SITESETTINGS_GET_SOLO_ALLOWLIST).
        # config-resolver-allow: write-path singleton (create=True provisioning; row handed to RuntimeDefaults.sync_from_site_settings)
        site = get_platform_site_settings_record(create=True)
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


def normalize_owner_filters(
    owners: list[str] | tuple[str, ...] | None,
    exclude_owners: list[str] | tuple[str, ...] | None,
) -> tuple[tuple[str, ...] | None, tuple[str, ...] | None]:
    """Normalize CLI filters and surface helper validation as ``CommandError``."""
    try:
        return normalize_runtime_sync_owner_filters(owners, exclude_owners)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
