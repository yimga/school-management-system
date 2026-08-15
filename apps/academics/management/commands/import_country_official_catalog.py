"""Import country OFFICIAL catalogs (real subject codes + term windows) into the
region-shared ``EducationSystemProfile.config`` — pure data population, no deploy.

This is the operator/ministry pump for the override layer that
``resolve_subject_code`` / ``resolve_term_windows`` already read: a country's real
ministry/board data lives in one JSON file, this loads it into the shared country
profile, and every school in that country inherits it — no code change.

Idempotent and additive (config keys a catalog does not mention are preserved).

Usage::

    manage.py import_country_official_catalog                 # shipped catalogs
    manage.py import_country_official_catalog --file path/KE.json
    manage.py import_country_official_catalog --dir path/to/catalogs/
    manage.py import_country_official_catalog --dry-run       # report only
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Import country official catalogs into region-shared education profiles (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", dest="file", default=None,
            help="Import a single catalog JSON file.",
        )
        parser.add_argument(
            "--dir", dest="dir", default=None,
            help="Import every *.json catalog in a directory (default: the shipped set).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would change; write nothing.",
        )

    def handle(self, *args, **opts):
        from apps.academics.official_catalog import (
            DEFAULT_CATALOG_DIR,
            OfficialCatalogError,
            import_catalog,
            iter_catalog_files,
            load_catalog_file,
        )

        dry = opts["dry_run"]
        if opts["file"]:
            paths = [opts["file"]]
        else:
            directory = opts["dir"] or DEFAULT_CATALOG_DIR
            paths = list(iter_catalog_files(directory))
            if not paths:
                raise CommandError(f"No *.json catalogs found in {directory}")

        applied = unchanged = skipped = failed = 0
        for path in paths:
            try:
                parsed = load_catalog_file(path)
                summary = import_catalog(parsed, dry_run=dry)
            except OfficialCatalogError as exc:
                failed += 1
                self.stderr.write(f"FAIL  {path}: {exc}")
                continue
            status = str(summary.get("status", ""))
            if status in ("applied", "dry-run"):
                applied += 1
            elif status == "unchanged":
                unchanged += 1
            else:
                skipped += 1
            self.stdout.write(
                f"{status.upper():9} {summary.get('country')}  "
                f"subjects+{summary.get('subject_codes_changed', 0)} "
                f"terms+{summary.get('term_windows_changed', 0)}  "
                f"[{summary.get('source', '')}]"
            )

        tail = "Dry run — nothing written." if dry else "Import complete."
        self.stdout.write(
            self.style.SUCCESS(
                f"{tail} {applied} applied, {unchanged} unchanged, "
                f"{skipped} skipped, {failed} failed."
            )
        )
