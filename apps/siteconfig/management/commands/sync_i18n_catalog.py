"""
Merge translatable strings into locale/*/LC_MESSAGES/django.po without GNU gettext.

  python manage.py sync_i18n_catalog
  python manage.py sync_i18n_catalog --dry-run
  python manage.py sync_i18n_catalog --compile

See apps.siteconfig.i18n_catalog_builder for extraction rules.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.siteconfig.i18n_catalog_builder import run_sync


class Command(BaseCommand):
    help = "Scan templates and Python for translatable strings and merge into django.po for all LANGUAGES."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report counts only; do not write .po/.mo files.",
        )
        parser.add_argument(
            "--compile",
            action="store_true",
            dest="compile_mo",
            help="Also write django.mo via polib (no msgfmt required).",
        )
        parser.add_argument(
            "--prune-stale",
            action="store_true",
            help="Remove django.po entries whose msgid no longer appears in the scan (destructive; translators review).",
        )

    def handle(self, *args, **options):
        base = settings.BASE_DIR
        langs = list(settings.LANGUAGES)
        discovered, added, pruned = run_sync(
            base_dir=base,
            languages=langs,
            dry_run=options["dry_run"],
            compile_mo=options["compile_mo"],
            prune_stale=options["prune_stale"],
        )
        self.stdout.write(f"Discovered {len(discovered)} unique msgids.")
        for code, n in sorted(added.items()):
            self.stdout.write(
                f"  {code}: +{n} new entries" + (" (dry-run)" if options["dry_run"] else "")
            )
        if options["prune_stale"]:
            for code, n in sorted(pruned.items()):
                if n:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  {code}: −{n} pruned stale entries"
                            + (" (dry-run)" if options["dry_run"] else "")
                        )
                    )
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry-run: no files written."))
        elif options["compile_mo"]:
            self.stdout.write(self.style.SUCCESS("Wrote django.mo where entries were merged."))
