"""Report per-locale translation coverage so operators can see at a glance
where catalogs need native-speaker review.

  python manage.py i18n_review_status            # human-readable table
  python manage.py i18n_review_status --json     # machine-readable JSON
  python manage.py i18n_review_status --strict   # exit 1 if any locale < 50% translated
"""

from __future__ import annotations

import json
from pathlib import Path

import polib
from django.conf import settings
from django.core.management.base import BaseCommand


def _to_locale_dir(code: str) -> str:
    if "-" not in code:
        return code
    lang, _, region = code.partition("-")
    return f"{lang}_{region.upper()}"


class Command(BaseCommand):
    help = "Report per-locale translation coverage for the marketing surface."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
        parser.add_argument("--strict", action="store_true", help="Exit 1 when any non-stub locale below 50%% translated.")
        parser.add_argument("--threshold", type=float, default=50.0, help="Strict threshold (percent). Default 50.")

    def handle(self, *args, **options):
        base = settings.BASE_DIR
        locale_root = Path(base) / "locale"
        results = []
        for code, name in settings.LANGUAGES:
            lc_dir = locale_root / _to_locale_dir(code) / "LC_MESSAGES"
            po_path = lc_dir / "django.po"
            mo_path = lc_dir / "django.mo"
            if not po_path.is_file():
                results.append({
                    "code": code, "name": name,
                    "total": 0, "translated": 0, "fuzzy": 0,
                    "percent": 0.0, "po": False, "mo": False,
                    "last_translator": "(none)",
                })
                continue
            po = polib.pofile(str(po_path))
            total = sum(1 for e in po if e.msgid and not e.obsolete)
            translated = sum(1 for e in po if e.msgid and e.msgstr and not e.obsolete)
            fuzzy = sum(1 for e in po if "fuzzy" in (e.flags or []))
            pct = (translated / total * 100.0) if total else 0.0
            results.append({
                "code": code, "name": name,
                "total": total, "translated": translated, "fuzzy": fuzzy,
                "percent": round(pct, 1),
                "po": True, "mo": mo_path.is_file(),
                "last_translator": (po.metadata or {}).get("Last-Translator", "(unset)"),
            })

        if options["as_json"]:
            self.stdout.write(json.dumps({"locales": results}, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(self.style.HTTP_INFO("Locale  Trans/Total  %      MO  Last-Translator"))
            self.stdout.write(self.style.HTTP_INFO("------  -----------  -----  --  ---------------"))
            for r in results:
                pct = f"{r['percent']:>5.1f}"
                mo = "y" if r["mo"] else "n"
                self.stdout.write(
                    f"{r['code']:<7} {r['translated']:>5}/{r['total']:<5}  {pct}%  {mo}   {r['last_translator']}"
                )

        if options["strict"]:
            threshold = float(options["threshold"])
            problem = [r for r in results if r["po"] and 0 < r["total"] and r["percent"] < threshold and r["code"] != "en"]
            if problem:
                self.stdout.write(self.style.ERROR(
                    f"\nSTRICT: {len(problem)} locale(s) below {threshold:.0f}% translation: "
                    + ", ".join(r["code"] for r in problem)
                ))
                raise SystemExit(1)
            self.stdout.write(self.style.SUCCESS(f"\nSTRICT: all non-en locales >= {threshold:.0f}% translated."))
