"""Export a country's curated defaults to an EDITABLE official-catalog template.

The other end of the demand-driven loop from ``import_country_official_catalog``:
this writes out a pre-filled, honestly-noted catalog file (the real subject
taxonomy + representative windows) so onboarding a country's real data is
export -> fill in official values -> import, never starting from a blank file.

Usage::

    manage.py export_country_catalog_template --country CM            # -> stdout
    manage.py export_country_catalog_template --country CM --out CM.json
    manage.py export_country_catalog_template --all --out-dir templates/
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Export curated country defaults to an editable official-catalog template."

    def add_arguments(self, parser):
        parser.add_argument("--country", dest="country", default=None, help="ISO alpha-2/3 country code.")
        parser.add_argument(
            "--all", action="store_true",
            help="Export every country that has curated data (needs --out-dir).",
        )
        parser.add_argument(
            "--out", dest="out", default=None,
            help="Output file for a single country ('-' or omit = stdout).",
        )
        parser.add_argument(
            "--out-dir", dest="out_dir", default=None,
            help="Output directory for --all: one <ISO>.json per country.",
        )

    def handle(self, *args, **opts):
        from apps.academics.official_catalog import (
            OfficialCatalogError,
            build_catalog_template,
            curated_countries,
            serialize_catalog,
        )

        if opts["all"]:
            if not opts["out_dir"]:
                raise CommandError("--all requires --out-dir <dir>")
            out_dir = Path(opts["out_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            written = 0
            for iso in curated_countries():
                try:
                    template = build_catalog_template(iso)
                except OfficialCatalogError:
                    continue
                (out_dir / f"{iso}.json").write_text(serialize_catalog(template), encoding="utf-8")
                written += 1
            self.stdout.write(self.style.SUCCESS(f"Wrote {written} catalog template(s) to {out_dir}"))
            return

        if not opts["country"]:
            raise CommandError("give --country <ISO> (or --all --out-dir <dir>)")
        try:
            template = build_catalog_template(opts["country"])
        except OfficialCatalogError as exc:
            raise CommandError(str(exc))

        text = serialize_catalog(template)
        out = opts["out"]
        if not out or out == "-":
            self.stdout.write(text)
        else:
            p = Path(out)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Wrote {p}"))
