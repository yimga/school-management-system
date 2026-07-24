"""Generate the ``en_XA`` pseudo-locale catalog for i18n QA.

Reads the source catalog ``locale/en/LC_MESSAGES/django.po`` and writes
``locale/en_XA/LC_MESSAGES/django.po`` where every ``msgstr`` is the pseudo-localized
form of its ``msgid`` (accented, bracketed, ~40% longer) with interpolation and
markup tokens preserved verbatim. See ``scripts/pseudo_locale_transform.py`` for the
transform and ``scripts/verify_pseudo_locale.py`` for the CI safety gate.

The catalog is a QA artifact — it is git-ignored (``locale/en_XA/``) and never
shipped. To eyeball-QA a running server:

  RMC_ENABLE_PSEUDO_LOCALE=1 python manage.py generate_pseudo_locale --compile
  # then add ("en-xa", "Pseudo (QA)") to settings.LANGUAGES behind that flag
  # (deferred while config/settings.py has in-flight edits) and switch language.

Anything that renders as plain English under en-xa is a hardcoded (untranslated)
string; anything that overflows its container is a layout-fragility bug.
"""

from __future__ import annotations

import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# Single source of truth for the transform lives in scripts/ (dependency-free so
# the CI gate can share it); make it importable from the Django process.
sys.path.insert(0, str(Path(settings.BASE_DIR) / "scripts"))
from pseudo_locale_transform import pseudofy  # noqa: E402

PSEUDO_CODE = "en_XA"


class Command(BaseCommand):
    help = "Generate the en_XA pseudo-locale catalog from locale/en for i18n QA."

    def add_arguments(self, parser):
        parser.add_argument(
            "--compile",
            action="store_true",
            dest="compile_mo",
            help="Also write django.mo via polib (so runserver picks it up without msgfmt).",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Report what would be written without touching disk.",
        )

    def handle(self, *args, **options):
        try:
            import polib
        except ImportError as exc:  # pragma: no cover - polib is a project dep
            raise CommandError("polib is required (pip install polib).") from exc

        base = Path(settings.BASE_DIR)
        src_path = base / "locale" / "en" / "LC_MESSAGES" / "django.po"
        if not src_path.exists():
            raise CommandError(f"Source catalog not found: {src_path}")

        src = polib.pofile(str(src_path))
        out = polib.POFile()
        out.metadata = dict(src.metadata)
        out.metadata["Language"] = "en_XA"
        out.metadata["X-Pseudo-Locale"] = "generated-do-not-ship"

        entries = 0
        for entry in src:
            if not entry.msgid:
                continue
            new = polib.POEntry(
                msgid=entry.msgid,
                occurrences=list(entry.occurrences),
                flags=[f for f in entry.flags if f != "fuzzy"],
            )
            if entry.msgid_plural:
                new.msgid_plural = entry.msgid_plural
                new.msgstr_plural = {
                    0: pseudofy(entry.msgid),
                    1: pseudofy(entry.msgid_plural),
                }
            else:
                new.msgstr = pseudofy(entry.msgid)
            out.append(new)
            entries += 1

        if options["check"]:
            self.stdout.write(
                f"[check] would write {entries} pseudo entries to "
                f"locale/{PSEUDO_CODE}/LC_MESSAGES/django.po"
            )
            return

        dest_dir = base / "locale" / PSEUDO_CODE / "LC_MESSAGES"
        dest_dir.mkdir(parents=True, exist_ok=True)
        po_path = dest_dir / "django.po"
        out.save(str(po_path))
        written = [po_path]
        if options["compile_mo"]:
            mo_path = dest_dir / "django.mo"
            out.save_as_mofile(str(mo_path))
            written.append(mo_path)

        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {entries} pseudo entries -> "
                + ", ".join(str(p.relative_to(base)) for p in written)
            )
        )
