#!/usr/bin/env python
"""Locale catalog coverage scanner.

Seven-pillar audit P11 follow-up. RunMyCampus ships 20 locales managed
by [`apps/siteconfig/i18n_catalog_builder.py`](../apps/siteconfig/i18n_catalog_builder.py)
and synced via `python manage.py sync_i18n_catalog --compile`.

The existing `verify_i18n_catalog_fresh.py` asserts that .po files are
in lock-step with the canonical msgid set. This complementary gate
reports **translation coverage** — for each locale, the fraction of
msgids that have a non-empty msgstr — so the operator and CI can see
which locales need translator attention without opening every .po file.

ABSOLUTE FLOOR + EXPLICIT DECLARATIONS (2026-07-21)
---------------------------------------------------
This gate used to be **regression-only**. That made it structurally incapable
of failing on the thing that matters: a locale that has *always* been at 0%
never regressed, so it stayed permanently green. On a platform aiming at 250+
countries, a locale gate that cannot notice 0% coverage is decoration.

It now enforces a contract instead of a trend:

  1. **Discovery, not a hard-coded tuple.** Every ``locale/<code>/LC_MESSAGES/
     django.po`` on disk is scanned. The old ``EXPECTED_LOCALES`` tuple was
     itself a blind spot -- ``locale/pt`` ships a tracked catalog and was never
     scanned by this gate at all.
  2. **Every shipping locale must be declared** in ``LOCALE_DECLARATIONS``
     below, with a kind and a written reason. An undeclared locale is a
     finding -- adding ``locale/xx`` with 0 translations turns the gate RED.
  3. **Anything not declared a stub must meet the floor.** ``full`` locales
     must reach ``MINIMUM_COVERAGE_PCT``; the ``source`` locale must reach
     ``SOURCE_MINIMUM_PCT``.
  4. **Declarations cannot rot.** A locale declared ``stub`` that has climbed
     to the floor is a finding: promote it to ``full`` so the floor starts
     protecting it.
  5. The original regression check is retained on top of all of the above.

Stub locales legitimately ship untranslated and fall back to English -- but
they are now *named with a reason each*, not silently tolerated by the absence
of a threshold.

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
# Must match what actually ships (settings.LANGUAGES == 20 codes, and each has a
# locale/<code>/LC_MESSAGES/*.po + compiled .mo). This tuple listed only 17 and
# silently OMITTED the three RTL locales fa / he / ur — so the coverage gate
# skipped catalogs that ship to real tenants. A scanner that quietly ignores
# shipped locales is worse than no scanner: it reports green over a blind spot.
EXPECTED_LOCALES = (
    "en", "ar", "de", "es", "fa", "fr", "ha", "he", "hi", "it", "ja",
    "pid", "pt_BR", "ru", "sw", "tr", "ur", "yo", "zh_Hans", "zh_Hant",
)

# --------------------------------------------------------------------------
# The coverage contract.
#
# MINIMUM_COVERAGE_PCT is the absolute floor for any locale declared ``full``.
# It is the number that makes this gate able to fail; it is deliberately not
# derived from current data, because a floor derived from current data is a
# baseline wearing a floor's clothes.
#
# Every locale that ships a catalog must appear in LOCALE_DECLARATIONS with:
#   kind     -- one of:
#       "source"   the msgid==msgstr identity catalog; must stay ~complete.
#       "full"     claimed as a translated locale; MUST meet the floor.
#       "stub"     deliberately ships below the floor and falls back to
#                  English at runtime. Requires a written reason. If it ever
#                  reaches the floor the declaration is stale and the gate
#                  fails until it is promoted to "full".
#       "unserved" a catalog is tracked on disk but the code is not in
#                  settings.LANGUAGES, so Django never activates it. Reported
#                  as a standing KNOWN GAP on every run.
#   reason   -- why, in words. Not optional; an empty reason is a finding.
# --------------------------------------------------------------------------
MINIMUM_COVERAGE_PCT = 60.0
SOURCE_MINIMUM_PCT = 99.0

_STUB_FIRSTTOUCH_REASON = (
    "AI-drafted first-touch pack shipped (auth / onboarding / portals / "
    "attendance / grades / fees / timetable); the bulk catalog is still "
    "untranslated and falls back to English. NEEDS NATIVE REVIEW before the "
    "coverage claim is production-grade. Promote to 'full' once native review "
    "lands and coverage reaches the floor."
)
_STUB_HUMANONLY_REASON = (
    "HUMAN-ONLY by policy (docs/i18n/TRANSLATION_REQUEST_PACKETS.md): AI drafts "
    "are forbidden for this locale -- a wrong term users accept as canonical is "
    "worse than an English fallback, and some of these languages have no settled "
    "software orthography. A translation-request packet is staged for native "
    "speakers; ships as English fallback until human translation lands. Promote "
    "to 'full' only when a native translator delivers and coverage reaches the "
    "floor. Do NOT AI-draft to raise this number."
)

LOCALE_DECLARATIONS: dict[str, tuple[str, str]] = {
    "en": (
        "source",
        "Source catalog: msgid == msgstr identity. Everything else falls back "
        "to this, so it must stay effectively complete.",
    ),
    # -- AI-drafted first-touch packs (Phases 2-5, 2026-08-14 -> 08-16). ----
    #    LTR locales; fr/es/pt_BR carry added depth (16-20%). ALL still need
    #    NATIVE REVIEW before any 'full' claim -- see _STUB_FIRSTTOUCH_REASON.
    "de": ("stub", _STUB_FIRSTTOUCH_REASON),
    "es": ("stub", _STUB_FIRSTTOUCH_REASON),
    "fr": ("stub", _STUB_FIRSTTOUCH_REASON),
    "hi": ("stub", _STUB_FIRSTTOUCH_REASON),
    "it": ("stub", _STUB_FIRSTTOUCH_REASON),
    "ja": ("stub", _STUB_FIRSTTOUCH_REASON),
    "pt_BR": ("stub", _STUB_FIRSTTOUCH_REASON),
    "ru": ("stub", _STUB_FIRSTTOUCH_REASON),
    "tr": ("stub", _STUB_FIRSTTOUCH_REASON),
    "zh_Hans": ("stub", _STUB_FIRSTTOUCH_REASON),
    "zh_Hant": ("stub", _STUB_FIRSTTOUCH_REASON),
    # -- AI-drafted first-touch packs, RTL (Phases 4-5, 2026-08-15). --------
    "ar": ("stub", _STUB_FIRSTTOUCH_REASON + " RTL locale."),
    "fa": ("stub", _STUB_FIRSTTOUCH_REASON + " RTL locale."),
    "he": ("stub", _STUB_FIRSTTOUCH_REASON + " RTL locale."),
    "ur": ("stub", _STUB_FIRSTTOUCH_REASON + " RTL locale."),
    # -- HUMAN-ONLY by policy: AI drafts forbidden (packets staged). --------
    "ha": ("stub", _STUB_HUMANONLY_REASON),
    "pid": ("stub", _STUB_HUMANONLY_REASON),
    "sw": ("stub", _STUB_HUMANONLY_REASON),
    "yo": ("stub", _STUB_HUMANONLY_REASON),
    # -- tracked but never activated ---------------------------------------
    "pt": (
        "unserved",
        "ORPHANED, pending deletion. settings.LANGUAGES ships 'pt-br' only, so "
        "Django resolves Portuguese to locale/pt_BR and never activates 'pt'. "
        "locale/pt contained exactly the 19 critical-UI msgids and nothing else "
        "-- a catalog whose only purpose was to satisfy "
        "verify_critical_msgid_depth.py, which checked 'pt' and passed while "
        "locale/pt_BR (the catalog users actually get) had 0 of 19 translated. "
        "On 2026-07-21 those 19 strings were merged into pt_BR with pt-BR "
        "orthography and that gate was retargeted to pt_BR, so locale/pt now "
        "has no consumer at all. It is left on disk only so this declaration "
        "and the merge land in separate reviewable steps; delete the directory "
        "and this entry together.",
    ),
}

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


def _discovered_locales() -> list[str]:
    """Every ``locale/<code>/LC_MESSAGES/django.po`` actually on disk.

    Discovery is what makes "add a locale with 0 translations" detectable at
    all: the old hard-coded ``EXPECTED_LOCALES`` tuple simply never looked.
    """
    if not LOCALE_ROOT.is_dir():
        return []
    return sorted(
        p.name
        for p in LOCALE_ROOT.iterdir()
        if p.is_dir() and (p / "LC_MESSAGES" / "django.po").is_file()
    )


def _locales_to_scan() -> list[str]:
    return sorted(
        set(EXPECTED_LOCALES) | set(_discovered_locales()) | set(LOCALE_DECLARATIONS)
    )


def _scan() -> list[LocaleStats]:
    stats: list[LocaleStats] = []
    for locale in _locales_to_scan():
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


def _declaration(locale: str) -> tuple[str, str] | None:
    return LOCALE_DECLARATIONS.get(locale)


def _contract_violations(stats: list[LocaleStats]) -> list[str]:
    """Absolute-floor + declaration checks. This is what makes the gate able to fail."""
    violations: list[str] = []
    on_disk = set(_discovered_locales())

    for s in stats:
        decl = _declaration(s.locale)
        if decl is None:
            violations.append(
                f"{s.locale}: ships a catalog ({s.po_path}) at "
                f"{s.coverage_pct:.1f}% but is NOT declared in "
                f"LOCALE_DECLARATIONS. Declare it 'full' (and meet the "
                f"{MINIMUM_COVERAGE_PCT:.0f}% floor) or 'stub' with a written "
                f"reason -- silence is not a declaration."
            )
            continue
        kind, reason = decl
        if not str(reason).strip():
            violations.append(f"{s.locale}: declared '{kind}' with an empty reason.")
        if kind not in ("source", "full", "stub", "unserved"):
            violations.append(
                f"{s.locale}: unknown declaration kind {kind!r} "
                f"(expected source/full/stub/unserved)."
            )
            continue
        if s.locale not in on_disk:
            if kind != "unserved":
                violations.append(
                    f"{s.locale}: declared '{kind}' but no catalog on disk at "
                    f"{s.po_path} -- remove the declaration or ship the .po."
                )
            continue
        if kind == "source" and s.coverage_pct < SOURCE_MINIMUM_PCT:
            violations.append(
                f"{s.locale}: source locale at {s.coverage_pct:.1f}% "
                f"(floor {SOURCE_MINIMUM_PCT:.0f}%) -- every other locale falls "
                f"back to it."
            )
        elif kind == "full" and s.coverage_pct < MINIMUM_COVERAGE_PCT:
            violations.append(
                f"{s.locale}: declared 'full' but only {s.coverage_pct:.1f}% "
                f"translated (floor {MINIMUM_COVERAGE_PCT:.0f}%)."
            )
        elif kind == "stub" and s.coverage_pct >= MINIMUM_COVERAGE_PCT:
            violations.append(
                f"{s.locale}: declared 'stub' but has reached "
                f"{s.coverage_pct:.1f}% -- stale declaration, promote it to "
                f"'full' so the {MINIMUM_COVERAGE_PCT:.0f}% floor protects it."
            )
    return violations


def _known_gaps(stats: list[LocaleStats]) -> list[str]:
    """Declared-but-unresolved situations, surfaced on every run (non-fatal)."""
    out = []
    for s in stats:
        decl = _declaration(s.locale)
        if decl and decl[0] == "unserved":
            out.append(f"{s.locale}: {decl[1]}")
    return out


def _baseline_payload(stats: list[LocaleStats]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            f"per-locale msgstr coverage. Absolute floor: locales declared "
            f"'full' must reach {MINIMUM_COVERAGE_PCT:.0f}%, the source locale "
            f"{SOURCE_MINIMUM_PCT:.0f}%; every locale on disk must carry a "
            f"LOCALE_DECLARATIONS entry with a written reason; plus the "
            f"original translated-count regression check"
        ),
        "locale_root": LOCALE_ROOT.relative_to(REPO_ROOT).as_posix(),
        "expected_locales": list(EXPECTED_LOCALES),
        "discovered_locales": _discovered_locales(),
        "minimum_coverage_pct": MINIMUM_COVERAGE_PCT,
        "source_minimum_pct": SOURCE_MINIMUM_PCT,
        "declarations": {
            code: {"kind": kind, "reason": reason}
            for code, (kind, reason) in sorted(LOCALE_DECLARATIONS.items())
        },
        "contract_violations": _contract_violations(stats),
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
    print(
        f"locale coverage: {len(stats)} locale(s); floor "
        f"{MINIMUM_COVERAGE_PCT:.0f}% for 'full', {SOURCE_MINIMUM_PCT:.0f}% for "
        f"'source'"
    )
    for s in stats:
        decl = _declaration(s.locale)
        kind = decl[0] if decl else "UNDECLARED"
        plural_note = (
            f"  plural={s.plural_incomplete}/{s.plural_msgids} incomplete"
            if s.plural_msgids else ""
        )
        print(
            f"  [{kind:9s}] {s.locale:8s} {s.translated:5d}/{s.total:5d} "
            f"({s.coverage_pct:5.1f}%){plural_note}  {s.po_path}"
        )


def _write_baseline(stats: list[LocaleStats]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(stats), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _regressions(stats: list[LocaleStats]) -> list[str]:
    baseline = _load_baseline()
    if baseline is None:
        return []
    by_locale_now = {s.locale: s.translated for s in stats}
    by_locale_baseline = {
        item["locale"]: item["translated"]
        for item in baseline.get("findings", [])
    }
    out: list[str] = []
    for locale, base in sorted(by_locale_baseline.items()):
        cur = by_locale_now.get(locale, 0)
        if base > 0 and cur < base:
            out.append(f"{locale}: translated dropped {base} -> {cur}")
    return out


def _report(stats: list[LocaleStats], *, check_regressions: bool) -> int:
    """Print the summary and return the process exit code.

    The floor/declaration contract is enforced in BOTH modes: a run that prints
    violations and exits 0 is exactly the failure mode this gate had.
    """
    _print_summary(stats)
    violations = _contract_violations(stats)
    gaps = _known_gaps(stats)
    regressions = _regressions(stats) if check_regressions else []
    if check_regressions and _load_baseline() is None:
        print("\nNo baseline on disk. Run without --compare to write one.")
    if gaps:
        print("\nKNOWN GAPS (declared, non-fatal):")
        for line in gaps:
            print(f"  ~ {line}")
    if violations:
        print("\nCONTRACT VIOLATIONS:")
        for line in violations:
            print(f"  - {line}")
    if regressions:
        print("\nREGRESSIONS:")
        for line in regressions:
            print(f"  - {line}")
    if violations or regressions:
        return 1
    print(
        f"\nLOCALE_COVERAGE_PASS ({len(stats)} locale(s), "
        f"{len(gaps)} declared known gap(s))"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    stats = _scan()
    if args.json:
        print(json.dumps(_baseline_payload(stats), indent=2, sort_keys=True))
        return 1 if _contract_violations(stats) else 0
    if args.compare:
        return _report(stats, check_regressions=True)
    rc = _report(stats, check_regressions=False)
    _write_baseline(stats)
    return rc


if __name__ == "__main__":
    sys.exit(main())
