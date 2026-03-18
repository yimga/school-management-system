"""
Update PolicyBundles for schools when their applied BlueprintPack version has increased (11.2).
Run from cron: python manage.py update_blueprint_bundles
Optional: --pack=slug to update only one pack; --dry-run to list schools without applying.
"""

from django.core.management.base import BaseCommand

from apps.policies.models import BlueprintPack
from apps.policies.blueprint_services import update_bundle_for_schools


class Command(BaseCommand):
    help = "Update bundle for schools when their BlueprintPack version increased (11.2, REFINEMENT Priority 1)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pack",
            type=str,
            default=None,
            help="BlueprintPack slug to update (default: all active packs)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only list schools that would be updated; do not apply.",
        )

    def handle(self, *args, **options):
        pack_slug = options["pack"]
        dry_run = options["dry_run"]

        if pack_slug:
            packs = BlueprintPack.objects.filter(slug=pack_slug, is_active=True)
        else:
            packs = BlueprintPack.objects.filter(is_active=True).order_by(
                "category", "name"
            )

        if not packs.exists():
            self.stdout.write(self.style.WARNING("No matching BlueprintPack(s) found."))
            return

        total_updated = 0
        for pack in packs:
            schools = pack.get_schools_needing_update()
            count = schools.count()
            if count == 0:
                continue
            if dry_run:
                self.stdout.write(
                    self.style.NOTICE(
                        f"Pack {pack.slug} (v{pack.version}): {count} school(s) would be updated: "
                        f"{list(schools.values_list('id', flat=True)[:10])}{'...' if count > 10 else ''}"
                    )
                )
                total_updated += count
                continue
            result = update_bundle_for_schools(pack, applied_by=None)
            total_updated += len(result)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Pack {pack.slug} (v{pack.version}): updated {len(result)} school(s)."
                )
            )

        if dry_run:
            self.stdout.write(
                self.style.NOTICE(
                    f"Dry run: {total_updated} school(s) would be updated."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Done. Total schools updated: {total_updated}.")
            )
