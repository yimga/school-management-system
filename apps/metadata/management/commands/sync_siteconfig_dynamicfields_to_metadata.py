"""Copy legacy siteconfig DynamicField* rows into metadata.* (idempotent)."""

from django.core.management.base import BaseCommand, CommandError

from apps.metadata.siteconfig_dynamicfield_sync import run_full_sync


class Command(BaseCommand):
    help = (
        "Sync siteconfig_dynamicfield* definitions and values into metadata.* "
        "(Batch 14). Use --dry-run to preview counts."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do not write; report row counts only.",
        )
        parser.add_argument(
            "--definitions-only",
            action="store_true",
            help="Sync DynamicFieldDefinition only.",
        )
        parser.add_argument(
            "--values-only",
            action="store_true",
            help="Sync DynamicFieldValue only (definitions should exist for type map).",
        )

    def handle(self, *args, **options):
        dry = bool(options["dry_run"])
        defs = not options["values_only"]
        vals = not options["definitions_only"]
        if options["definitions_only"] and options["values_only"]:
            raise CommandError(
                "Cannot pass both --definitions-only and --values-only."
            )

        stats = run_full_sync(dry_run=dry, definitions=defs, values=vals)
        mode = "DRY-RUN" if dry else "APPLY"
        self.stdout.write(f"[{mode}] siteconfig → metadata DynamicField sync\n")
        if defs:
            self.stdout.write(
                f"  Definitions: rows_seen={stats.definition_rows_seen} "
                f"upserted={stats.definitions_upserted}\n"
            )
        if vals:
            self.stdout.write(
                f"  Values: rows_seen={stats.value_rows_seen} "
                f"upserted={stats.values_upserted}\n"
            )
        for w in stats.warnings[:50]:
            self.stdout.write(self.style.WARNING(f"  WARN: {w}\n"))
        if not stats.warnings and not dry:
            self.stdout.write(
                "  Note: legacy siteconfig DynamicField* EAV retired (siteconfig.0168); "
                "sync is a documented no-op on current releases.\n"
            )
