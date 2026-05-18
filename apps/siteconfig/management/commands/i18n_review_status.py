"""Report per-locale translation coverage AND native-speaker review state.

  python manage.py i18n_review_status                    # human-readable table
  python manage.py i18n_review_status --json             # machine-readable JSON
  python manage.py i18n_review_status --strict           # exit 1 if any non-stub locale < 50% translated
  python manage.py i18n_review_status --mark-reviewed fr --reviewer "<name>" --notes "<short>"
                                                         # flip a locale to production-ready

The review-status SOT lives at ``var/i18n-review-status.json`` (one entry per
locale: kind, reviewer, reviewed_at, notes). The coverage data is computed
fresh from the .po files on every run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


REVIEW_STATUS_PATH = "var/i18n-review-status.json"


def _to_locale_dir(code: str) -> str:
    if "-" not in code:
        return code
    lang, _, region = code.partition("-")
    return f"{lang}_{region.upper()}"


def _load_review_status(base_dir: Path) -> dict:
    path = base_dir / REVIEW_STATUS_PATH
    if not path.is_file():
        return {"locales": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"locales": {}}


def _save_review_status(base_dir: Path, payload: dict) -> None:
    path = base_dir / REVIEW_STATUS_PATH
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


class Command(BaseCommand):
    help = "Report per-locale translation coverage + native-speaker review state."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit 1 when any non-stub locale is below the threshold.",
        )
        parser.add_argument(
            "--threshold",
            type=float,
            default=50.0,
            help="Strict threshold (percent). Default 50. Stub locales are exempt.",
        )
        parser.add_argument(
            "--mark-reviewed",
            metavar="LOCALE",
            help="Mark a locale as production-ready (requires --reviewer; --notes optional).",
        )
        parser.add_argument(
            "--reviewer",
            help="Native-speaker reviewer name (required with --mark-reviewed).",
        )
        parser.add_argument(
            "--notes",
            default="",
            help="Optional review notes — written verbatim into var/i18n-review-status.json.",
        )

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)

        # --mark-reviewed mode: write-side, then return.
        if options.get("mark_reviewed"):
            return self._handle_mark_reviewed(base, options)

        # Read-side: compute coverage + join to review-status.
        locale_root = base / "locale"
        status = _load_review_status(base)
        status_by_code = (status or {}).get("locales", {}) or {}

        results = []
        for code, name in settings.LANGUAGES:
            lc_dir = locale_root / _to_locale_dir(code) / "LC_MESSAGES"
            po_path = lc_dir / "django.po"
            mo_path = lc_dir / "django.mo"
            entry = status_by_code.get(code, {})
            review_status = entry.get("review_status", "unreviewed")
            if not po_path.is_file():
                results.append(
                    {
                        "code": code,
                        "name": name,
                        "total": 0,
                        "translated": 0,
                        "fuzzy": 0,
                        "percent": 0.0,
                        "po": False,
                        "mo": False,
                        "last_translator": "(none)",
                        "review_status": review_status,
                        "kind": entry.get("kind", "unknown"),
                        "reviewer": entry.get("reviewer"),
                        "reviewed_at": entry.get("reviewed_at"),
                    }
                )
                continue
            po = polib.pofile(str(po_path))
            total = sum(1 for e in po if e.msgid and not e.obsolete)
            translated = sum(1 for e in po if e.msgid and e.msgstr and not e.obsolete)
            fuzzy = sum(1 for e in po if "fuzzy" in (e.flags or []))
            pct = (translated / total * 100.0) if total else 0.0
            results.append(
                {
                    "code": code,
                    "name": name,
                    "total": total,
                    "translated": translated,
                    "fuzzy": fuzzy,
                    "percent": round(pct, 1),
                    "po": True,
                    "mo": mo_path.is_file(),
                    "last_translator": (po.metadata or {}).get("Last-Translator", "(unset)"),
                    "review_status": review_status,
                    "kind": entry.get("kind", "unknown"),
                    "reviewer": entry.get("reviewer"),
                    "reviewed_at": entry.get("reviewed_at"),
                }
            )

        if options["as_json"]:
            self.stdout.write(json.dumps({"locales": results}, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(
                self.style.HTTP_INFO(
                    "Locale  Trans/Total  %       Review-Status         Kind                              Reviewer"
                )
            )
            self.stdout.write(
                self.style.HTTP_INFO(
                    "------  -----------  ------  --------------------  --------------------------------  ----------------"
                )
            )
            for r in results:
                pct = f"{r['percent']:>5.1f}"
                rs = r["review_status"]
                kind = r.get("kind", "")
                reviewer = r.get("reviewer") or "—"
                self.stdout.write(
                    f"{r['code']:<7} {r['translated']:>5}/{r['total']:<5}  {pct}%  {rs:<20}  {kind:<32}  {reviewer}"
                )

        if options["strict"]:
            threshold = float(options["threshold"])
            problem = [
                r
                for r in results
                if r["po"]
                and 0 < r["total"]
                and r["percent"] < threshold
                and r["code"] != "en"
                and r.get("review_status") != "stub"
            ]
            if problem:
                self.stdout.write(
                    self.style.ERROR(
                        f"\nSTRICT: {len(problem)} non-stub locale(s) below {threshold:.0f}% translation: "
                        + ", ".join(r["code"] for r in problem)
                    )
                )
                raise SystemExit(1)
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSTRICT: all non-stub non-en locales >= {threshold:.0f}% translated."
                )
            )

    def _handle_mark_reviewed(self, base: Path, options: dict) -> None:
        code = options["mark_reviewed"]
        reviewer = options.get("reviewer")
        notes = (options.get("notes") or "").strip()
        if not reviewer:
            raise CommandError("--mark-reviewed requires --reviewer \"<name>\"")

        status = _load_review_status(base)
        locales = status.setdefault("locales", {})
        if code not in locales:
            raise CommandError(
                f"locale {code!r} not in {REVIEW_STATUS_PATH}. "
                f"Add it to settings.LANGUAGES + seed an entry first."
            )
        entry = locales[code]
        entry["review_status"] = "production-ready"
        entry["kind"] = "native-reviewed"
        entry["reviewer"] = reviewer
        entry["reviewed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if notes:
            entry["notes"] = notes

        _save_review_status(base, status)
        self.stdout.write(
            self.style.SUCCESS(
                f"marked {code} as production-ready (reviewer={reviewer}). "
                f"Wrote {REVIEW_STATUS_PATH}."
            )
        )
