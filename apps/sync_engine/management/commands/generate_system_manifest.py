"""Write this deployment's ``system_manifest.json``.

Run at IMAGE BUILD TIME on the operator deployment (the same layer that runs
``collectstatic`` and ``write_build_stamp.py``), so the manifest describes the tree that
was actually shipped. Running it later, on a box, is also valid and is how an appliance
records what it is currently made of.

    python manage.py generate_system_manifest
    python manage.py generate_system_manifest --check     # CI: is the committed one current?
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.sync_engine.system_manifest import (
    SystemManifestGenerator,
    load_manifest,
    manifest_path,
)


class Command(BaseCommand):
    help = "Generate system_manifest.json (SHA-256 of every shippable file + migration heads)."

    def add_arguments(self, parser):
        parser.add_argument("--root", default="", help="Tree to crawl (default: BASE_DIR).")
        parser.add_argument("--out", default="", help="Where to write (default: <root>/system_manifest.json).")
        parser.add_argument("--version-label", default="", help="Human label, e.g. 2026.08.22-b.")
        parser.add_argument("--channel", default="stable", help="stable | beta | custom-tier.")
        parser.add_argument("--include-tests", action="store_true", help="Also hash the test suite.")
        parser.add_argument(
            "--check",
            action="store_true",
            help="Do not write; exit non-zero when the on-disk manifest is stale.",
        )

    def handle(self, *args, **options):
        root = Path(options["root"]) if options["root"] else Path(str(settings.BASE_DIR))
        generator = SystemManifestGenerator(
            root=root,
            include_tests=bool(options["include_tests"]),
            version_label=options["version_label"],
            channel=options["channel"],
        )

        if options["check"]:
            current = generator.digest()
            on_disk = str((load_manifest(options["out"] or None) or {}).get("manifest_hash") or "")
            if not on_disk:
                raise CommandError(
                    f"no manifest at {options['out'] or manifest_path()} — run this command without --check"
                )
            if on_disk != current:
                raise CommandError(
                    f"system_manifest.json is STALE: on disk {on_disk[:12]}, tree hashes to {current[:12]}"
                )
            self.stdout.write(self.style.SUCCESS(f"manifest current ({current[:12]})"))
            return

        written = generator.write(options["out"] or None)
        payload = load_manifest(written)
        counts = ", ".join(f"{k}={v}" for k, v in (payload.get("counts_by_category") or {}).items())
        self.stdout.write(
            self.style.SUCCESS(
                f"wrote {written}\n"
                f"  hash    {payload.get('manifest_hash', '')[:12]}\n"
                f"  version {payload.get('version_label', '')} ({payload.get('channel', '')})\n"
                f"  files   {payload.get('file_count', 0)} ({counts})\n"
                f"  bytes   {payload.get('total_bytes', 0)}"
            )
        )
