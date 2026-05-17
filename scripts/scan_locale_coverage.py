#!/usr/bin/env python
"""Locale catalog coverage scanner.

Seven-pillar audit P11 follow-up. RunMyCampus ships 17 locales managed
by [`apps/siteconfig/i18n_catalog_builder.py`](../apps/siteconfig/i18n_catalog_builder.py)
and synced via `python manage.py sync_i18n_catalog --compile`.

The existing `verify_i18n_catalog_fresh.py` asserts that .po files are
in lock-step with the canonical msgid set. This complementary gate
reports **translation coverage** — for each locale, the fraction of
msgids that have a non-empty msgstr — so the operator and CI can see
which locales need translator attention without opening every .po file.

It is intentionally **drift-detection only**, never zero-tolerance:
stub locales (yo, ha, sw, pid, fr per memory v3.11) ship with msgstr=""
and fall back to English. A regression is "a locale that USED to have
coverage drops back to 0 strings."

Usage:
    python scripts/scan_locale_coverage.py             # write baseline
    python scripts/scan_locale_coverage.py --compare   # diff vs baseline (CI)
    python scripts/scan_locale_coverage.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCALE_ROOT = REPO_ROOT / "locale"
BASELINE_PATH = (
    REPO_ROOT / "var" / "security-audit-baseline-locale-coverage.json"
)

# Locales the registry says we ship. Keeping this hard-coded mirrors the
# `LANGUAGES` tuple in config/settings.py at the time of writing
# (memory v3.13). Drift detection will flag a locale's coverage change,
# not new locales — operators add new dirs and re-baseline.
EXPECTED_LOCALES = (
    "en", "ar", "de", "es", "fr", "ha", "hi", "it", "ja",
    "pid", "pt_BR", "ru", "sw", "tr", "yo", "zh_Hans", "zh_Hant",
)

# Match a `msgstr "..."`. Multi-line msgstr blocks (the standard PO
# format) start with `msgstr ""` followed by `"..."` continuation lines.
_MSGID_RE = re.compile(r'^msgid\s+"(.*)"$')
_MSGSTR_RE = re.compile(r'^msgstr\s+"(.*)"$')
_CONT_RE = re.compile(r'^"(.*)"$')


@dataclass
class LocaleStats:
    locale: str
    po_path: str
    total: int
    translated: int
    empty: int
    coverage_pct: float
    plural_msgids: int = 0
    plural_incomplete: int = 0


_MSGID_PLURAL_RE = re.compile(r'^msgid_plural\s+"(.*)"$')
_MSGSTR_INDEXED_RE = re.compile(r'^msgstr\[(?P<idx>\d+)\]\s+"(.*)"$')


def _read_po(path: Path) -> tuple[int, int, int, int, int]:
    """Return ``(total, translated, empty, plural_msgids, plural_incomplete)``.

    * ``total`` / ``translated`` / ``empty`` — singular msgid coverage.
    * ``plural_msgids`` — count of entries that have a ``msgid_plural``.
    * ``plural_incomplete`` — plural entries where at least one
      ``msgstr[N]`` form is empty (P11 plural-form audit, P11 follow-up).
    """
    if not path.exists():
        return 0, 0, 0, 0, 0
    text = path.read_text(encoding="utf-8", errors="replace")
    total = 0
    translated = 0
    empty = 0
    plural_msgids = 0
    plural_incomplete = 0
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m_id = _MSGID_RE.match(line)
        if m_id is None:
            i += 1
            continue
        # Collect msgid body (with continuation).
        msgid_value = m_id.group(1)
        j = i + 1
        while j < len(lines) and (cont := _CONT_RE.match(lines[j].strip())):
            msgid_value += cont.group(1)
            j += 1
        # Optional msgid_plural follows immediately after.
        has_plural = False
        if j < len(lines) and _MSGID_PLURAL_RE.match(lines[j].strip()):
            has_plural = True
            j += 1
            while j < len(lines) and (cont := _CONT_RE.match(lines[j].strip())):
                j += 1
        # Walk to the matching msgstr (or msgstr[N]).
        while (
            j < len(lines)
            and not _MSGSTR_RE.match(lines[j].strip())
            and not _MSGSTR_INDEXED_RE.match(lines[j].strip())
        ):
            j += 1
        if j >= len(lines):
            break
        # Skip header pseudo-entry (msgid "" + metadata in msgstr).
        if msgid_value == "" and not has_plural:
            # Walk past msgstr block.
            m_str = _MSGSTR_RE.match(lines[j].strip())
            j += 1
            while j < len(lines) and (cont := _CONT_RE.match(lines[j].strip())):
                j += 1
            i = j
            continue
        if has_plural:
            # Plural entry: collect every msgstr[N] form.
            plural_msgids += 1
            forms_present: dict[int, bool] = {}
            while j < len(lines):
                line_strip = lines[j].strip()
                m_idx = _MSGSTR_INDEXED_RE.match(line_strip)
                if not m_idx:
                    break
                idx = int(m_idx.group("idx"))
                form_value = m_idx.group(2)
                j += 1
                while j < len(lines) and (cont := _CONT_RE.match(lines[j].strip())):
                    form_value += cont.group(1)
                    j += 1
                forms_present[idx] = bool(form_value)
            # We count the entry as a singular for the total/translated
            # bucket via the first form (idx=0) so legacy counts continue
            # to make sense; plural completeness is its own metric.
            total += 1
            if forms_present.get(0):
                translated += 1
            else:
                empty += 1
            if not all(forms_present.values()) or not forms_present:
                plural_incomplete += 1
            i = j
            continue
        # Singular path.
        m_str = _MSGSTR_RE.match(lines[j].strip())
        msgstr_value = m_str.group(1) if m_str else ""
        j += 1
        while j < len(lines) and (cont := _CONT_RE.match(lines[j].strip())):
            msgstr_value += cont.group(1)
            j += 1
        total += 1
        if msgstr_value:
            translated += 1
        else:
            empty += 1
        i = j
    return total, translated, empty, plural_msgids, plural_incomplete


def _scan() -> list[LocaleStats]:
    stats: list[LocaleStats] = []
    for locale in EXPECTED_LOCALES:
        po = LOCALE_ROOT / locale / "LC_MESSAGES" / "django.po"
        total, translated, empty, plural_msgids, plural_incomplete = _read_po(po)
        pct = (100.0 * translated / total) if total else 0.0
        stats.append(LocaleStats(
            locale=locale,
            po_path=po.relative_to(REPO_ROOT).as_posix(),
            total=total,
            translated=translated,
            empty=empty,
            coverage_pct=round(pct, 1),
            plural_msgids=plural_msgids,
            plural_incomplete=plural_incomplete,
        ))
    return stats


def _baseline_payload(stats: list[LocaleStats]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "track per-locale msgstr coverage; drift-detection only "
            "(stub locales ship empty and fall back to English)"
        ),
        "locale_root": LOCALE_ROOT.relative_to(REPO_ROOT).as_posix(),
        "expected_locales": list(EXPECTED_LOCALES),
        "finding_count": len(stats),  # one per locale; keeps shape consistent
        "findings": [asdict(s) for s in stats],
    }


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _print_summary(stats: list[LocaleStats]) -> None:
    print(f"locale coverage: {len(stats)} locale(s)")
    for s in stats:
        bar = "[OK ]" if s.translated > 0 else "[stub]"
        plural_note = (
            f"  plural={s.plural_incomplete}/{s.plural_msgids} incomplete"
            if s.plural_msgids else ""
        )
        print(
            f"  {bar} {s.locale:8s} {s.translated:5d}/{s.total:5d} "
            f"({s.coverage_pct:5.1f}%){plural_note}  {s.po_path}"
        )


def _write_baseline(stats: list[LocaleStats]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(stats), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _compare(stats: list[LocaleStats]) -> int:
    baseline = _load_baseline()
    if baseline is None:
        _print_summary(stats)
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 0
    by_locale_now = {s.locale: s.translated for s in stats}
    by_locale_baseline = {
        item["locale"]: item["translated"]
        for item in baseline.get("findings", [])
    }
    regressions: list[str] = []
    for locale, base in by_locale_baseline.items():
        cur = by_locale_now.get(locale, 0)
        if base > 0 and cur < base:
            regressions.append(
                f"{locale}: translated dropped {base} -> {cur}"
            )
    _print_summary(stats)
    if regressions:
        print("\nREGRESSIONS:")
        for line in regressions:
            print(f"  - {line}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    stats = _scan()
    if args.json:
        print(json.dumps(_baseline_payload(stats), indent=2, sort_keys=True))
        return 0
    if args.compare:
        return _compare(stats)
    _print_summary(stats)
    _write_baseline(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
