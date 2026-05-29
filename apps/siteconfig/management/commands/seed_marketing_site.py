"""
Seed the public marketing site end-to-end (DB CMS + config/marketing_content JSON).

Idempotent. Run:

    python manage.py seed_marketing_site

Includes French marketing `.po` strings, loop-asset verification, and CMS/JSON sync.
Included in ``bootstrap_platform_catalog --all`` (replaces bare ``seed_marketing_cms``).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.schools.marketing_content_seed import sync_marketing_content_json_files


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _run_script(command: BaseCommand, rel: str, *, label: str) -> None:
    script = _repo_root() / rel
    if not script.is_file():
        raise CommandError(f"{label}: script missing at {script}")
    command.stdout.write(f"{label} …")
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=_repo_root(),
        check=False,
    )
    if proc.returncode != 0:
        raise CommandError(f"{label} failed (exit {proc.returncode})")


class Command(BaseCommand):
    help = (
        "Seed marketing site: CMS, marketing_content JSON, French translations, "
        "and loop asset verification."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-cms",
            action="store_true",
            help="Skip seed_marketing_cms (DB blog posts and CMS keys).",
        )
        parser.add_argument(
            "--skip-json",
            action="store_true",
            help="Skip writing config/marketing_content/*.json files.",
        )
        parser.add_argument(
            "--force-json",
            action="store_true",
            help="Overwrite existing marketing_content JSON files from definitions.",
        )
        parser.add_argument(
            "--skip-loops",
            action="store_true",
            help="Skip ensure_marketing_loops.py (committed loop binary verification).",
        )
        parser.add_argument(
            "--skip-fr-translations",
            action="store_true",
            help="Skip scripts/seed_french_marketing_translations.py.",
        )
        parser.add_argument(
            "--skip-compile-fr",
            action="store_true",
            help="Skip compilemessages for fr after French seed.",
        )

    def handle(self, *args, **options):
        if not options["skip_cms"]:
            self.stdout.write("Running seed_marketing_cms …")
            call_command("seed_marketing_cms", verbosity=options["verbosity"])

        if not options["skip_json"]:
            self.stdout.write("Syncing config/marketing_content/*.json …")
            written, skipped = sync_marketing_content_json_files(
                force=options["force_json"]
            )
            self.stdout.write(
                f"  marketing_content JSON: {written} written, {skipped} already present"
            )

        if not options["skip_fr_translations"]:
            _run_script(
                self,
                "scripts/seed_french_marketing_translations.py",
                label="Seeding French marketing translations",
            )
            _run_script(
                self,
                "scripts/generate_french_marketing_review_packet.py",
                label="Generating French native-review packet",
            )
            from apps.schools.marketing_i18n_gate import sync_french_review_status_in_ledger

            if sync_french_review_status_in_ledger():
                self.stdout.write("  i18n-review-status.json fr entry refreshed")
            if not options["skip_compile_fr"]:
                try:
                    call_command("compilemessages", locale=["fr"], verbosity=0)
                    self.stdout.write("  compilemessages fr: OK")
                except CommandError as exc:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  compilemessages fr skipped ({exc}); run sync_i18n_catalog --compile"
                        )
                    )

        if not options["skip_loops"]:
            _run_script(
                self,
                "scripts/ensure_marketing_loops.py",
                label="Verifying committed marketing loop assets",
            )

        self.stdout.write(
            self.style.SUCCESS("seed_marketing_site: marketing site seed complete.")
        )
