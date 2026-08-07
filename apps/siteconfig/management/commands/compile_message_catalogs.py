"""Compile the Django gettext catalogs (locale/*/LC_MESSAGES/*.po -> *.mo).

Django's ``compilemessages`` shells out to GNU gettext's ``msgfmt``, which is NOT
installed on this build host (or in CI). This command compiles every ``.po`` with
polib (pure Python) instead, so a translation committed to a ``.po`` actually
reaches users after deploy — previously the deploy ran only ``collectstatic`` and
served whatever stale ``.mo`` happened to be committed.

Idempotent; safe to run on every build. Wired into ``build.sh`` before
``collectstatic``.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Compile all locale/*/LC_MESSAGES/*.po files to .mo using polib."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Report which .mo files are missing/stale without writing them.",
        )

    def handle(self, *args, **options):
        try:
            import polib
        except ImportError:
            self.stderr.write(
                "polib is not installed; cannot compile message catalogs. "
                "Add polib to requirements.txt."
            )
            return

        locale_paths = list(getattr(settings, "LOCALE_PATHS", []) or [])
        if not locale_paths:
            # Fall back to the conventional project-root locale/ directory.
            locale_paths = [Path(settings.BASE_DIR) / "locale"]

        check_only = bool(options.get("check"))
        compiled = 0
        stale = 0
        failed = 0
        for base in locale_paths:
            base = Path(base)
            if not base.exists():
                continue
            for po_path in sorted(base.glob("*/LC_MESSAGES/*.po")):
                mo_path = po_path.with_suffix(".mo")
                is_stale = (
                    not mo_path.exists()
                    or mo_path.stat().st_mtime < po_path.stat().st_mtime
                )
                if check_only:
                    if is_stale:
                        stale += 1
                        self.stdout.write(f"  stale: {po_path}")
                    continue
                try:
                    po = polib.pofile(str(po_path))
                    po.save_as_mofile(str(mo_path))
                    compiled += 1
                except (OSError, ValueError) as exc:
                    failed += 1
                    self.stderr.write(f"  FAILED {po_path}: {exc}")

        if check_only:
            self.stdout.write(f"message catalogs: {stale} stale .mo file(s)")
            return
        summary = f"Compiled {compiled} catalog(s)"
        if failed:
            summary += f", {failed} failed"
        self.stdout.write(self.style.SUCCESS(summary))
